"""质检模块 RBAC 权限测试（权限码目录 + 接口拦截）。"""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.permissions import ALL_PERMISSIONS, OUTBOUND_PERMISSIONS, QC_MODULE, QC_PERMISSIONS
from tests.conftest import QC_ALL_PERMISSIONS, auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/qc"
NO_PERM = "outbound:number:list"


def test_permission_catalog_matches_expected() -> None:
    """权限目录：质检码齐全、module 正确、全量目录不丢外呼码。"""
    codes = {item.code for item in QC_PERMISSIONS}
    assert codes == set(QC_ALL_PERMISSIONS)
    assert all(item.module == QC_MODULE for item in QC_PERMISSIONS)
    assert len(QC_PERMISSIONS) == len(codes), "质检权限码不得重复"
    assert ALL_PERMISSIONS == OUTBOUND_PERMISSIONS + QC_PERMISSIONS


class TestQcPermissionGuard:
    def test_conversation_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("qc_no_conv", NO_PERM)
        response = client.get(f"{PREFIX}/conversations", headers=auth_headers(token))
        assert response.status_code == 403
        assert response.json()["code"] == 40301

    def test_conversation_create_requires_permission(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("qc_conv_list_only", "qc:conversation:list")
        response = client.post(
            f"{PREFIX}/conversations",
            headers=auth_headers(token),
            json={"tenant_id": tenant.id, "started_at": "2026-01-01T10:00:00Z"},
        )
        assert response.status_code == 403

    def test_reviewer_group_list_requires_permission(
        self, client: TestClient, user_token
    ) -> None:
        token = user_token("qc_no_reviewer", NO_PERM)
        assert (
            client.get(f"{PREFIX}/reviewer-groups", headers=auth_headers(token)).status_code == 403
        )

    def test_task_create_requires_permission(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("qc_task_list_only", "qc:task:list")
        response = client.post(
            f"{PREFIX}/tasks",
            headers=auth_headers(token),
            json={
                "tenant_id": tenant.id,
                "task_name": "无权限任务",
                "group_id": 1,
                "time_from": "2026-01-01T00:00:00Z",
                "time_to": "2026-01-02T00:00:00Z",
            },
        )
        assert response.status_code == 403

    def test_dispatch_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("qc_task_no_dispatch", "qc:task:list")
        response = client.post(f"{PREFIX}/tasks/1/dispatch", headers=auth_headers(token))
        assert response.status_code == 403

    def test_my_items_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("qc_no_work", NO_PERM)
        assert client.get(f"{PREFIX}/my/items", headers=auth_headers(token)).status_code == 403

    def test_case_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("qc_no_case", NO_PERM)
        assert client.get(f"{PREFIX}/cases", headers=auth_headers(token)).status_code == 403

    def test_report_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("qc_no_report", NO_PERM)
        assert (
            client.get(f"{PREFIX}/reports/overview", headers=auth_headers(token)).status_code == 403
        )

    def test_granted_permission_passes(self, client: TestClient, user_token) -> None:
        token = user_token("qc_conv_list", "qc:conversation:list")
        response = client.get(f"{PREFIX}/conversations", headers=auth_headers(token))
        assert response.status_code == 200

    def test_superuser_bypasses_permission(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("qc_super", is_superuser=True)
        response = client.get(f"{PREFIX}/conversations", headers=auth_headers(token))
        assert response.status_code == 200