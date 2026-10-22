"""认证相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(min_length=1, max_length=64, description="用户名")
    password: str = Field(min_length=1, max_length=128, description="密码")


class RefreshRequest(BaseModel):
    """刷新令牌请求。"""

    refresh_token: str = Field(min_length=1, description="refresh_token")


class LogoutRequest(BaseModel):
    """登出请求：可选传入 refresh_token 一并失效。"""

    refresh_token: str | None = Field(default=None, description="refresh_token")


class TokenResponse(BaseModel):
    """令牌响应。"""

    access_token: str = Field(description="访问令牌")
    refresh_token: str = Field(description="刷新令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(description="access_token 有效期（秒）")


class RoleBrief(BaseModel):
    """角色简要信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class UserInfo(BaseModel):
    """当前登录用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str
    email: str | None = None
    phone: str | None = None
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None
    roles: list[RoleBrief] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
