"""超时回收（§22）。

必须幂等：同一条记录被重复扫描只能产生一次有效回收。
实现要点：
1. SELECT ... FOR UPDATE 加锁；
2. 锁内复核状态与超时时间（幂等关键）；
3. 标记 TIMEOUT、写 CallHistory、释放坐席预占、收尾会话；
4. 走失败重试阶梯，让数据重新进入可执行队列。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.outbound.enums import (
    AssignmentStatus,
    CallStatus,
    RecordStatus,
    SessionStatus,
)
from app.repositories.outbound.list_repository import OutboundListRepository
from app.repositories.outbound.record_repository import OutboundRecordRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.services.outbound.retry_policy import (
    can_retry,
    mark_terminal,
    schedule_retry,
    sync_name_list_status,
)
from app.services.outbound.task_progress import maybe_complete_task

logger = logging.getLogger(__name__)

RECYCLE_REASON = "呼叫超时，系统自动回收"
DEFAULT_BATCH = 100


class OutboundTimeoutService:
    """超时回收。每条记录一个事务。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.record_repo = OutboundRecordRepository(db)
        self.task_repo = OutboundTaskRepository(db)
        self.list_repo = OutboundListRepository(db)

    def recycle(self, *, limit: int = DEFAULT_BATCH) -> dict[str, object]:
        """扫描并回收超时记录，返回统计。"""
        now = self._now()
        candidates = self.record_repo.list_timed_out(limit=limit, now=now)

        result: dict[str, object] = {
            "scanned": len(candidates),
            "recycled": 0,
            "skipped": 0,
        }
        for candidate in candidates:
            if self._recycle_one(candidate.id, now):
                result["recycled"] = int(result["recycled"]) + 1  # type: ignore[arg-type]
            else:
                result["skipped"] = int(result["skipped"]) + 1  # type: ignore[arg-type]
            self.db.commit()

        # 规则 2：回收后继续按任务检查，全部记录到终态的任务自动完成
        completed = 0
        for task_id in {candidate.task_id for candidate in candidates}:
            task = self.task_repo.get_by_id(task_id)
            if task is not None and maybe_complete_task(self.db, task, now=now):
                completed += 1
        if completed:
            self.db.commit()
            result["task_completed"] = completed
            logger.info("超时回收后自动完成任务数：%s", completed)

        if result["recycled"]:
            logger.warning("超时回收完成：%s", result)
        return result

    # ---------- 内部 ----------

    def _recycle_one(self, record_id: int, now: datetime) -> bool:
        # 1. 加锁读取
        record = self.record_repo.lock_by_id(record_id)
        if record is None or record.is_deleted:
            return False

        # 2. 锁内复核（幂等的关键：并发/重复扫描时只有一个能通过）
        if record.status not in (RecordStatus.ASSIGNED, RecordStatus.CALLING):
            return False
        if record.timeout_at is None or record.timeout_at >= now:
            return False

        task = self.task_repo.get_by_id(record.task_id)
        name_list = self.list_repo.get_by_id(record.list_id)
        session = (
            self.record_repo.get_session(record.session_id)
            if record.session_id is not None
            else None
        )

        previous_status = record.status
        # 3. 标记超时
        record.status = RecordStatus.TIMEOUT
        record.timeout_at = None
        record.failure_reason = RECYCLE_REASON

        # 4. 写呼叫历史（保持与正常呼叫一致的可追溯性）
        self.record_repo.create_history(
            tenant_id=record.tenant_id,
            session_id=record.session_id,
            record_id=record.id,
            task_id=record.task_id,
            list_id=record.list_id,
            agent_id=record.agent_id,
            phone=record.current_phone or "",
            call_status=CallStatus.TIMEOUT,
            failure_reason=RECYCLE_REASON,
            started_at=record.last_call_at,
            ended_at=now,
            duration=0,
            provider="timeout-recycler",
        )

        # 5. 释放坐席预占
        released = self._release_assignments(record.id, now)

        # 6. 会话收尾
        if session is not None:
            session.status = SessionStatus.TIMEOUT
            session.finished_at = now
            session.timeout_at = None

        # 7. 重试阶梯：还有重试机会则重新入队，否则保留 TIMEOUT 作为终态
        #    （不改成 EXHAUSTED/FAILED，因为「超时」是更准确的终态描述，且已在 CallHistory 留痕）
        if task is not None:
            record.retry_count += 1
            if can_retry(record, task):
                schedule_retry(record, task, now=now)
            else:
                mark_terminal(record, RecordStatus.TIMEOUT)
        else:
            mark_terminal(record, RecordStatus.TIMEOUT)
        sync_name_list_status(name_list, record.status)

        logger.warning(
            "超时回收：record=%s 原状态=%s 新状态=%s 释放预占=%s",
            record.id,
            previous_status.value,
            record.status.value,
            released,
        )
        return True

    def _release_assignments(self, record_id: int, now: datetime) -> int:
        assignments = self.record_repo.list_active_assignments(record_id)
        for assignment in assignments:
            assignment.status = AssignmentStatus.RELEASED
            assignment.released_at = now
            assignment.release_reason = RECYCLE_REASON
        return len(assignments)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


__all__ = ["DEFAULT_BATCH", "RECYCLE_REASON", "OutboundTimeoutService"]
