"""外呼类型接口测试（OB-004）。"""

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound/types"


def _create_payload(tenant_id: int, **overrides) -> dict:
    payload = {"tenant_id": tenant_id, "code": "TP-NEW", "name": "新类型", "level": 1}
    payload.update(overrides)
    return payload


class TestTypePermissions:
    def test_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("type_no_perm", "outbound:scene:list")
        response = client.get(PREFIX, headers=auth_headers(token))
        assert response.status_code == 403
        assert response.json()["code"] == 40301

    def test_create_requires_create_permission(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("type_only_list", "outbound:type:list")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_create_payload(tenant.id)
        )
        assert response.status_code == 403

    def test_delete_requires_delete_permission(
        self, client: TestClient, user_token, outbound_type
    ) -> None:
        token = user_token("type_only_create", "outbound:type:create")
        response = client.delete(f"{PREFIX}/{outbound_type.id}", headers=auth_headers(token))
        assert response.status_code == 403

    def test_superuser_bypasses_permission(self, client: TestClient, user_token) -> None:
        token = user_token("type_super", is_superuser=True)
        response = client.get(PREFIX, headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["code"] == 0


class TestTypeCrud:
    def test_create_success(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("type_creator", "outbound:type:create")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_create_payload(tenant.id, code="TP-C1")
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["code"] == "TP-C1"
        assert data["level"] == 1
        assert data["status"] == "ENABLED"
        assert data["id"] > 0

    def test_create_duplicate_code_conflict(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("type_dup", "outbound:type:create")
        body = _create_payload(tenant.id, code="TP-DUP")
        assert client.post(PREFIX, headers=auth_headers(token), json=body).status_code == 200

        response = client.post(PREFIX, headers=auth_headers(token), json=body)
        assert response.status_code == 409
        assert response.json()["code"] == 40901

    def test_create_with_unknown_tenant(self, client: TestClient, user_token) -> None:
        token = user_token("type_bad_tenant", "outbound:type:create")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_create_payload(999999, code="TP-X")
        )
        assert response.status_code == 404
        assert response.json()["code"] == 40401

    def test_create_with_disabled_tenant(
        self, client: TestClient, user_token, disabled_tenant
    ) -> None:
        token = user_token("type_off_tenant", "outbound:type:create")
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_create_payload(disabled_tenant.id, code="TP-Y"),
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_second_level_requires_parent(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("type_lv2", "outbound:type:create")
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_create_payload(tenant.id, code="TP-L2", level=2),
        )
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_first_level_rejects_parent(
        self, client: TestClient, user_token, tenant, outbound_type
    ) -> None:
        token = user_token("type_lv1_parent", "outbound:type:create")
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_create_payload(tenant.id, code="TP-L1P", level=1, parent_id=outbound_type.id),
        )
        assert response.status_code == 400

    def test_parent_must_be_first_level(
        self, client: TestClient, user_token, tenant, outbound_type
    ) -> None:
        token = user_token("type_parent_lv2", "outbound:type:create")
        child = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_create_payload(
                tenant.id, code="TP-CHILD", level=2, parent_id=outbound_type.id
            ),
        ).json()["data"]

        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_create_payload(tenant.id, code="TP-GRAND", level=2, parent_id=child["id"]),
        )
        assert response.status_code == 400
        assert "一级类型" in response.json()["message"]

    def test_get_detail_and_not_found(self, client: TestClient, user_token, outbound_type) -> None:
        token = user_token("type_detail", "outbound:type:list")
        response = client.get(f"{PREFIX}/{outbound_type.id}", headers=auth_headers(token))
        assert response.status_code == 200

        response = client.get(f"{PREFIX}/999999", headers=auth_headers(token))
        assert response.status_code == 404
        assert response.json()["code"] == 40401

    def test_update_success(self, client: TestClient, user_token, outbound_type) -> None:
        token = user_token("type_updater", "outbound:type:update")
        response = client.put(
            f"{PREFIX}/{outbound_type.id}",
            headers=auth_headers(token),
            json={"name": "改名后的类型"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "改名后的类型"
        assert response.json()["data"]["code"] == "TYPE-001"

    def test_update_rejects_unknown_field(
        self, client: TestClient, user_token, outbound_type
    ) -> None:
        token = user_token("type_bad_field", "outbound:type:update")
        response = client.put(
            f"{PREFIX}/{outbound_type.id}",
            headers=auth_headers(token),
            json={"unknown_field": 1},
        )
        assert response.status_code == 400

    def test_status_change(self, client: TestClient, user_token, outbound_type) -> None:
        token = user_token("type_status", "outbound:type:update")
        response = client.put(
            f"{PREFIX}/{outbound_type.id}/status",
            headers=auth_headers(token),
            json={"status": "DISABLED"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "DISABLED"

    def test_status_change_invalid_value(
        self, client: TestClient, user_token, outbound_type
    ) -> None:
        token = user_token("type_status_bad", "outbound:type:update")
        response = client.put(
            f"{PREFIX}/{outbound_type.id}/status",
            headers=auth_headers(token),
            json={"status": "NOT_A_STATUS"},
        )
        assert response.status_code == 400


class TestTypeList:
    def test_pagination_and_filter(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("type_lister", "outbound:type:create", "outbound:type:list")
        for index in range(3):
            client.post(
                PREFIX,
                headers=auth_headers(token),
                json=_create_payload(tenant.id, code=f"TP-P{index}", name=f"分页类型{index}"),
            )

        response = client.get(
            PREFIX,
            headers=auth_headers(token),
            params={"tenant_id": tenant.id, "page": 2, "page_size": 2},
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["total"] == 3
        assert body["page"] == 2
        assert body["page_size"] == 2
        assert len(body["items"]) == 1

    def test_name_filter(self, client: TestClient, user_token, tenant, outbound_type) -> None:
        token = user_token("type_name_filter", "outbound:type:list")
        response = client.get(
            PREFIX,
            headers=auth_headers(token),
            params={"tenant_id": tenant.id, "name": "营销"},
        )
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert [item["code"] for item in items] == ["TYPE-001"]

    def test_page_size_upper_bound(self, client: TestClient, user_token) -> None:
        token = user_token("type_page_limit", "outbound:type:list")
        response = client.get(
            PREFIX, headers=auth_headers(token), params={"page_size": settings.MAX_PAGE_SIZE + 1}
        )
        assert response.status_code == 400


class TestTypeReferenceRules:
    def test_cannot_delete_type_with_child(
        self, client: TestClient, user_token, tenant, outbound_type
    ) -> None:
        token = user_token("type_del_child", "outbound:type:create", "outbound:type:delete")
        client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_create_payload(tenant.id, code="TP-C", level=2, parent_id=outbound_type.id),
        )

        response = client.delete(f"{PREFIX}/{outbound_type.id}", headers=auth_headers(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40904

    def test_cannot_delete_type_used_by_scene(
        self, client: TestClient, user_token, outbound_type, outbound_scene
    ) -> None:
        token = user_token("type_del_scene", "outbound:type:delete")
        response = client.delete(f"{PREFIX}/{outbound_type.id}", headers=auth_headers(token))
        assert response.status_code == 409
        assert "外呼场景" in response.json()["message"]

    def test_cannot_delete_type_used_by_task(
        self, client: TestClient, user_token, outbound_type, outbound_task
    ) -> None:
        token = user_token("type_del_task", "outbound:type:delete")
        response = client.delete(f"{PREFIX}/{outbound_type.id}", headers=auth_headers(token))
        assert response.status_code == 409

    def test_delete_unreferenced_type(self, client: TestClient, user_token, tenant) -> None:
        token = user_token(
            "type_del_ok", "outbound:type:create", "outbound:type:delete", "outbound:type:list"
        )
        created = client.post(
            PREFIX, headers=auth_headers(token), json=_create_payload(tenant.id, code="TP-FREE")
        ).json()["data"]

        deleted = client.delete(f"{PREFIX}/{created['id']}", headers=auth_headers(token))
        assert deleted.status_code == 200
        fetched = client.get(f"{PREFIX}/{created['id']}", headers=auth_headers(token))
        assert fetched.status_code == 404

    def test_referenced_type_cannot_change_code(
        self, client: TestClient, user_token, outbound_type, outbound_scene
    ) -> None:
        token = user_token("type_ref_code", "outbound:type:update")
        response = client.put(
            f"{PREFIX}/{outbound_type.id}",
            headers=auth_headers(token),
            json={"code": "TP-CHANGED"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40904
        assert "code" in response.json()["message"]

    def test_referenced_type_can_rename(
        self, client: TestClient, user_token, outbound_type, outbound_scene
    ) -> None:
        token = user_token("type_ref_rename", "outbound:type:update")
        response = client.put(
            f"{PREFIX}/{outbound_type.id}",
            headers=auth_headers(token),
            json={"name": "仅改名称", "sort_order": 5},
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "仅改名称"

    def test_resending_unchanged_code_is_allowed(
        self, client: TestClient, user_token, outbound_type, outbound_scene
    ) -> None:
        """引用后原样回传 code 不算破坏性修改（前端编辑表单必然带上 code）。"""
        token = user_token("type_ref_noop", "outbound:type:update")
        response = client.put(
            f"{PREFIX}/{outbound_type.id}",
            headers=auth_headers(token),
            json={"code": outbound_type.code, "name": "改名同时回传原编码"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["code"] == outbound_type.code

    def test_unreferenced_type_can_change_code(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token(
            "type_free_code", "outbound:type:create", "outbound:type:update"
        )
        created = client.post(
            PREFIX, headers=auth_headers(token), json=_create_payload(tenant.id, code="TP-OLD")
        ).json()["data"]

        response = client.put(
            f"{PREFIX}/{created['id']}", headers=auth_headers(token), json={"code": "TP-LATEST"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["code"] == "TP-LATEST"
