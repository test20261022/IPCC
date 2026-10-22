"""回呼任务状态机（§46 / §77）。

状态与流转集中在此，业务代码禁止散落 `status == xxx` 判断。
"""

from app.core.exceptions import StateNotAllowed
from app.models.outbound.enums import CallbackStatus

#: 允许的流转表（ASSUMPTION-055：需求仅列出状态集合，流转按业务常识收敛）
CALLBACK_TRANSITIONS: dict[CallbackStatus, frozenset[CallbackStatus]] = {
    CallbackStatus.PENDING: frozenset(
        {CallbackStatus.ASSIGNED, CallbackStatus.CANCELLED}
    ),
    CallbackStatus.ASSIGNED: frozenset(
        {
            CallbackStatus.CALLING,
            # 人工回呼允许坐席线下联系客户后直接登记结果，无需经过系统拨号
            CallbackStatus.SUCCESS,
            CallbackStatus.FAILED,
            CallbackStatus.PENDING,
            CallbackStatus.CANCELLED,
        }
    ),
    CallbackStatus.CALLING: frozenset(
        {
            CallbackStatus.SUCCESS,
            CallbackStatus.FAILED,
            CallbackStatus.PENDING,
            CallbackStatus.CANCELLED,
        }
    ),
    # 回呼失败允许退回待回呼重新排队（重呼场景）
    CallbackStatus.FAILED: frozenset({CallbackStatus.PENDING}),
    CallbackStatus.SUCCESS: frozenset(),
    CallbackStatus.CANCELLED: frozenset(),
}

#: 终态：已成功 / 已失败 / 已取消（已失败可通过重呼退回「待回呼」）
FINAL_STATUSES: frozenset[CallbackStatus] = frozenset(
    {CallbackStatus.SUCCESS, CallbackStatus.FAILED, CallbackStatus.CANCELLED}
)

#: 允许派单（分配坐席）的状态
ASSIGNABLE_STATUSES: frozenset[CallbackStatus] = frozenset({CallbackStatus.PENDING})

#: 允许发起呼叫的状态（必须先分配坐席）
CALLABLE_STATUSES: frozenset[CallbackStatus] = frozenset({CallbackStatus.ASSIGNED})

#: 允许取消的状态
CANCELLABLE_STATUSES: frozenset[CallbackStatus] = frozenset(
    {CallbackStatus.PENDING, CallbackStatus.ASSIGNED, CallbackStatus.CALLING}
)

#: 状态中文名，用于拼装给人看的提示信息（同时保留枚举值，便于前端与排障）
_STATUS_LABELS: dict[CallbackStatus, str] = {
    CallbackStatus.PENDING: "待回呼",
    CallbackStatus.ASSIGNED: "已分配",
    CallbackStatus.CALLING: "呼叫中",
    CallbackStatus.SUCCESS: "已成功",
    CallbackStatus.FAILED: "已失败",
    CallbackStatus.CANCELLED: "已取消",
}


def label(status: CallbackStatus) -> str:
    """状态的可读文案，形如「已成功（SUCCESS）」。"""
    return f"{_STATUS_LABELS.get(status, status.value)}（{status.value}）"


def labels(statuses: frozenset[CallbackStatus]) -> str:
    return "、".join(label(item) for item in sorted(statuses, key=lambda i: i.value))


def allowed_targets(current: CallbackStatus) -> list[CallbackStatus]:
    """当前状态可流转到的目标状态。"""
    return sorted(CALLBACK_TRANSITIONS.get(current, frozenset()), key=lambda item: item.value)


def can_transition(current: CallbackStatus, target: CallbackStatus) -> bool:
    """§77：判断是否允许流转。"""
    return target in CALLBACK_TRANSITIONS.get(current, frozenset())


def ensure_transition(current: CallbackStatus, target: CallbackStatus) -> None:
    """不允许的流转抛 40902。"""
    if current == target:
        raise StateNotAllowed(f"回呼任务已处于{label(current)}状态")
    if not can_transition(current, target):
        targets = labels(CALLBACK_TRANSITIONS.get(current, frozenset())) or "无"
        raise StateNotAllowed(
            f"不允许从{label(current)}流转到{label(target)}，当前可流转：{targets}"
        )


def ensure_assignable(current: CallbackStatus) -> None:
    """派单前的状态校验。"""
    if current not in ASSIGNABLE_STATUSES:
        raise StateNotAllowed(
            f"{label(current)}状态不允许派单，可派单状态：{labels(ASSIGNABLE_STATUSES)}"
        )


def ensure_callable(current: CallbackStatus) -> None:
    """发起回呼前的状态校验。"""
    if current not in CALLABLE_STATUSES:
        raise StateNotAllowed(
            f"{label(current)}状态不允许发起回呼，可呼叫状态：{labels(CALLABLE_STATUSES)}"
        )


def ensure_cancellable(current: CallbackStatus) -> None:
    """取消前的状态校验。"""
    if current not in CANCELLABLE_STATUSES:
        raise StateNotAllowed(
            f"{label(current)}状态不允许取消，可取消状态：{labels(CANCELLABLE_STATUSES)}"
        )


__all__ = [
    "ASSIGNABLE_STATUSES",
    "CALLABLE_STATUSES",
    "CALLBACK_TRANSITIONS",
    "CANCELLABLE_STATUSES",
    "FINAL_STATUSES",
    "allowed_targets",
    "can_transition",
    "ensure_assignable",
    "ensure_callable",
    "ensure_cancellable",
    "ensure_transition",
    "label",
    "labels",
]
