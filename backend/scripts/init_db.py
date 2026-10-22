"""初始化数据库：执行迁移 + 创建内置角色与超级管理员。

用法（在 backend/ 目录下执行）：
    python -m scripts.init_db
"""

import logging
import sys
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.core.config import BASE_DIR, settings
from app.core.logging import setup_logging
from app.core.permissions import ALL_PERMISSIONS
from app.core.security import hash_password
from app.db.session import session_scope
from app.models.user import Role
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

ADMIN_ROLE_CODE = "admin"
ADMIN_ROLE_NAME = "系统管理员"


def run_migrations() -> None:
    """执行 alembic upgrade head。"""
    config = Config(str(Path(BASE_DIR) / "alembic.ini"))
    config.set_main_option("script_location", str(Path(BASE_DIR) / "alembic"))
    command.upgrade(config, "head")
    logger.info("数据库迁移已执行至 head")


def seed_permissions(repo: UserRepository, role: Role) -> tuple[int, int]:
    """落库权限码目录，并把全部权限授予内置 admin 角色。

    返回 (新增权限数, 新增授权数)。幂等：重复执行不会产生重复数据。
    """
    created = 0
    granted = 0
    for definition in ALL_PERMISSIONS:
        permission = repo.get_permission_by_code(definition.code)
        if permission is None:
            permission = repo.create_permission(
                code=definition.code,
                name=definition.name,
                module=definition.module,
                description=definition.description,
            )
            created += 1
        if all(existing.code != permission.code for existing in role.permissions):
            role.permissions.append(permission)
            granted += 1
    return created, granted


def seed() -> None:
    """创建内置角色、权限码与超级管理员（幂等）。"""
    with session_scope() as db:
        repo = UserRepository(db)

        role = repo.get_role_by_code(ADMIN_ROLE_CODE)
        if role is None:
            role = repo.create_role(
                code=ADMIN_ROLE_CODE,
                name=ADMIN_ROLE_NAME,
                description="内置角色，拥有全部权限",
                is_system=True,
            )
            logger.info("已创建内置角色：%s", ADMIN_ROLE_CODE)

        created_permissions, granted_permissions = seed_permissions(repo, role)
        logger.info(
            "权限码同步完成：新增 %s 个，新增授权 %s 条，当前共 %s 个权限",
            created_permissions,
            granted_permissions,
            len(ALL_PERMISSIONS),
        )

        user = repo.get_by_username(settings.FIRST_SUPERUSER)
        if user is None:
            user = repo.create_user(
                username=settings.FIRST_SUPERUSER,
                password_hash=hash_password(settings.FIRST_SUPERUSER_PASSWORD),
                nickname=settings.FIRST_SUPERUSER_NICKNAME,
                is_active=True,
                is_superuser=True,
            )
            repo.assign_role(user, role)
            logger.info("已创建超级管理员：%s", settings.FIRST_SUPERUSER)
        else:
            logger.info("超级管理员已存在，跳过：%s", settings.FIRST_SUPERUSER)


def main() -> int:
    setup_logging()
    try:
        run_migrations()
        # alembic 的 fileConfig 会覆盖根日志配置，此处恢复应用日志
        setup_logging()
        seed()
    except Exception:
        logger.exception("初始化数据库失败")
        return 1
    logger.info("初始化完成，可使用 %s 登录", settings.FIRST_SUPERUSER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
