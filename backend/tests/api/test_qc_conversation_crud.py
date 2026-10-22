"""质检对话 CRUD / 详情 / 转写接口测试（QC 一期）。"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.qc.enums import ConversationChannel, MessageRole, MessageSource, TranscriptStatus
from app.models.qc.review import QcTask, QcTaskItem
from tests.conftest import QC_ALL_PERMISSIONS, auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/qc/conversations"


def _payload(tenant_id: int, *, started_at: str | None = None, **overrides) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "agent_name": "客服小王",
        "ext_ref_no": None,
        "channel": "CHAT",
        "started_at": started_at or "2026-01-01T10:00:00+08:00",
        "messages": [
            {"role": "AGENT", "content": "您好，请问有什么可以帮您？"},
            {"role": "CUSTOMER", "content": "我想查一下上个月的账单。"},
            {"role": "AGENT", "content": "好的，正在为您查询。"},
        ],
    }
    payload.update(overrides)
    return payload


def _token(user_token) -> str:
    return user_token("qc_conv_admin", *QC_ALL_PERMISSIONS)


def _create(client: TestClient, token: str, tenant_id: int, **overrides) -> dict:
    response = client.post(
        PREFIX, headers=auth_headers(token), json=_payload(tenant_id, **overrides)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


class TestConversationCreate:
    def test_create_with_messages(self, client: TestClient, user_token, tenant) -> None:
        data = _create(client, _token(user_token), tenant.id)
        assert data["source"] == "MANUAL"
        assert data["msg_count"] == 3
        assert data["channel"] == "CHAT"
        # 纯文本对话无需转写
        assert data["transcript_status"] == TranscriptStatus.NOT_REQUIRED.value

    def test_detail_returns_ordered_messages(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = _token(user_token)
        created = _create(client, token, tenant.id)
        response = client.get(f"{PREFIX}/{created['id']}", headers=auth_headers(token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert [item["seq"] for item in data["messages"]] == [1, 2, 3]
        assert data["messages"][0]["role"] == MessageRole.AGENT.value
        assert data["messages"][0]["source"] == MessageSource.TEXT.value
        assert data["messages"][1]["content"] == "我想查一下上个月的账单。"

    def test_messages_endpoint(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        created = _create(client, token, tenant.id)
        response = client.get(f"{PREFIX}/{created['id']}/messages", headers=auth_headers(token))
        assert response.status_code == 200
        assert len(response.json()["data"]) == 3

    def test_create_voice_requires_transcript(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = _token(user_token)
        created = _create(
            client,
            token,
            tenant.id,
            channel="VOICE",
            recording_path="qc_conversations/a.wav",
            messages=[],
        )
        assert created["transcript_status"] == TranscriptStatus.PENDING.value


class TestConversationQuery:
    def test_list_filters(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        _create(client, token, tenant.id, agent_name="客服甲", ext_ref_no="REF-1")
        _create(client, token, tenant.id, agent_name="客服乙", ext_ref_no="REF-2")

        by_agent = client.get(
            PREFIX, headers=auth_headers(token), params={"agent_name": "客服甲"}
        ).json()["data"]
        assert by_agent["total"] == 1
        assert by_agent["items"][0]["agent_name"] == "客服甲"

        by_keyword = client.get(
            PREFIX, headers=auth_headers(token), params={"keyword": "REF-2"}
        ).json()["data"]
        assert by_keyword["total"] == 1
        assert by_keyword["items"][0]["ext_ref_no"] == "REF-2"

    def test_list_tenant_scope(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        _create(client, token, tenant.id)
        response = client.get(PREFIX, headers=auth_headers(token), params={"tenant_id": tenant.id})
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1


class TestConversationUpdateDelete:
    def test_update_recomputes_transcript_status(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = _token(user_token)
        created = _create(client, token, tenant.id)
        response = client.put(
            f"{PREFIX}/{created['id']}",
            headers=auth_headers(token),
            json={"channel": "VOICE", "recording_path": "qc_conversations/b.wav"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["channel"] == ConversationChannel.VOICE.value
        assert data["transcript_status"] == TranscriptStatus.PENDING.value

    def test_delete_then_get_404(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        created = _create(client, token, tenant.id)
        deleted = client.delete(f"{PREFIX}/{created['id']}", headers=auth_headers(token))
        assert deleted.status_code == 200
        fetched = client.get(f"{PREFIX}/{created['id']}", headers=auth_headers(token))
        assert fetched.status_code == 404

    def test_delete_blocked_when_referenced_by_item(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        token = _token(user_token)
        created = _create(client, token, tenant.id)
        now = datetime.now(timezone.utc)
        task = QcTask(
            tenant_id=tenant.id,
            task_name="引用任务",
            time_from=now - timedelta(hours=1),
            time_to=now + timedelta(hours=1),
        )
        db_session.add(task)
        db_session.flush()
        db_session.add(
            QcTaskItem(tenant_id=tenant.id, task_id=task.id, conversation_id=created["id"])
        )
        db_session.flush()

        response = client.delete(f"{PREFIX}/{created['id']}", headers=auth_headers(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40902


class TestConversationTranscribe:
    def test_transcribe_voice_conversation(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        created = _create(
            client,
            token,
            tenant.id,
            channel="VOICE",
            recording_path="qc_conversations/a.wav",
            messages=[],
        )
        response = client.post(f"{PREFIX}/{created['id']}/transcribe", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["transcript_status"] == TranscriptStatus.SUCCESS.value
        assert data["transcript_engine"] == "mock"
        assert data["message_count"] > 0

        messages = client.get(
            f"{PREFIX}/{created['id']}/messages", headers=auth_headers(token)
        ).json()["data"]
        assert len(messages) == data["message_count"]
        assert all(item["source"] == MessageSource.ASR.value for item in messages)

    def test_transcribe_text_conversation_rejected(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = _token(user_token)
        created = _create(client, token, tenant.id)
        response = client.post(f"{PREFIX}/{created['id']}/transcribe", headers=auth_headers(token))
        assert response.status_code == 400
        assert response.json()["code"] == 40001