"""同步 / 异步桥接。

Service 层是同步实现（同步 SQLAlchemy），而 Provider 接口按 §29 定义为 async
（便于真实实现使用 httpx.AsyncClient，并满足 §102-14「不阻塞 HTTP」）。

本模块把两者隔离在一处，替换为任务队列时只需改这里。
"""

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """在同步上下文执行协程。

    - 当前线程没有事件循环（同步端点 / 定时任务）→ 直接 asyncio.run；
    - 若已在事件循环内（异步端点调用）→ 放到独立线程运行，避免嵌套事件循环。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
