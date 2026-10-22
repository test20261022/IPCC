"""Redis 缓存封装：不可用时自动降级（登出黑名单不生效，仅记录日志）。"""

import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
_initialized = False

BLACKLIST_PREFIX = "auth:blacklist:"


def get_redis() -> redis.Redis | None:
    """获取 Redis 客户端；未配置或不可用返回 None（降级）。"""
    global _client, _initialized
    if _initialized:
        return _client

    _initialized = True
    if not settings.REDIS_URL:
        logger.warning("未配置 REDIS_URL，缓存能力降级")
        return None

    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        _client = client
        logger.info("Redis 已连接：%s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis 不可用，缓存能力降级：%s", exc)
        _client = None
    return _client


def reset_client() -> None:
    """重置连接状态（测试使用）。"""
    global _client, _initialized
    _client = None
    _initialized = False


def is_available() -> bool:
    """Redis 是否可用。"""
    return get_redis() is not None


def blacklist_token(jti: str, ttl_seconds: int) -> bool:
    """登出：将 jti 加入黑名单。返回是否写入成功。"""
    if not jti or ttl_seconds <= 0:
        return False
    client = get_redis()
    if client is None:
        logger.warning("Redis 不可用，登出黑名单未生效（jti=%s）", jti)
        return False
    try:
        client.set(f"{BLACKLIST_PREFIX}{jti}", "1", ex=ttl_seconds)
        return True
    except Exception as exc:
        logger.warning("写入登出黑名单失败：%s", exc)
        return False


def is_token_blacklisted(jti: str) -> bool:
    """判断 token 是否已登出。Redis 不可用时返回 False（降级放行）。"""
    if not jti:
        return False
    client = get_redis()
    if client is None:
        return False
    try:
        return client.exists(f"{BLACKLIST_PREFIX}{jti}") == 1
    except Exception as exc:
        logger.warning("查询登出黑名单失败：%s", exc)
        return False
