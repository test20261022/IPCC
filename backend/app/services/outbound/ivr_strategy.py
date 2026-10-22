"""IVR 外呼策略引擎（OB-017）。

职责（§31 / §32）——全部是可确定性验证的业务逻辑，不依赖 Provider Mock：
1. **有效按键处理**：COLLECT_DTMF 节点消费一次输入（DTMF 按键或 ASR 识别结果），
   按 priority 升序匹配流转条件，命中即跳转，并把按键计入 collected_keys。
2. **非法按键处理**：无任何流转命中（含兜底）时重播本节点提示音，
   重播次数超过节点 max_replay 后挂断。
3. **转人工路由策略**：TRANSFER_AGENT 节点先判断技能队列是否有空闲坐席；
   无可用坐席时按节点配置的 no_agent_action 兜底（§32 禁止硬编码）。
4. 其余流转条件：ASR 识别结果关键字、时段（TIME_RANGE）、队列可用性（QUEUE_AVAILABLE）。

本模块不访问数据库、不提交事务，只做状态推演，便于单测覆盖与接口复用。

ASSUMPTION-050：需求未定义「无条件流转」的表达方式。约定
`condition_type=KEY` 且 `condition_value` 为空或 `*` 即「无条件 / 任意按键」兜底流转：
- 对 PLAY / REPLAY 节点，它表示「播报后无条件进入下一节点」；
- 对 COLLECT_DTMF 节点，它表示「任意按键（含非法按键）都进入该分支」。
ASSUMPTION-051：TRANSFER_AGENT 的兜底动作只由 no_agent_action 决定，
该节点上的出向流转不参与匹配（校验接口会给出提示）。
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.models.outbound.enums import IvrConditionType, IvrNodeType, NoAgentAction

logger = logging.getLogger(__name__)

#: 无条件 / 任意按键的通配写法
WILDCARD = "*"

#: 输入类型
INPUT_KEY = "KEY"
INPUT_ASR = "ASR"

#: 转人工判定为「有可用坐席」的 condition_value 写法
QUEUE_AVAILABLE_TRUE = {None, "", WILDCARD, "true", "TRUE", "1", "yes", "Y"}
#: 转人工判定为「无可用坐席」的 condition_value 写法
QUEUE_AVAILABLE_FALSE = {"false", "FALSE", "0", "no", "N"}

#: 引擎最多推演的步数，防止节点环导致死循环
DEFAULT_MAX_STEPS = 50


# ---------------- 输入 ----------------

@dataclass(frozen=True)
class IvrSimulationInput:
    """一次模拟输入：DTMF 按键（KEY）或语音识别结果（ASR）。"""

    input_type: str
    value: str


@dataclass(frozen=True)
class IvrSimulationContext:
    """模拟运行的环境事实。

    queue_available 由调用方决定：None 表示无法判定（引擎跳过队列条件流转）。
    """

    inputs: tuple[IvrSimulationInput, ...] = ()
    current_time: str | None = None
    queue_available: bool | None = None


# ---------------- 输出 ----------------

@dataclass
class IvrStep:
    """一步推演轨迹（供接口直接序列化）。"""

    index: int
    node_key: str
    node_name: str
    node_type: str
    action: str
    detail: str
    from_node_key: str | None = None
    to_node_key: str | None = None
    condition_type: str | None = None
    condition_value: str | None = None
    replay_count: int = 0


@dataclass
class IvrSimulationResult:
    """IVR 流程推演结果。"""

    entry_node_key: str | None = None
    final_node_key: str | None = None
    ended: bool = True
    transferred: bool = False
    no_agent_action: str | None = None
    collected_keys: list[str] = field(default_factory=list)
    replay_count: int = 0
    end_reason: str = ""
    steps: list[IvrStep] = field(default_factory=list)


# ---------------- 条件判定 ----------------

def _to_minutes(value: str) -> int | None:
    """把 HH:MM 转成分钟数；非法格式返回 None。"""
    text = value.strip()
    if ":" not in text:
        return None
    hour_text, _, minute_text = text.partition(":")
    if not hour_text.isdigit() or not minute_text.isdigit():
        return None
    hour, minute = int(hour_text), int(minute_text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def time_in_range(condition_value: str | None, current_time: str | None) -> bool:
    """判断 current_time 是否落在 condition_value 描述的时段内。

    condition_value 支持多段，用英文逗号分隔，形如 `09:00-12:00,14:00-18:00`。
    跨零点时段（如 `22:00-06:00`）按「或」语义处理。
    """
    if not condition_value or not current_time:
        return False
    now = _to_minutes(current_time)
    if now is None:
        return False

    for segment in condition_value.split(","):
        part = segment.strip()
        if "-" not in part:
            continue
        start_text, _, end_text = part.partition("-")
        start = _to_minutes(start_text)
        end = _to_minutes(end_text)
        if start is None or end is None:
            continue
        if start <= end:
            if start <= now <= end:
                return True
        elif now >= start or now <= end:  # 跨零点
            return True
    return False


def is_valid_time_range(condition_value: str | None) -> bool:
    """校验时段表达式是否合法。

    形如 `09:00-12:00,14:00-18:00`：至少一段，且每段都是合法的 HH:MM-HH:MM。
    """
    if not condition_value:
        return False
    segments = [segment.strip() for segment in condition_value.split(",")]
    if not segments or any(not segment for segment in segments):
        return False
    for segment in segments:
        if "-" not in segment:
            return False
        start_text, _, end_text = segment.partition("-")
        if _to_minutes(start_text) is None or _to_minutes(end_text) is None:
            return False
    return True


def queue_available_matches(
    condition_value: str | None, queue_available: bool | None
) -> bool:
    """队列可用性条件是否命中；queue_available 为 None（无法判定）时不命中。"""
    if queue_available is None:
        return False
    if condition_value in QUEUE_AVAILABLE_TRUE:
        return queue_available is True
    if condition_value in QUEUE_AVAILABLE_FALSE:
        return queue_available is False
    return False


def is_fallback_value(condition_value: str | None) -> bool:
    """是否「无条件 / 任意按键」兜底写法。"""
    return condition_value is None or condition_value.strip() in ("", WILDCARD)


def _edge_matches(
    transition: Any,
    *,
    input_type: str | None,
    input_value: str | None,
    current_time: str | None,
    queue_available: bool | None,
) -> bool:
    """单个流转条件是否命中当前输入与环境事实。"""
    condition_type = transition.condition_type
    condition_value = transition.condition_value

    if condition_type == IvrConditionType.KEY:
        if is_fallback_value(condition_value):
            return True
        # 没有按键输入时（PLAY / REPLAY 节点）具体按键条件不命中
        return input_type == INPUT_KEY and condition_value == input_value

    if condition_type == IvrConditionType.ASR_RESULT:
        if input_type != INPUT_ASR:
            return False
        if is_fallback_value(condition_value):
            return True
        return str(condition_value) in str(input_value or "")

    if condition_type == IvrConditionType.TIME_RANGE:
        return time_in_range(condition_value, current_time)

    if condition_type == IvrConditionType.QUEUE_AVAILABLE:
        return queue_available_matches(condition_value, queue_available)

    return False


def resolve_next(
    transitions: list[Any],
    *,
    input_type: str | None = None,
    input_value: str | None = None,
    current_time: str | None = None,
    queue_available: bool | None = None,
) -> Any | None:
    """按 priority 升序返回第一个命中的流转；全部不命中返回 None。"""
    ordered = sorted(transitions, key=lambda item: (item.priority, item.id))
    for transition in ordered:
        if _edge_matches(
            transition,
            input_type=input_type,
            input_value=input_value,
            current_time=current_time,
            queue_available=queue_available,
        ):
            return transition
    return None


# ---------------- 推演 ----------------

class _Runner:
    """单次推演的内部状态机。"""

    def __init__(
        self,
        *,
        nodes: list[Any],
        transitions: list[Any],
        entry_node_key: str | None,
        context: IvrSimulationContext,
        max_steps: int,
    ) -> None:
        self.nodes_by_key = {node.node_key: node for node in nodes}
        self.nodes_by_id = {node.id: node for node in nodes}
        #: from_node_id -> 该节点的出向流转（保持 priority 升序）
        self.edges: dict[int, list[Any]] = {}
        for transition in transitions:
            self.edges.setdefault(transition.from_node_id, []).append(transition)
        for items in self.edges.values():
            items.sort(key=lambda item: (item.priority, item.id))

        self.entry_node_key = entry_node_key
        self.context = context
        self.max_steps = max_steps
        self.result = IvrSimulationResult(entry_node_key=entry_node_key)
        self.replay_counts: dict[int, int] = {}

    # ---------- 工具 ----------

    def _edges_of(self, node: Any) -> list[Any]:
        return self.edges.get(node.id, [])

    def _add_step(self, node: Any, action: str, detail: str, **extra: Any) -> None:
        step = IvrStep(
            index=len(self.result.steps) + 1,
            node_key=node.node_key,
            node_name=node.name,
            node_type=str(node.node_type),
            action=action,
            detail=detail,
            replay_count=self.replay_counts.get(node.id, 0),
            **extra,
        )
        self.result.steps.append(step)

    def _bump_replay(self, node: Any) -> int:
        count = self.replay_counts.get(node.id, 0) + 1
        self.replay_counts[node.id] = count
        self.result.replay_count = max(self.result.replay_count, count)
        return count

    def _finish(self, node: Any, reason: str) -> None:
        self.result.final_node_key = node.node_key
        self.result.end_reason = reason
        self.result.ended = True

    def _move(self, node: Any, transition: Any, detail: str) -> Any | None:
        """按流转跳转；to_node_id 为空表示流程结束。"""
        target = self.nodes_by_id.get(transition.to_node_id) if transition.to_node_id else None
        self._add_step(
            node,
            "MOVE",
            detail,
            from_node_key=node.node_key,
            to_node_key=target.node_key if target else None,
            condition_type=str(transition.condition_type),
            condition_value=transition.condition_value,
        )
        if target is None:
            self._finish(node, "FLOW_END")
        return target

    # ---------- 主循环 ----------

    def run(self) -> IvrSimulationResult:
        current = self.nodes_by_key.get(self.entry_node_key) if self.entry_node_key else None
        if current is None:
            self.result.end_reason = "ENTRY_NOT_FOUND"
            self.result.final_node_key = None
            return self.result

        pending = list(self.context.inputs)
        steps = 0
        while current is not None:
            steps += 1
            if steps > self.max_steps:
                self._add_step(current, "ABORT", f"推演步数超过上限 {self.max_steps}，终止")
                self._finish(current, "MAX_STEPS")
                break
            current = self._visit(current, pending)

        if self.result.ended and not self.result.final_node_key:
            self.result.final_node_key = self.entry_node_key
        return self.result

    def _visit(self, node: Any, pending: list[IvrSimulationInput]) -> Any | None:
        """处理一个节点；返回下一个节点，None 表示流程结束。"""
        node_type = node.node_type

        if node_type == IvrNodeType.HANGUP:
            self._add_step(node, "HANGUP", "执行挂断")
            self._finish(node, "HANGUP")
            return None

        if node_type == IvrNodeType.CALLBACK:
            self._add_step(node, "CALLBACK", "进入回呼流程（OB-029）")
            self._finish(node, "CALLBACK")
            return None

        if node_type == IvrNodeType.TRANSFER_AGENT:
            return self._visit_transfer(node)

        if node_type == IvrNodeType.REPLAY:
            return self._visit_replay(node)

        if node_type == IvrNodeType.COLLECT_DTMF:
            return self._visit_collect(node, pending)

        # 默认按 PLAY 处理
        return self._visit_play(node)

    def _visit_play(self, node: Any) -> Any | None:
        self._add_step(node, "PLAY", node.content or "（无播报内容）")
        transition = resolve_next(
            self._edges_of(node),
            current_time=self.context.current_time,
            queue_available=self.context.queue_available,
        )
        if transition is None:
            self._add_step(node, "END", "无后续流转，流程结束")
            self._finish(node, "FLOW_END")
            return None
        return self._move(node, transition, "播报完成，按流转进入下一节点")

    def _visit_replay(self, node: Any) -> Any | None:
        count = self._bump_replay(node)
        if count > node.max_replay:
            self._add_step(node, "HANGUP", f"重播次数已达上限 {node.max_replay}，挂断")
            self._finish(node, "HANGUP")
            return None
        self._add_step(node, "REPLAY", f"重播提示音（{count}/{node.max_replay}）")
        transition = resolve_next(
            self._edges_of(node),
            current_time=self.context.current_time,
            queue_available=self.context.queue_available,
        )
        if transition is None:
            self._add_step(node, "END", "重播后无后续流转，流程结束")
            self._finish(node, "FLOW_END")
            return None
        return self._move(node, transition, "重播完成，按流转进入下一节点")

    def _visit_collect(self, node: Any, pending: list[IvrSimulationInput]) -> Any | None:
        if node.content:
            self._add_step(node, "PLAY", node.content)

        if not pending:
            self._add_step(node, "NO_INPUT", "等待输入但无后续模拟输入，流程结束")
            self._finish(node, "NO_INPUT")
            return None

        current_input = pending.pop(0)
        if current_input.input_type == INPUT_KEY:
            self.result.collected_keys.append(current_input.value)

        transition = resolve_next(
            self._edges_of(node),
            input_type=current_input.input_type,
            input_value=current_input.value,
            current_time=self.context.current_time,
            queue_available=self.context.queue_available,
        )
        if transition is None:
            # §31 非法按键：重播本节点，超过 max_replay 后挂断
            label = "按键" if current_input.input_type == INPUT_KEY else "识别结果"
            count = self._bump_replay(node)
            if count > node.max_replay:
                self._add_step(
                    node,
                    "HANGUP",
                    f"{label}「{current_input.value}」无匹配流转，重播已达上限 "
                    f"{node.max_replay} 次，挂断",
                )
                self._finish(node, "HANGUP")
                return None
            self._add_step(
                node,
                "REPLAY",
                f"{label}「{current_input.value}」无匹配流转，重播提示（{count}/{node.max_replay}）",
            )
            return node

        detail = (
            f"{'按键' if current_input.input_type == INPUT_KEY else '识别结果'}"
            f"「{current_input.value}」命中流转"
        )
        return self._move(node, transition, detail)

    def _visit_transfer(self, node: Any) -> Any | None:
        """§32 转人工路由策略：有可用坐席即转接，否则按 no_agent_action 兜底。"""
        if self.context.queue_available is True:
            self._add_step(node, "TRANSFER", "技能队列有可用坐席，转接人工坐席成功")
            self.result.transferred = True
            self._finish(node, "TRANSFERRED")
            return None

        action = node.no_agent_action or NoAgentAction.HANGUP
        self.result.no_agent_action = str(action)
        pending_reason = (
            "无法判定队列可用性（按无可用坐席处理）"
            if self.context.queue_available is None
            else "技能队列无可用坐席"
        )

        if action == NoAgentAction.QUEUE:
            self._add_step(node, "QUEUE", f"{pending_reason}，转入技能队列排队")
            self._finish(node, "QUEUE")
            return None

        if action == NoAgentAction.CALLBACK:
            self._add_step(node, "CALLBACK", f"{pending_reason}，转为回呼任务（OB-029）")
            self._finish(node, "CALLBACK")
            return None

        if action == NoAgentAction.HANGUP:
            self._add_step(node, "HANGUP", f"{pending_reason}，挂断")
            self._finish(node, "HANGUP")
            return None

        if action == NoAgentAction.REPLAY:
            count = self._bump_replay(node)
            if count > node.max_replay:
                self._add_step(
                    node,
                    "HANGUP",
                    f"{pending_reason}，重播已达上限 {node.max_replay} 次，挂断",
                )
                self._finish(node, "HANGUP")
                return None
            self._add_step(
                node, "REPLAY", f"{pending_reason}，重播提示（{count}/{node.max_replay}）"
            )
            return node

        # 兜底：未知动作按挂断处理，避免出现无出口节点
        self._add_step(node, "HANGUP", f"{pending_reason}，兜底动作未识别，挂断")
        self._finish(node, "HANGUP")
        return None


def simulate(
    *,
    nodes: list[Any],
    transitions: list[Any],
    entry_node_key: str | None,
    context: IvrSimulationContext | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> IvrSimulationResult:
    """按流程结构推演一次 IVR 执行过程（OB-017）。

    nodes / transitions 为 ORM 对象列表；引擎只读取属性，不访问数据库、不写库。
    """
    runner = _Runner(
        nodes=nodes,
        transitions=transitions,
        entry_node_key=entry_node_key,
        context=context or IvrSimulationContext(),
        max_steps=max_steps,
    )
    return runner.run()


__all__ = [
    "DEFAULT_MAX_STEPS",
    "INPUT_ASR",
    "INPUT_KEY",
    "IvrSimulationContext",
    "IvrSimulationInput",
    "IvrSimulationResult",
    "IvrStep",
    "is_fallback_value",
    "is_valid_time_range",
    "queue_available_matches",
    "resolve_next",
    "simulate",
    "time_in_range",
]
