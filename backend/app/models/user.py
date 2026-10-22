"""用户 / 角色 / 权限模型（RBAC）。

【基线冻结】本文件为全项目认证与权限的唯一来源，后续模块只允许读取，禁止修改。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Table, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.log import LoginLog, OperationLog  # noqa: F401

# 用户 - 角色 多对多
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", BigIntPK, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", BigIntPK, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

# 角色 - 权限 多对多
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", BigIntPK, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        BigIntPK,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    __table_args__ = (
        # 软删除 + 唯一用户名：用部分唯一索引，删除后可复用同名账号
        Index(
            "uq_users_username_active",
            "username",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "uq_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("is_deleted = false AND email IS NOT NULL"),
            sqlite_where=text("is_deleted = 0 AND email IS NOT NULL"),
        ),
        # 按租户维度查账号（数据范围过滤）
        Index("ix_users_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 租户归属（ASSUMPTION-058）：绑定后普通用户只能访问本租户数据；
    # 为空表示平台账号（可跨租户），超管同样不受限。
    tenant_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        comment="所属租户；空表示平台账号（不受租户范围限制）",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        secondary=user_roles, back_populates="users", lazy="selectin"
    )

    @property
    def role_codes(self) -> list[str]:
        return [role.code for role in self.roles]

    def permission_codes(self) -> set[str]:
        """超级管理员拥有全部权限（由 require_permission 直接放行）。"""
        codes: set[str] = set()
        for role in self.roles:
            for permission in role.permissions:
                codes.add(permission.code)
        return codes


class Role(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "roles"
    __table_args__ = (
        Index(
            "uq_roles_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    # 内置角色不允许删除（如 admin）
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"
    __table_args__ = (Index("uq_permissions_code", "code", unique=True),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )
