"""任务进度收尾：全部名单到终态后自动完成任务（ASSUMPTION-057）。

规则（规则 2「任务成功定义」的确认结果）：
- 任务下**所有执行记录都进入终态**时，任务自动由 RUNNING 流转为 COMPLETED；
- 尚未生成任何执行记录时不自动完成（避免刚建好的任务被误判为已完成）；
- 只在 RUNNING 下自动完成，与 task_state 的流转表保持一致（PAUSED → COMPLETED 不被允许，
  暂停中的任务由人工恢复或取消）。

终态定义复用 retry_policy.TERMINAL_STATUSES，避免两处口径分叉。
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.outbound import OutboundTask
from app.models.outbound.enums import RecordStatus, TaskStatus
from app.repositories.outbound.record_repository import OutboundRecordRepository
from app.services.outbound.retry_policy import TERMINAL_STATUSES

#: 未到终态的执行记录状态
UNFINISHED_STATUSES: tuple[RecordStatus, ...] = tuple(
    status for status in RecordStatus if status not in TERMINAL_STATUSES
)


def maybe_complete_task(
    db: Session, task: OutboundTask, *, now: datetime | None = None
) -> bool:
    """所有执行记录都到终态时把任务置为 COMPLETED；返回是否发生了流转。

    调用方负责提交事务（与执行/回收同事务，避免出现「记录已终态但任务没完成」的中间态）。
    """
    if task.status != TaskStatus.RUNNING:
        return False

    repo = OutboundRecordRepository(db)
    if repo.count(task_id=task.id) == 0:
        return False
    if repo.count(task_id=task.id, statuses=UNFINISHED_STATUSES) > 0:
        return False

    task.status = TaskStatus.COMPLETED
    task.finished_at = now or datetime.now(timezone.utc)
    return True


__all__ = ["UNFINISHED_STATUSES", "maybe_complete_task"]
