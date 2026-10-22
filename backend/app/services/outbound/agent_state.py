"""坐席状态机（§11 / §77）。

状态流转集中在此，业务代码禁止散落 `status == xxx` 判断。
所有状态变化都必须写 AgentStatusLog（由 AgentService 统一负责）。
"""

from app.core.exceptions import StateNotAllowed
from app.models.outbound.enums import AgentStatus

#: 允许的流转表（ASSUMPTION-041）
#: §11 只给出了主链路，这里补齐「释放预占 / 直接人工呼叫」两条必需边，否则坐席无法回到空闲。
AGENT_TRANSITIONS: dict[AgentStatus, frozenset[AgentStatus]] = {
    AgentStatus.OFFLINE: frozenset({AgentStatus.IDLE}),
    AgentStatus.IDLE: frozenset(
        {AgentStatus.RESERVED, AgentStatus.BUSY, AgentStatus.PAUSED, AgentStatus.OFFLINE}
    ),
    AgentStatus.RESERVED: frozenset(
        {AgentStatus.BUSY, AgentStatus.IDLE, AgentStatus.OFFLINE}
    ),
    AgentStatus.BUSY: frozenset({AgentStatus.IDLE, AgentStatus.PAUSED}),
    AgentStatus.PAUSED: frozenset({AgentStatus.IDLE}),
}

_STATUS_LABELS: dict[AgentStatus, str] = {
    AgentStatus.OFFLINE: "离线",
    AgentStatus.IDLE: "空闲",
    AgentStatus.BUSY: "忙碌",
    AgentStatus.RESERVED: "预占",
    AgentStatus.PAUSED: "小休",
}


def label(status: AgentStatus) -> str:
    """状态可读文案，形如「空闲（IDLE）」。"""
    return f"{_STATUS_LABELS.get(status, status.value)}（{status.value}）"


def labels(statuses: frozenset[AgentStatus]) -> str:
    return "、".join(label(item) for item in sorted(statuses, key=lambda i: i.value))


def allowed_targets(current: AgentStatus) -> list[AgentStatus]:
    return sorted(AGENT_TRANSITIONS.get(current, frozenset()), key=lambda item: item.value)


def can_transition(current: AgentStatus, target: AgentStatus) -> bool:
    """§77：判断是否允许流转。"""
    return target in AGENT_TRANSITIONS.get(current, frozenset())


def ensure_transition(current: AgentStatus, target: AgentStatus) -> None:
    """非法流转抛 40902（§11 明确要求 OFFLINE → BUSY 必须拒绝）。"""
    if current == target:
        raise StateNotAllowed(f"坐席已处于{label(current)}状态")
    if not can_transition(current, target):
        targets = labels(AGENT_TRANSITIONS.get(current, frozenset())) or "无"
        raise StateNotAllowed(
            f"不允许从{label(current)}流转到{label(target)}，当前可流转：{targets}"
        )
