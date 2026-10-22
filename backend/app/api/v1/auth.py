"""认证接口：登录 / 刷新 / 登出 / 当前用户信息。Router 只做 HTTP 层（§54）。"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user, get_token_payload, get_user_agent
from app.core.response import ApiResponse, ok
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse, UserInfo
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
    summary="登录",
    description="用户名 + 密码登录，返回 access_token / refresh_token。",
)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Any:
    service = AuthService(db)
    data = service.login(
        username=payload.username,
        password=payload.password,
        ip=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return ok(data)


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponse],
    summary="刷新令牌",
    description="使用 refresh_token 换取新的 access_token。",
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> Any:
    return ok(AuthService(db).refresh(payload.refresh_token))


@router.post(
    "/logout",
    response_model=ApiResponse[None],
    summary="登出",
    description="将当前 access_token 加入黑名单，可选传入 refresh_token 一并失效。",
)
def logout(
    payload: LogoutRequest | None = None,
    token_payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> Any:
    AuthService(db).logout(access_jti=str(token_payload.get("jti", "")), payload=payload)
    return ok(None, message="已登出")


@router.get(
    "/me",
    response_model=ApiResponse[UserInfo],
    summary="当前登录用户",
    description="返回当前用户基础信息、角色与权限码集合。",
)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    return ok(AuthService(db).build_user_info(current_user))
