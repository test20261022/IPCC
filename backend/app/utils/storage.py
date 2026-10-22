"""本地文件存储（MVP）。

§102-26：原始文件只落盘、不入库，数据库仅保存相对路径。
后续如需替换为 MinIO / S3 / OSS，只需替换本模块实现（§66 同类思路）。
"""

import re
import time
from pathlib import Path

from app.core.config import BASE_DIR, settings

_UNSAFE_CHARS = re.compile(r"[^\w.\u4e00-\u9fa5-]", re.UNICODE)


def storage_root() -> Path:
    """存储根目录（相对路径按 backend/ 解析）。"""
    root = Path(settings.STORAGE_DIR)
    return root if root.is_absolute() else Path(BASE_DIR) / root


def safe_filename(filename: str) -> str:
    """去掉路径分隔符与不安全字符，避免目录穿越。"""
    name = Path(filename).name
    cleaned = _UNSAFE_CHARS.sub("_", name).strip("._")
    return cleaned or "unnamed"


def save_bytes(*, subdir: str, filename: str, content: bytes) -> str:
    """保存文件，返回相对存储根目录的路径（POSIX 风格，便于跨平台存储）。"""
    target_dir = storage_root() / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    # 加时间戳前缀，避免同名文件互相覆盖
    unique_name = f"{int(time.time() * 1000)}_{safe_filename(filename)}"
    (target_dir / unique_name).write_bytes(content)
    return (Path(subdir) / unique_name).as_posix()


def absolute_path(relative_path: str) -> Path:
    """相对路径 → 绝对路径。"""
    return storage_root() / relative_path


def exists(relative_path: str | None) -> bool:
    return bool(relative_path) and absolute_path(str(relative_path)).is_file()
