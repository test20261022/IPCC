"""质检明细项数据访问（执行域）。

领取 / 释放 / 提交一律走带状态条件的原子 UPDATE（禁止先查后改），
以 `rowcount == 1` 判定成功，天然规避并发重复领取与重复提交。
"""

from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.qc.conversation import QcConversation, QcMessage
from app.models.qc.enums import QcGrade, QcItemStatus
from app.models.qc.review import QcReviewResult, QcTaskItem


class QcTaskItemRepository:
    """明细项查询、领取 / 释放 / 提交与超时回收。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 查询 ----------

    def get_by_id(self, item_id: int, tenant_id: int | None = None) -> QcTaskItem | None:
        stmt = select(QcTaskItem).where(
            QcTaskItem.id == item_id, QcTaskItem.is_deleted.is_(False)
        )
        if tenant_id is not None:
            stmt = stmt.where(QcTaskItem.tenant_id == tenant_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_conversation(self, conversation_id: int) -> QcConversation | None:
        stmt = select(QcConversation).where(
            QcConversation.id == conversation_id, QcConversation.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_messages(self, conversation_id: int) -> list[QcMessage]:
        """对话消息按 seq 升序（对话消息 append-only，不做软删除）。"""
        stmt = (
            select(QcMessage)
            .where(QcMessage.conversation_id == conversation_id)
            .order_by(QcMessage.seq.asc(), QcMessage.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    @staticmethod
    def _apply_my_filters(
        stmt,
        *,
        reviewer_id: int,
        tenant_id: int | None = None,
        status: QcItemStatus | None = None,
    ):
        stmt = stmt.where(
            QcTaskItem.is_deleted.is_(False), QcTaskItem.reviewer_id == reviewer_id
        )
        if tenant_id is not None:
            stmt = stmt.where(QcTaskItem.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(QcTaskItem.status == status)
        return stmt

    def list_my_items(
        self,
        *,
        page: int,
        page_size: int,
        reviewer_id: int,
        tenant_id: int | None = None,
        status: QcItemStatus | None = None,
    ) -> list[QcTaskItem]:
        offset = (page - 1) * page_size
        stmt = self._apply_my_filters(
            select(QcTaskItem), reviewer_id=reviewer_id, tenant_id=tenant_id, status=status
        )
        stmt = stmt.order_by(QcTaskItem.id.asc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count_my_items(
        self,
        *,
        reviewer_id: int,
        tenant_id: int | None = None,
        status: QcItemStatus | None = None,
    ) -> int:
        stmt = self._apply_my_filters(
            select(func.count()).select_from(QcTaskItem),
            reviewer_id=reviewer_id,
            tenant_id=tenant_id,
            status=status,
        )
        return int(self.db.execute(stmt).scalar_one())

    # ---------- 领取 / 释放 / 提交（原子 UPDATE）----------

    def claim(
        self,
        item_id: int,
        *,
        reviewer_id: int,
        now: datetime,
        timeout_at: datetime,
    ) -> bool:
        """乐观锁领取：仅 PENDING 可被领取；返回是否命中（rowcount == 1）。"""
        stmt = (
            update(QcTaskItem)
            .where(
                QcTaskItem.id == item_id,
                QcTaskItem.is_deleted.is_(False),
                QcTaskItem.status == QcItemStatus.PENDING,
            )
            .values(
                status=QcItemStatus.REVIEWING,
                reviewer_id=reviewer_id,
                locked_at=now,
                timeout_at=timeout_at,
                updated_at=now,
            )
        )
        return int(self.db.execute(stmt).rowcount or 0) == 1

    def release(self, item_id: int, *, reviewer_id: int, now: datetime) -> bool:
        """释放回 PENDING：仅本人持有的 REVIEWING 明细可释放。"""
        stmt = (
            update(QcTaskItem)
            .where(
                QcTaskItem.id == item_id,
                QcTaskItem.is_deleted.is_(False),
                QcTaskItem.status == QcItemStatus.REVIEWING,
                QcTaskItem.reviewer_id == reviewer_id,
            )
            .values(
                status=QcItemStatus.PENDING,
                locked_at=None,
                timeout_at=None,
                updated_at=now,
            )
        )
        return int(self.db.execute(stmt).rowcount or 0) == 1

    def submit_item(
        self,
        item_id: int,
        *,
        reviewer_id: int,
        grade: QcGrade,
        now: datetime,
    ) -> bool:
        """条件 UPDATE 明细为 COMPLETED，写回 grade 与 submitted_at。"""
        stmt = (
            update(QcTaskItem)
            .where(
                QcTaskItem.id == item_id,
                QcTaskItem.is_deleted.is_(False),
                QcTaskItem.status == QcItemStatus.REVIEWING,
                QcTaskItem.reviewer_id == reviewer_id,
            )
            .values(
                status=QcItemStatus.COMPLETED,
                grade=grade,
                submitted_at=now,
                locked_at=None,
                timeout_at=None,
                updated_at=now,
            )
        )
        return int(self.db.execute(stmt).rowcount or 0) == 1

    def insert_result(self, **values: object) -> bool:
        """落库评分结果；命中 `uq_qc_review_results_item` 冲突则返回 False（重复提交）。"""
        stmt = (
            pg_insert(QcReviewResult)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["item_id"], index_where=text("is_deleted = false")
            )
            # INSERT 的 rowcount 在 psycopg 下不可靠（返回 -1），用 RETURNING 判定是否真正插入
            .returning(QcReviewResult.id)
        )
        return len(self.db.execute(stmt).scalars().all()) == 1

    # ---------- 超时回收 ----------

    def list_timeout_items(self, *, now: datetime, limit: int) -> list[int]:
        """扫描超时未提交的明细 id（REVIEWING 且 timeout_at 已过）。"""
        stmt = (
            select(QcTaskItem.id)
            .where(
                QcTaskItem.is_deleted.is_(False),
                QcTaskItem.status == QcItemStatus.REVIEWING,
                QcTaskItem.timeout_at.is_not(None),
                QcTaskItem.timeout_at < now,
            )
            .order_by(QcTaskItem.timeout_at.asc(), QcTaskItem.id.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def recycle(self, item_id: int, *, now: datetime) -> bool:
        """行锁 + 锁内复核，把超时明细退回 PENDING（幂等，reviewer_id 保持不变）。"""
        stmt = (
            select(QcTaskItem)
            .where(QcTaskItem.id == item_id, QcTaskItem.is_deleted.is_(False))
            .with_for_update()
        )
        item = self.db.execute(stmt).scalar_one_or_none()
        if item is None:
            return False
        if item.status != QcItemStatus.REVIEWING:
            return False
        if item.timeout_at is None or item.timeout_at >= now:
            return False

        item.status = QcItemStatus.PENDING
        item.locked_at = None
        item.timeout_at = None
        self.db.flush()
        return True


__all__ = ["QcTaskItemRepository"]