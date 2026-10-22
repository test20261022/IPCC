"""回呼业务服务（OB-029 IVR 回呼 / OB-030 人工回呼）。

职责：
- 回呼流程配置 CRUD（触发条件存 trigger_condition，匹配逻辑集中在 callback_trigger）；
- 回呼任务：IVR 自动生成（§78 同一会话幂等）/ 人工创建、派单、发起回呼、完成、取消、重呼；
- 到期回呼批量派单（定时任务调用，也可手动触发）。

ASSUMPTION-056：回呼任务关联了外呼任务时，主叫号码沿用该任务的号码配置；
否则按「轮询 + 剩余次数」从租户可用号码中选择，避免回呼抢占某个固定号码。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import (
    Conflict,
    NotFound,
    ParamError,
    ResourceReferenced,
    StateNotAllowed,
)
from app.models.outbound import CallbackFlow, CallbackTask
from app.models.outbound.enums import (
    AgentStatus,
    CallbackSource,
    CallbackStatus,
    CallbackTriggerType,
    CallStatus,
    CommonStatus,
    NumberSelectStrategy,
)
from app.providers.call.base import CallGatewayProvider
from app.providers.factory import get_call_provider
from app.repositories.outbound.agent_repository import OutboundAgentRepository
from app.repositories.outbound.callback_repository import (
    CallbackFlowRepository,
    CallbackTaskRepository,
)
from app.repositories.outbound.list_repository import OutboundListRepository
from app.repositories.outbound.number_repository import OutboundNumberRepository
from app.repositories.outbound.record_repository import OutboundRecordRepository
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.schemas.outbound.callback import (
    CallbackFlowCreate,
    CallbackFlowUpdate,
    CallbackTaskCreate,
    CallbackTriggerContextIn,
)
from app.services.outbound.callback_state import (
    ensure_assignable,
    ensure_callable,
    ensure_cancellable,
    ensure_transition,
)
from app.services.outbound.callback_trigger import (
    CallbackTriggerContext,
    CallbackTriggerDecision,
    condition_priority,
    match_condition,
)
from app.services.outbound.common import apply_updates, ensure_tenant_active
from app.services.outbound.number_selector import OutboundNumberSelector
from app.utils.async_bridge import run_sync
from app.utils.validators import is_valid_phone

logger = logging.getLogger(__name__)


class CallbackService:
    """回呼业务流程。事务在本层提交。"""

    def __init__(
        self, db: Session, *, call_provider: CallGatewayProvider | None = None
    ) -> None:
        self.db = db
        self.flow_repo = CallbackFlowRepository(db)
        self.task_repo = CallbackTaskRepository(db)
        self.agent_repo = OutboundAgentRepository(db)
        self.number_repo = OutboundNumberRepository(db)
        self.record_repo = OutboundRecordRepository(db)
        self.ref = ReferenceRepository(db)
        self.selector = OutboundNumberSelector(db)
        self.outbound_task_repo = OutboundTaskRepository(db)
        self.list_repo = OutboundListRepository(db)
        self._call_provider = call_provider

    @property
    def call_provider(self) -> CallGatewayProvider:
        if self._call_provider is None:
            self._call_provider = get_call_provider()
        return self._call_provider

    # ---------------- 回呼流程 ----------------

    def list_flows(self, **filters: object) -> tuple[list[CallbackFlow], int]:
        page = int(filters.pop("page"))  # type: ignore[arg-type]
        page_size = int(filters.pop("page_size"))  # type: ignore[arg-type]
        items = self.flow_repo.list_paged(page=page, page_size=page_size, **filters)  # type: ignore[arg-type]
        total = self.flow_repo.count(**filters)  # type: ignore[arg-type]
        return items, total

    def get_flow(self, flow_id: int) -> CallbackFlow:
        flow = self.flow_repo.get_by_id(flow_id)
        if flow is None:
            raise NotFound("回呼流程不存在")
        return flow

    def create_flow(self, payload: CallbackFlowCreate) -> CallbackFlow:
        ensure_tenant_active(self.db, payload.tenant_id)
        if self.flow_repo.get_by_code(tenant_id=payload.tenant_id, code=payload.code) is not None:
            raise Conflict(f"同一租户下回呼流程编码已存在：{payload.code}")
        self._validate_ivr_flow(payload.ivr_flow_id, payload.tenant_id)

        flow = self.flow_repo.create(**payload.model_dump())
        self.db.commit()
        logger.info("创建回呼流程成功：id=%s code=%s", flow.id, flow.code)
        return flow

    def update_flow(self, flow_id: int, payload: CallbackFlowUpdate) -> CallbackFlow:
        flow = self.get_flow(flow_id)
        changes = payload.model_dump(exclude_unset=True)
        if "ivr_flow_id" in changes:
            self._validate_ivr_flow(changes["ivr_flow_id"], flow.tenant_id)

        apply_updates(flow, payload)
        self.db.commit()
        logger.info("更新回呼流程成功：id=%s fields=%s", flow_id, sorted(changes))
        return flow

    def set_flow_status(self, flow_id: int, status: CommonStatus) -> CallbackFlow:
        flow = self.get_flow(flow_id)
        if status == CommonStatus.DISABLED and flow.status != status:
            if self.task_repo.count(flow_id=flow_id):
                raise ResourceReferenced("回呼流程已产生回呼任务，禁止停用")
        if flow.status != status:
            flow.status = status
            self.db.commit()
            logger.info("回呼流程状态变更：id=%s -> %s", flow_id, status)
        return flow

    def delete_flow(self, flow_id: int) -> dict[str, Any]:
        flow = self.get_flow(flow_id)
        if self.task_repo.count(flow_id=flow_id):
            raise ResourceReferenced("回呼流程已产生回呼任务，禁止删除")
        flow.mark_deleted()
        self.db.commit()
        logger.info("删除回呼流程成功：id=%s", flow_id)
        return {"flow_id": flow_id}

    # ---------------- 自动触发（OB-029） ----------------

    def create_from_ivr(self, payload: CallbackTriggerContextIn) -> dict[str, Any]:
        """IVR 会话结束时按触发条件生成回呼任务（§45）；同一会话幂等（§78）。"""
        ensure_tenant_active(self.db, payload.tenant_id)
        self._validate_phone(payload.phone)
        self._validate_origin_session(payload.origin_session_id, payload.tenant_id)

        existing = self.task_repo.get_by_origin_session(payload.origin_session_id)
        if existing is not None:
            return self._build_trigger_result(
                created=False,
                reason="同一 IVR 会话已生成回呼任务（§78 幂等命中）",
                flow=None,
                decision=None,
                task=existing,
            )

        context = CallbackTriggerContext(
            source=CallbackSource.IVR.value,
            keys=tuple(payload.keys),
            no_agent=payload.no_agent,
            no_answer=payload.no_answer,
            current_time=payload.current_time,
            attempt_count=payload.attempt_count,
        )
        flow, decision = self._match_flow(
            tenant_id=payload.tenant_id, context=context, flow_id=payload.flow_id
        )
        if flow is None or not decision.matched:
            return self._build_trigger_result(
                created=False, reason=decision.reason, flow=None, decision=decision, task=None
            )

        task = self._create_row(
            tenant_id=payload.tenant_id,
            source=CallbackSource.IVR,
            phone=payload.phone,
            flow_id=flow.id,
            task_id=payload.task_id,
            list_id=payload.list_id,
            origin_session_id=payload.origin_session_id,
            trigger_type=decision.trigger_type,
            delay_seconds=decision.delay_seconds,
            agent_id=None,
            remark=payload.remark,
        )
        self.db.commit()
        logger.info(
            "IVR 回呼任务已生成：id=%s flow=%s trigger=%s",
            task.id,
            flow.code,
            decision.trigger_value,
        )
        return self._build_trigger_result(
            created=True,
            reason=f"命中回呼流程「{flow.name}」：{decision.reason}",
            flow=flow,
            decision=decision,
            task=task,
        )

    def _match_flow(
        self,
        *,
        tenant_id: int,
        context: CallbackTriggerContext,
        flow_id: int | None,
    ) -> tuple[CallbackFlow | None, CallbackTriggerDecision]:
        """挑选回呼流程：显式指定优先，否则按优先级取第一个命中的流程。"""
        if flow_id is not None:
            flow = self.get_flow(flow_id)
            if flow.tenant_id != tenant_id:
                raise ParamError("回呼流程与来话不属于同一租户")
            if flow.status != CommonStatus.ENABLED:
                raise StateNotAllowed("回呼流程已停用")
            return flow, match_condition(flow.trigger_condition, context)

        candidates = sorted(
            self.flow_repo.list_enabled(tenant_id=tenant_id),
            key=lambda item: (condition_priority(item.trigger_condition), item.id),
        )
        # 未命中时回显最具体的失败原因（业务时段门禁 / 尝试次数超限等），便于排查配置
        fallback: CallbackTriggerDecision | None = None
        for flow in candidates:
            decision = match_condition(flow.trigger_condition, context)
            if decision.matched:
                return flow, decision
            if fallback is None:
                fallback = decision
        return None, (
            fallback
            if fallback is not None
            else CallbackTriggerDecision(
                matched=False, reason="没有启用中的回呼流程满足触发条件"
            )
        )

    # ---------------- 回呼任务 ----------------

    def list_tasks(self, **filters: object) -> tuple[list[CallbackTask], int]:
        page = int(filters.pop("page"))  # type: ignore[arg-type]
        page_size = int(filters.pop("page_size"))  # type: ignore[arg-type]
        items = self.task_repo.list_paged(page=page, page_size=page_size, **filters)  # type: ignore[arg-type]
        total = self.task_repo.count(**filters)  # type: ignore[arg-type]
        return items, total

    def get_task(self, task_id: int) -> CallbackTask:
        task = self.task_repo.get_by_id(task_id)
        if task is None:
            raise NotFound("回呼任务不存在")
        return task

    def create_task(self, payload: CallbackTaskCreate) -> CallbackTask:
        """人工创建回呼任务（OB-030），也支持 IVR 回呼的直接落库。"""
        ensure_tenant_active(self.db, payload.tenant_id)
        self._validate_phone(payload.phone)

        if payload.source == CallbackSource.IVR and payload.origin_session_id is None:
            raise ParamError("IVR 回呼必须携带原会话 ID（§78 幂等键）")
        if payload.origin_session_id is not None:
            existing = self.task_repo.get_by_origin_session(payload.origin_session_id)
            if existing is not None:
                logger.info("回呼任务命中幂等，返回已存在任务：id=%s", existing.id)
                return existing

        flow: CallbackFlow | None = None
        if payload.flow_id is not None:
            flow = self.get_flow(payload.flow_id)
            if flow.tenant_id != payload.tenant_id:
                raise ParamError("回呼流程与任务不属于同一租户")
        self._validate_related(payload)
        if payload.agent_id is not None:
            self._validate_agent(payload.agent_id, payload.tenant_id)

        task = self._create_row(
            tenant_id=payload.tenant_id,
            source=payload.source,
            phone=payload.phone,
            flow_id=payload.flow_id,
            task_id=payload.task_id,
            list_id=payload.list_id,
            origin_session_id=payload.origin_session_id,
            trigger_type=payload.trigger_type,
            delay_seconds=0,
            agent_id=payload.agent_id,
            remark=payload.remark,
            scheduled_at=payload.scheduled_at or self._scheduled_from_flow(flow),
        )
        if payload.agent_id is not None:
            task.status = CallbackStatus.ASSIGNED
            task.assigned_at = self._now()
        self.db.commit()
        logger.info(
            "创建回呼任务成功：id=%s source=%s phone=%s",
            task.id,
            task.source,
            task.phone,
        )
        return task

    def assign_task(
        self, task_id: int, *, agent_id: int | None = None, auto: bool = False
    ) -> CallbackTask:
        """派单：指定坐席，或在自动模式下挑选空闲坐席。"""
        task = self.get_task(task_id)
        ensure_assignable(task.status)

        if agent_id is not None:
            self._validate_agent(agent_id, task.tenant_id)
        else:
            if task.agent_id is not None:
                # 重呼场景：沿用原坐席，先确认其仍然可用
                self._validate_agent(task.agent_id, task.tenant_id)
                agent_id = task.agent_id
                auto = True
            else:
                agent = self._pick_idle_agent(tenant_id=task.tenant_id)
                if agent is None:
                    raise StateNotAllowed("当前没有空闲坐席，无法自动派单")
                agent_id = agent.id
                auto = True

        task.agent_id = agent_id
        task.assigned_at = self._now()
        ensure_transition(task.status, CallbackStatus.ASSIGNED)
        task.status = CallbackStatus.ASSIGNED
        task.finished_at = None
        self.db.commit()
        logger.info("回呼任务派单成功：task=%s agent=%s auto=%s", task_id, agent_id, auto)
        return task

    def dispatch_due(self, *, tenant_id: int | None = None, limit: int = 50) -> dict[str, int]:
        """批量派单到期回呼任务（定时任务与手动入口共用）。"""
        due = self.task_repo.list_due(now=self._now(), tenant_id=tenant_id, limit=limit)
        assigned = 0
        skipped = 0
        for task in due:
            try:
                agent_id = task.agent_id
                if agent_id is not None:
                    agent = self.ref.get_agent_by_id(agent_id)
                    if agent is None or agent.status == AgentStatus.OFFLINE:
                        agent_id = None
                if agent_id is None:
                    agent = self._pick_idle_agent(tenant_id=task.tenant_id)
                    if agent is None:
                        skipped += 1
                        continue
                    agent_id = agent.id
                task.agent_id = agent_id
                task.assigned_at = self._now()
                task.status = CallbackStatus.ASSIGNED
                assigned += 1
            except Exception:  # noqa: BLE001 - 单条失败不影响其余任务
                logger.exception("回呼任务派单失败：task=%s", task.id)
                skipped += 1
        self.db.commit()
        logger.info(
            "到期回呼派单完成：扫描=%s 派单=%s 跳过=%s", len(due), assigned, skipped
        )
        return {"scanned": len(due), "assigned": assigned, "skipped": skipped}

    def call_task(self, task_id: int) -> dict[str, Any]:
        """发起一次回呼（§46）：校验状态与坐席、占用主叫号码、拨号并回写结果。"""
        task = self.get_task(task_id)
        ensure_callable(task.status)
        if task.agent_id is None:
            raise ParamError("回呼任务尚未分配坐席，无法发起回呼")
        self._validate_agent(task.agent_id, task.tenant_id)

        now = self._now()
        ensure_transition(task.status, CallbackStatus.CALLING)
        task.status = CallbackStatus.CALLING
        task.last_call_at = now
        task.attempt_count = (task.attempt_count or 0) + 1

        calling_number = self._pick_calling_number(
            tenant_id=task.tenant_id, task_id=task.task_id
        )
        if calling_number is None:
            task.status = CallbackStatus.FAILED
            task.finished_at = now
            self.db.commit()
            logger.warning("回呼失败：无可用主叫号码 task=%s", task_id)
            return {
                "task_id": task.id,
                "status": task.status,
                "attempt_count": task.attempt_count,
                "call_status": None,
                "failure_reason": "外呼号码已全部不可用（不存在 / 停用 / 次数耗尽）",
                "calling_number": None,
                "history_id": None,
            }

        history = self.record_repo.create_history(
            tenant_id=task.tenant_id,
            callback_task_id=task.id,
            task_id=task.task_id,
            list_id=task.list_id,
            agent_id=task.agent_id,
            phone=task.phone,
            call_status=CallStatus.INITIATED,
            started_at=now,
            provider=self.call_provider.name,
        )
        result = run_sync(
            self.call_provider.make_call(
                phone=task.phone, agent_id=task.agent_id, session_id=None
            )
        )
        ended = self._now()
        history.call_status = result.call_status
        history.failure_reason = result.failure_reason
        history.provider_call_id = result.provider_call_id
        history.duration = result.duration
        history.recording_path = result.recording_path
        history.ended_at = ended
        if result.success:
            history.connected_at = ended

        if result.success:
            task.status = CallbackStatus.SUCCESS
            task.finished_at = ended
        else:
            task.status = CallbackStatus.FAILED
            task.finished_at = ended
        self.db.commit()

        logger.info(
            "回呼执行完成：task=%s phone=%s 结果=%s 主叫=%s",
            task.id,
            task.phone,
            result.call_status.value,
            calling_number.caller_number,
        )
        return {
            "task_id": task.id,
            "status": task.status,
            "attempt_count": task.attempt_count,
            "call_status": result.call_status.value,
            "failure_reason": result.failure_reason,
            "calling_number": calling_number.caller_number,
            "history_id": history.id,
        }

    def finish_task(
        self, task_id: int, *, success: bool, remark: str | None = None
    ) -> CallbackTask:
        """人工登记回呼结果（坐席线下沟通后回填）。"""
        task = self.get_task(task_id)
        target = CallbackStatus.SUCCESS if success else CallbackStatus.FAILED
        ensure_transition(task.status, target)
        task.status = target
        task.finished_at = self._now()
        if remark:
            task.remark = remark
        self.db.commit()
        logger.info("回呼任务结果登记：id=%s -> %s", task_id, target)
        return task

    def cancel_task(self, task_id: int, *, reason: str = "") -> CallbackTask:
        task = self.get_task(task_id)
        ensure_cancellable(task.status)
        ensure_transition(task.status, CallbackStatus.CANCELLED)
        task.status = CallbackStatus.CANCELLED
        task.finished_at = self._now()
        if reason:
            task.remark = reason
        self.db.commit()
        logger.info("回呼任务已取消：id=%s reason=%s", task_id, reason)
        return task

    def requeue_task(self, task_id: int, *, reason: str = "") -> CallbackTask:
        """把已失败的回呼任务退回待回呼，等待重新分配与呼出（重呼）。"""
        task = self.get_task(task_id)
        ensure_transition(task.status, CallbackStatus.PENDING)
        task.status = CallbackStatus.PENDING
        task.finished_at = None
        task.assigned_at = None
        if reason:
            task.remark = reason
        self.db.commit()
        logger.info("回呼任务已重新入队：id=%s reason=%s", task_id, reason)
        return task

    # ---------------- 内部 ----------------

    def _create_row(
        self,
        *,
        tenant_id: int,
        source: CallbackSource,
        phone: str,
        flow_id: int | None,
        task_id: int | None,
        list_id: int | None,
        origin_session_id: int | None,
        trigger_type: CallbackTriggerType | None,
        delay_seconds: int,
        agent_id: int | None,
        remark: str,
        scheduled_at: datetime | None = None,
    ) -> CallbackTask:
        scheduled = scheduled_at
        if scheduled is None and delay_seconds > 0:
            scheduled = self._now() + timedelta(seconds=delay_seconds)
        return self.task_repo.create(
            tenant_id=tenant_id,
            source=source,
            phone=phone,
            flow_id=flow_id,
            task_id=task_id,
            list_id=list_id,
            origin_session_id=origin_session_id,
            trigger_type=trigger_type,
            scheduled_at=scheduled,
            agent_id=agent_id,
            status=CallbackStatus.PENDING,
            remark=remark,
        )

    def _scheduled_from_flow(self, flow: CallbackFlow | None) -> datetime | None:
        """人工创建时若指定了流程，按流程的 delay_seconds 计算计划回呼时间。"""
        if flow is None:
            return None
        raw = (flow.trigger_condition or {}).get("delay_seconds")
        try:
            delay = max(0, int(raw))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return self._now() + timedelta(seconds=delay) if delay else None

    def _build_trigger_result(
        self,
        *,
        created: bool,
        reason: str,
        flow: CallbackFlow | None,
        decision: CallbackTriggerDecision | None,
        task: CallbackTask | None,
    ) -> dict[str, Any]:
        return {
            "created": created,
            "reason": reason,
            "flow_id": flow.id if flow is not None else (task.flow_id if task else None),
            "flow_name": flow.name if flow is not None else None,
            "trigger_type": decision.trigger_type
            if decision is not None and decision.matched
            else (task.trigger_type if task else None),
            "task": task,
        }

    def _validate_phone(self, phone: str) -> None:
        if not is_valid_phone(phone):
            raise ParamError(f"回呼号码格式不合法：{phone}")

    def _validate_ivr_flow(self, ivr_flow_id: int | None, tenant_id: int) -> None:
        if ivr_flow_id is None:
            return
        flow = self.ref.get_ivr_flow_by_id(ivr_flow_id)
        if flow is None:
            raise NotFound("IVR 流程不存在")
        if flow.tenant_id != tenant_id:
            raise ParamError("IVR 流程与回呼流程不属于同一租户")

    def _validate_related(self, payload: CallbackTaskCreate) -> None:
        """校验关联的外呼任务 / 名单 / 会话归属，避免跨租户引用与悬空外键（§60）。"""
        if payload.task_id is not None:
            outbound_task = self.outbound_task_repo.get_by_id(payload.task_id)
            if outbound_task is None:
                raise NotFound("外呼任务不存在")
            if outbound_task.tenant_id != payload.tenant_id:
                raise ParamError("外呼任务与回呼任务不属于同一租户")
        if payload.list_id is not None:
            name_list = self.list_repo.get_by_id(payload.list_id)
            if name_list is None:
                raise NotFound("名单不存在")
            if name_list.tenant_id != payload.tenant_id:
                raise ParamError("名单与回呼任务不属于同一租户")
        self._validate_origin_session(payload.origin_session_id, payload.tenant_id)

    def _validate_origin_session(
        self, origin_session_id: int | None, tenant_id: int
    ) -> None:
        """原会话是幂等键且带外键约束，必须先校验存在性，避免落库时抛外键冲突。

        否则调用方传错会话 ID 只会得到 500，无法判断是参数问题还是系统故障。
        """
        if origin_session_id is None:
            return
        session = self.record_repo.get_session_any_state(origin_session_id)
        if session is None:
            raise NotFound(f"原会话不存在：{origin_session_id}")
        if session.tenant_id != tenant_id:
            raise ParamError("原会话与回呼任务不属于同一租户")

    def _validate_agent(self, agent_id: int, tenant_id: int) -> None:
        agent = self.ref.get_agent_by_id(agent_id)
        if agent is None:
            raise NotFound("坐席不存在")
        if agent.tenant_id != tenant_id:
            raise ParamError("坐席与回呼任务不属于同一租户")
        if agent.status == AgentStatus.OFFLINE:
            raise StateNotAllowed("坐席当前离线，无法执行回呼")

    def _pick_idle_agent(self, *, tenant_id: int, limit: int = 50):
        """挑选空闲坐席（按 id 升序，保证结果确定）。"""
        candidates = self.agent_repo.list_paged(
            page=1, page_size=limit, tenant_id=tenant_id, status=AgentStatus.IDLE
        )
        return candidates[0] if candidates else None

    def _pick_calling_number(self, *, tenant_id: int, task_id: int | None):
        candidates = self.selector.ordered_candidates(
            strategy=NumberSelectStrategy.ROUND_ROBIN,
            tenant_id=tenant_id,
            task_id=task_id,
        )
        for candidate in candidates:
            if self.number_repo.consume_atomically(candidate.id) == 1:
                self.db.refresh(candidate)
                return candidate
        return None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


__all__ = ["CallbackService"]
