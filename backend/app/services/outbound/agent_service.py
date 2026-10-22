"""坐席服务（§11 状态机与状态历史 / §34 示闲触发自动分配 / OB-018 坐席 CRUD）。"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ParamError, ResourceReferenced
from app.models.outbound import Agent, AgentStatusLog
from app.models.outbound.enums import AgentStatus, AssignmentStatus, SessionStatus
from app.repositories.outbound.agent_repository import OutboundAgentRepository
from app.repositories.outbound.record_repository import OutboundRecordRepository
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.schemas.outbound.config import AgentCreate, AgentUpdate
from app.services.outbound.agent_state import ensure_transition
from app.services.outbound.common import ensure_tenant_active

logger = logging.getLogger(__name__)

#: 认为坐席「正在工作中」的会话状态，删除坐席前需先结束这些会话
ACTIVE_SESSION_STATUSES = (
    SessionStatus.CREATED,
    SessionStatus.ASSIGNED,
    SessionStatus.CALLING,
    SessionStatus.CONNECTED,
)

#: 未释放的坐席预占状态
OPEN_ASSIGNMENT_STATUSES = (AssignmentStatus.RESERVED, AssignmentStatus.ACCEPTED)


class OutboundAgentService:
    """坐席状态管理。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = OutboundAgentRepository(db)
        self.ref = ReferenceRepository(db)
        self.record_repo = OutboundRecordRepository(db)
        self._assignment_service = None

    @property
    def assignment_service(self):  # noqa: ANN201 - 延迟导入避免循环依赖
        if self._assignment_service is None:
            from app.services.outbound.assignment_service import OutboundAssignmentService

            self._assignment_service = OutboundAssignmentService(self.db)
        return self._assignment_service

    # ---------- 查询 ----------

    def list_agents(
        self, *, page: int, page_size: int, **filters: object
    ) -> tuple[list[Agent], int]:
        items = self.repo.list_paged(page=page, page_size=page_size, **filters)
        total = self.repo.count(**filters)
        return items, total

    def get_agent(self, agent_id: int) -> Agent:
        agent = self.repo.get_by_id(agent_id)
        if agent is None:
            raise NotFound("坐席不存在")
        return agent

    def list_status_logs(self, agent_id: int, *, limit: int = 50) -> list[AgentStatusLog]:
        from sqlalchemy import select

        stmt = (
            select(AgentStatusLog)
            .where(AgentStatusLog.agent_id == agent_id)
            .order_by(AgentStatusLog.id.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_status(self, *, tenant_id: int, skill_queue_id: int | None = None) -> dict[str, int]:
        """坐席各状态数量（供实时监控与预测外呼复用）。"""
        return self.repo.count_by_status(tenant_id=tenant_id, skill_queue_id=skill_queue_id)

    # ---------- 坐席 CRUD（规则 8）----------

    def create_agent(self, payload: AgentCreate) -> Agent:
        ensure_tenant_active(self.db, payload.tenant_id)

        user = self.ref.get_user_by_id(payload.user_id)
        if user is None:
            raise NotFound("关联用户不存在")
        if not user.is_active:
            raise ParamError("关联用户已停用，无法开通坐席")
        if self.repo.get_by_user_id(payload.user_id) is not None:
            raise Conflict("该用户已开通坐席（一个用户最多一个坐席）")

        self._validate_placement(
            tenant_id=payload.tenant_id,
            site_id=payload.site_id,
            skill_queue_id=payload.skill_queue_id,
        )

        agent = self.repo.create(
            user_id=payload.user_id,
            tenant_id=payload.tenant_id,
            site_id=payload.site_id,
            skill_queue_id=payload.skill_queue_id,
            extension=payload.extension,
            status=AgentStatus.OFFLINE,
        )
        self.db.commit()
        logger.info(
            "创建坐席成功：id=%s user=%s tenant=%s", agent.id, user.username, agent.tenant_id
        )
        return agent

    def update_agent(self, agent_id: int, payload: AgentUpdate) -> Agent:
        agent = self.get_agent(agent_id)
        changes = payload.model_dump(exclude_unset=True)

        self._validate_placement(
            tenant_id=agent.tenant_id,
            site_id=changes.get("site_id", agent.site_id),
            skill_queue_id=changes.get("skill_queue_id", agent.skill_queue_id),
        )

        for field, value in changes.items():
            setattr(agent, field, value)
        self.db.commit()
        logger.info("更新坐席成功：id=%s fields=%s", agent_id, sorted(changes))
        return agent

    def delete_agent(self, agent_id: int) -> None:
        """软删除坐席；仍在工作中（有未释放预占或进行中会话）时拒绝，避免留下悬空引用。"""
        agent = self.get_agent(agent_id)

        if self.repo.count_assignments(
            agent_id=agent_id, statuses=list(OPEN_ASSIGNMENT_STATUSES)
        ):
            raise ResourceReferenced("坐席存在未释放的派单预占，请先释放后再删除")
        if self._count_active_sessions(agent_id) > 0:
            raise ResourceReferenced("坐席存在进行中的外呼会话，请先结束后再删除")

        agent.mark_deleted()
        self.db.commit()
        logger.info("删除坐席成功：id=%s", agent_id)

    def _count_active_sessions(self, agent_id: int) -> int:
        return self.record_repo.count_sessions(
            agent_id=agent_id, statuses=list(ACTIVE_SESSION_STATUSES)
        )

    def _validate_placement(
        self, *, tenant_id: int, site_id: int | None, skill_queue_id: int | None
    ) -> None:
        """校验站点 / 技能队列存在且属于同一租户（§60 禁止跨租户引用）。"""
        if site_id is not None:
            site = self.ref.get_site_by_id(site_id)
            if site is None:
                raise NotFound("站点不存在")
            if site.tenant_id != tenant_id:
                raise ParamError("站点与坐席不属于同一租户")
        if skill_queue_id is not None:
            queue = self.ref.get_skill_queue_by_id(skill_queue_id)
            if queue is None:
                raise NotFound("技能队列不存在")
            if queue.tenant_id != tenant_id:
                raise ParamError("技能队列与坐席不属于同一租户")
            if site_id is not None and queue.site_id != site_id:
                raise ParamError("技能队列不属于所选站点")

    # ---------- 状态变更（§11 + §34）----------

    def change_status(
        self,
        agent_id: int,
        target: AgentStatus,
        *,
        reason: str = "",
        operator_id: int | None = None,
        auto_assign: bool = True,
    ) -> dict[str, object]:
        """变更坐席状态并写历史；置为 IDLE 时立即触发自动分配（§34）。"""
        agent = self.get_agent(agent_id)
        ensure_transition(agent.status, target)

        now = datetime.now(timezone.utc)
        from_status = agent.status
        agent.status = target
        if target == AgentStatus.IDLE:
            agent.last_idle_at = now
        elif target == AgentStatus.BUSY:
            agent.last_busy_at = now

        self.repo.create_status_log(
            agent_id=agent.id,
            from_status=from_status,
            to_status=target,
            reason=(reason or "手动变更状态")[:255],
            operator_id=operator_id,
        )
        self.db.commit()

        logger.info(
            "坐席状态变更：agent=%s %s→%s", agent.id, from_status.value, target.value
        )

        result: dict[str, object] = {
            "agent_id": agent.id,
            "from_status": from_status.value,
            "to_status": target.value,
            "assignment": None,
        }
        # §34：坐席示闲（BUSY → IDLE 或 OFFLINE → IDLE）后立即执行自动分配
        if target == AgentStatus.IDLE and auto_assign:
            result["assignment"] = self.assignment_service.assign_for_agent(agent.id)
        return result
