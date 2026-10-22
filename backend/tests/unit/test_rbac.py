"""权限校验依赖单元测试（纯内存构造，不依赖数据库）。"""

import pytest

from app.api.deps import require_permission
from app.core.exceptions import Forbidden
from app.models.user import Permission, Role, User

CHECKER = require_permission("outbound:number:list", "outbound:number:create")


def _make_user(*, is_superuser: bool = False, permissions: list[str] | None = None) -> User:
    user = User(username="u", password_hash="x", is_superuser=is_superuser)
    if permissions is None:
        return user

    role = Role(name="r", code="r")
    for code in permissions:
        role.permissions.append(Permission(name=code, code=code, module="outbound"))
    user.roles.append(role)
    return user


def test_superuser_bypasses_permission_check() -> None:
    user = _make_user(is_superuser=True)
    assert CHECKER(current_user=user) is user


def test_user_with_matching_permission_passes() -> None:
    user = _make_user(permissions=["outbound:number:list"])
    assert CHECKER(current_user=user) is user


def test_user_with_any_one_of_permissions_passes() -> None:
    user = _make_user(permissions=["outbound:number:create"])
    assert CHECKER(current_user=user) is user


def test_user_without_permission_is_rejected() -> None:
    user = _make_user(permissions=["outbound:scene:list"])
    with pytest.raises(Forbidden) as exc_info:
        CHECKER(current_user=user)
    assert "outbound:number:list" in str(exc_info.value)


def test_user_with_no_role_is_rejected() -> None:
    with pytest.raises(Forbidden):
        CHECKER(current_user=_make_user())
