"""密码哈希与 JWT 签发 / 校验。"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import Unauthorized

# bcrypt 仅取前 72 字节，超长密码需截断，否则 4.x 直接抛错
_BCRYPT_MAX_BYTES = 72

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def hash_password(plain: str) -> str:
    """生成密码哈希。"""
    raw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码，哈希非法时返回 False 而非抛错。"""
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:_BCRYPT_MAX_BYTES], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _encode(subject: str | int, token_type: str, expires_delta: timedelta) -> tuple[str, str, int]:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + expires_delta,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, payload["jti"], int(expires_delta.total_seconds())


def create_access_token(subject: str | int) -> tuple[str, str, int]:
    """返回 (token, jti, 有效期秒数)。"""
    return _encode(
        subject, TOKEN_TYPE_ACCESS, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(subject: str | int) -> tuple[str, str, int]:
    """返回 (token, jti, 有效期秒数)。"""
    return _encode(subject, TOKEN_TYPE_REFRESH, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """解析并校验 token，失败统一抛 40101。"""
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("登录已过期，请重新登录") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("凭据无效") from exc

    if expected_type and payload.get("type") != expected_type:
        raise Unauthorized("凭据类型不正确")
    return payload
