"""外呼任务状态机（§18 / §77）。

状态与流转集中在此，业务代码禁止散落 `status == xxx` 判断；
新增/调整流转只改这一处。
"""

from app.core.exceptions import StateNotAllowed
from app.models.outbound.enums import TaskStatus

#: 允许的流转表（ASSUMPTION-020：需求仅列出状态集合，未定义流转，此处按业务常识收敛）
TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.READY: frozenset(
        {TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.DRAFT, TaskStatus.CANCELLED}
    ),
    TaskStatus.RUNNING: frozenset(
        {TaskStatus.PAUSED, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    ),
    TaskStatus.PAUSED: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

#: 允许删除的状态（ASSUMPTION-019：执行中/就绪/暂停的任务需先取消再删除）
DELETABLE_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.DRAFT, TaskStatus.CANCELLED}
)

#: 允许编辑配置的状态（运行中需先暂停，避免执行期改配置）
EDITABLE_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.DRAFT, TaskStatus.READY, TaskStatus.PAUSED}
)

#: 进入这些状态时写入 finished_at
FINISHED_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
)

#: 状态中文名，用于拼装给人看的提示信息（同时保留枚举值，便于前端与排障）
_STATUS_LABELS: dict[TaskStatus, str] = {
    TaskStatus.DRAFT: "草稿",
    TaskStatus.READY: "就绪",
    TaskStatus.RUNNING: "运行中",
    TaskStatus.PAUSED: "已暂停",
    TaskStatus.COMPLETED: "已完成",
    TaskStatus.CANCELLED: "已取消",
}


def label(status: TaskStatus) -> str:
    """状态的可读文案，形如「运行中（RUNNING）」。"""
    return f"{_STATUS_LABELS.get(status, status.value)}（{status.value}）"


def labels(statuses: frozenset[TaskStatus]) -> str:
    return "、".join(label(item) for item in sorted(statuses, key=lambda i: i.value))


def allowed_targets(current: TaskStatus) -> list[TaskStatus]:
    """当前状态可流转到的目标状态。"""
    return sorted(TASK_TRANSITIONS.get(current, frozenset()), key=lambda item: item.value)


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    """§77：判断是否允许流转。"""
    return target in TASK_TRANSITIONS.get(current, frozenset())


def ensure_transition(current: TaskStatus, target: TaskStatus) -> None:
    """不允许的流转抛 40902。"""
    if current == target:
        raise StateNotAllowed(f"任务已处于{label(current)}状态")
    if not can_transition(current, target):
        targets = labels(TASK_TRANSITIONS.get(current, frozenset())) or "无"
        raise StateNotAllowed(
            f"不允许从{label(current)}流转到{label(target)}，当前可流转：{targets}"
        )


def ensure_editable(current: TaskStatus) -> None:
    """配置类修改前的状态校验。"""
    if current not in EDITABLE_STATUSES:
        raise StateNotAllowed(
            f"{label(current)}状态不允许修改任务配置，可编辑状态：{labels(EDITABLE_STATUSES)}"
        )


def ensure_deletable(current: TaskStatus) -> None:
    """删除前的状态校验。"""
    if current not in DELETABLE_STATUSES:
        raise StateNotAllowed(
            f"{label(current)}状态不允许删除任务，可删除状态：{labels(DELETABLE_STATUSES)}"
        )
