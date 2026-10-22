"""外呼下拉选项接口测试。"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import OutboundTask
from app.models.outbound.enums import TaskStatus
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound/options"


class TestTenantOptions:
    def test_requires_login(self, client: TestClient) -> None:
        response = client.get(f"{PREFIX}/tenants")
        assert response.status_code == 401
        assert response.json()["code"] == 40101

    def test_returns_enabled_tenants_only(
        self, client: TestClient, user_token, tenant, disabled_tenant
    ) -> None:
        token = user_token("option_user", "outbound:type:list")
        response = client.get(f"{PREFIX}/tenants", headers=auth_headers(token))

        assert response.status_code == 200
        data = response.json()["data"]
        codes = [item["code"] for item in data]
        assert tenant.code in codes
        assert disabled_tenant.code not in codes
        assert set(data[0].keys()) == {"id", "code", "name"}


class TestTaskOptions:
    """任务下拉走选项接口，供不需要 outbound:task:list 权限的页面使用。"""

    def test_requires_login(self, client: TestClient, tenant) -> None:
        response = client.get(f"{PREFIX}/tasks", params={"tenant_id": tenant.id})
        assert response.status_code == 401

    def test_requires_tenant_id(self, client: TestClient, user_token) -> None:
        token = user_token("option_task_no_tenant", "outbound:report:list")
        response = client.get(f"{PREFIX}/tasks", headers=auth_headers(token))
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_no_task_list_permission_needed(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        db_session.add(
            OutboundTask(tenant_id=tenant.id, task_name="报表筛选任务", status=TaskStatus.DRAFT)
        )
        db_session.flush()

        token = user_token("option_task", "outbound:report:list", tenant_id=tenant.id)
        response = client.get(
            f"{PREFIX}/tasks", headers=auth_headers(token), params={"tenant_id": tenant.id}
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert [item["task_name"] for item in data] == ["报表筛选任务"]
        assert set(data[0].keys()) == {"id", "tenant_id", "task_name"}

    def test_bound_user_cannot_read_other_tenant(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        from app.models.outbound import Tenant

        another = Tenant(code="TENANT-OPT-TASK", name="任务下拉越权租户")
        db_session.add(another)
        db_session.flush()

        token = user_token("option_task_cross", "outbound:report:list", tenant_id=tenant.id)
        response = client.get(
            f"{PREFIX}/tasks", headers=auth_headers(token), params={"tenant_id": another.id}
        )
        assert response.status_code == 403
