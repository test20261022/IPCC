"""质检明细项状态机。

PENDING 待质检 -> REVIEWING 质检中 -> COMPLETED 已完成；
超时回收将 REVIEWING 退回 PENDING；领取超时后置 TIMEOUT（终态）。
"""

from app.core.exceptions import StateNotAllowed
from app.models.qc.enums import QcItemStatus

#: 允许的流转表
QC_ITEM_TRANSITIONS: dict[QcItemStatus, frozenset[QcItemStatus]] = {
    QcItemStatus.PENDING: frozenset({QcItemStatus.REVIEWING, QcItemStatus.TIMEOUT}),
    QcItemStatus.REVIEWING: frozenset({QcItemStatus.COMPLETED, QcItemStatus.PENDING}),
    QcItemStatus.COMPLETED: frozenset(),
    QcItemStatus.TIMEOUT: frozenset(),
}

#: 状态中文名，用于拼装提示信息
_STATUS_LABELS: dict[QcItemStatus, str] = {
    QcItemStatus.PENDING: "待质检",
    QcItemStatus.REVIEWING: "质检中",
    QcItemStatus.COMPLETED: "已完成",
    QcItemStatus.TIMEOUT: "已超时",
}


def label(status: QcItemStatus) -> str:
    """状态的可读文案，形如「质检中（REVIEWING）」。"""
    return f"{_STATUS_LABELS.get(status, status.value)}（{status.value}）"


def labels(statuses: frozenset[QcItemStatus]) -> str:
    return "、".join(label(item) for item in sorted(statuses, key=lambda i: i.value))


def can_transition(current: QcItemStatus, target: QcItemStatus) -> bool:
    """判断是否允许流转。"""
    return target in QC_ITEM_TRANSITIONS.get(current, frozenset())


def ensure_item_transition(current: QcItemStatus, target: QcItemStatus) -> None:
    """不允许的流转抛 40902。"""
    if current == target:
        raise StateNotAllowed(f"明细已处于{label(current)}状态")
    if not can_transition(current, target):
        targets = labels(QC_ITEM_TRANSITIONS.get(current, frozenset())) or "无"
        raise StateNotAllowed(
            f"不允许从{label(current)}流转到{label(target)}，当前可流转：{targets}"
        )


__all__ = [
    "QC_ITEM_TRANSITIONS",
    "can_transition",
    "ensure_item_transition",
    "label",
    "labels",
]