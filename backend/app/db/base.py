"""SQLAlchemy 声明式基类与通用 Mixin。

全项目唯一 Base（§47），禁止另起一套；所有新模型继承
Base + TimestampMixin + SoftDeleteMixin，主键使用 BigIntPK。
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# PostgreSQL 使用 BIGINT；SQLite 仅用于轻量本地调试时降级为 INTEGER
BigIntPK = BigInteger().with_variant(Integer, "sqlite")
BigIntCol = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""


class TimestampMixin:
    """创建 / 更新时间（timestamptz，UTC）。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    """软删除。需要唯一约束时使用部分唯一索引 WHERE is_deleted = false（§50）。"""

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def mark_deleted(self) -> None:
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
