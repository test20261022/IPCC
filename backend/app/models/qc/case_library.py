"""优秀案例库：从已完成质检的对话中沉淀优秀模板，用于减少重复投入与在岗培训。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin


class QcCaseLibrary(Base, TimestampMixin, SoftDeleteMixin):
    """优秀案例：一条对话最多沉淀一个案例（发布为模板）。"""

    __tablename__ = "qc_case_library"
    __table_args__ = (
        Index(
            "uq_qc_case_library_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_qc_case_library_tenant_published", "tenant_id", "is_published"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("qc_conversations.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("qc_task_items.id", ondelete="SET NULL"),
        nullable=True,
        comment="来源质检明细（任务被删后案例仍保留）",
    )

    title: Mapped[str] = mapped_column(String(128), nullable=False, comment="案例标题")
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False, comment="入选理由 / 亮点")
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, comment="标签，供筛选")

    is_published: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否发布为模板"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


__all__ = ["QcCaseLibrary"]