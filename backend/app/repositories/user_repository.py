"""用户 / 角色 / 权限数据访问。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import Permission, Role, User, role_permissions, user_roles


class UserRepository:
    """RBAC 相关查询。所有查询默认过滤软删除数据。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 用户 ----------

    def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id, User.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username, User.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        nickname: str = "",
        email: str | None = None,
        phone: str | None = None,
        is_active: bool = True,
        is_superuser: bool = False,
        tenant_id: int | None = None,
    ) -> User:
        user = User(
            username=username,
            password_hash=password_hash,
            nickname=nickname,
            email=email,
            phone=phone,
            is_active=is_active,
            is_superuser=is_superuser,
            tenant_id=tenant_id,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def list_active_options(self, *, limit: int = 200) -> list[User]:
        """启用中的用户账号（供开通坐席时选择关联用户）。"""
        stmt = (
            select(User)
            .where(User.is_deleted.is_(False), User.is_active.is_(True))
            .order_by(User.id.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_permission_codes(self, user_id: int) -> list[str]:
        stmt = (
            select(Permission.code)
            .join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .join(Role, Role.id == role_permissions.c.role_id)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(
                user_roles.c.user_id == user_id,
                Role.is_deleted.is_(False),
            )
            .distinct()
        )
        return list(self.db.execute(stmt).scalars().all())

    # ---------- 角色 ----------

    def get_role_by_code(self, code: str) -> Role | None:
        stmt = select(Role).where(Role.code == code, Role.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def create_role(
        self, *, code: str, name: str, description: str = "", is_system: bool = False
    ) -> Role:
        role = Role(code=code, name=name, description=description, is_system=is_system)
        self.db.add(role)
        self.db.flush()
        return role

    def assign_role(self, user: User, role: Role) -> None:
        if role not in user.roles:
            user.roles.append(role)
            self.db.flush()

    # ---------- 权限 ----------

    def get_permission_by_code(self, code: str) -> Permission | None:
        stmt = select(Permission).where(Permission.code == code)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_permission(
        self, *, code: str, name: str, module: str = "", description: str = ""
    ) -> Permission:
        permission = Permission(code=code, name=name, module=module, description=description)
        self.db.add(permission)
        self.db.flush()
        return permission
