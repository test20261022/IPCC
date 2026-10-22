"""数据范围与多租户隔离测试（规则 7 确认结果）。

规则（ASSUMPTION-058）：
- 超级管理员可跨租户，tenant_id 为空表示不限租户；
- 已绑定租户的普通用户：强制收敛到自身租户，显式传其他租户返回 403；
- 未绑定租户的普通用户：视为平台账号，不受租户范围限制。
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import Tenant
from tests.conftest import auth_headers

TYPES_PREFIX = f"{settings.API_V1_PREFIX}/outbound/types"
TASKS_PREFIX = f"{settings.API_V1_PREFIX}/outbound/tasks"
OPTIONS_PREFIX = f"{settings.API_V1_PREFIX}/outbound/options"

TYPE_PERMS = ("outbound:type:list",)
TASK_PERMS = ("outbound:task:list",)


def _make_tenant(db: Session, code: str, name: str) -> Tenant:
    tenant = Tenant(code=code, name=name)
    db.add(tenant)
    db.flush()
    return tenant


def _make_type(db: Session, tenant: Tenant, code: str, name: str) -> None:
    from app.models.outbound import OutboundType

    db.add(OutboundType(tenant_id=tenant.id, code=code, name=name, level=1))
    db.flush()


def _make_task(db: Session, tenant: Tenant, name: str) -> None:
    from app.models.outbound import OutboundTask
    from app.models.outbound.enums import TaskStatus

    db.add(
        OutboundTask(tenant_id=tenant.id, task_name=name, status=TaskStatus.DRAFT)
    )
    db.flush()


class TestBoundUserScope:
    def test_list_without_tenant_defaults_to_own_tenant(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        """不传 tenant_id 时不再「看到全部租户」，而是收敛到自身租户。"""
        another = _make_tenant(db_session, "TENANT-OTHER", "另一个租户")
        _make_type(db_session, tenant, "T-MINE", "我的类型")
        _make_type(db_session, another, "T-OTHER", "别人的类型")

        token = user_token("scope_bound", *TYPE_PERMS, tenant_id=tenant.id)
        response = client.get(TYPES_PREFIX, headers=auth_headers(token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["code"] == "T-MINE"

    def test_explicit_other_tenant_forbidden(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        another = _make_tenant(db_session, "TENANT-FORBID", "越权目标租户")
        token = user_token("scope_cross", *TYPE_PERMS, tenant_id=tenant.id)

        response = client.get(
            TYPES_PREFIX, headers=auth_headers(token), params={"tenant_id": another.id}
        )
        assert response.status_code == 403
        assert response.json()["code"] == 40301
        assert "其他租户" in response.json()["message"]

    def test_own_tenant_explicit_is_allowed(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        _make_type(db_session, tenant, "T-MINE", "我的类型")
        token = user_token("scope_own", *TYPE_PERMS, tenant_id=tenant.id)

        response = client.get(
            TYPES_PREFIX, headers=auth_headers(token), params={"tenant_id": tenant.id}
        )
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1

    def test_task_list_scoped_too(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        another = _make_tenant(db_session, "TENANT-TASK", "任务第二租户")
        _make_task(db_session, tenant, "我的任务")
        _make_task(db_session, another, "别人的任务")

        token = user_token("scope_task", *TASK_PERMS, tenant_id=tenant.id)
        response = client.get(TASKS_PREFIX, headers=auth_headers(token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["task_name"] == "我的任务"


class TestPlatformAndSuperuser:
    def test_unbound_user_is_unrestricted(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        """未绑定租户的账号视为平台账号，仍可跨租户（保持既有行为）。"""
        another = _make_tenant(db_session, "TENANT-PLAT", "平台视角租户")
        _make_type(db_session, tenant, "T-A", "类型A")
        _make_type(db_session, another, "T-B", "类型B")

        token = user_token("scope_platform", *TYPE_PERMS)
        response = client.get(TYPES_PREFIX, headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["data"]["total"] >= 2

    def test_superuser_can_query_other_tenant(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        another = _make_tenant(db_session, "TENANT-ROOT", "超管目标租户")
        _make_type(db_session, another, "T-ROOT", "超管可见类型")

        token = user_token("scope_root", is_superuser=True, tenant_id=tenant.id)
        response = client.get(
            TYPES_PREFIX, headers=auth_headers(token), params={"tenant_id": another.id}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["code"] == "T-ROOT"

    def test_superuser_without_tenant_sees_all(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        another = _make_tenant(db_session, "TENANT-ROOT2", "超管第二租户")
        _make_type(db_session, tenant, "T-S1", "超管类型1")
        _make_type(db_session, another, "T-S2", "超管类型2")

        token = user_token("scope_root_all", is_superuser=True)
        response = client.get(TYPES_PREFIX, headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["data"]["total"] >= 2


class TestTenantOptions:
    def test_bound_user_only_sees_own_tenant(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        _make_tenant(db_session, "TENANT-OPT", "下拉里不该出现的租户")
        token = user_token("scope_opt", "outbound:type:list", tenant_id=tenant.id)

        response = client.get(f"{OPTIONS_PREFIX}/tenants", headers=auth_headers(token))
        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["data"]]
        assert ids == [tenant.id]

    def test_superuser_sees_all_tenants(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        other = _make_tenant(db_session, "TENANT-OPT2", "超管可见租户")
        token = user_token("scope_opt_root", is_superuser=True)

        response = client.get(f"{OPTIONS_PREFIX}/tenants", headers=auth_headers(token))
        ids = [item["id"] for item in response.json()["data"]]
        assert tenant.id in ids
        assert other.id in ids


class TestRealtimeMonitorScope:
    def test_monitor_tenant_scoped_for_bound_user(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        """实时监控是必填租户接口，绑定用户传其他租户也要被拦。"""
        another = _make_tenant(db_session, "TENANT-MON", "监控越权租户")
        token = user_token("scope_mon", "outbound:monitor:view", tenant_id=tenant.id)

        forbidden = client.get(
            f"{settings.API_V1_PREFIX}/outbound/reports/monitor",
            headers=auth_headers(token),
            params={"tenant_id": another.id},
        )
        assert forbidden.status_code == 403

        allowed = client.get(
            f"{settings.API_V1_PREFIX}/outbound/reports/monitor",
            headers=auth_headers(token),
            params={"tenant_id": tenant.id},
        )
        assert allowed.status_code == 200
        assert allowed.json()["data"]["tenant_id"] == tenant.id
