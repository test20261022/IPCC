"""回呼域数据访问（OB-029 / OB-030）：回呼流程与回呼任务。"""

from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.outbound import CallbackFlow, CallbackTask
from app.models.outbound.enums import CallbackSource, CallbackStatus, CommonStatus


class CallbackFlowRepository:
    """回呼流程查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, flow_id: int) -> CallbackFlow | None:
        stmt = select(CallbackFlow).where(
            CallbackFlow.id == flow_id, CallbackFlow.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, *, tenant_id: int, code: str) -> CallbackFlow | None:
        stmt = select(CallbackFlow).where(
            CallbackFlow.tenant_id == tenant_id,
            CallbackFlow.code == code,
            CallbackFlow.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        code: str | None = None,
        name: str | None = None,
        status: CommonStatus | None = None,
        ivr_flow_id: int | None = None,
    ) -> Select:
        stmt = stmt.where(CallbackFlow.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(CallbackFlow.tenant_id == tenant_id)
        if code:
            stmt = stmt.where(CallbackFlow.code.ilike(f"%{code}%"))
        if name:
            stmt = stmt.where(CallbackFlow.name.ilike(f"%{name}%"))
        if status is not None:
            stmt = stmt.where(CallbackFlow.status == status)
        if ivr_flow_id is not None:
            stmt = stmt.where(CallbackFlow.ivr_flow_id == ivr_flow_id)
        return stmt

    def list_paged(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        code: str | None = None,
        name: str | None = None,
        status: CommonStatus | None = None,
        ivr_flow_id: int | None = None,
    ) -> list[CallbackFlow]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(
            select(CallbackFlow),
            tenant_id=tenant_id,
            code=code,
            name=name,
            status=status,
            ivr_flow_id=ivr_flow_id,
        )
        stmt = stmt.order_by(CallbackFlow.id.asc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(
        self,
        *,
        tenant_id: int | None = None,
        code: str | None = None,
        name: str | None = None,
        status: CommonStatus | None = None,
        ivr_flow_id: int | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(CallbackFlow),
            tenant_id=tenant_id,
            code=code,
            name=name,
            status=status,
            ivr_flow_id=ivr_flow_id,
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_enabled(self, *, tenant_id: int, limit: int = 200) -> list[CallbackFlow]:
        """启用中的回呼流程（自动触发时按优先级挑选）。"""
        stmt = (
            select(CallbackFlow)
            .where(
                CallbackFlow.tenant_id == tenant_id,
                CallbackFlow.status == CommonStatus.ENABLED,
                CallbackFlow.is_deleted.is_(False),
            )
            .order_by(CallbackFlow.id.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(self, **values: object) -> CallbackFlow:
        flow = CallbackFlow(**values)
        self.db.add(flow)
        self.db.flush()
        return flow


class CallbackTaskRepository:
    """回呼任务查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, task_id: int) -> CallbackTask | None:
        stmt = select(CallbackTask).where(
            CallbackTask.id == task_id, CallbackTask.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_origin_session(self, origin_session_id: int) -> CallbackTask | None:
        """同一 IVR 会话已生成的回呼任务（§78 幂等）。"""
        stmt = select(CallbackTask).where(
            CallbackTask.origin_session_id == origin_session_id,
            CallbackTask.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        source: CallbackSource | None = None,
        status: CallbackStatus | None = None,
        flow_id: int | None = None,
        task_id: int | None = None,
        list_id: int | None = None,
        agent_id: int | None = None,
        phone: str | None = None,
    ) -> Select:
        stmt = stmt.where(CallbackTask.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(CallbackTask.tenant_id == tenant_id)
        if source is not None:
            stmt = stmt.where(CallbackTask.source == source)
        if status is not None:
            stmt = stmt.where(CallbackTask.status == status)
        if flow_id is not None:
            stmt = stmt.where(CallbackTask.flow_id == flow_id)
        if task_id is not None:
            stmt = stmt.where(CallbackTask.task_id == task_id)
        if list_id is not None:
            stmt = stmt.where(CallbackTask.list_id == list_id)
        if agent_id is not None:
            stmt = stmt.where(CallbackTask.agent_id == agent_id)
        if phone:
            stmt = stmt.where(CallbackTask.phone.ilike(f"%{phone}%"))
        return stmt

    def list_paged(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        source: CallbackSource | None = None,
        status: CallbackStatus | None = None,
        flow_id: int | None = None,
        task_id: int | None = None,
        list_id: int | None = None,
        agent_id: int | None = None,
        phone: str | None = None,
    ) -> list[CallbackTask]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(
            select(CallbackTask),
            tenant_id=tenant_id,
            source=source,
            status=status,
            flow_id=flow_id,
            task_id=task_id,
            list_id=list_id,
            agent_id=agent_id,
            phone=phone,
        )
        stmt = (
            stmt.order_by(CallbackTask.id.desc()).offset(offset).limit(page_size)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count(
        self,
        *,
        tenant_id: int | None = None,
        source: CallbackSource | None = None,
        status: CallbackStatus | None = None,
        flow_id: int | None = None,
        task_id: int | None = None,
        list_id: int | None = None,
        agent_id: int | None = None,
        phone: str | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(CallbackTask),
            tenant_id=tenant_id,
            source=source,
            status=status,
            flow_id=flow_id,
            task_id=task_id,
            list_id=list_id,
            agent_id=agent_id,
            phone=phone,
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_due(
        self, *, now: datetime, tenant_id: int | None = None, limit: int = 100
    ) -> list[CallbackTask]:
        """到期待回呼任务：未设计划时间的视为立即可派单。"""
        stmt = select(CallbackTask).where(
            CallbackTask.is_deleted.is_(False),
            CallbackTask.status == CallbackStatus.PENDING,
            or_(CallbackTask.scheduled_at.is_(None), CallbackTask.scheduled_at <= now),
        )
        if tenant_id is not None:
            stmt = stmt.where(CallbackTask.tenant_id == tenant_id)
        stmt = stmt.order_by(CallbackTask.id.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def create(self, **values: object) -> CallbackTask:
        task = CallbackTask(**values)
        self.db.add(task)
        self.db.flush()
        return task
