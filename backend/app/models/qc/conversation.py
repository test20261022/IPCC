"""质检对话域：对话主表 / 对话消息 / 导入批次。

对应业务：客服（坐席）与客户的对话记录。支持人工录入与外部系统批量导入（TXT / JSON / XLSX）；
纯文本对话无需转写，语音对话按 TranscriptStatus 走 ASR 转写后再补充消息（一期为 Mock）。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin
from app.models.outbound.enums import enum_type
from app.models.qc.enums import (
    ConversationChannel,
    ConversationSource,
    MessageRole,
    MessageSource,
    QcImportFormat,
    QcImportStatus,
    TranscriptStatus,
)


class QcConversation(Base, TimestampMixin, SoftDeleteMixin):
    """对话主表：客服与客户的一次完整对话。"""

    __tablename__ = "qc_conversations"
    __table_args__ = (
        # 列表与派发按时间区间筛选
        Index("ix_qc_conversations_tenant_started_at", "tenant_id", "started_at"),
        Index("ix_qc_conversations_tenant_agent_name", "tenant_id", "agent_name"),
        # 外部系统对话唯一标识：同租户内不重复导入（导入幂等的数据库层保证）
        Index(
            "uq_qc_conversations_tenant_ext_ref",
            "tenant_id",
            "ext_ref_no",
            unique=True,
            postgresql_where=text("is_deleted = false AND ext_ref_no IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    ext_ref_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="外部系统对话唯一标识（导入去重）"
    )
    agent_name: Mapped[str] = mapped_column(
        String(64), default="", nullable=False, comment="客服（坐席）"
    )
    agent_ext: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="客服分机 / 工号"
    )
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="客户标识")

    channel: Mapped[ConversationChannel] = mapped_column(
        enum_type(ConversationChannel), default=ConversationChannel.CHAT, nullable=False
    )
    source: Mapped[ConversationSource] = mapped_column(
        enum_type(ConversationSource), default=ConversationSource.MANUAL, nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="对话开始时间（派发分片依据）"
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="对话时长（秒）"
    )
    msg_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="消息条数")

    recording_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="录音路径，仅存路径不存二进制（§66）"
    )
    transcript_status: Mapped[TranscriptStatus] = mapped_column(
        enum_type(TranscriptStatus), default=TranscriptStatus.NOT_REQUIRED, nullable=False
    )
    transcript_engine: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="实际使用的转写 Provider 名称"
    )

    messages: Mapped[list["QcMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class QcMessage(Base, TimestampMixin):
    """对话消息：一条消息一行，append-only，不做软删除（同 CallHistory 口径）。"""

    __tablename__ = "qc_messages"
    __table_args__ = (Index("ix_qc_messages_conversation_seq", "conversation_id", "seq"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntCol, nullable=False, comment="归属租户")
    conversation_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("qc_conversations.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, comment="对话内顺序，从 1 开始")
    role: Mapped[MessageRole] = mapped_column(
        enum_type(MessageRole), default=MessageRole.CUSTOMER, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False, comment="消息内容")
    start_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="相对对话开始的起始毫秒"
    )
    end_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="相对对话开始的结束毫秒"
    )
    source: Mapped[MessageSource] = mapped_column(
        enum_type(MessageSource), default=MessageSource.TEXT, nullable=False
    )

    conversation: Mapped["QcConversation"] = relationship(back_populates="messages")


class QcImportBatch(Base, TimestampMixin, SoftDeleteMixin):
    """对话导入批次（对齐外呼名单导入的批次口径）。"""

    __tablename__ = "qc_import_batches"
    __table_args__ = (Index("ix_qc_import_batches_tenant_status", "tenant_id", "status"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    file_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="落盘路径（相对 STORAGE_DIR）"
    )
    format: Mapped[QcImportFormat] = mapped_column(
        enum_type(QcImportFormat), default=QcImportFormat.JSON, nullable=False
    )
    total_rows: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="文件总条数"
    )
    success_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[QcImportStatus] = mapped_column(
        enum_type(QcImportStatus), default=QcImportStatus.PENDING, nullable=False
    )
    error_detail: Mapped[list[dict] | None] = mapped_column(
        JSONB, nullable=True, comment="失败行明细（行号 / 原因），上限见配置"
    )


__all__ = ["QcConversation", "QcImportBatch", "QcMessage"]