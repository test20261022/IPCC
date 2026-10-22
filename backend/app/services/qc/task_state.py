"""质检任务状态机。

状态与流转集中在此，业务代码禁止散落 `status == xxx` 判断；
新增/调整流转只改这一处。
"""

from app.core.exceptions import StateNotAllowed
from app.models.qc.enums import QcTaskStatus

#: 允许的流转表：草稿 -> 已派发 -> 质检中 -> 已完成；任意未终态均可取消。
#: 说明：明细提交完最后一单时由条件 UPDATE 把任务从 DISPATCHED / REVIEWING 直接置为
#: COMPLETED（原子更新，不做「先查后改」），因此 DISPATCHED 也必须允许流转到 COMPLETED。
QC_TASK_TRANSITIONS: dict[QcTaskStatus, frozenset[QcTaskStatus]] = {
    QcTaskStatus.DRAFT: frozenset({QcTaskStatus.DISPATCHED, QcTaskStatus.CANCELLED}),
    QcTaskStatus.DISPATCHED: frozenset(
        {QcTaskStatus.REVIEWING, QcTaskStatus.COMPLETED, QcTaskStatus.CANCELLED}
    ),
    QcTaskStatus.REVIEWING: frozenset({QcTaskStatus.COMPLETED, QcTaskStatus.CANCELLED}),
    QcTaskStatus.COMPLETED: frozenset(),
    QcTaskStatus.CANCELLED: frozenset(),
}

#: 允许编辑配置的状态（派发后配置冻结，避免明细与区间不一致）
EDITABLE_STATUSES: frozenset[QcTaskStatus] = frozenset({QcTaskStatus.DRAFT})

#: 允许删除的状态
DELETABLE_STATUSES: frozenset[QcTaskStatus] = frozenset(
    {QcTaskStatus.DRAFT, QcTaskStatus.CANCELLED}
)

#: 进入这些状态时写入 finished_at
FINISHED_STATUSES: frozenset[QcTaskStatus] = frozenset(
    {QcTaskStatus.COMPLETED, QcTaskStatus.CANCELLED}
)

#: 状态中文名，用于拼装给人看的提示信息（同时保留枚举值，便于前端与排障）
_STATUS_LABELS: dict[QcTaskStatus, str] = {
    QcTaskStatus.DRAFT: "草稿",
    QcTaskStatus.DISPATCHED: "已派发",
    QcTaskStatus.REVIEWING: "质检中",
    QcTaskStatus.COMPLETED: "已完成",
    QcTaskStatus.CANCELLED: "已取消",
}


def label(status: QcTaskStatus) -> str:
    """状态的可读文案，形如「已派发（DISPATCHED）」。"""
    return f"{_STATUS_LABELS.get(status, status.value)}（{status.value}）"


def labels(statuses: frozenset[QcTaskStatus]) -> str:
    return "、".join(label(item) for item in sorted(statuses, key=lambda i: i.value))


def allowed_targets(current: QcTaskStatus) -> list[QcTaskStatus]:
    """当前状态可流转到的目标状态。"""
    return sorted(QC_TASK_TRANSITIONS.get(current, frozenset()), key=lambda item: item.value)


def can_transition(current: QcTaskStatus, target: QcTaskStatus) -> bool:
    """判断是否允许流转。"""
    return target in QC_TASK_TRANSITIONS.get(current, frozenset())


def ensure_transition(current: QcTaskStatus, target: QcTaskStatus) -> None:
    """不允许的流转抛 40902。"""
    if current == target:
        raise StateNotAllowed(f"任务已处于{label(current)}状态")
    if not can_transition(current, target):
        targets = labels(QC_TASK_TRANSITIONS.get(current, frozenset())) or "无"
        raise StateNotAllowed(
            f"不允许从{label(current)}流转到{label(target)}，当前可流转：{targets}"
        )


def ensure_editable(current: QcTaskStatus) -> None:
    """配置类修改前的状态校验。"""
    if current not in EDITABLE_STATUSES:
        raise StateNotAllowed(
            f"{label(current)}状态不允许修改任务配置，可编辑状态：{labels(EDITABLE_STATUSES)}"
        )


def ensure_deletable(current: QcTaskStatus) -> None:
    """删除前的状态校验。"""
    if current not in DELETABLE_STATUSES:
        raise StateNotAllowed(
            f"{label(current)}状态不允许删除任务，可删除状态：{labels(DELETABLE_STATUSES)}"
        )


__all__ = [
    "DELETABLE_STATUSES",
    "EDITABLE_STATUSES",
    "FINISHED_STATUSES",
    "QC_TASK_TRANSITIONS",
    "allowed_targets",
    "can_transition",
    "ensure_deletable",
    "ensure_editable",
    "ensure_transition",
    "label",
    "labels",
]