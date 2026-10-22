"""名单域：导入批次与名单行。

对应需求：OB-011 名单导入（多号码 + 动态表头）、OB-012 全场景变量获取、
OB-021 外呼会话名单、OB-023 外呼任务看板名单信息。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin
from app.models.outbound.enums import ImportBatchStatus, ListStatus, enum_type


class OutboundImportBatch(Base, TimestampMixin, SoftDeleteMixin):
    """名单导入批次（§24 / §25）。

    failed_detail 仅保存失败行明细（行号 / 字段 / 原因 / 原始值），
    禁止把 Excel 原始文件内容整体入库（§102-26）。
    """

    __tablename__ = "outbound_import_batches"
    __table_args__ = (
        Index("ix_outbound_import_batches_tenant_id", "tenant_id"),
        Index("ix_outbound_import_batches_task_id", "task_id"),
        Index("ix_outbound_import_batches_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("outbound_tasks.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="落盘路径（不存二进制）"
    )
    file_size: Mapped[int] = mapped_column(
        BigIntCol, default=0, nullable=False, comment="文件字节数"
    )

    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="总行数")
    success_rows: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="成功行数"
    )
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="失败行数")

    status: Mapped[ImportBatchStatus] = mapped_column(
        enum_type(ImportBatchStatus), default=ImportBatchStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="整体失败原因")
    failed_detail: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True, comment="失败明细：[{row, field, reason, raw}]"
    )

    imported_by: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="导入人"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboundList(Base, TimestampMixin, SoftDeleteMixin):
    """名单行（§26）。

    注意：user_id / order_id 是导入名单携带的**业务标识**（字符串），
    不是 users.id / 订单表主键，禁止当作外键使用（§26 字段名照搬，语义以本注释为准）。
    """

    __tablename__ = "outbound_lists"
    __table_args__ = (
        Index("ix_outbound_lists_tenant_id", "tenant_id"),
        Index("ix_outbound_lists_task_id", "task_id"),
        Index("ix_outbound_lists_status", "status"),
        Index("ix_outbound_lists_import_batch_id", "import_batch_id"),
        # OB-021 按 UserID 取号码；OB-023 按 OrderID 取号码
        Index("ix_outbound_lists_user_id", "user_id"),
        Index("ix_outbound_lists_order_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("outbound_tasks.id", ondelete="CASCADE"), nullable=False
    )
    import_batch_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_import_batches.id", ondelete="SET NULL"),
        nullable=True,
        comment="来源导入批次",
    )

    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="业务 UserID")
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="业务 OrderID")
    recipient_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="收件人")
    recipient_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="收件人号码（§23 收件号码来源）"
    )
    phone_numbers: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, comment="多号码清单（§24 多号码列）"
    )
    dynamic_fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="动态表头字段（§24 / OB-012 变量来源）"
    )

    status: Mapped[ListStatus] = mapped_column(
        enum_type(ListStatus), default=ListStatus.PENDING, nullable=False
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="名单优先级（§34 分配排序依据）"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="已尝试次数"
    )
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str] = mapped_column(String(255), default="", nullable=False)


__all__ = ["OutboundImportBatch", "OutboundList"]
