"""执行域数据访问：执行记录 / 会话 / 呼叫历史 / 坐席预占（P5 执行引擎）。"""

from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.outbound import (
    AgentAssignment,
    CallHistory,
    OutboundList,
    OutboundRecord,
    OutboundSession,
    OutboundTask,
)
from app.models.outbound.enums import AssignmentStatus, CallStatus, RecordStatus, SessionStatus


class OutboundRecordRepository:
    """执行记录与相关实体的查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 执行记录 ----------

    def get_by_id(self, record_id: int) -> OutboundRecord | None:
        stmt = select(OutboundRecord).where(
            OutboundRecord.id == record_id,
            OutboundRecord.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def lock_by_id(self, record_id: int) -> OutboundRecord | None:
        """行锁读取（§22：超时回收必须先加锁再复核状态）。"""
        stmt = (
            select(OutboundRecord)
            .where(OutboundRecord.id == record_id)
            .with_for_update()
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        task_id: int | None = None,
        list_id: int | None = None,
        agent_id: int | None = None,
        status: RecordStatus | None = None,
        statuses: list[RecordStatus] | None = None,
    ) -> Select:
        stmt = stmt.where(OutboundRecord.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(OutboundRecord.tenant_id == tenant_id)
        if task_id is not None:
            stmt = stmt.where(OutboundRecord.task_id == task_id)
        if list_id is not None:
            stmt = stmt.where(OutboundRecord.list_id == list_id)
        if agent_id is not None:
            stmt = stmt.where(OutboundRecord.agent_id == agent_id)
        if status is not None:
            stmt = stmt.where(OutboundRecord.status == status)
        if statuses:
            stmt = stmt.where(OutboundRecord.status.in_(statuses))
        return stmt

    def list_paged(self, *, page: int, page_size: int, **filters: object) -> list[OutboundRecord]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(select(OutboundRecord), **filters)  # type: ignore[arg-type]
        stmt = stmt.order_by(OutboundRecord.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, **filters: object) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(OutboundRecord), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_existing_list_ids(self, task_id: int) -> set[int]:
        """任务下已生成执行记录的名单 ID（构建记录时用于幂等）。"""
        stmt = select(OutboundRecord.list_id).where(
            OutboundRecord.task_id == task_id, OutboundRecord.is_deleted.is_(False)
        )
        return set(self.db.execute(stmt).scalars().all())

    def list_executable(self, task_id: int, *, limit: int, now: datetime) -> list[OutboundRecord]:
        """待执行记录：PENDING，或已到重试时间的 RETRY_WAITING（§21）。"""
        stmt = (
            select(OutboundRecord)
            .where(
                OutboundRecord.task_id == task_id,
                OutboundRecord.is_deleted.is_(False),
                or_(
                    OutboundRecord.status == RecordStatus.PENDING,
                    and_(
                        OutboundRecord.status == RecordStatus.RETRY_WAITING,
                        or_(
                            OutboundRecord.next_retry_at.is_(None),
                            OutboundRecord.next_retry_at <= now,
                        ),
                    ),
                ),
            )
            .order_by(OutboundRecord.id.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_timed_out(self, *, limit: int, now: datetime) -> list[OutboundRecord]:
        """超时待回收记录（§22：ASSIGNED / CALLING 且已过 timeout_at）。"""
        stmt = (
            select(OutboundRecord)
            .where(
                OutboundRecord.is_deleted.is_(False),
                OutboundRecord.status.in_([RecordStatus.ASSIGNED, RecordStatus.CALLING]),
                OutboundRecord.timeout_at.is_not(None),
                OutboundRecord.timeout_at < now,
            )
            .order_by(OutboundRecord.timeout_at.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(self, **values: object) -> OutboundRecord:
        record = OutboundRecord(**values)
        self.db.add(record)
        self.db.flush()
        return record

    def pick_pending_for_task(self, task_id: int) -> OutboundRecord | None:
        """取一条可派单记录（§34 排序维度之一：名单优先级，数值大者优先）。"""
        stmt = (
            select(OutboundRecord)
            .join(OutboundList, OutboundList.id == OutboundRecord.list_id)
            .where(
                OutboundRecord.task_id == task_id,
                OutboundRecord.is_deleted.is_(False),
                OutboundRecord.status == RecordStatus.PENDING,
            )
            .order_by(OutboundList.priority.desc(), OutboundRecord.id.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def history_stats(
        self,
        *,
        task_id: int | None = None,
        tenant_id: int | None = None,
        since: datetime | None = None,
    ) -> tuple[int, int]:
        """呼叫历史统计，返回 (总呼叫数, 接通数)（§36 接通率统计口径）。"""

        def base():
            stmt = select(func.count()).select_from(CallHistory)
            if task_id is not None:
                stmt = stmt.where(CallHistory.task_id == task_id)
            if tenant_id is not None:
                stmt = stmt.where(CallHistory.tenant_id == tenant_id)
            if since is not None:
                stmt = stmt.where(CallHistory.created_at >= since)
            return stmt

        total = int(self.db.execute(base()).scalar_one())
        answered_stmt = base().where(CallHistory.call_status == CallStatus.CONNECTED)
        answered = int(self.db.execute(answered_stmt).scalar_one())
        return total, answered

    def bulk_insert(self, values: list[dict[str, object]]) -> int:
        if not values:
            return 0
        self.db.execute(OutboundRecord.__table__.insert(), values)
        self.db.flush()
        return len(values)

    # ---------- 会话 ----------

    def get_session(self, session_id: int) -> OutboundSession | None:
        stmt = select(OutboundSession).where(
            OutboundSession.id == session_id, OutboundSession.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_session_any_state(self, session_id: int) -> OutboundSession | None:
        """按主键读取会话，忽略软删除标记。

        callback_tasks.origin_session_id 的外键指向物理行，校验时必须与之一致，
        否则会话被软删除后会被误判成「不存在」而拒绝写入。
        """
        stmt = select(OutboundSession).where(OutboundSession.id == session_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_session(self, **values: object) -> OutboundSession:
        session = OutboundSession(**values)
        self.db.add(session)
        self.db.flush()
        return session

    def list_sessions_by_record(self, record_id: int) -> list[OutboundSession]:
        stmt = (
            select(OutboundSession)
            .where(OutboundSession.is_deleted.is_(False))
            .order_by(OutboundSession.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def _apply_session_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        task_id: int | None = None,
        agent_id: int | None = None,
        list_id: int | None = None,
        status: SessionStatus | None = None,
        statuses: list[SessionStatus] | None = None,
    ) -> Select:
        stmt = stmt.where(OutboundSession.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(OutboundSession.tenant_id == tenant_id)
        if task_id is not None:
            stmt = stmt.where(OutboundSession.task_id == task_id)
        if agent_id is not None:
            stmt = stmt.where(OutboundSession.agent_id == agent_id)
        if list_id is not None:
            stmt = stmt.where(OutboundSession.list_id == list_id)
        if status is not None:
            stmt = stmt.where(OutboundSession.status == status)
        if statuses:
            stmt = stmt.where(OutboundSession.status.in_(statuses))
        return stmt

    def list_sessions_paged(
        self, *, page: int, page_size: int, **filters: object
    ) -> list[OutboundSession]:
        offset = (page - 1) * page_size
        stmt = self._apply_session_filters(
            select(OutboundSession), **filters  # type: ignore[arg-type]
        )
        stmt = stmt.order_by(OutboundSession.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count_sessions(self, **filters: object) -> int:
        stmt = self._apply_session_filters(
            select(func.count()).select_from(OutboundSession), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())

    def get_by_list_id(self, list_id: int) -> OutboundRecord | None:
        """按名单查执行记录（唯一：uq_outbound_records_task_list 之外，一个名单只属于一个任务）。"""
        stmt = (
            select(OutboundRecord)
            .where(
                OutboundRecord.list_id == list_id,
                OutboundRecord.is_deleted.is_(False),
            )
            .order_by(OutboundRecord.id.asc())
        )
        return self.db.execute(stmt).scalars().first()

    # ---------- 呼叫历史 ----------

    def create_history(self, **values: object) -> CallHistory:
        history = CallHistory(**values)
        self.db.add(history)
        self.db.flush()
        return history

    def get_history_by_provider_call_id(self, provider_call_id: str) -> CallHistory | None:
        stmt = select(CallHistory).where(CallHistory.provider_call_id == provider_call_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_histories_by_record(self, record_id: int) -> list[CallHistory]:
        stmt = (
            select(CallHistory)
            .where(CallHistory.record_id == record_id)
            .order_by(CallHistory.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_histories_by_list(self, list_id: int) -> list[CallHistory]:
        """名单的拨打历史（OB-023-2）。"""
        stmt = (
            select(CallHistory)
            .where(CallHistory.list_id == list_id)
            .order_by(CallHistory.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def find_success_phone(self, list_id: int) -> str | None:
        """名单是否已呼叫成功（OB-021-1.4）：返回成功号码，未成功返回 None。"""
        stmt = (
            select(CallHistory.phone)
            .where(
                CallHistory.list_id == list_id,
                CallHistory.call_status == CallStatus.CONNECTED,
            )
            .order_by(CallHistory.id.asc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def list_sessions_by_list(self, list_id: int) -> list[OutboundSession]:
        stmt = (
            select(OutboundSession)
            .where(
                OutboundSession.list_id == list_id,
                OutboundSession.is_deleted.is_(False),
            )
            .order_by(OutboundSession.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_agent_worklist(
        self,
        *,
        agent_id: int,
        statuses: list[RecordStatus],
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[OutboundRecord, OutboundList, OutboundTask]], int]:
        """坐席名下待呼名单（OB-021-1）：执行记录 + 名单 + 任务三表联查。"""
        base = (
            select(OutboundRecord, OutboundList, OutboundTask)
            .join(OutboundList, OutboundList.id == OutboundRecord.list_id)
            .join(OutboundTask, OutboundTask.id == OutboundRecord.task_id)
            .where(
                OutboundRecord.is_deleted.is_(False),
                OutboundRecord.agent_id == agent_id,
                OutboundRecord.status.in_(statuses),
            )
        )
        offset = (page - 1) * page_size
        rows = list(
            self.db.execute(
                base.order_by(OutboundList.priority.desc(), OutboundRecord.id.asc())
                .offset(offset)
                .limit(page_size)
            ).all()
        )

        count_stmt = (
            select(func.count())
            .select_from(OutboundRecord)
            .where(
                OutboundRecord.is_deleted.is_(False),
                OutboundRecord.agent_id == agent_id,
                OutboundRecord.status.in_(statuses),
            )
        )
        total = int(self.db.execute(count_stmt).scalar_one())
        return rows, total

    # ---------- 坐席预占（P6 使用，P5 仅在超时回收时释放）----------

    def list_active_assignments(self, record_id: int) -> list[AgentAssignment]:
        stmt = select(AgentAssignment).where(
            AgentAssignment.record_id == record_id,
            AgentAssignment.is_deleted.is_(False),
            AgentAssignment.status.in_(
                [AssignmentStatus.RESERVED, AssignmentStatus.ACCEPTED]
            ),
        )
        return list(self.db.execute(stmt).scalars().all())


__all__ = ["OutboundRecordRepository", "RecordStatus", "SessionStatus"]
