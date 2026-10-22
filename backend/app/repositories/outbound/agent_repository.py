"""坐席与预占数据访问（OB-018）。"""

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.outbound import Agent, AgentAssignment, AgentStatusLog
from app.models.outbound.enums import AgentStatus, AssignmentStatus


class OutboundAgentRepository:
    """坐席查询、状态历史与预占记录。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 坐席 ----------

    def get_by_id(self, agent_id: int) -> Agent | None:
        stmt = select(Agent).where(Agent.id == agent_id, Agent.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_user_id(self, user_id: int) -> Agent | None:
        stmt = select(Agent).where(Agent.user_id == user_id, Agent.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        site_id: int | None = None,
        skill_queue_id: int | None = None,
        status: AgentStatus | None = None,
        statuses: list[AgentStatus] | None = None,
    ) -> Select:
        stmt = stmt.where(Agent.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(Agent.tenant_id == tenant_id)
        if site_id is not None:
            stmt = stmt.where(Agent.site_id == site_id)
        if skill_queue_id is not None:
            stmt = stmt.where(Agent.skill_queue_id == skill_queue_id)
        if status is not None:
            stmt = stmt.where(Agent.status == status)
        if statuses:
            stmt = stmt.where(Agent.status.in_(statuses))
        return stmt

    def list_paged(self, *, page: int, page_size: int, **filters: object) -> list[Agent]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(select(Agent), **filters)  # type: ignore[arg-type]
        stmt = stmt.order_by(Agent.id.asc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, **filters: object) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(Agent), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_idle_candidates(
        self, *, tenant_id: int, skill_queue_id: int | None, limit: int = 50
    ) -> list[Agent]:
        """空闲坐席（§34 排序维度之一：先按技能队列匹配）。"""
        stmt = self._apply_filters(
            select(Agent),
            tenant_id=tenant_id,
            skill_queue_id=skill_queue_id,
            status=AgentStatus.IDLE,
        )
        # 先按技能队列精确匹配，再按最近示闲时间轮转，保证公平
        stmt = stmt.order_by(Agent.last_idle_at.asc().nullsfirst(), Agent.id.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_by_status(
        self, *, tenant_id: int, skill_queue_id: int | None = None
    ) -> dict[str, int]:
        stmt = (
            select(Agent.status, func.count())
            .where(Agent.is_deleted.is_(False), Agent.tenant_id == tenant_id)
            .group_by(Agent.status)
        )
        if skill_queue_id is not None:
            stmt = stmt.where(Agent.skill_queue_id == skill_queue_id)

        counts: dict[str, int] = {}
        for status_value, amount in self.db.execute(stmt).all():
            key = status_value.value if hasattr(status_value, "value") else str(status_value)
            counts[key] = int(amount)
        return counts

    def create(self, **values: object) -> Agent:
        agent = Agent(**values)
        self.db.add(agent)
        self.db.flush()
        return agent

    def create_status_log(self, **values: object) -> AgentStatusLog:
        log = AgentStatusLog(**values)
        self.db.add(log)
        self.db.flush()
        return log

    # ---------- 预占 ----------

    def get_assignment(self, assignment_id: int) -> AgentAssignment | None:
        stmt = select(AgentAssignment).where(
            AgentAssignment.id == assignment_id, AgentAssignment.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_assignment_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        agent_id: int | None = None,
        task_id: int | None = None,
        status: AssignmentStatus | None = None,
        statuses: list[AssignmentStatus] | None = None,
    ) -> Select:
        stmt = stmt.where(AgentAssignment.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(AgentAssignment.tenant_id == tenant_id)
        if agent_id is not None:
            stmt = stmt.where(AgentAssignment.agent_id == agent_id)
        if task_id is not None:
            stmt = stmt.where(AgentAssignment.task_id == task_id)
        if status is not None:
            stmt = stmt.where(AgentAssignment.status == status)
        if statuses:
            stmt = stmt.where(AgentAssignment.status.in_(statuses))
        return stmt

    def list_assignments_paged(
        self, *, page: int, page_size: int, **filters: object
    ) -> list[AgentAssignment]:
        offset = (page - 1) * page_size
        stmt = self._apply_assignment_filters(
            select(AgentAssignment), **filters  # type: ignore[arg-type]
        )
        stmt = stmt.order_by(AgentAssignment.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count_assignments(self, **filters: object) -> int:
        stmt = self._apply_assignment_filters(
            select(func.count()).select_from(AgentAssignment), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())

    def get_active_assignment_by_record(self, record_id: int) -> AgentAssignment | None:
        stmt = (
            select(AgentAssignment)
            .where(
                AgentAssignment.is_deleted.is_(False),
                AgentAssignment.record_id == record_id,
                AgentAssignment.status.in_(
                    [AssignmentStatus.RESERVED, AssignmentStatus.ACCEPTED]
                ),
            )
            .order_by(AgentAssignment.id.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def get_active_assignment_by_agent(self, agent_id: int) -> AgentAssignment | None:
        """坐席当前的活跃预占（RESERVED / ACCEPTED）——数据库部分唯一索引保证最多一条。"""
        stmt = (
            select(AgentAssignment)
            .where(
                AgentAssignment.is_deleted.is_(False),
                AgentAssignment.agent_id == agent_id,
                AgentAssignment.status.in_(
                    [AssignmentStatus.RESERVED, AssignmentStatus.ACCEPTED]
                ),
            )
            .order_by(AgentAssignment.id.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def list_expired_reservations(
        self, *, now: datetime, limit: int = 100
    ) -> list[AgentAssignment]:
        """预占已过期但未释放的记录（§35 自动释放）。"""
        stmt = (
            select(AgentAssignment)
            .where(
                AgentAssignment.is_deleted.is_(False),
                AgentAssignment.status == AssignmentStatus.RESERVED,
                AgentAssignment.expires_at.is_not(None),
                AgentAssignment.expires_at < now,
            )
            .order_by(AgentAssignment.expires_at.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create_assignment(self, **values: object) -> AgentAssignment:
        assignment = AgentAssignment(**values)
        self.db.add(assignment)
        self.db.flush()
        return assignment
