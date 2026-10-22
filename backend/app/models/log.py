"""登录日志 / 操作日志（§70）。"""

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntCol, BigIntPK, TimestampMixin


class LoginLog(Base, TimestampMixin):
    """登录日志：成功与失败都记录。"""

    __tablename__ = "login_logs"
    __table_args__ = (Index("ix_login_logs_username_created", "username", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigIntCol, nullable=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    message: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class OperationLog(Base, TimestampMixin):
    """操作日志：记录谁、何时、对什么做了什么（写操作由中间件统一落库）。"""

    __tablename__ = "operation_logs"
    __table_args__ = (
        Index("ix_operation_logs_user_created", "user_id", "created_at"),
        Index("ix_operation_logs_module_created", "module", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigIntCol, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    module: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    method: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    path: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
