"""通用校验规则：号码格式等（供 Schema 与 Service 共用，避免规则两处维护）。"""

import re

#: 号码格式：以数字开头，允许数字与 + -，长度 5~32
PHONE_PATTERN = r"^[0-9][0-9+\-]{4,31}$"

_PHONE_RE = re.compile(PHONE_PATTERN)


def is_valid_phone(value: str | None) -> bool:
    """号码格式校验。"""
    if not value:
        return False
    return _PHONE_RE.match(value.strip()) is not None
