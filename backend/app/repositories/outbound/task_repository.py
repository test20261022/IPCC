"""外呼任务数据访问（OB-006 / OB-020）。"""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.outbound import OutboundTask, OutboundTaskNumber
from app.models.outbound.enums import DispatchMode, TaskStatus


class OutboundTaskRepository:
    """任务与任务号码配置查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 任务 ----------

    def get_by_id(self, task_id: int) -> OutboundTask | None:
        stmt = select(OutboundTask).where(
            OutboundTask.id == task_id, OutboundTask.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_name(self, tenant_id: int, task_name: str) -> OutboundTask | None:
        stmt = select(OutboundTask).where(
            OutboundTask.tenant_id == tenant_id,
            OutboundTask.task_name == task_name,
            OutboundTask.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_copied_task(
        self, tenant_id: int, task_name: str, source_task_id: int
    ) -> OutboundTask | None:
        """OB-020 幂等键：同租户下由同一来源任务复制出、且同名的那一条。"""
        stmt = select(OutboundTask).where(
            OutboundTask.tenant_id == tenant_id,
            OutboundTask.task_name == task_name,
            OutboundTask.copied_from_id == source_task_id,
            OutboundTask.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        task_name: str | None = None,
        site_id: int | None = None,
        skill_queue_id: int | None = None,
        type_id: int | None = None,
        scene_id: int | None = None,
        status: TaskStatus | None = None,
        dispatch_mode: DispatchMode | None = None,
    ) -> Select:
        stmt = stmt.where(OutboundTask.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(OutboundTask.tenant_id == tenant_id)
        if task_name:
            stmt = stmt.where(OutboundTask.task_name.ilike(f"%{task_name}%"))
        # OB-006：站点 / 技能队列 / 外呼类型查询条件
        if site_id is not None:
            stmt = stmt.where(OutboundTask.site_id == site_id)
        if skill_queue_id is not None:
            stmt = stmt.where(OutboundTask.skill_queue_id == skill_queue_id)
        if type_id is not None:
            stmt = stmt.where(OutboundTask.type_id == type_id)
        if scene_id is not None:
            stmt = stmt.where(OutboundTask.scene_id == scene_id)
        if status is not None:
            stmt = stmt.where(OutboundTask.status == status)
        if dispatch_mode is not None:
            stmt = stmt.where(OutboundTask.dispatch_mode == dispatch_mode)
        return stmt

    def list_paged(self, *, page: int, page_size: int, **filters: object) -> list[OutboundTask]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(select(OutboundTask), **filters)  # type: ignore[arg-type]
        stmt = stmt.order_by(OutboundTask.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, **filters: object) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(OutboundTask), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> OutboundTask:
        task = OutboundTask(**values)
        self.db.add(task)
        self.db.flush()
        return task

    def list_running_ids(self, *, limit: int = 50) -> list[int]:
        """运行中的任务 ID（定时重试派发用）。"""
        stmt = (
            select(OutboundTask.id)
            .where(
                OutboundTask.is_deleted.is_(False),
                OutboundTask.status == TaskStatus.RUNNING,
            )
            .order_by(OutboundTask.id.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_assignable(
        self, *, tenant_id: int, skill_queue_id: int | None, limit: int = 20
    ) -> list[OutboundTask]:
        """可派单任务（§33）：RUNNING 且派单模式为 AUTO / PREDICTIVE。

        排序维度之一：任务优先级（§34，数值越小越先派单）。
        技能队列为空的「通用任务」也允许派给任意队列的坐席（ASSUMPTION-042）。
        """
        stmt = select(OutboundTask).where(
            OutboundTask.is_deleted.is_(False),
            OutboundTask.tenant_id == tenant_id,
            OutboundTask.status == TaskStatus.RUNNING,
            OutboundTask.dispatch_mode.in_([DispatchMode.AUTO, DispatchMode.PREDICTIVE]),
        )
        if skill_queue_id is not None:
            stmt = stmt.where(
                or_(
                    OutboundTask.skill_queue_id == skill_queue_id,
                    OutboundTask.skill_queue_id.is_(None),
                )
            )
        stmt = stmt.order_by(OutboundTask.priority.asc(), OutboundTask.id.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    # ---------- 任务号码配置 ----------

    def list_task_numbers(self, task_id: int) -> list[OutboundTaskNumber]:
        stmt = (
            select(OutboundTaskNumber)
            .where(
                OutboundTaskNumber.task_id == task_id,
                OutboundTaskNumber.is_deleted.is_(False),
            )
            .order_by(OutboundTaskNumber.sort_order.asc(), OutboundTaskNumber.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_enabled_numbers(self, task_id: int) -> int:
        """启用中的号码数量，进入 READY 前的最小校验依据。"""
        stmt = (
            select(func.count())
            .select_from(OutboundTaskNumber)
            .where(
                OutboundTaskNumber.task_id == task_id,
                OutboundTaskNumber.is_deleted.is_(False),
                OutboundTaskNumber.enabled.is_(True),
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    def soft_delete_task_numbers(self, task_id: int) -> int:
        rows = self.list_task_numbers(task_id)
        for row in rows:
            row.mark_deleted()
        self.db.flush()
        return len(rows)

    def add_task_number(self, **values: object) -> OutboundTaskNumber:
        row = OutboundTaskNumber(**values)
        self.db.add(row)
        self.db.flush()
        return row
