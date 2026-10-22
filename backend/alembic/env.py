"""Alembic 运行环境：连接串与元数据统一从应用配置读取。"""

import logging
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.core.logging import APP_HANDLER_NAME
from app.models import Base  # 通过 models 包集中注册全部表

config = context.config
# 允许外部（如测试）通过环境变量指定目标库，否则使用应用配置
database_url = os.getenv("ALEMBIC_DATABASE_URL") or settings.DATABASE_URL
config.set_main_option("sqlalchemy.url", database_url)

# 应用已初始化日志时（如 init_db / pytest 进程内执行迁移）不再覆盖，避免重复输出
_app_logging_ready = any(
    getattr(handler, "name", None) == APP_HANDLER_NAME
    for handler in logging.getLogger().handlers
)
if config.config_file_name is not None and not _app_logging_ready:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL。"""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
