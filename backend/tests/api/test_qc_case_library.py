"""优秀案例库测试：CRUD / 发布 / 唯一约束（QC 一期）。"""

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import QC_ALL_PERMISSIONS, auth_headers

CASES = f"{settings.API_V1_PREFIX}/qc/cases"
CONVERSATIONS = f"{settings.API_V1_PREFIX}/qc/conversations"


def _token(user_token) -> str:
    return user_token("qc_case_admin", *QC_ALL_PERMISSIONS)


def _payload(tenant_id: int, conversation_id: int, **overrides) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "title": "耐心解答账单疑问",
        "reason": "话术规范、响应及时",
        "tags": ["服务态度", "账单"],
    }
    payload.update(overrides)
    return payload


def _create_case(client: TestClient, token: str, tenant_id: int, conversation_id: int, **overrides):
    response = client.post(
        CASES, headers=auth_headers(token), json=_payload(tenant_id, conversation_id, **overrides)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


class TestCaseCreate:
    def test_create_case(
        self, client: TestClient, user_token, tenant, make_qc_conversation
    ) -> None:
        token = _token(user_token)
        conversation = make_qc_conversation(tenant.id)
        data = _create_case(client, token, tenant.id, conversation.id)
        assert data["is_published"] is False
        assert data["published_at"] is None
        assert data["tags"] == ["服务态度", "账单"]

    def test_duplicate_conversation_conflict(
        self, client: TestClient, user_token, tenant, make_qc_conversation
    ) -> None:
        token = _token(user_token)
        conversation = make_qc_conversation(tenant.id)
        _create_case(client, token, tenant.id, conversation.id)
        response = client.post(
            CASES, headers=auth_headers(token), json=_payload(tenant.id, conversation.id)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40901

    def test_missing_conversation_not_found(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        response = client.post(
            CASES, headers=auth_headers(token), json=_payload(tenant.id, 999999)
        )
        assert response.status_code == 404

    def test_delete_conversation_blocked_by_case(
        self, client: TestClient, user_token, tenant, make_qc_conversation
    ) -> None:
        token = _token(user_token)
        conversation = make_qc_conversation(tenant.id)
        _create_case(client, token, tenant.id, conversation.id)
        response = client.delete(
            f"{CONVERSATIONS}/{conversation.id}", headers=auth_headers(token)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902


class TestCaseQueryUpdate:
    def test_list_filters(
        self, client: TestClient, user_token, tenant, make_qc_conversation
    ) -> None:
        token = _token(user_token)
        first = _create_case(
            client, token, tenant.id, make_qc_conversation(tenant.id).id, title="案例A"
        )
        _create_case(
            client, token, tenant.id, make_qc_conversation(tenant.id).id,
            title="案例B", tags=["投诉处理"],
        )
        client.post(f"{CASES}/{first['id']}/publish", headers=auth_headers(token))

        published = client.get(
            CASES,
            headers=auth_headers(token),
            params={"tenant_id": tenant.id, "is_published": True},
        ).json()["data"]
        assert published["total"] == 1
        assert published["items"][0]["title"] == "案例A"

        by_tag = client.get(
            CASES, headers=auth_headers(token), params={"tenant_id": tenant.id, "tag": "投诉处理"}
        ).json()["data"]
        assert by_tag["total"] == 1
        assert by_tag["items"][0]["title"] == "案例B"

        by_keyword = client.get(
            CASES, headers=auth_headers(token), params={"tenant_id": tenant.id, "keyword": "案例A"}
        ).json()["data"]
        assert by_keyword["total"] == 1

    def test_update_and_publish(self, client: TestClient, user_token, tenant,
                                make_qc_conversation) -> None:
        token = _token(user_token)
        created = _create_case(client, token, tenant.id, make_qc_conversation(tenant.id).id)
        updated = client.put(
            f"{CASES}/{created['id']}", headers=auth_headers(token), json={"title": "改后的标题"}
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["title"] == "改后的标题"

        published = client.post(f"{CASES}/{created['id']}/publish", headers=auth_headers(token))
        assert published.status_code == 200
        assert published.json()["data"]["is_published"] is True
        assert published.json()["data"]["published_at"] is not None

    def test_publish_is_idempotent(self, client: TestClient, user_token, tenant,
                                   make_qc_conversation) -> None:
        token = _token(user_token)
        created = _create_case(client, token, tenant.id, make_qc_conversation(tenant.id).id)
        first = client.post(f"{CASES}/{created['id']}/publish", headers=auth_headers(token))
        second = client.post(f"{CASES}/{created['id']}/publish", headers=auth_headers(token))
        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["data"]["published_at"] == second.json()["data"]["published_at"]

    def test_delete_case(
        self, client: TestClient, user_token, tenant, make_qc_conversation
    ) -> None:
        token = _token(user_token)
        created = _create_case(client, token, tenant.id, make_qc_conversation(tenant.id).id)
        deleted = client.delete(f"{CASES}/{created['id']}", headers=auth_headers(token))
        assert deleted.status_code == 200
        fetched = client.get(f"{CASES}/{created['id']}", headers=auth_headers(token))
        assert fetched.status_code == 404