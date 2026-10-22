"""自动分配服务（§33 派单链路 / §34 示闲触发与排序 / §35 预占）。

排序规则**全部集中在本服务**（§34 明确要求）：
1. 技能队列：坐席的 skill_queue 与任务队列匹配（任务队列为空视为通用任务）；
2. 任务优先级：OutboundTask.priority 升序（越小越先派）；
3. 名单优先级：OutboundList.priority 降序（越大越先派）。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFound, StateNotAllowed
from app.models.outbound import Agent, AgentAssignment, OutboundRecord, OutboundTask
from app.models.outbound.enums import (
    AgentStatus,
    AssignmentStatus,
    RecordStatus,
    SessionStatus,
)
from app.repositories.outbound.agent_repository import OutboundAgentRepository
from app.repositories.outbound.record_repository import OutboundRecordRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository

logger = logging.getLogger(__name__)

RELEASE_REASON_EXPIRED = "预占超时，系统自动释放"
RELEASE_REASON_FINISHED = "呼叫结束，释放坐席"


class OutboundAssignmentService:
    """坐席预占与派单。每个坐席一次派单一个事务。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.agent_repo = OutboundAgentRepository(db)
        self.record_repo = OutboundRecordRepository(db)
        self.task_repo = OutboundTaskRepository(db)

    # ---------- 示闲触发（§34）----------

    def assign_for_agent(self, agent_id: int) -> dict[str, object] | None:
        """给指定空闲坐席派一单；无可派数据时返回 None。"""
        agent = self.agent_repo.get_by_id(agent_id)
        if agent is None:
            raise NotFound("坐席不存在")
        if agent.status != AgentStatus.IDLE:
            return None

        # §35：一个坐席不允许被两个任务同时预占（先查活跃预占，DB 部分唯一索引兜底）
        if self.agent_repo.get_active_assignment_by_agent(agent.id) is not None:
            logger.info("坐席已有活跃预占，跳过派单：agent=%s", agent.id)
            return None

        picked = self._pick_task_and_record(agent)
        if picked is None:
            return None
        task, record = picked

        now = self._now()
        assignment = self._reserve(agent, task, record, now=now)
        self._dispatch(agent, task, record, assignment, now=now)
        self.db.commit()

        logger.info(
            "自动派单成功：agent=%s task=%s record=%s assignment=%s",
            agent.id,
            task.id,
            record.id,
            assignment.id,
        )
        return {
            "agent_id": agent.id,
            "task_id": task.id,
            "record_id": record.id,
            "assignment_id": assignment.id,
            "expires_at": assignment.expires_at,
        }

    def dispatch_pending(
        self, *, tenant_id: int | None = None, limit: int = 50
    ) -> dict[str, object]:
        """批量派单：遍历空闲坐席逐个派单。"""
        stats: dict[str, object] = {"agents_scanned": 0, "assigned": 0, "skipped": 0}
        agents = self.agent_repo.list_paged(
            page=1, page_size=limit, tenant_id=tenant_id, status=AgentStatus.IDLE
        )
        for agent in agents:
            stats["agents_scanned"] = int(stats["agents_scanned"]) + 1
            if self.assign_for_agent(agent.id) is not None:
                stats["assigned"] = int(stats["assigned"]) + 1
            else:
                stats["skipped"] = int(stats["skipped"]) + 1
        return stats

    # ---------- 接单 / 释放 ----------

    def accept(self, assignment_id: int) -> dict[str, object]:
        """坐席接单：RESERVED → ACCEPTED，坐席状态 → BUSY（§11 RESERVED → BUSY）。"""
        assignment = self._get_assignment(assignment_id)
        if assignment.status != AssignmentStatus.RESERVED:
            raise StateNotAllowed(f"当前预占状态为 {assignment.status.value}，无法接单")

        now = self._now()
        assignment.status = AssignmentStatus.ACCEPTED
        agent = self.agent_repo.get_by_id(assignment.agent_id)
        if agent is not None:
            self._switch_agent_status(agent, AgentStatus.BUSY, reason="坐席接单", now=now)
        self.db.commit()
        return {"assignment_id": assignment.id, "status": assignment.status.value}

    def release(self, assignment_id: int, *, reason: str = "") -> dict[str, object]:
        assignment = self._get_assignment(assignment_id)
        if assignment.status not in (AssignmentStatus.RESERVED, AssignmentStatus.ACCEPTED):
            raise StateNotAllowed(f"当前预占状态为 {assignment.status.value}，无需释放")

        self._release_assignment(assignment, reason=reason or "手动释放", now=self._now())
        self.db.commit()
        return {"assignment_id": assignment.id, "status": assignment.status.value}

    def accept_for_call(self, agent_id: int, record_id: int) -> None:
        """坐席开始呼叫：有本单预占则接单（RESERVED→ACCEPTED），随后置忙。"""
        assignment = self.agent_repo.get_active_assignment_by_record(record_id)
        if (
            assignment is not None
            and assignment.agent_id == agent_id
            and assignment.status == AssignmentStatus.RESERVED
        ):
            assignment.status = AssignmentStatus.ACCEPTED

        agent = self.agent_repo.get_by_id(agent_id)
        if agent is not None:
            self._switch_agent_status(
                agent, AgentStatus.BUSY, reason="坐席开始呼叫", now=self._now()
            )
        self.db.commit()

    def release_for_record(
        self,
        record_id: int,
        *,
        reason: str = RELEASE_REASON_FINISHED,
        trigger_assign: bool = True,
    ) -> dict[str, object] | None:
        """呼叫结束后释放坐席，并让坐席回到空闲（§34：示闲即尝试下一单）。

        trigger_assign 只会「预占」下一单而不会立即呼叫，因此不存在递归风险。
        """
        assignment = self.agent_repo.get_active_assignment_by_record(record_id)
        agent_id: int | None = assignment.agent_id if assignment is not None else None

        if assignment is not None:
            self._release_assignment(assignment, reason=reason, now=self._now())

        if agent_id is None:
            # 无预占的人工呼叫：把坐席直接放回空闲
            record = self.record_repo.get_by_id(record_id)
            candidate_id = record.agent_id if record is not None else None
            agent = self.agent_repo.get_by_id(candidate_id) if candidate_id else None
            if agent is not None and agent.status == AgentStatus.BUSY:
                self._switch_agent_status(
                    agent, AgentStatus.IDLE, reason=reason, now=self._now()
                )
                agent_id = agent.id

        self.db.commit()

        if agent_id is not None and trigger_assign:
            return self.assign_for_agent(agent_id)
        return None

    # ---------- 预占超时释放（§35）----------

    def expire_reservations(self, *, limit: int = 100) -> dict[str, object]:
        """释放已过期的预占。返回统计（幂等：已释放的不会重复处理）。"""
        now = self._now()
        candidates = self.agent_repo.list_expired_reservations(now=now, limit=limit)

        result: dict[str, object] = {
            "scanned": len(candidates),
            "released": 0,
            "skipped": 0,
        }
        for candidate in candidates:
            assignment = self.agent_repo.get_assignment(candidate.id)
            # 复核状态，保证并发/重复扫描只释放一次（幂等）
            if (
                assignment is None
                or assignment.status != AssignmentStatus.RESERVED
                or assignment.expires_at is None
                or assignment.expires_at >= now
            ):
                result["skipped"] = int(result["skipped"]) + 1
                self.db.commit()
                continue
            self._release_assignment(
                assignment, reason=RELEASE_REASON_EXPIRED, now=now, expired=True
            )
            result["released"] = int(result["released"]) + 1
            self.db.commit()

        if result["released"]:
            logger.warning("预占超时释放：%s", result)
        return result

    # ---------- 查询 ----------

    def list_assignments(
        self, *, page: int, page_size: int, **filters: object
    ) -> tuple[list[AgentAssignment], int]:
        items = self.agent_repo.list_assignments_paged(
            page=page, page_size=page_size, **filters
        )
        total = self.agent_repo.count_assignments(**filters)
        return items, total

    # ---------- 内部 ----------

    def _pick_task_and_record(
        self, agent: Agent
    ) -> tuple[OutboundTask, OutboundRecord] | None:
        """§34：技能队列 → 任务优先级 → 名单优先级。"""
        tasks = self.task_repo.list_assignable(
            tenant_id=agent.tenant_id, skill_queue_id=agent.skill_queue_id
        )
        for task in tasks:
            record = self.record_repo.pick_pending_for_task(task.id)
            if record is not None:
                return task, record
        return None

    def _reserve(
        self, agent: Agent, task: OutboundTask, record: OutboundRecord, *, now: datetime
    ) -> AgentAssignment:
        """创建预占（§35：必须带过期时间）。"""
        return self.agent_repo.create_assignment(
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            task_id=task.id,
            record_id=record.id,
            status=AssignmentStatus.RESERVED,
            reserved_at=now,
            expires_at=now + timedelta(seconds=settings.RESERVATION_TIMEOUT_SECONDS),
        )

    def _dispatch(
        self,
        agent: Agent,
        task: OutboundTask,
        record: OutboundRecord,
        assignment: AgentAssignment,
        *,
        now: datetime,
    ) -> None:
        """派单：记录置 ASSIGNED、坐席置 RESERVED、复用/创建会话。"""
        record.status = RecordStatus.ASSIGNED
        record.agent_id = agent.id
        record.assigned_at = now
        record.timeout_at = now + timedelta(seconds=task.call_timeout_seconds)

        session = self._ensure_session(agent, task, record, now=now)
        if session is not None:
            record.session_id = session.id

        self._switch_agent_status(
            agent, AgentStatus.RESERVED, reason=f"自动派单：任务#{task.id}", now=now
        )
        logger.debug("派单明细：assignment=%s record=%s", assignment.id, record.id)

    def _ensure_session(
        self, agent: Agent, task: OutboundTask, record: OutboundRecord, *, now: datetime
    ):
        if record.session_id is not None:
            existing = self.record_repo.get_session(record.session_id)
            if existing is not None:
                existing.agent_id = agent.id
                return existing
        return self.record_repo.create_session(
            tenant_id=agent.tenant_id,
            task_id=task.id,
            list_id=record.list_id,
            agent_id=agent.id,
            status=SessionStatus.ASSIGNED,
            current_attempt=0,
            started_at=now,
        )

    def _release_assignment(
        self,
        assignment: AgentAssignment,
        *,
        reason: str,
        now: datetime,
        expired: bool = False,
    ) -> None:
        assignment.status = (
            AssignmentStatus.EXPIRED if expired else AssignmentStatus.RELEASED
        )
        assignment.released_at = now
        assignment.release_reason = reason[:255]

        agent = self.agent_repo.get_by_id(assignment.agent_id)
        if agent is not None and agent.status in (AgentStatus.RESERVED, AgentStatus.BUSY):
            self._switch_agent_status(agent, AgentStatus.IDLE, reason=reason, now=now)

    def _switch_agent_status(
        self, agent: Agent, target: AgentStatus, *, reason: str, now: datetime
    ) -> None:
        """内部状态切换（写状态历史，§11）。"""
        from app.services.outbound.agent_state import can_transition

        current = agent.status
        if current == target:
            return
        if not can_transition(current, target):
            logger.warning(
                "跳过非法状态流转：agent=%s %s→%s", agent.id, current.value, target.value
            )
            return

        agent.status = target
        if target == AgentStatus.IDLE:
            agent.last_idle_at = now
        elif target == AgentStatus.BUSY:
            agent.last_busy_at = now

        self.agent_repo.create_status_log(
            agent_id=agent.id,
            from_status=current,
            to_status=target,
            reason=reason[:255],
        )

    def _get_assignment(self, assignment_id: int) -> AgentAssignment:
        assignment = self.agent_repo.get_assignment(assignment_id)
        if assignment is None:
            raise NotFound("预占记录不存在")
        return assignment

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


__all__ = [
    "OutboundAssignmentService",
    "RELEASE_REASON_EXPIRED",
    "RELEASE_REASON_FINISHED",
]
