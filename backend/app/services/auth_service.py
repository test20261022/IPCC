"""认证服务：登录 / 刷新 / 登出 / 当前用户信息。"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.cache import blacklist_token, is_token_blacklisted
from app.core.exceptions import Forbidden, Unauthorized
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.log import LoginLog
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LogoutRequest, RoleBrief, TokenResponse, UserInfo

logger = logging.getLogger(__name__)

# token 已过期时仍需保留黑名单语义，这里按最长有效期兜底（refresh 有效期）
_REFRESH_TTL_SECONDS = 7 * 24 * 3600


class AuthService:
    """认证业务。事务在本层提交（§55）。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = UserRepository(db)

    # ---------- 登录 ----------

    def login(
        self,
        *,
        username: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        user = self.repo.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            self._write_login_log(None, username, ip, user_agent, False, "用户名或密码错误")
            # 失败日志必须独立落库，不能随随后的异常一起回滚
            self.db.commit()
            raise Unauthorized("用户名或密码错误")

        if not user.is_active:
            self._write_login_log(user.id, username, ip, user_agent, False, "账号已停用")
            self.db.commit()
            raise Forbidden("账号已停用")

        access_token, _, expires_in = create_access_token(user.id)
        refresh_token, _, _ = create_refresh_token(user.id)

        user.last_login_at = datetime.now(timezone.utc)
        self._write_login_log(user.id, user.username, ip, user_agent, True, "登录成功")
        self.db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

    # ---------- 刷新 ----------

    def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token, expected_type=TOKEN_TYPE_REFRESH)
        if is_token_blacklisted(str(payload.get("jti", ""))):
            raise Unauthorized("登录已失效，请重新登录")

        user_id = self._parse_subject(payload)
        user = self.repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise Unauthorized("用户不存在或已停用")

        access_token, _, expires_in = create_access_token(user.id)
        new_refresh_token, _, _ = create_refresh_token(user.id)
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

    # ---------- 登出 ----------

    def logout(self, *, access_jti: str, payload: LogoutRequest | None = None) -> None:
        """将 access_token 拉黑；若提供 refresh_token 则一并拉黑。"""
        blacklist_token(access_jti, _REFRESH_TTL_SECONDS)

        if payload and payload.refresh_token:
            try:
                refresh_payload = decode_token(
                    payload.refresh_token, expected_type=TOKEN_TYPE_REFRESH
                )
                blacklist_token(str(refresh_payload.get("jti", "")), _REFRESH_TTL_SECONDS)
            except Unauthorized:
                logger.info("登出时 refresh_token 已失效，忽略")

    # ---------- 用户信息 ----------

    def build_user_info(self, user: User) -> UserInfo:
        permissions = sorted(self.repo.get_permission_codes(user.id))
        return UserInfo(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            phone=user.phone,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            last_login_at=user.last_login_at,
            roles=[RoleBrief.model_validate(role) for role in user.roles],
            permissions=permissions,
        )

    # ---------- 内部 ----------

    @staticmethod
    def _parse_subject(payload: dict) -> int:
        try:
            return int(str(payload.get("sub", "")))
        except (TypeError, ValueError) as exc:
            raise Unauthorized("凭据无效") from exc

    def _write_login_log(
        self,
        user_id: int | None,
        username: str,
        ip: str | None,
        user_agent: str | None,
        success: bool,
        message: str,
    ) -> None:
        self.db.add(
            LoginLog(
                user_id=user_id,
                username=username,
                ip=ip,
                user_agent=(user_agent or "")[:255] or None,
                success=success,
                message=message,
            )
        )
