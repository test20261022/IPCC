"""对话域数据访问：对话 / 消息 / 导入批次 / 转写与删除校验依赖的读取。

所有查询默认过滤软删除；tenant_id 传入才过滤（None 表示不限租户）。
"""

from datetime import datetime

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.qc import QcCaseLibrary, QcConversation, QcImportBatch, QcMessage, QcTaskItem
from app.models.qc.enums import (
    ConversationChannel,
    ConversationSource,
    MessageSource,
    TranscriptStatus,
)


class QcConversationRepository:
    """对话主表、消息、导入批次的查询与批量写入。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 对话主表 ----------

    def get_by_id(self, conversation_id: int) -> QcConversation | None:
        stmt = select(QcConversation).where(
            QcConversation.id == conversation_id,
            QcConversation.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_ext_ref(self, tenant_id: int, ext_ref_no: str) -> QcConversation | None:
        """按外部系统唯一标识取对话（导入幂等校验）。"""
        stmt = select(QcConversation).where(
            QcConversation.tenant_id == tenant_id,
            QcConversation.ext_ref_no == ext_ref_no,
            QcConversation.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_existing_ext_refs(self, tenant_id: int, ext_ref_nos: list[str]) -> set[str]:
        """批量取已存在的 ext_ref_no（一次性判重，避免逐条查询）。"""
        if not ext_ref_nos:
            return set()
        stmt = select(QcConversation.ext_ref_no).where(
            QcConversation.tenant_id == tenant_id,
            QcConversation.ext_ref_no.in_(ext_ref_nos),
            QcConversation.is_deleted.is_(False),
        )
        return {row[0] for row in self.db.execute(stmt).all() if row[0]}

    def list_by_ids(self, conversation_ids: list[int]) -> list[QcConversation]:
        """按主键集合取对话（供转写批量使用）。"""
        if not conversation_ids:
            return []
        stmt = select(QcConversation).where(
            QcConversation.id.in_(conversation_ids),
            QcConversation.is_deleted.is_(False),
        )
        return list(self.db.execute(stmt).scalars().all())

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        agent_name: str | None = None,
        channel: ConversationChannel | None = None,
        source: ConversationSource | None = None,
        transcript_status: TranscriptStatus | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        keyword: str | None = None,
    ) -> Select:
        stmt = stmt.where(QcConversation.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(QcConversation.tenant_id == tenant_id)
        if agent_name:
            stmt = stmt.where(QcConversation.agent_name.ilike(f"%{agent_name}%"))
        if channel is not None:
            stmt = stmt.where(QcConversation.channel == channel)
        if source is not None:
            stmt = stmt.where(QcConversation.source == source)
        if transcript_status is not None:
            stmt = stmt.where(QcConversation.transcript_status == transcript_status)
        if started_from is not None:
            stmt = stmt.where(QcConversation.started_at >= started_from)
        if started_to is not None:
            stmt = stmt.where(QcConversation.started_at <= started_to)
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    QcConversation.ext_ref_no.ilike(like),
                    QcConversation.customer_id.ilike(like),
                    QcConversation.agent_name.ilike(like),
                )
            )
        return stmt

    def list_paged(self, *, page: int, page_size: int, **filters: object) -> list[QcConversation]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(select(QcConversation), **filters)  # type: ignore[arg-type]
        stmt = stmt.order_by(QcConversation.started_at.desc(), QcConversation.id.desc())
        stmt = stmt.offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, **filters: object) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(QcConversation), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> QcConversation:
        conversation = QcConversation(**values)
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def bulk_insert_conversations(self, values: list[dict[str, object]]) -> list[int]:
        """批量写入对话并返回按写入顺序排列的主键（一次 INSERT，避免逐行 add）。"""
        if not values:
            return []
        stmt = QcConversation.__table__.insert().returning(QcConversation.__table__.c.id)
        result = self.db.execute(stmt, values)
        return [int(row[0]) for row in result.all()]

    # ---------- 消息 ----------

    def list_messages(self, conversation_id: int) -> list[QcMessage]:
        stmt = (
            select(QcMessage)
            .where(QcMessage.conversation_id == conversation_id)
            .order_by(QcMessage.seq.asc(), QcMessage.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_messages(self, conversation_id: int) -> int:
        stmt = select(func.count()).select_from(QcMessage).where(
            QcMessage.conversation_id == conversation_id
        )
        return int(self.db.execute(stmt).scalar_one())

    def max_message_seq(self, conversation_id: int) -> int:
        stmt = select(func.coalesce(func.max(QcMessage.seq), 0)).where(
            QcMessage.conversation_id == conversation_id
        )
        return int(self.db.execute(stmt).scalar_one())

    def bulk_insert_messages(self, values: list[dict[str, object]]) -> int:
        if not values:
            return 0
        self.db.execute(QcMessage.__table__.insert(), values)
        self.db.flush()
        return len(values)

    def delete_messages_by_source(self, conversation_id: int, source: MessageSource) -> int:
        """删除指定来源的消息（转写重跑时清理旧的 ASR 消息）。"""
        stmt = delete(QcMessage).where(
            QcMessage.conversation_id == conversation_id,
            QcMessage.source == source,
        )
        return int(self.db.execute(stmt).rowcount or 0)

    # ---------- 删除保护：被质检 / 案例库引用 ----------

    def count_task_items(self, conversation_id: int) -> int:
        """被质检明细引用的条数（未完成 / 已完成 / 超时均计入）。"""
        stmt = select(func.count()).select_from(QcTaskItem).where(
            QcTaskItem.conversation_id == conversation_id,
            QcTaskItem.is_deleted.is_(False),
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_case_references(self, conversation_id: int) -> int:
        stmt = select(func.count()).select_from(QcCaseLibrary).where(
            QcCaseLibrary.conversation_id == conversation_id,
            QcCaseLibrary.is_deleted.is_(False),
        )
        return int(self.db.execute(stmt).scalar_one())

    # ---------- 导入批次 ----------

    def create_batch(self, **values: object) -> QcImportBatch:
        batch = QcImportBatch(**values)
        self.db.add(batch)
        self.db.flush()
        return batch

    def get_batch(self, batch_id: int) -> QcImportBatch | None:
        stmt = select(QcImportBatch).where(
            QcImportBatch.id == batch_id,
            QcImportBatch.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_batch_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
    ) -> Select:
        stmt = stmt.where(QcImportBatch.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(QcImportBatch.tenant_id == tenant_id)
        return stmt

    def list_batches_paged(
        self, *, page: int, page_size: int, **filters: object
    ) -> list[QcImportBatch]:
        offset = (page - 1) * page_size
        stmt = self._apply_batch_filters(
            select(QcImportBatch), **filters  # type: ignore[arg-type]
        )
        stmt = stmt.order_by(QcImportBatch.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count_batches(self, **filters: object) -> int:
        stmt = self._apply_batch_filters(
            select(func.count()).select_from(QcImportBatch), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())


__all__ = ["QcConversationRepository"]