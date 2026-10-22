"""会话与看板接口测试（OB-021 / OB-023 / §37 / §40 / §41）。"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import (
    Agent,
    CallHistory,
    OutboundList,
    OutboundNumber,
    OutboundRecord,
    OutboundSession,
    OutboundTask,
    OutboundTaskNumber,
)
from app.models.outbound.enums import (
    AgentStatus,
    CallStatus,
    DispatchMode,
    ListStatus,
    NumberSelectStrategy,
    RecordStatus,
    SessionStatus,
    TaskStatus,
)
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound"
ALL_SESSION_PERMS = (
    "outbound:session:list",
    "outbound:session:call",
    "outbound:list:list",
)
PHONE_A = "13800000001"
PHONE_B = "13800001111"


@pytest.fixture
def env(db_session: Session, tenant, outbound_type, outbound_scene, make_user):
    """会话/看板环境：任务（OrderID 优先）+ 名单 + 执行记录 + 坐席 + 会话。"""
    number = OutboundNumber(
        tenant_id=tenant.id, display_name="看板号码", caller_number="02112347777", usage_limit=50
    )
    db_session.add(number)

    task = OutboundTask(
        tenant_id=tenant.id,
        task_name="会话任务",
        type_id=outbound_type.id,
        scene_id=outbound_scene.id,
        status=TaskStatus.RUNNING,
        dispatch_mode=DispatchMode.AUTO,
        max_retry_count=2,
        retry_interval=120,
        number_select_strategy=NumberSelectStrategy.ORDER,
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        OutboundTaskNumber(
            tenant_id=tenant.id,
            task_id=task.id,
            number_id=number.id,
            order_id=1,
            user_id=2,
            recipient_number=3,
        )
    )

    agent_user = make_user("session_agent_user")
    agent = Agent(
        user_id=agent_user.id, tenant_id=tenant.id, status=AgentStatus.BUSY
    )
    db_session.add(agent)

    name_list = OutboundList(
        tenant_id=tenant.id,
        task_id=task.id,
        user_id="U1",
        order_id="O1111",
        recipient_name="张三",
        recipient_phone="13900000001",
        phone_numbers=[],
        dynamic_fields={"订单金额": "188.00"},
        status=ListStatus.PENDING,
    )
    db_session.add(name_list)
    db_session.flush()

    record = OutboundRecord(
        tenant_id=tenant.id,
        task_id=task.id,
        list_id=name_list.id,
        agent_id=agent.id,
        status=RecordStatus.ASSIGNED,
        current_attempt=1,
        retry_count=0,
    )
    db_session.add(record)
    db_session.flush()

    session = OutboundSession(
        tenant_id=tenant.id,
        task_id=task.id,
        list_id=name_list.id,
        agent_id=agent.id,
        status=SessionStatus.CALLING,
        current_phone=PHONE_A,
        current_attempt=1,
    )
    db_session.add(session)
    db_session.flush()
    record.session_id = session.id

    return {
        "tenant": tenant,
        "task": task,
        "agent": agent,
        "list": name_list,
        "record": record,
        "session": session,
        "number": number,
    }


class TestSessionQuery:
    def test_list_sessions(self, client: TestClient, user_token, env) -> None:
        token = user_token("session_list", *ALL_SESSION_PERMS)
        response = client.get(
            f"{PREFIX}/sessions",
            headers=auth_headers(token),
            params={"tenant_id": env["tenant"].id},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["status"] == "CALLING"

    def test_list_sessions_filter_by_agent(self, client: TestClient, user_token, env) -> None:
        token = user_token("session_filter", *ALL_SESSION_PERMS)
        response = client.get(
            f"{PREFIX}/sessions",
            headers=auth_headers(token),
            params={"agent_id": env["agent"].id},
        )
        assert response.json()["data"]["total"] == 1

        response = client.get(
            f"{PREFIX}/sessions", headers=auth_headers(token), params={"agent_id": 999999}
        )
        assert response.json()["data"]["total"] == 0

    def test_session_detail_without_summary_returns_null(
        self, client: TestClient, user_token, env
    ) -> None:
        """§40：小结缺失返回 null，前端显示 '-'，接口不报错。"""
        token = user_token("session_detail", *ALL_SESSION_PERMS)
        response = client.get(
            f"{PREFIX}/sessions/{env['session'].id}", headers=auth_headers(token)
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["summary"] is None
        assert data["list_info"]["user_id"] == "U1"
        assert data["list_info"]["order_id"] == "O1111"
        assert data["task_name"] == "会话任务"
        assert data["phones"]  # 号码已按任务配置解析
        assert data["histories"] == []

    def test_session_detail_not_found(self, client: TestClient, user_token) -> None:
        token = user_token("session_404", *ALL_SESSION_PERMS)
        response = client.get(f"{PREFIX}/sessions/999999", headers=auth_headers(token))
        assert response.status_code == 404

    def test_requires_permission(self, client: TestClient, user_token, env) -> None:
        token = user_token("session_no_perm", "outbound:task:list")
        assert client.get(f"{PREFIX}/sessions", headers=auth_headers(token)).status_code == 403


class TestServiceSummary:
    def test_create_then_update(
        self, client: TestClient, user_token, env, db_session: Session
    ) -> None:
        token = user_token("summary_user", *ALL_SESSION_PERMS)
        session_id = env["session"].id

        created = client.post(
            f"{PREFIX}/sessions/{session_id}/summary",
            headers=auth_headers(token),
            json={
                "session_id": session_id,
                "summary": "客户已确认订单",
                "result": "已解决",
                "tags": ["已确认"],
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["data"]["summary"] == "客户已确认订单"
        assert created.json()["data"]["tags"] == ["已确认"]

        fetched = client.get(
            f"{PREFIX}/sessions/{session_id}/summary", headers=auth_headers(token)
        )
        assert fetched.json()["data"]["summary"] == "客户已确认订单"

        updated = client.put(
            f"{PREFIX}/sessions/{session_id}/summary",
            headers=auth_headers(token),
            json={"summary": "客户要求改期"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["summary"] == "客户要求改期"
        assert updated.json()["data"]["result"] == "已解决"  # 未传字段保持不变

    def test_update_before_create_rejected(
        self, client: TestClient, user_token, env
    ) -> None:
        token = user_token("summary_before", *ALL_SESSION_PERMS)
        response = client.put(
            f"{PREFIX}/sessions/{env['session'].id}/summary",
            headers=auth_headers(token),
            json={"summary": "还没有小结"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_get_summary_when_missing(self, client: TestClient, user_token, env) -> None:
        token = user_token("summary_null", *ALL_SESSION_PERMS)
        response = client.get(
            f"{PREFIX}/sessions/{env['session'].id}/summary", headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json()["data"] is None

    def test_summary_requires_call_permission(self, client: TestClient, user_token, env) -> None:
        token = user_token("summary_no_perm", "outbound:session:list")
        response = client.post(
            f"{PREFIX}/sessions/{env['session'].id}/summary",
            headers=auth_headers(token),
            json={"session_id": env["session"].id, "summary": "x"},
        )
        assert response.status_code == 403

    def test_summary_one_per_session(
        self, client: TestClient, user_token, env, db_session: Session
    ) -> None:
        """§40：一会话一条（DB 部分唯一索引 + 覆盖写入）。"""
        token = user_token("summary_unique", *ALL_SESSION_PERMS)
        session_id = env["session"].id
        for text in ("第一次", "第二次"):
            client.post(
                f"{PREFIX}/sessions/{session_id}/summary",
                headers=auth_headers(token),
                json={"session_id": session_id, "summary": text},
            )

        from app.models.outbound import ServiceSummary

        count = db_session.query(ServiceSummary).filter_by(session_id=session_id).count()
        assert count == 1


class TestAgentWorklist:
    def test_worklist_shows_agent_lists(self, client: TestClient, user_token, env) -> None:
        """OB-021-1：坐席名下名单 + 号码数量 + 来源顺序 + 是否已成功。"""
        token = user_token("worklist", *ALL_SESSION_PERMS)
        response = client.get(
            f"{PREFIX}/agents/{env['agent'].id}/worklist", headers=auth_headers(token)
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["total"] == 1

        item = data["items"][0]
        assert item["record_id"] == env["record"].id
        assert item["task_name"] == "会话任务"
        assert item["user_id"] == "U1"
        assert item["order_id"] == "O1111"
        assert item["phone_count"] >= 2
        assert item["phone_source"] == "OrderID → UserID → 收件人号码"
        assert item["has_success"] is False
        assert item["retry_count"] == 0

    def test_worklist_excludes_finished_by_default(
        self, client: TestClient, user_token, env, db_session: Session
    ) -> None:
        token = user_token("worklist_finished", *ALL_SESSION_PERMS)
        env["record"].status = RecordStatus.SUCCESS
        db_session.flush()

        default = client.get(
            f"{PREFIX}/agents/{env['agent'].id}/worklist", headers=auth_headers(token)
        ).json()["data"]
        assert default["total"] == 0

        with_finished = client.get(
            f"{PREFIX}/agents/{env['agent'].id}/worklist",
            headers=auth_headers(token),
            params={"include_finished": True},
        ).json()["data"]
        assert with_finished["total"] == 1

    def test_worklist_empty_for_other_agent(self, client: TestClient, user_token, env) -> None:
        token = user_token("worklist_other", *ALL_SESSION_PERMS)
        data = client.get(
            f"{PREFIX}/agents/999999/worklist", headers=auth_headers(token)
        ).json()["data"]
        assert data["total"] == 0


class TestListPhones:
    def test_phone_order_follows_task_config(
        self, client: TestClient, user_token, env
    ) -> None:
        """OB-023-1 / §23：号码顺序严格按任务配置（OrderID → UserID → 收件人号码）。"""
        token = user_token("phones_order", *ALL_SESSION_PERMS)
        response = client.get(
            f"{PREFIX}/lists/{env['list'].id}/phones", headers=auth_headers(token)
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]

        # OrderID=O1111 → 13700001111；UserID=U1 → 13800000001；收件号码 13900000001
        assert data["phones"] == ["13700001111", "13800000001", "13900000001"]
        assert data["phone_source"] == "OrderID → UserID → 收件人号码"
        assert data["provider_phones"]["order_id"] == ["13700001111"]
        assert data["provider_phones"]["user_id"] == ["13800000001"]
        assert data["has_success"] is False
        assert data["retry_interval"] == 120
        assert data["max_retry_count"] == 2
        assert data["record_status"] == "ASSIGNED"

    def test_success_flag_reflects_call_history(
        self, client: TestClient, user_token, env, db_session: Session
    ) -> None:
        """OB-021-1.4 / 2.1：名单是否已呼叫成功。"""
        token = user_token("phones_success", *ALL_SESSION_PERMS)
        db_session.add(
            CallHistory(
                tenant_id=env["tenant"].id,
                session_id=env["session"].id,
                record_id=env["record"].id,
                task_id=env["task"].id,
                list_id=env["list"].id,
                agent_id=env["agent"].id,
                phone=PHONE_A,
                call_status=CallStatus.CONNECTED,
                duration=30,
            )
        )
        db_session.flush()

        data = client.get(
            f"{PREFIX}/lists/{env['list'].id}/phones", headers=auth_headers(token)
        ).json()["data"]
        assert data["has_success"] is True
        assert data["success_phone"] == PHONE_A

    def test_phones_unknown_list(self, client: TestClient, user_token) -> None:
        token = user_token("phones_404", *ALL_SESSION_PERMS)
        assert (
            client.get(f"{PREFIX}/lists/999999/phones", headers=auth_headers(token)).status_code
            == 404
        )


class TestHistoriesAndBoard:
    def _add_history(self, db_session: Session, env: dict) -> CallHistory:
        history = CallHistory(
            tenant_id=env["tenant"].id,
            session_id=env["session"].id,
            record_id=env["record"].id,
            task_id=env["task"].id,
            list_id=env["list"].id,
            agent_id=env["agent"].id,
            phone=PHONE_B,
            call_status=CallStatus.NO_ANSWER,
            failure_reason="无人接听（Mock 规则：1111 结尾）",
            provider="mock",
        )
        db_session.add(history)
        db_session.flush()
        return history

    def test_list_histories(self, client: TestClient, user_token, env, db_session: Session) -> None:
        token = user_token("histories", *ALL_SESSION_PERMS)
        self._add_history(db_session, env)

        response = client.get(
            f"{PREFIX}/lists/{env['list'].id}/histories", headers=auth_headers(token)
        )
        assert response.status_code == 200
        items = response.json()["data"]
        assert len(items) == 1
        assert items[0]["phone"] == PHONE_B
        assert items[0]["call_status"] == "NO_ANSWER"

    def test_board_aggregates_everything(
        self, client: TestClient, user_token, env, db_session: Session
    ) -> None:
        """OB-023：名单信息 + 号码 + 拨打历史 + 会话 + 小结 + 接口信息。"""
        token = user_token("board", *ALL_SESSION_PERMS)
        self._add_history(db_session, env)
        client.post(
            f"{PREFIX}/sessions/{env['session'].id}/summary",
            headers=auth_headers(token),
            json={"session_id": env["session"].id, "summary": "客户未接电话"},
        )

        response = client.get(
            f"{PREFIX}/lists/{env['list'].id}/board", headers=auth_headers(token)
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]

        assert data["list_info"]["user_id"] == "U1"
        assert data["list_info"]["dynamic_fields"] == {"订单金额": "188.00"}
        assert data["phones"] == ["13700001111", "13800000001", "13900000001"]
        assert len(data["histories"]) == 1
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["task_id"] == env["task"].id
        assert len(data["summaries"]) == 1
        assert data["summaries"][0]["summary"] == "客户未接电话"

        external = data["external_info"]
        assert external["provider"] == "mock"
        assert external["source_order"] == ["order_id", "user_id", "recipient_number"]
        assert external["provider_phones"]["order_id"] == ["13700001111"]
        assert external["task_name"] == "会话任务"

    def test_board_unknown_list(self, client: TestClient, user_token) -> None:
        token = user_token("board_404", *ALL_SESSION_PERMS)
        assert (
            client.get(f"{PREFIX}/lists/999999/board", headers=auth_headers(token)).status_code
            == 404
        )

    def test_board_requires_list_permission(self, client: TestClient, user_token, env) -> None:
        token = user_token("board_no_perm", "outbound:session:list")
        assert (
            client.get(
                f"{PREFIX}/lists/{env['list'].id}/board", headers=auth_headers(token)
            ).status_code
            == 403
        )


class TestSessionLifecycleFields:
    def test_session_timestamps_nullable(self, client: TestClient, user_token, env) -> None:
        """字段缺失不报错（§40）：未结束的会话 finished_at 为 null。"""
        token = user_token("session_fields", *ALL_SESSION_PERMS)
        data = client.get(
            f"{PREFIX}/sessions/{env['session'].id}", headers=auth_headers(token)
        ).json()["data"]
        assert data["session"]["finished_at"] is None
        assert data["session"]["started_at"] is None
        assert isinstance(datetime.now(timezone.utc), datetime)
