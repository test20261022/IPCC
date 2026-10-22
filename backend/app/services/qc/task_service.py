"""质检任务服务：任务维护、分批派发、取消与明细查询。

派发是本模块的核心：按「专家组启用成员数」把时间区间内的对话分片，
分批 `INSERT ... SELECT`（每批提交一次），最后回填 total_items 并推进状态。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import Conflict, NotFound, ParamError
from app.models.qc.enums import QcGrade, QcItemStatus, QcTaskStatus
from app.models.qc.review import QcTask
from app.repositories.qc.reviewer_repository import QcReviewerGroupRepository
from app.repositories.qc.task_repository import QcTaskRepository
from app.schemas.qc.review import QcTaskCreate, QcTaskUpdate
from app.services.outbound.common import ensure_tenant_active
from app.services.qc import task_state
from app.services.qc.report_service import QcReportService

logger = logging.getLogger(__name__)


class QcTaskService:
    """质检任务业务。事务在本层提交（派发为批间提交）。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = QcTaskRepository(db)
        self.group_repo = QcReviewerGroupRepository(db)

    # ---------- 查询 ----------

    def list_tasks(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        status: QcTaskStatus | None = None,
        keyword: str | None = None,
    ) -> tuple[list[QcTask], int]:
        items = self.repo.list_paged(
            page=page, page_size=page_size, tenant_id=tenant_id, status=status, keyword=keyword
        )
        total = self.repo.count(tenant_id=tenant_id, status=status, keyword=keyword)
        return items, total

    def get_task(self, task_id: int) -> QcTask:
        task = self.repo.get_by_id(task_id)
        if task is None:
            raise NotFound("质检任务不存在")
        return task

    def get_task_detail(self, task_id: int) -> dict:
        task = self.get_task(task_id)
        return {
            **self._task_dict(task),
            "completion_rate": self._completion_rate(task.completed_items, task.total_items),
        }

    def list_items(
        self,
        *,
        task_id: int,
        page: int,
        page_size: int,
        status: QcItemStatus | None = None,
        reviewer_id: int | None = None,
        grade: QcGrade | None = None,
    ) -> tuple[list, int]:
        self.get_task(task_id)
        items = self.repo.list_items(
            page=page,
            page_size=page_size,
            task_id=task_id,
            status=status,
            reviewer_id=reviewer_id,
            grade=grade,
        )
        total = self.repo.count_items(
            task_id=task_id, status=status, reviewer_id=reviewer_id, grade=grade
        )
        return items, total

    def task_report(self, task_id: int) -> dict:
        """任务级报表：与 /qc/reports/overview 同口径。"""
        task = self.get_task(task_id)
        return QcReportService(self.db).overview(task_id=task.id)

    # ---------- 新增 / 编辑 / 删除 ----------

    def create_task(self, payload: QcTaskCreate) -> QcTask:
        ensure_tenant_active(self.db, payload.tenant_id)
        self._ensure_time_range(payload.time_from, payload.time_to)
        self._ensure_group(payload.tenant_id, payload.group_id)

        if self.repo.get_by_name(payload.tenant_id, payload.task_name) is not None:
            raise Conflict(f"任务名称已存在：{payload.task_name}")

        task = self.repo.create(
            tenant_id=payload.tenant_id,
            task_name=payload.task_name,
            group_id=payload.group_id,
            time_from=payload.time_from,
            time_to=payload.time_to,
            dispatch_mode=payload.dispatch_mode,
            status=QcTaskStatus.DRAFT,
        )
        self.db.commit()
        logger.info("创建质检任务成功：id=%s name=%s", task.id, task.task_name)
        return task

    def update_task(self, task_id: int, payload: QcTaskUpdate) -> QcTask:
        task = self.get_task(task_id)
        task_state.ensure_editable(task.status)

        # 只更新显式传入且非空字段（None 视为未提供，避免把 NOT NULL 列清空）
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            return task

        if "task_name" in changes and changes["task_name"] != task.task_name:
            if self.repo.get_by_name(task.tenant_id, str(changes["task_name"])) is not None:
                raise Conflict(f"任务名称已存在：{changes['task_name']}")
        if "group_id" in changes and changes["group_id"] is not None:
            self._ensure_group(task.tenant_id, int(changes["group_id"]))

        time_from = changes.get("time_from", task.time_from)
        time_to = changes.get("time_to", task.time_to)
        self._ensure_time_range(time_from, time_to)

        for field, value in changes.items():
            setattr(task, field, value)
        self.db.commit()
        logger.info("更新质检任务成功：id=%s fields=%s", task_id, sorted(changes))
        return task

    def delete_task(self, task_id: int) -> dict:
        task = self.get_task(task_id)
        task_state.ensure_deletable(task.status)

        now = datetime.now(timezone.utc)
        removed_items = self.repo.soft_delete_items(task_id, now=now)
        task.mark_deleted()
        self.db.commit()
        logger.info("删除质检任务成功：id=%s 联动软删明细=%s", task_id, removed_items)
        return {"task_id": task_id, "removed_items": removed_items}

    # ---------- 取消 ----------

    def cancel_task(self, task_id: int) -> QcTask:
        task = self.get_task(task_id)
        task_state.ensure_transition(task.status, QcTaskStatus.CANCELLED)

        task.status = QcTaskStatus.CANCELLED
        task.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.info("取消质检任务：id=%s", task_id)
        return task

    # ---------- 派发 ----------

    def dispatch(self, task_id: int) -> dict:
        """把时间区间内的对话分批派发给专家组启用成员。

        分批提交避免 10 万行单事务长时间持锁；已插入的对话由 NOT EXISTS + ON CONFLICT
        双重兜底，中断后可重复调用续跑（此时任务仍为 DRAFT）。
        """
        task = self.get_task(task_id)
        task_state.ensure_transition(task.status, QcTaskStatus.DISPATCHED)
        if task.group_id is None:
            raise ParamError("任务未绑定专家组")
        self._ensure_group(task.tenant_id, task.group_id)

        reviewer_ids = sorted(
            {member.user_id for member in self.group_repo.list_active_members(task.group_id)}
        )
        reviewer_count = len(reviewer_ids)
        if reviewer_count == 0:
            raise ParamError("专家组没有可用成员")

        total = self.repo.count_conversations(
            tenant_id=task.tenant_id, time_from=task.time_from, time_to=task.time_to
        )
        if total == 0:
            raise ParamError("时间区间内没有可质检的对话")

        capacity = reviewer_count * settings.QC_MAX_PER_REVIEWER
        if total > capacity:
            raise ParamError(
                f"时间区间内共 {total} 条对话，超过 {reviewer_count} 位专家单任务上限 "
                f"{capacity} 条，请拆批派发或缩小时间区间"
            )

        batch_size = settings.QC_DISPATCH_BATCH_SIZE
        while True:
            inserted = self.repo.dispatch_batch(
                task_id=task.id,
                tenant_id=task.tenant_id,
                time_from=task.time_from,
                time_to=task.time_to,
                reviewer_ids=reviewer_ids,
                dispatch_mode=task.dispatch_mode,
                total=total,
                batch_size=batch_size,
            )
            if inserted <= 0:
                break
            self.db.commit()

        now = datetime.now(timezone.utc)
        task.total_items = self.repo.count_task_items(task.id)
        task.status = QcTaskStatus.DISPATCHED
        task.dispatched_at = now
        self.db.commit()
        logger.info(
            "派发质检任务：id=%s total=%s reviewers=%s mode=%s",
            task.id,
            task.total_items,
            reviewer_count,
            task.dispatch_mode.value,
        )
        return {
            "task_id": task.id,
            "total_items": task.total_items,
            "dispatched_at": task.dispatched_at,
            "reviewer_count": reviewer_count,
        }

    # ---------- 内部 ----------

    def _ensure_group(self, tenant_id: int, group_id: int) -> None:
        group = self.group_repo.get_by_id(group_id)
        if group is None:
            raise NotFound("专家组不存在")
        if group.tenant_id != tenant_id:
            raise ParamError("专家组与任务不属于同一租户")

    @staticmethod
    def _ensure_time_range(time_from: datetime, time_to: datetime) -> None:
        if time_from > time_to:
            raise ParamError("时间区间非法：起始时间不能晚于结束时间")

    @staticmethod
    def _completion_rate(completed: int, total: int) -> float:
        return round(completed / total, 4) if total else 0.0

    @staticmethod
    def _task_dict(task: QcTask) -> dict:
        return {
            "id": task.id,
            "tenant_id": task.tenant_id,
            "task_name": task.task_name,
            "group_id": task.group_id,
            "time_from": task.time_from,
            "time_to": task.time_to,
            "status": task.status,
            "dispatch_mode": task.dispatch_mode,
            "total_items": task.total_items,
            "completed_items": task.completed_items,
            "dispatched_at": task.dispatched_at,
            "finished_at": task.finished_at,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }


__all__ = ["QcTaskService"]