"""外呼号码接口测试（OB-001 / OB-005）。"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import OutboundTaskNumber
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound/numbers"

ALL_NUMBER_PERMS = (
    "outbound:number:list",
    "outbound:number:create",
    "outbound:number:update",
    "outbound:number:delete",
    "outbound:number:use",
)


def _payload(tenant_id: int, **overrides) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "display_name": "客服外显",
        "caller_number": "02166668888",
        "usage_limit": 10,
    }
    payload.update(overrides)
    return payload


class TestNumberPermissions:
    def test_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("num_no_perm", "outbound:type:list")
        assert client.get(PREFIX, headers=auth_headers(token)).status_code == 403

    def test_consume_requires_use_permission(
        self, client: TestClient, user_token, outbound_number
    ) -> None:
        token = user_token("num_no_use", "outbound:number:list", "outbound:number:update")
        response = client.post(
            f"{PREFIX}/{outbound_number.id}/consume", headers=auth_headers(token)
        )
        assert response.status_code == 403
        assert response.json()["code"] == 40301

    def test_consume_allowed_with_use_permission(
        self, client: TestClient, user_token, outbound_number
    ) -> None:
        token = user_token("num_user", "outbound:number:use")
        response = client.post(
            f"{PREFIX}/{outbound_number.id}/consume", headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json()["data"]["used_count"] == 1


class TestNumberCreate:
    def test_create_success(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("num_creator", "outbound:number:create")
        response = client.post(PREFIX, headers=auth_headers(token), json=_payload(tenant.id))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["caller_number"] == "02166668888"
        assert data["used_count"] == 0
        assert data["usage_limit"] == 10
        assert data["status"] == "ENABLED"

    def test_unlimited_usage(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("num_unlimited", "outbound:number:create")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(tenant.id, usage_limit=None)
        )
        assert response.status_code == 200
        assert response.json()["data"]["usage_limit"] is None

    def test_invalid_caller_number_format(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("num_bad_format", "outbound:number:create")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(tenant.id, caller_number="abc-123")
        )
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_blank_display_name_rejected(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("num_blank_name", "outbound:number:create")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(tenant.id, display_name="   ")
        )
        assert response.status_code == 400

    def test_duplicate_caller_number_in_same_tenant(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("num_dup", "outbound:number:create")
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(tenant.id, caller_number=outbound_number.caller_number),
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40901

    def test_same_caller_number_allowed_in_other_tenant(
        self, client: TestClient, user_token, tenant, outbound_number, db_session: Session
    ) -> None:
        from app.models.outbound import Tenant

        other = Tenant(code="TENANT-002", name="另一租户")
        db_session.add(other)
        db_session.flush()

        token = user_token("num_other_tenant", *ALL_NUMBER_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(other.id, caller_number=outbound_number.caller_number),
        )
        assert response.status_code == 200
        assert response.json()["data"]["tenant_id"] == other.id

    def test_unknown_tenant(self, client: TestClient, user_token) -> None:
        token = user_token("num_bad_tenant", "outbound:number:create")
        response = client.post(PREFIX, headers=auth_headers(token), json=_payload(999999))
        assert response.status_code == 404

    def test_disabled_tenant(self, client: TestClient, user_token, disabled_tenant) -> None:
        token = user_token("num_off_tenant", "outbound:number:create")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(disabled_tenant.id)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902


class TestNumberQuery:
    def test_list_shows_usage(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("num_lister", "outbound:number:list")
        response = client.get(
            PREFIX, headers=auth_headers(token), params={"tenant_id": tenant.id}
        )
        assert response.status_code == 200
        item = response.json()["data"]["items"][0]
        assert item["used_count"] == 0
        assert item["usage_limit"] == 2

    def test_filter_by_caller_number(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("num_filter", "outbound:number:list")
        response = client.get(
            PREFIX, headers=auth_headers(token), params={"caller_number": "8888"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1

    def test_filter_with_no_match(self, client: TestClient, user_token) -> None:
        token = user_token("num_no_match", "outbound:number:list")
        response = client.get(
            PREFIX, headers=auth_headers(token), params={"caller_number": "0000000"}
        )
        assert response.json()["data"]["total"] == 0

    def test_detail_not_found(self, client: TestClient, user_token) -> None:
        token = user_token("num_detail_404", "outbound:number:list")
        assert client.get(f"{PREFIX}/999999", headers=auth_headers(token)).status_code == 404


class TestNumberUpdate:
    def test_update_display_name_and_limit(
        self, client: TestClient, user_token, outbound_number
    ) -> None:
        token = user_token("num_updater", "outbound:number:update")
        response = client.put(
            f"{PREFIX}/{outbound_number.id}",
            headers=auth_headers(token),
            json={"display_name": "新外显", "usage_limit": 99},
        )
        assert response.status_code == 200
        assert response.json()["data"]["display_name"] == "新外显"
        assert response.json()["data"]["usage_limit"] == 99

    def test_caller_number_is_immutable(
        self, client: TestClient, user_token, outbound_number
    ) -> None:
        token = user_token("num_immutable", "outbound:number:update")
        response = client.put(
            f"{PREFIX}/{outbound_number.id}",
            headers=auth_headers(token),
            json={"caller_number": "02100001111"},
        )
        assert response.status_code == 400

    def test_status_change(self, client: TestClient, user_token, outbound_number) -> None:
        token = user_token("num_status", "outbound:number:update")
        response = client.put(
            f"{PREFIX}/{outbound_number.id}/status",
            headers=auth_headers(token),
            json={"status": "DISABLED"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "DISABLED"


class TestNumberConsume:
    def test_consume_increments_and_stops_at_limit(
        self, client: TestClient, user_token, outbound_number
    ) -> None:
        token = user_token("num_consume", *ALL_NUMBER_PERMS)

        first = client.post(f"{PREFIX}/{outbound_number.id}/consume", headers=auth_headers(token))
        assert first.status_code == 200
        assert first.json()["data"]["used_count"] == 1

        second = client.post(f"{PREFIX}/{outbound_number.id}/consume", headers=auth_headers(token))
        assert second.status_code == 200
        assert second.json()["data"]["used_count"] == 2

        exhausted = client.post(
            f"{PREFIX}/{outbound_number.id}/consume", headers=auth_headers(token)
        )
        assert exhausted.status_code == 409
        assert exhausted.json()["code"] == 40903

    def test_consume_step_over_limit(self, client: TestClient, user_token, outbound_number) -> None:
        token = user_token("num_step", *ALL_NUMBER_PERMS)
        response = client.post(
            f"{PREFIX}/{outbound_number.id}/consume",
            headers=auth_headers(token),
            params={"step": 5},
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40903

    def test_consume_disabled_number(self, client: TestClient, user_token, outbound_number) -> None:
        token = user_token("num_consume_off", *ALL_NUMBER_PERMS)
        client.put(
            f"{PREFIX}/{outbound_number.id}/status",
            headers=auth_headers(token),
            json={"status": "DISABLED"},
        )
        response = client.post(
            f"{PREFIX}/{outbound_number.id}/consume", headers=auth_headers(token)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_consume_unknown_number(self, client: TestClient, user_token) -> None:
        token = user_token("num_consume_404", *ALL_NUMBER_PERMS)
        response = client.post(f"{PREFIX}/999999/consume", headers=auth_headers(token))
        assert response.status_code == 404
        assert response.json()["code"] == 40401

    def test_unlimited_number_never_exhausts(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("num_consume_unlimited", *ALL_NUMBER_PERMS)
        created = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(tenant.id, caller_number="02155556666", usage_limit=None),
        ).json()["data"]

        for expected in range(1, 4):
            response = client.post(
                f"{PREFIX}/{created['id']}/consume", headers=auth_headers(token)
            )
            assert response.status_code == 200
            assert response.json()["data"]["used_count"] == expected


class TestNumberDeleteRules:
    def test_delete_referenced_number_rejected(
        self,
        client: TestClient,
        user_token,
        tenant,
        outbound_number,
        outbound_task,
        db_session: Session,
    ) -> None:
        db_session.add(
            OutboundTaskNumber(
                tenant_id=tenant.id, task_id=outbound_task.id, number_id=outbound_number.id
            )
        )
        db_session.flush()

        token = user_token("num_del_ref", *ALL_NUMBER_PERMS)
        response = client.delete(f"{PREFIX}/{outbound_number.id}", headers=auth_headers(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40904

    def test_delete_unreferenced_number(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("num_del_ok", *ALL_NUMBER_PERMS)
        created = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(tenant.id, caller_number="02144443333"),
        ).json()["data"]

        deleted = client.delete(f"{PREFIX}/{created['id']}", headers=auth_headers(token))
        assert deleted.status_code == 200
        fetched = client.get(f"{PREFIX}/{created['id']}", headers=auth_headers(token))
        assert fetched.status_code == 404
