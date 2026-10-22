"""日志初始化（§70）。"""

import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
APP_HANDLER_NAME = "app-console"


def setup_logging() -> None:
    """初始化根日志：输出到 stdout，级别由 DEBUG 决定。

    可重复调用：被第三方（如 alembic 的 fileConfig）改写后会重新生效。
    """
    level = logging.DEBUG if settings.DEBUG else logging.INFO

    root = logging.getLogger()
    if not any(getattr(handler, "name", None) == APP_HANDLER_NAME for handler in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.name = APP_HANDLER_NAME
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(handler)
    root.setLevel(level)

    # 降低第三方库噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
