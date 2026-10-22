"""对话域 Schema：对话 / 消息 / 导入批次的出入参。

QcSchemaBase / QcOutBase 为质检域公共基类，供同域的 case.py 复用（避免再增基类文件）。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.qc.enums import (
    ConversationChannel,
    ConversationSource,
    MessageRole,
    MessageSource,
    QcImportFormat,
    QcImportStatus,
    TranscriptStatus,
)


class QcSchemaBase(BaseModel):
    """质检模块 Schema 基类：允许从 ORM 对象直接构造。"""

    model_config = ConfigDict(from_attributes=True)


class QcOutBase(QcSchemaBase):
    """出参基类：统一带上主键与时间戳。"""

    id: int = Field(description="主键")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class QcUpdateBase(QcSchemaBase):
    """入参基类：更新语义为「只更新显式传入的字段」。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ---------------- 对话 ----------------

class MessageIn(QcSchemaBase):
    """写入一条对话消息。"""

    role: MessageRole = Field(default=MessageRole.CUSTOMER, description="说话人")
    content: str = Field(default="", description="消息内容")
    start_ms: int | None = Field(default=None, ge=0, description="相对对话开始的起始毫秒")
    end_ms: int | None = Field(default=None, ge=0, description="相对对话开始的结束毫秒")


class ConversationCreateIn(QcSchemaBase):
    """人工录入对话。"""

    tenant_id: int = Field(gt=0, description="租户")
    ext_ref_no: str | None = Field(default=None, max_length=128, description="外部系统唯一标识")
    agent_name: str = Field(default="", max_length=64, description="客服（坐席）")
    agent_ext: str | None = Field(default=None, max_length=32, description="客服分机 / 工号")
    customer_id: str | None = Field(default=None, max_length=64, description="客户标识")
    channel: ConversationChannel = Field(
        default=ConversationChannel.CHAT, description="对话渠道"
    )
    started_at: datetime = Field(description="对话开始时间")
    ended_at: datetime | None = Field(default=None, description="对话结束时间")
    duration: int = Field(default=0, ge=0, description="对话时长（秒）")
    recording_path: str | None = Field(
        default=None, max_length=512, description="录音路径，仅语音对话使用"
    )
    messages: list[MessageIn] = Field(default_factory=list, description="对话消息")


class ConversationUpdateIn(QcUpdateBase):
    """编辑对话（仅对话级字段，不涉及消息）。"""

    ext_ref_no: str | None = Field(default=None, max_length=128)
    agent_name: str | None = Field(default=None, max_length=64)
    agent_ext: str | None = Field(default=None, max_length=32)
    customer_id: str | None = Field(default=None, max_length=64)
    channel: ConversationChannel | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration: int | None = Field(default=None, ge=0)
    recording_path: str | None = Field(default=None, max_length=512)


class MessageOut(QcOutBase):
    """对话消息出参。"""

    conversation_id: int
    seq: int = Field(description="对话内顺序，从 1 开始")
    role: MessageRole
    content: str
    start_ms: int | None = None
    end_ms: int | None = None
    source: MessageSource


class ConversationOut(QcOutBase):
    """对话主表出参。"""

    tenant_id: int
    ext_ref_no: str | None = None
    agent_name: str
    agent_ext: str | None = None
    customer_id: str | None = None
    channel: ConversationChannel
    source: ConversationSource
    started_at: datetime
    ended_at: datetime | None = None
    duration: int
    msg_count: int
    recording_path: str | None = None
    transcript_status: TranscriptStatus
    transcript_engine: str | None = None


class ConversationDetailOut(ConversationOut):
    """对话详情：主表 + 消息（按 seq 升序）。"""

    messages: list[MessageOut] = Field(default_factory=list)


class TranscribeResultOut(QcSchemaBase):
    """语音转写结果。"""

    conversation_id: int
    transcript_status: TranscriptStatus
    transcript_engine: str | None = None
    message_count: int = Field(description="转写后该对话的消息总数")


# ---------------- 导入批次 ----------------

class QcImportBatchOut(QcOutBase):
    """对话导入批次出参。"""

    tenant_id: int
    file_name: str
    file_path: str | None = None
    format: QcImportFormat
    total_rows: int
    success_rows: int
    failed_rows: int
    status: QcImportStatus
    error_detail: list[dict[str, Any]] | None = None


__all__ = [
    "ConversationCreateIn",
    "ConversationDetailOut",
    "ConversationOut",
    "ConversationUpdateIn",
    "MessageIn",
    "MessageOut",
    "QcImportBatchOut",
    "QcOutBase",
    "QcSchemaBase",
    "QcUpdateBase",
    "TranscribeResultOut",
]