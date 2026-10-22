"""FastAPI 依赖：数据库会话、当前用户、权限校验、数据权限入口。

【基线冻结】鉴权契约在此定义，后续模块只允许调用，禁止修改。
"""

import logging
from collections.abc import Callable
from typing import Any

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.cache import is_token_blacklisted
from app.core.exceptions import Forbidden, Unauthorized
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <access_token>")


def get_client_ip(request: Request) -> str | None:
    """优先取代理转发头，无则取直连地址。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def get_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """解析并校验 access_token（含登出黑名单校验）。"""
    if credentials is None or not credentials.credentials:
        raise Unauthorized()
    payload = decode_token(credentials.credentials, expected_type=TOKEN_TYPE_ACCESS)
    if is_token_blacklisted(str(payload.get("jti", ""))):
        raise Unauthorized("登录已失效，请重新登录")
    return payload


def get_current_user(
    payload: dict[str, Any] = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> User:
    """当前登录用户。"""
    try:
        user_id = int(str(payload.get("sub", "")))
    except (TypeError, ValueError) as exc:
        raise Unauthorized("凭据无效") from exc

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise Unauthorized("用户不存在")
    if not user.is_active:
        raise Forbidden("账号已停用")
    return user


def require_permission(*codes: str) -> Callable[..., User]:
    """权限校验依赖工厂：满足任意一个权限码即放行。

    超级管理员直接放行（§59），其操作仍由操作日志中间件记录。
    用法：`current_user: User = Depends(require_permission("outbound:number:list"))`
    """

    def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_superuser:
            return current_user
        owned = current_user.permission_codes()
        if not any(code in owned for code in codes):
            logger.warning(
                "权限不足：user=%s 需要=%s 拥有=%s",
                current_user.username,
                list(codes),
                sorted(owned),
            )
            raise Forbidden(f"缺少权限：{' / '.join(codes)}")
        return current_user

    return _checker


def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    """仅超级管理员可访问。"""
    if not current_user.is_superuser:
        raise Forbidden("仅超级管理员可执行该操作")
    return current_user


# ---------------- 数据范围（规则 7：多租户隔离） ----------------


def _resolve_tenant_scope(current_user: User, tenant_id: int | None) -> int | None:
    """把入参 tenant_id 收敛为「该用户实际可访问的租户」。

    规则（ASSUMPTION-058）：
    - 超级管理员：可跨租户，tenant_id 为空表示不限租户；
    - 已绑定租户的普通用户：强制收敛到自己所属租户，显式传其他租户返回 403；
    - 未绑定租户的普通用户：视为平台账号，不受租户范围限制。
    """
    if current_user.is_superuser or current_user.tenant_id is None:
        return tenant_id
    if tenant_id is not None and tenant_id != current_user.tenant_id:
        logger.warning(
            "越权访问租户数据：user=%s 所属租户=%s 请求租户=%s",
            current_user.username,
            current_user.tenant_id,
            tenant_id,
        )
        raise Forbidden("无权访问其他租户的数据")
    return current_user.tenant_id


def tenant_scope_optional(
    tenant_id: int | None = Query(default=None, gt=0, description="租户；普通用户只能查所属租户"),
    current_user: User = Depends(get_current_user),
) -> int | None:
    """可选租户范围的列表接口使用：返回实际生效的 tenant_id（可能被强制覆盖）。"""
    return _resolve_tenant_scope(current_user, tenant_id)


def tenant_scope_required(
    tenant_id: int = Query(gt=0, description="租户；普通用户只能查所属租户"),
    current_user: User = Depends(get_current_user),
) -> int:
    """必填租户范围的接口使用（如实时监控快照）。"""
    resolved = _resolve_tenant_scope(current_user, tenant_id)
    if resolved is None:  # pragma: no cover - 参数为必填，不会被置空
        raise Forbidden("无法确定租户范围")
    return resolved
