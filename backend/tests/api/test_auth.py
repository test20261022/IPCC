"""认证接口测试：登录 / 刷新 / 登出 / 当前用户。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import is_available as cache_available
from app.core.config import settings
from app.core.security import hash_password
from app.models.log import LoginLog
from app.models.user import User
from tests.conftest import auth_headers, login

PREFIX = settings.API_V1_PREFIX


class TestLogin:
    def test_login_success(self, client: TestClient, admin_user: User) -> None:
        response = client.post(
            f"{PREFIX}/auth/login",
            json={"username": "admin_test", "password": "Admin@123456"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["token_type"] == "bearer"
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def test_login_wrong_password(self, client: TestClient, admin_user: User) -> None:
        response = client.post(
            f"{PREFIX}/auth/login",
            json={"username": "admin_test", "password": "wrong-password"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == 40101

    def test_login_unknown_user(self, client: TestClient) -> None:
        response = client.post(
            f"{PREFIX}/auth/login",
            json={"username": "not-exists", "password": "whatever"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == 40101

    def test_login_inactive_user(self, client: TestClient, db_session: Session) -> None:
        db_session.add(
            User(
                username="disabled_user",
                password_hash=hash_password("Admin@123456"),
                nickname="停用用户",
                is_active=False,
            )
        )
        db_session.flush()

        response = client.post(
            f"{PREFIX}/auth/login",
            json={"username": "disabled_user", "password": "Admin@123456"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == 40301

    def test_login_missing_field_returns_param_error(self, client: TestClient) -> None:
        response = client.post(f"{PREFIX}/auth/login", json={"username": "admin_test"})
        assert response.status_code == 400
        assert response.json()["code"] == 40001


class TestCurrentUser:
    def test_me_without_token(self, client: TestClient) -> None:
        response = client.get(f"{PREFIX}/auth/me")
        assert response.status_code == 401
        assert response.json()["code"] == 40101

    def test_me_with_invalid_token(self, client: TestClient) -> None:
        response = client.get(f"{PREFIX}/auth/me", headers=auth_headers("invalid.token.value"))
        assert response.status_code == 401
        assert response.json()["code"] == 40101

    def test_me_with_refresh_token_rejected(self, client: TestClient, admin_user: User) -> None:
        login_response = client.post(
            f"{PREFIX}/auth/login",
            json={"username": "admin_test", "password": "Admin@123456"},
        )
        refresh_token = login_response.json()["data"]["refresh_token"]

        response = client.get(f"{PREFIX}/auth/me", headers=auth_headers(refresh_token))
        assert response.status_code == 401

    def test_me_returns_superuser_info(self, client: TestClient, admin_user: User) -> None:
        token = login(client, "admin_test", "Admin@123456")
        response = client.get(f"{PREFIX}/auth/me", headers=auth_headers(token))

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["username"] == "admin_test"
        assert data["is_superuser"] is True
        assert data["roles"] == []

    def test_me_returns_role_permissions(self, client: TestClient, normal_user: User) -> None:
        token = login(client, "user_test", "User@123456")
        response = client.get(f"{PREFIX}/auth/me", headers=auth_headers(token))

        data = response.json()["data"]
        assert data["is_superuser"] is False
        assert data["permissions"] == ["outbound:number:list"]
        assert [role["code"] for role in data["roles"]] == ["operator"]


class TestRefresh:
    def test_refresh_success(self, client: TestClient, admin_user: User) -> None:
        login_response = client.post(
            f"{PREFIX}/auth/login",
            json={"username": "admin_test", "password": "Admin@123456"},
        )
        refresh_token = login_response.json()["data"]["refresh_token"]

        response = client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        assert response.json()["data"]["access_token"]

    def test_refresh_with_access_token_rejected(self, client: TestClient, admin_user: User) -> None:
        access_token = login(client, "admin_test", "Admin@123456")
        response = client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": access_token})
        assert response.status_code == 401

    def test_refresh_with_garbage_rejected(self, client: TestClient) -> None:
        response = client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": "garbage"})
        assert response.status_code == 401


class TestLogout:
    @pytest.mark.skipif(not cache_available(), reason="Redis 不可用时登出黑名单不生效（降级）")
    def test_logout_then_access_rejected(self, client: TestClient, admin_user: User) -> None:
        token = login(client, "admin_test", "Admin@123456")

        logout_response = client.post(f"{PREFIX}/auth/logout", headers=auth_headers(token))
        assert logout_response.status_code == 200
        assert logout_response.json()["code"] == 0

        me_response = client.get(f"{PREFIX}/auth/me", headers=auth_headers(token))
        assert me_response.status_code == 401

    def test_logout_without_token(self, client: TestClient) -> None:
        response = client.post(f"{PREFIX}/auth/logout")
        assert response.status_code == 401


class TestErrorFormat:
    def test_unknown_route_uses_unified_format(self, client: TestClient) -> None:
        response = client.get(f"{PREFIX}/not-exists")
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == 40401
        assert "message" in body and "data" in body

    def test_health(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ok"


class TestLoginLogPersisted:
    """登录日志必须落库，失败日志不得随异常回滚（§70）。"""

    def test_successful_login_writes_log(
        self, client: TestClient, admin_user: User, db_session: Session
    ) -> None:
        client.post(
            f"{PREFIX}/auth/login",
            json={"username": "admin_test", "password": "Admin@123456"},
        )

        logs = _login_logs(db_session, "admin_test")
        assert len(logs) == 1
        assert logs[0].success is True
        assert logs[0].user_id == admin_user.id

    def test_failed_login_writes_log(
        self, client: TestClient, admin_user: User, db_session: Session
    ) -> None:
        client.post(
            f"{PREFIX}/auth/login",
            json={"username": "admin_test", "password": "wrong-password"},
        )

        logs = _login_logs(db_session, "admin_test")
        assert len(logs) == 1
        assert logs[0].success is False
        assert logs[0].message == "用户名或密码错误"

    def test_unknown_user_login_writes_log(
        self, client: TestClient, db_session: Session
    ) -> None:
        client.post(
            f"{PREFIX}/auth/login",
            json={"username": "ghost_user", "password": "whatever"},
        )

        logs = _login_logs(db_session, "ghost_user")
        assert len(logs) == 1
        assert logs[0].success is False
        assert logs[0].user_id is None

    def test_inactive_user_login_writes_log(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add(
            User(
                username="disabled_log_user",
                password_hash=hash_password("Admin@123456"),
                nickname="停用用户",
                is_active=False,
            )
        )
        db_session.flush()

        client.post(
            f"{PREFIX}/auth/login",
            json={"username": "disabled_log_user", "password": "Admin@123456"},
        )

        logs = _login_logs(db_session, "disabled_log_user")
        assert len(logs) == 1
        assert logs[0].success is False
        assert logs[0].message == "账号已停用"


def _login_logs(db_session: Session, username: str) -> list[LoginLog]:
    statement = select(LoginLog).where(LoginLog.username == username)
    return list(db_session.execute(statement).scalars().all())
