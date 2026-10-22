"""失败重试阶梯（§20 / §21 / §22 共用，避免执行与回收两处各写一份）。

阶梯规则（ASSUMPTION-033）：
- 永久性失败（如无可呼叫号码）或任务未配置重试（max_retry_count <= 0）→ FAILED；
- 还有重试机会（retry_count < max_retry_count）→ RETRY_WAITING + next_retry_at；
- 否则 → EXHAUSTED（重试已耗尽）。

调用方需先完成 retry_count 自增。
"""

from datetime import datetime, timedelta

from app.models.outbound import OutboundList, OutboundRecord, OutboundTask
from app.models.outbound.enums import ListStatus, RecordStatus

#: 终态（不再重试）
TERMINAL_STATUSES = frozenset(
    {
        RecordStatus.SUCCESS,
        RecordStatus.FAILED,
        RecordStatus.EXHAUSTED,
        RecordStatus.TIMEOUT,
    }
)


def can_retry(record: OutboundRecord, task: OutboundTask) -> bool:
    """任务配置了重试且尚未用尽。"""
    return task.max_retry_count > 0 and record.retry_count < task.max_retry_count


def schedule_retry(record: OutboundRecord, task: OutboundTask, *, now: datetime) -> None:
    """进入重试等待，并写入下次可执行时间（§21 失败后按 retry_interval 重试）。"""
    record.status = RecordStatus.RETRY_WAITING
    record.next_retry_at = now + timedelta(seconds=max(task.retry_interval, 0))


def mark_terminal(record: OutboundRecord, status: RecordStatus) -> None:
    """置为终态并清掉待重试时间。"""
    record.status = status
    record.next_retry_at = None


def apply_failure_ladder(
    record: OutboundRecord, task: OutboundTask, *, now: datetime, permanent: bool = False
) -> RecordStatus:
    """执行流程的失败收尾：按阶梯写入状态并返回最终状态。"""
    if permanent or task.max_retry_count <= 0:
        mark_terminal(record, RecordStatus.FAILED)
    elif can_retry(record, task):
        schedule_retry(record, task, now=now)
    else:
        mark_terminal(record, RecordStatus.EXHAUSTED)
    return record.status


def sync_name_list_status(
    name_list: OutboundList | None, record_status: RecordStatus
) -> None:
    """名单行状态跟随执行记录汇总。"""
    if name_list is None:
        return
    if record_status == RecordStatus.SUCCESS:
        name_list.status = ListStatus.SUCCESS
    elif record_status in TERMINAL_STATUSES:
        name_list.status = ListStatus.EXHAUSTED
    elif record_status in (RecordStatus.ASSIGNED, RecordStatus.CALLING):
        name_list.status = ListStatus.PROCESSING
    else:
        name_list.status = ListStatus.PENDING
