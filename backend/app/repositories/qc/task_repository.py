"""质检任务与明细数据访问（含 10 万条分批派发）。

派发核心：分批 `INSERT ... SELECT`（禁止逐行 ORM insert），
- 子查询对 qc_conversations 做 `row_number() over (order by id)` 得到稳定序号 rn；
- 外层按派发模式把 rn 折算为专家下标，再用 CASE 映射为成员用户 id；
- 带 `ON CONFLICT (task_id, conversation_id) WHERE is_deleted = false DO NOTHING` 保证幂等，
  与模型 `uq_qc_task_items_task_conversation` 的部分唯一索引条件字面一致。
"""

import math
from datetime import datetime

from sqlalchemy import Select, case, func, literal, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.qc.conversation import QcConversation
from app.models.qc.enums import QcDispatchMode, QcGrade, QcItemStatus, QcTaskStatus
from app.models.qc.review import QcTask, QcTaskItem

#: 明细表参与 INSERT ... SELECT 的列（顺序与 SELECT 输出一一对应）
_ITEM_INSERT_COLUMNS = [
    "tenant_id",
    "task_id",
    "conversation_id",
    "reviewer_id",
    "status",
    "is_deleted",
    "created_at",
    "updated_at",
]


class QcTaskRepository:
    """质检任务查询、明细查询与分批派发。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 任务 ----------

    def get_by_id(self, task_id: int, tenant_id: int | None = None) -> QcTask | None:
        stmt = select(QcTask).where(QcTask.id == task_id, QcTask.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(QcTask.tenant_id == tenant_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_name(self, tenant_id: int, task_name: str) -> QcTask | None:
        stmt = select(QcTask).where(
            QcTask.tenant_id == tenant_id,
            QcTask.task_name == task_name,
            QcTask.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def _apply_filters(
        stmt: Select,
        *,
        tenant_id: int | None = None,
        status: QcTaskStatus | None = None,
        keyword: str | None = None,
    ) -> Select:
        stmt = stmt.where(QcTask.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(QcTask.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(QcTask.status == status)
        if keyword:
            stmt = stmt.where(QcTask.task_name.ilike(f"%{keyword}%"))
        return stmt

    def list_paged(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        status: QcTaskStatus | None = None,
        keyword: str | None = None,
    ) -> list[QcTask]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(
            select(QcTask), tenant_id=tenant_id, status=status, keyword=keyword
        )
        stmt = stmt.order_by(QcTask.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(
        self,
        *,
        tenant_id: int | None = None,
        status: QcTaskStatus | None = None,
        keyword: str | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(QcTask),
            tenant_id=tenant_id,
            status=status,
            keyword=keyword,
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> QcTask:
        task = QcTask(**values)
        self.db.add(task)
        self.db.flush()
        return task

    # ---------- 明细项查询 ----------

    @staticmethod
    def _apply_item_filters(
        stmt: Select,
        *,
        task_id: int | None = None,
        status: QcItemStatus | None = None,
        reviewer_id: int | None = None,
        grade: QcGrade | None = None,
    ) -> Select:
        stmt = stmt.where(QcTaskItem.is_deleted.is_(False))
        if task_id is not None:
            stmt = stmt.where(QcTaskItem.task_id == task_id)
        if status is not None:
            stmt = stmt.where(QcTaskItem.status == status)
        if reviewer_id is not None:
            stmt = stmt.where(QcTaskItem.reviewer_id == reviewer_id)
        if grade is not None:
            stmt = stmt.where(QcTaskItem.grade == grade)
        return stmt

    def list_items(
        self,
        *,
        page: int,
        page_size: int,
        task_id: int | None = None,
        status: QcItemStatus | None = None,
        reviewer_id: int | None = None,
        grade: QcGrade | None = None,
    ) -> list[QcTaskItem]:
        offset = (page - 1) * page_size
        stmt = self._apply_item_filters(
            select(QcTaskItem),
            task_id=task_id,
            status=status,
            reviewer_id=reviewer_id,
            grade=grade,
        )
        stmt = stmt.order_by(QcTaskItem.id.asc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count_items(
        self,
        *,
        task_id: int | None = None,
        status: QcItemStatus | None = None,
        reviewer_id: int | None = None,
        grade: QcGrade | None = None,
    ) -> int:
        stmt = self._apply_item_filters(
            select(func.count()).select_from(QcTaskItem),
            task_id=task_id,
            status=status,
            reviewer_id=reviewer_id,
            grade=grade,
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_task_items(self, task_id: int) -> int:
        """任务下有效明细数（派发后回填 total_items，不用 rowcount 累加）。"""
        stmt = (
            select(func.count())
            .select_from(QcTaskItem)
            .where(QcTaskItem.task_id == task_id, QcTaskItem.is_deleted.is_(False))
        )
        return int(self.db.execute(stmt).scalar_one())

    def soft_delete_items(self, task_id: int, *, now: datetime) -> int:
        """软删除任务下全部明细（与任务软删除联动）。"""
        stmt = (
            update(QcTaskItem)
            .where(QcTaskItem.task_id == task_id, QcTaskItem.is_deleted.is_(False))
            .values(is_deleted=True, deleted_at=now, updated_at=now)
        )
        return int(self.db.execute(stmt).rowcount or 0)

    # ---------- 任务进度 ----------

    def increment_completed(self, task_id: int, *, now: datetime) -> None:
        """已完成数原子 +1（提交质检结果后调用）。"""
        stmt = (
            update(QcTask)
            .where(QcTask.id == task_id, QcTask.is_deleted.is_(False))
            .values(completed_items=QcTask.completed_items + 1, updated_at=now)
        )
        self.db.execute(stmt)

    def complete_if_done(self, task_id: int, *, now: datetime) -> bool:
        """条件 UPDATE：仅当已完成数追平总数且仍处于进行态时推进为 COMPLETED。"""
        stmt = (
            update(QcTask)
            .where(
                QcTask.id == task_id,
                QcTask.is_deleted.is_(False),
                QcTask.status.in_([QcTaskStatus.DISPATCHED, QcTaskStatus.REVIEWING]),
                QcTask.total_items > 0,
                QcTask.completed_items >= QcTask.total_items,
            )
            .values(status=QcTaskStatus.COMPLETED, finished_at=now, updated_at=now)
        )
        return int(self.db.execute(stmt).rowcount or 0) == 1

    # ---------- 派发 ----------

    def count_conversations(
        self, *, tenant_id: int, time_from: datetime, time_to: datetime
    ) -> int:
        """时间区间内可质检的对话总数（tenant / 未删除 / started_at 闭区间）。"""
        stmt = (
            select(func.count())
            .select_from(QcConversation)
            .where(
                QcConversation.tenant_id == tenant_id,
                QcConversation.is_deleted.is_(False),
                QcConversation.started_at >= time_from,
                QcConversation.started_at <= time_to,
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    @staticmethod
    def _reviewer_case(
        reviewer_idx: ColumnElement, reviewer_ids: list[int]
    ) -> ColumnElement:
        """把分片下标映射为专家用户 id（CASE 表达式，稳定且可读）。"""
        whens = [
            (reviewer_idx == index, reviewer_id)
            for index, reviewer_id in enumerate(reviewer_ids)
        ]
        return case(*whens, else_=reviewer_ids[-1])

    def dispatch_batch(
        self,
        *,
        task_id: int,
        tenant_id: int,
        time_from: datetime,
        time_to: datetime,
        reviewer_ids: list[int],
        dispatch_mode: QcDispatchMode,
        total: int,
        batch_size: int,
    ) -> int:
        """执行一批 `INSERT ... SELECT`，返回本批实际插入行数。

        序号 rn 在「全量对话集合」上计算并保持稳定，因此跨批次的专家分配不会漂移；
        已插入的对话通过 NOT EXISTS 在外层排除（配合 ON CONFLICT 双保险），
        使同一批语句可重复续跑而不重复插入。
        """
        reviewer_count = len(reviewer_ids)
        rn = func.row_number().over(order_by=QcConversation.id.asc()).label("rn")
        ranked = (
            select(QcConversation.id.label("conversation_id"), rn)
            .where(
                QcConversation.tenant_id == tenant_id,
                QcConversation.is_deleted.is_(False),
                QcConversation.started_at >= time_from,
                QcConversation.started_at <= time_to,
            )
            .subquery()
        )

        if dispatch_mode == QcDispatchMode.ROUND_ROBIN:
            reviewer_idx: ColumnElement = (ranked.c.rn - 1) % reviewer_count
        else:
            # 连续均分：chunk = ceil(total / n)，下标 = min(floor((rn - 1) / chunk), n - 1)
            # 注意必须 floor：SQLAlchemy 会把除法结果类型标记为 NUMERIC，直接比较会落到 ELSE。
            chunk = max(1, math.ceil(total / reviewer_count))
            reviewer_idx = func.least(
                func.floor((ranked.c.rn - 1) / chunk), reviewer_count - 1
            )

        inserted = select(QcTaskItem.id).where(
            QcTaskItem.task_id == task_id,
            QcTaskItem.conversation_id == ranked.c.conversation_id,
            QcTaskItem.is_deleted.is_(False),
        )
        source = (
            select(
                literal(tenant_id),
                literal(task_id),
                ranked.c.conversation_id,
                self._reviewer_case(reviewer_idx, reviewer_ids),
                literal(QcItemStatus.PENDING.value),
                literal(False),
                func.now(),
                func.now(),
            )
            .select_from(ranked)
            .where(~inserted.exists())
            .order_by(ranked.c.rn.asc())
            .limit(batch_size)
        )

        stmt = (
            pg_insert(QcTaskItem)
            .from_select(_ITEM_INSERT_COLUMNS, source)
            .on_conflict_do_nothing(
                index_elements=["task_id", "conversation_id"],
                index_where=text("is_deleted = false"),
            )
            # INSERT ... SELECT 的 rowcount 在 psycopg 下不可靠（返回 -1），
            # 故用 RETURNING 取回真实插入行数（冲突未插入的行不会出现在结果中）。
            .returning(QcTaskItem.id)
        )
        result = self.db.execute(stmt)
        return len(result.scalars().all())


__all__ = ["QcTaskRepository"]