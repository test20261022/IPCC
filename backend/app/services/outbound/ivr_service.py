"""IVR 外呼策略服务（OB-017）。

规则：
- 流程被外呼任务引用时禁止删除、禁止停用（回显引用任务名称）。
- 转人工节点（TRANSFER_AGENT）必须显式配置 no_agent_action，落实 §32「禁止硬编码兜底」。
- 流转的源 / 目标节点必须属于同一流程；源节点下同条件不允许重复配置。
- 删除节点联动软删除与之相关的流转；删除入口节点时清空流程入口。

ASSUMPTION-052：需求未定义「被引用后能否改结构」。此处采用「引用只锁删除与停用，
结构仍可编辑」——否则已上线任务的 IVR 一旦配错便无法修正。
ASSUMPTION-053：模拟运行时若未显式指定 queue_available，则按
「指定技能队列 → 该队列 IDLE 坐席数」、否则「租户下 IDLE 坐席数」推断队列可用性。
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ParamError, ResourceReferenced
from app.models.outbound import IvrFlow, IvrNode, IvrTransition
from app.models.outbound.enums import CommonStatus, IvrConditionType, IvrNodeType
from app.repositories.outbound.agent_repository import OutboundAgentRepository
from app.repositories.outbound.ivr_repository import (
    IvrFlowRepository,
    IvrNodeRepository,
    IvrTransitionRepository,
)
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.schemas.outbound.ivr import (
    IvrFlowCreate,
    IvrFlowUpdate,
    IvrNodeCreate,
    IvrNodeUpdate,
    IvrTransitionCreate,
    IvrTransitionUpdate,
)
from app.services.outbound.common import apply_updates, ensure_tenant_active
from app.services.outbound.ivr_strategy import (
    QUEUE_AVAILABLE_FALSE,
    QUEUE_AVAILABLE_TRUE,
    IvrSimulationContext,
    IvrSimulationInput,
    is_valid_time_range,
    simulate,
)

logger = logging.getLogger(__name__)

#: 不允许有出向流转的终结节点类型（有则给出提示，运行时不会被使用）
TERMINAL_NODE_TYPES = frozenset(
    {IvrNodeType.HANGUP, IvrNodeType.CALLBACK, IvrNodeType.TRANSFER_AGENT}
)


class IvrService:
    """IVR 流程业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.flow_repo = IvrFlowRepository(db)
        self.node_repo = IvrNodeRepository(db)
        self.transition_repo = IvrTransitionRepository(db)
        self.ref = ReferenceRepository(db)
        self.agent_repo = OutboundAgentRepository(db)

    # ---------------- 查询 ----------------

    def list_flows(self, **filters: object) -> tuple[list[IvrFlow], int]:
        page = int(filters.pop("page"))  # type: ignore[arg-type]
        page_size = int(filters.pop("page_size"))  # type: ignore[arg-type]
        items = self.flow_repo.list_paged(page=page, page_size=page_size, **filters)  # type: ignore[arg-type]
        total = self.flow_repo.count(**filters)  # type: ignore[arg-type]
        return items, total

    def get_flow(self, flow_id: int) -> IvrFlow:
        flow = self.flow_repo.get_by_id(flow_id)
        if flow is None:
            raise NotFound("IVR 流程不存在")
        return flow

    def get_flow_detail(self, flow_id: int) -> dict[str, Any]:
        """流程详情：一次返回节点与流转，供前端编辑器渲染。"""
        flow = self.get_flow(flow_id)
        return {
            "flow": flow,
            "nodes": self.node_repo.list_by_flow(flow_id),
            "transitions": self.transition_repo.list_by_flow(flow_id),
        }

    def get_node(self, node_id: int) -> IvrNode:
        node = self.node_repo.get_by_id(node_id)
        if node is None:
            raise NotFound("IVR 节点不存在")
        return node

    def get_transition(self, transition_id: int) -> IvrTransition:
        transition = self.transition_repo.get_by_id(transition_id)
        if transition is None:
            raise NotFound("IVR 流转不存在")
        return transition

    # ---------------- 流程 ----------------

    def create_flow(self, payload: IvrFlowCreate) -> IvrFlow:
        ensure_tenant_active(self.db, payload.tenant_id)
        if self.flow_repo.get_by_code(tenant_id=payload.tenant_id, code=payload.code) is not None:
            raise Conflict(f"同一租户下流程编码已存在：{payload.code}")

        flow = self.flow_repo.create(**payload.model_dump())
        self.db.commit()
        logger.info("创建 IVR 流程成功：id=%s code=%s", flow.id, flow.code)
        return flow

    def update_flow(self, flow_id: int, payload: IvrFlowUpdate) -> IvrFlow:
        flow = self.get_flow(flow_id)
        changes = payload.model_dump(exclude_unset=True)

        entry_key = changes.get("entry_node_key", flow.entry_node_key)
        if entry_key is not None:
            if self.node_repo.get_by_key(flow_id=flow_id, node_key=str(entry_key)) is None:
                raise ParamError(f"入口节点不存在：{entry_key}")

        apply_updates(flow, payload)
        self.db.commit()
        logger.info("更新 IVR 流程成功：id=%s fields=%s", flow_id, sorted(changes))
        return flow

    def set_flow_status(self, flow_id: int, status: CommonStatus) -> IvrFlow:
        flow = self.get_flow(flow_id)
        if status == CommonStatus.DISABLED and flow.status != status:
            if self.ref.count_tasks_by_ivr_flow(flow_id):
                raise ResourceReferenced("IVR 流程已被外呼任务引用，禁止停用")
            if self.ref.count_callback_flows_by_ivr_flow(flow_id):
                raise ResourceReferenced("IVR 流程已被回呼流程引用，禁止停用")
        if flow.status != status:
            flow.status = status
            self.db.commit()
            logger.info("IVR 流程状态变更：id=%s -> %s", flow_id, status)
        return flow

    def delete_flow(self, flow_id: int) -> dict[str, Any]:
        """软删除流程，并联动软删除其节点与流转。"""
        flow = self.get_flow(flow_id)

        referenced_tasks = self.ref.list_tasks_using_ivr_flows([flow_id])
        if referenced_tasks:
            names = "、".join(dict.fromkeys(referenced_tasks))
            raise ResourceReferenced(f"IVR 流程已被以下任务引用，禁止删除：{names}")
        if self.ref.count_callback_flows_by_ivr_flow(flow_id):
            raise ResourceReferenced("IVR 流程已被回呼流程引用，禁止删除")

        nodes = self.node_repo.list_by_flow(flow_id)
        transitions = self.transition_repo.list_by_flow(flow_id)
        for transition in transitions:
            transition.mark_deleted()
        for node in nodes:
            node.mark_deleted()
        flow.mark_deleted()
        self.db.commit()

        logger.info(
            "删除 IVR 流程成功：id=%s 联动节点=%s 流转=%s",
            flow_id,
            len(nodes),
            len(transitions),
        )
        return {
            "flow_id": flow_id,
            "removed_nodes": len(nodes),
            "removed_transitions": len(transitions),
        }

    # ---------------- 节点 ----------------

    def create_node(self, flow_id: int, payload: IvrNodeCreate) -> IvrNode:
        flow = self.get_flow(flow_id)
        if payload.tenant_id != flow.tenant_id:
            raise ParamError("节点与流程不属于同一租户")
        if self.node_repo.get_by_key(flow_id=flow_id, node_key=payload.node_key) is not None:
            raise Conflict(f"流程内节点标识已存在：{payload.node_key}")

        values = payload.model_dump()
        values["flow_id"] = flow_id
        values["tenant_id"] = flow.tenant_id
        self._validate_node_rule(
            node_type=payload.node_type,
            no_agent_action=payload.no_agent_action,
            config=payload.config,
            tenant_id=flow.tenant_id,
        )

        node = self.node_repo.create(**values)
        self.db.commit()
        logger.info(
            "创建 IVR 节点成功：flow=%s key=%s type=%s",
            flow_id,
            node.node_key,
            node.node_type,
        )
        return node

    def update_node(self, node_id: int, payload: IvrNodeUpdate) -> IvrNode:
        node = self.get_node(node_id)
        changes = payload.model_dump(exclude_unset=True)

        node_type = changes.get("node_type", node.node_type)
        no_agent_action = changes.get("no_agent_action", node.no_agent_action)
        config = changes.get("config", node.config)
        self._validate_node_rule(
            node_type=node_type,
            no_agent_action=no_agent_action,
            config=config,
            tenant_id=node.tenant_id,
        )

        apply_updates(node, payload)
        self.db.commit()
        logger.info("更新 IVR 节点成功：id=%s fields=%s", node_id, sorted(changes))
        return node

    def delete_node(self, node_id: int) -> dict[str, Any]:
        """删除节点：联动软删除相关流转，并在删除入口节点时清空入口。"""
        node = self.get_node(node_id)
        flow = self.get_flow(node.flow_id)

        related = {
            item.id: item
            for item in self.transition_repo.list_by_nodes([node_id])
            + self.transition_repo.list_referencing_nodes([node_id])
        }
        for transition in related.values():
            transition.mark_deleted()

        if flow.entry_node_key == node.node_key:
            flow.entry_node_key = None

        node.mark_deleted()
        self.db.commit()

        logger.info("删除 IVR 节点成功：id=%s 联动流转=%s", node_id, len(related))
        return {"node_id": node_id, "removed_transitions": len(related)}

    # ---------------- 流转 ----------------

    def create_transition(self, flow_id: int, payload: IvrTransitionCreate) -> IvrTransition:
        flow = self.get_flow(flow_id)
        if payload.tenant_id != flow.tenant_id:
            raise ParamError("流转与流程不属于同一租户")

        node = self.node_repo.get_by_id(payload.from_node_id)
        if node is None or node.flow_id != flow_id:
            raise ParamError("源节点不属于该 IVR 流程")
        if payload.to_node_id is not None:
            target = self.node_repo.get_by_id(payload.to_node_id)
            if target is None or target.flow_id != flow_id:
                raise ParamError("目标节点不属于该 IVR 流程")

        self._validate_condition(
            condition_type=payload.condition_type, condition_value=payload.condition_value
        )
        if self.transition_repo.exists_same_condition(
            from_node_id=payload.from_node_id,
            condition_type=str(payload.condition_type),
            condition_value=payload.condition_value,
        ):
            raise Conflict("该源节点下相同条件的流转已存在")

        values = payload.model_dump()
        values["flow_id"] = flow_id
        values["tenant_id"] = flow.tenant_id
        transition = self.transition_repo.create(**values)
        self.db.commit()
        logger.info(
            "创建 IVR 流转成功：flow=%s from=%s type=%s",
            flow_id,
            payload.from_node_id,
            payload.condition_type,
        )
        return transition

    def update_transition(
        self, transition_id: int, payload: IvrTransitionUpdate
    ) -> IvrTransition:
        transition = self.get_transition(transition_id)
        changes = payload.model_dump(exclude_unset=True)

        if "to_node_id" in changes and changes["to_node_id"] is not None:
            target = self.node_repo.get_by_id(int(changes["to_node_id"]))
            if target is None or target.flow_id != transition.flow_id:
                raise ParamError("目标节点不属于该 IVR 流程")

        condition_type = changes.get("condition_type", transition.condition_type)
        condition_value = changes.get("condition_value", transition.condition_value)
        self._validate_condition(
            condition_type=condition_type, condition_value=condition_value
        )
        if self.transition_repo.exists_same_condition(
            from_node_id=transition.from_node_id,
            condition_type=str(condition_type),
            condition_value=condition_value,
            exclude_id=transition_id,
        ):
            raise Conflict("该源节点下相同条件的流转已存在")

        apply_updates(transition, payload)
        self.db.commit()
        logger.info("更新 IVR 流转成功：id=%s fields=%s", transition_id, sorted(changes))
        return transition

    def delete_transition(self, transition_id: int) -> None:
        transition = self.get_transition(transition_id)
        transition.mark_deleted()
        self.db.commit()
        logger.info("删除 IVR 流转成功：id=%s", transition_id)

    # ---------------- 结构校验 ----------------

    def validate_flow(self, flow_id: int) -> dict[str, Any]:
        """结构校验（OB-017）：错误阻断发布，提示不阻断。"""
        flow = self.get_flow(flow_id)
        nodes = self.node_repo.list_by_flow(flow_id)
        transitions = self.transition_repo.list_by_flow(flow_id)
        node_by_id = {node.id: node for node in nodes}
        node_keys = {node.node_key for node in nodes}

        issues: list[dict[str, str]] = []
        issues.extend(self._collect_errors(flow, nodes, transitions, node_by_id, node_keys))
        issues.extend(self._collect_warnings(flow, nodes, transitions))

        error_count = sum(1 for item in issues if item["level"] == "ERROR")
        warning_count = len(issues) - error_count
        return {
            "valid": error_count == 0,
            "issues": issues,
            "error_count": error_count,
            "warning_count": warning_count,
            "node_count": len(nodes),
            "transition_count": len(transitions),
        }

    def _collect_errors(
        self,
        flow: IvrFlow,
        nodes: list[IvrNode],
        transitions: list[IvrTransition],
        node_by_id: dict[int, IvrNode],
        node_keys: set[str],
    ) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []

        if not nodes:
            issues.append(
                {
                    "level": "ERROR",
                    "code": "NO_NODE",
                    "target": flow.code,
                    "message": "流程未配置任何节点",
                }
            )
            return issues

        if not flow.entry_node_key:
            issues.append(
                {
                    "level": "ERROR",
                    "code": "ENTRY_MISSING",
                    "target": flow.code,
                    "message": "未设置入口节点",
                }
            )
        elif flow.entry_node_key not in node_keys:
            issues.append(
                {
                    "level": "ERROR",
                    "code": "ENTRY_NOT_FOUND",
                    "target": flow.entry_node_key,
                    "message": f"入口节点不存在：{flow.entry_node_key}",
                }
            )

        for node in nodes:
            # §32：转人工节点必须显式声明无坐席兜底动作，禁止依赖代码硬编码
            if (
                node.node_type == IvrNodeType.TRANSFER_AGENT
                and node.no_agent_action is None
            ):
                issues.append(
                    {
                        "level": "ERROR",
                        "code": "NO_AGENT_ACTION_MISSING",
                        "target": node.node_key,
                        "message": "转人工节点未配置「无可用坐席动作」",
                    }
                )

        for transition in transitions:
            source = node_by_id.get(transition.from_node_id)
            if source is None:
                issues.append(
                    {
                        "level": "ERROR",
                        "code": "FROM_NODE_NOT_IN_FLOW",
                        "target": str(transition.id),
                        "message": "流转的源节点不属于本流程",
                    }
                )
                continue
            if transition.to_node_id is not None and transition.to_node_id not in node_by_id:
                issues.append(
                    {
                        "level": "ERROR",
                        "code": "TO_NODE_NOT_IN_FLOW",
                        "target": source.node_key,
                        "message": "流转的目标节点不属于本流程",
                    }
                )
            condition_issue = self._condition_error(source.node_key, transition)
            if condition_issue is not None:
                issues.append(condition_issue)

        return issues

    @staticmethod
    def _condition_error(
        node_key: str, transition: IvrTransition
    ) -> dict[str, str] | None:
        condition_type = transition.condition_type
        condition_value = transition.condition_value

        if condition_type == IvrConditionType.TIME_RANGE:
            if not is_valid_time_range(condition_value):
                return {
                    "level": "ERROR",
                    "code": "TIME_RANGE_INVALID",
                    "target": node_key,
                    "message": f"时段条件无法解析：{condition_value}（应为 09:00-18:00 形式）",
                }
            return None

        if condition_type == IvrConditionType.QUEUE_AVAILABLE:
            if condition_value not in QUEUE_AVAILABLE_TRUE | QUEUE_AVAILABLE_FALSE:
                return {
                    "level": "ERROR",
                    "code": "QUEUE_CONDITION_INVALID",
                    "target": node_key,
                    "message": (
                        f"队列可用性取值非法：{condition_value}"
                        "（应为 true / false 或留空表示有可用坐席）"
                    ),
                }
        return None

    def _collect_warnings(
        self,
        flow: IvrFlow,
        nodes: list[IvrNode],
        transitions: list[IvrTransition],
    ) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        outgoing: dict[int, list[IvrTransition]] = {}
        for transition in transitions:
            outgoing.setdefault(transition.from_node_id, []).append(transition)

        issues.extend(self._reachability_warnings(flow.entry_node_key, nodes, transitions))

        for node in nodes:
            edges = outgoing.get(node.id, [])
            if node.node_type in TERMINAL_NODE_TYPES and edges:
                issues.append(
                    {
                        "level": "WARNING",
                        "code": "TERMINAL_HAS_TRANSITION",
                        "target": node.node_key,
                        "message": "终结型节点配置了出向流转，运行时不会使用",
                    }
                )
            if node.node_type == IvrNodeType.COLLECT_DTMF and not edges:
                issues.append(
                    {
                        "level": "WARNING",
                        "code": "COLLECT_WITHOUT_TRANSITION",
                        "target": node.node_key,
                        "message": "按键采集节点没有任何流转，收集到输入后无法继续",
                    }
                )
            for edge in edges:
                if edge.to_node_id == node.id:
                    issues.append(
                        {
                            "level": "WARNING",
                            "code": "SELF_LOOP",
                            "target": node.node_key,
                            "message": "存在自环流转，运行时会受推演步数上限保护",
                        }
                    )
        return issues

    @staticmethod
    def _reachability_warnings(
        entry_node_key: str | None,
        nodes: list[IvrNode],
        transitions: list[IvrTransition],
    ) -> list[dict[str, str]]:
        """从入口节点做一次 BFS，标记不可达节点。"""
        if not entry_node_key:
            return []
        start = next((node for node in nodes if node.node_key == entry_node_key), None)
        if start is None:
            return []

        adjacency: dict[int, list[int]] = {}
        for transition in transitions:
            if transition.to_node_id is not None:
                adjacency.setdefault(transition.from_node_id, []).append(transition.to_node_id)

        reachable = {start.id}
        stack = [start.id]
        while stack:
            current = stack.pop()
            for nxt in adjacency.get(current, []):
                if nxt not in reachable:
                    reachable.add(nxt)
                    stack.append(nxt)

        return [
            {
                "level": "WARNING",
                "code": "UNREACHABLE_NODE",
                "target": node.node_key,
                "message": "从入口节点不可达",
            }
            for node in nodes
            if node.id not in reachable
        ]

    # ---------------- 模拟运行 ----------------

    def simulate_flow(
        self,
        flow_id: int,
        *,
        inputs: list[IvrSimulationInput],
        current_time: str | None = None,
        queue_available: bool | None = None,
        skill_queue_id: int | None = None,
        max_steps: int | None = None,
    ) -> dict[str, Any]:
        """按流程结构推演一次外呼 IVR 执行过程（OB-017）。"""
        flow = self.get_flow(flow_id)
        nodes = self.node_repo.list_by_flow(flow_id)
        transitions = self.transition_repo.list_by_flow(flow_id)

        resolved_queue_state = self._resolve_queue_available(
            tenant_id=flow.tenant_id,
            explicit=queue_available,
            skill_queue_id=skill_queue_id,
        )

        kwargs: dict[str, Any] = {}
        if max_steps is not None:
            kwargs["max_steps"] = max_steps

        result = simulate(
            nodes=nodes,
            transitions=transitions,
            entry_node_key=flow.entry_node_key,
            context=IvrSimulationContext(
                inputs=tuple(inputs),
                current_time=current_time,
                queue_available=resolved_queue_state,
            ),
            **kwargs,
        )

        return {
            "flow_id": flow.id,
            "flow_name": flow.name,
            "entry_node_key": result.entry_node_key,
            "final_node_key": result.final_node_key,
            "ended": result.ended,
            "transferred": result.transferred,
            "no_agent_action": result.no_agent_action,
            "collected_keys": result.collected_keys,
            "replay_count": result.replay_count,
            "end_reason": result.end_reason,
            "queue_available": resolved_queue_state,
            "steps": [
                {
                    "index": step.index,
                    "node_key": step.node_key,
                    "node_name": step.node_name,
                    "node_type": step.node_type,
                    "action": step.action,
                    "detail": step.detail,
                    "from_node_key": step.from_node_key,
                    "to_node_key": step.to_node_key,
                    "condition_type": step.condition_type,
                    "condition_value": step.condition_value,
                    "replay_count": step.replay_count,
                }
                for step in result.steps
            ],
        }

    def _resolve_queue_available(
        self,
        *,
        tenant_id: int,
        explicit: bool | None,
        skill_queue_id: int | None,
    ) -> bool | None:
        """推断技能队列可用性：显式传入优先，否则按空闲坐席数判断（ASSUMPTION-053）。"""
        if explicit is not None:
            return explicit
        counts = self.agent_repo.count_by_status(
            tenant_id=tenant_id, skill_queue_id=skill_queue_id
        )
        return counts.get("IDLE", 0) > 0

    # ---------------- 内部校验 ----------------

    def _validate_node_rule(
        self,
        *,
        node_type: IvrNodeType,
        no_agent_action: Any,
        config: dict[str, Any] | None,
        tenant_id: int,
    ) -> None:
        """§32：转人工节点必须显式声明无可用坐席的兜底动作。"""
        if node_type == IvrNodeType.TRANSFER_AGENT and no_agent_action is None:
            raise ParamError(
                "转人工节点必须配置「无可用坐席动作」"
                "（QUEUE 排队 / CALLBACK 回呼 / REPLAY 重播 / HANGUP 挂断）"
            )

        if not config:
            return
        queue_id = config.get("skill_queue_id")
        if queue_id is None:
            return
        queue = self.ref.get_skill_queue_by_id(int(queue_id))
        if queue is None:
            raise NotFound(f"技能队列不存在：{queue_id}")
        if queue.tenant_id != tenant_id:
            raise ParamError("技能队列与流程不属于同一租户")

    @staticmethod
    def _validate_condition(
        *, condition_type: IvrConditionType, condition_value: str | None
    ) -> None:
        if condition_type == IvrConditionType.TIME_RANGE:
            if not is_valid_time_range(condition_value):
                raise ParamError(
                    f"时段条件无法解析：{condition_value}，"
                    "格式如 09:00-18:00 或 09:00-12:00,14:00-18:00"
                )
        elif condition_type == IvrConditionType.QUEUE_AVAILABLE:
            if condition_value not in QUEUE_AVAILABLE_TRUE | QUEUE_AVAILABLE_FALSE:
                raise ParamError(
                    f"队列可用性取值非法：{condition_value}（应为 true / false 或留空）"
                )

    def ensure_flow_enabled(self, flow_id: int) -> IvrFlow:
        """供其他服务复用的 IVR 流程可用性校验。"""
        flow = self.get_flow(flow_id)
        if flow.status != CommonStatus.ENABLED:
            raise ParamError("IVR 流程已停用")
        return flow


__all__ = ["TERMINAL_NODE_TYPES", "IvrService"]
