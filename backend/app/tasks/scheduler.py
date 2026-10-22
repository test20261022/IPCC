"""APScheduler 定时任务（§22 超时回收 / §21 重试派发）。

MVP 为单机调度（§76 不做分布式调度）；多实例部署时需叠加分布式锁或独立 worker。
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.session import session_scope
from app.services.outbound.assignment_service import OutboundAssignmentService
from app.services.outbound.callback_service import CallbackService
from app.services.outbound.execution_service import OutboundExecutionService
from app.services.outbound.timeout_service import OutboundTimeoutService
from app.services.qc.review_service import QcReviewService

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _timeout_recycle_job() -> None:
    """扫描超时记录并回收（§22）。"""
    with session_scope() as db:
        try:
            OutboundTimeoutService(db).recycle()
        except Exception:  # noqa: BLE001 - 定时任务不允许因单次异常退出
            logger.exception("超时回收任务执行失败")


def _retry_dispatch_job() -> None:
    """扫描到期的重试记录并重新执行（§21）。"""
    with session_scope() as db:
        try:
            OutboundExecutionService(db).execute_due_retries()
        except Exception:  # noqa: BLE001
            logger.exception("重试派发任务执行失败")


def _reservation_expire_job() -> None:
    """释放已过期的坐席预占（§35）。"""
    with session_scope() as db:
        try:
            OutboundAssignmentService(db).expire_reservations()
        except Exception:  # noqa: BLE001
            logger.exception("预占超时释放任务执行失败")


def _callback_dispatch_job() -> None:
    """扫描到期回呼任务并派单（§46）。"""
    with session_scope() as db:
        try:
            CallbackService(db).dispatch_due(limit=settings.CALLBACK_DISPATCH_BATCH_SIZE)
        except Exception:  # noqa: BLE001
            logger.exception("到期回呼派单任务执行失败")


def _qc_item_recycle_job() -> None:
    """回收质检中已超时的明细项，退回待质检（质检模块）。"""
    with session_scope() as db:
        try:
            QcReviewService(db).recycle_timeout_items()
        except Exception:  # noqa: BLE001
            logger.exception("质检超时回收任务执行失败")


def start_scheduler() -> BackgroundScheduler | None:
    """启动定时任务；已启动或显式关闭时返回 None。"""
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("定时任务未启用（SCHEDULER_ENABLED=false）")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _timeout_recycle_job,
        "interval",
        seconds=settings.TIMEOUT_RECYCLE_INTERVAL_SECONDS,
        id="timeout_recycle",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _retry_dispatch_job,
        "interval",
        seconds=settings.RETRY_DISPATCH_INTERVAL_SECONDS,
        id="retry_dispatch",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _reservation_expire_job,
        "interval",
        seconds=settings.RESERVATION_EXPIRE_INTERVAL_SECONDS,
        id="reservation_expire",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _callback_dispatch_job,
        "interval",
        seconds=settings.CALLBACK_DISPATCH_INTERVAL_SECONDS,
        id="callback_dispatch",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _qc_item_recycle_job,
        "interval",
        seconds=settings.QC_ITEM_RECYCLE_INTERVAL_SECONDS,
        id="qc_item_recycle",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "定时任务已启动：超时回收每 %ss，重试派发每 %ss，预占释放每 %ss，回呼派单每 %ss，"
        "质检明细回收每 %ss",
        settings.TIMEOUT_RECYCLE_INTERVAL_SECONDS,
        settings.RETRY_DISPATCH_INTERVAL_SECONDS,
        settings.RESERVATION_EXPIRE_INTERVAL_SECONDS,
        settings.CALLBACK_DISPATCH_INTERVAL_SECONDS,
        settings.QC_ITEM_RECYCLE_INTERVAL_SECONDS,
    )
    return scheduler


def shutdown_scheduler() -> None:
    """停止定时任务（应用关闭时调用）。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("定时任务已停止")
