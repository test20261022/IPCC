"""回呼接口测试（OB-029 IVR 回呼 / OB-030 人工回呼）。"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import Agent, CallbackTask, CallHistory, OutboundSession, Tenant
from app.models.outbound.enums import AgentStatus, CallbackStatus
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound/callback"

ALL_CALLBACK_PERMS = (
    "outbound:callback:list",
    "outbound:callback:create",
    "outbound:callback:execute",
)

#: Mock 网关规则：非特殊后缀的号码判定为接通
PHONE_OK = "13700000001"
#: 以 1111 结尾 → 无人接听（Mock 规则）
PHONE_NO_ANSWER = "13700001111"


def _make_agent(
    db: Session, tenant, user_id: int, **overrides
) -> Agent:
    values: dict = {
        "tenant_id": tenant.id,
        "user_id": user_id,
        "status": AgentStatus.IDLE,
    }
    values.update(overrides)
    agent = Agent(**values)
    db.add(agent)
    db.flush()
    return agent


def _make_session(db: Session, tenant) -> OutboundSession:
    """callback_tasks.origin_session_id 有外键约束，幂等键必须指向真实会话。"""
    session = OutboundSession(tenant_id=tenant.id)
    db.add(session)
    db.flush()
    return session


def _make_tenant(db: Session, code: str = "TENANT-002") -> Tenant:
    """第二个启用租户，用于跨租户引用校验（disabled_tenant 会先被租户状态拦截）。"""
    another = Tenant(code=code, name=f"租户-{code}")
    db.add(another)
    db.flush()
    return another


def _create_flow(client: TestClient, headers: dict, tenant_id: int, **overrides) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "code": "CB-001",
        "name": "回呼流程",
        "trigger_condition": {"triggers": ["NO_AGENT"]},
    }
    payload.update(overrides)
    response = client.post(f"{PREFIX}/flows", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_task(client: TestClient, headers: dict, tenant_id: int, **overrides) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "source": "MANUAL",
        "phone": PHONE_OK,
    }
    payload.update(overrides)
    response = client.post(f"{PREFIX}/tasks", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


class TestCallbackPermissions:
    def test_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("cb_no_perm", "outbound:type:list")
        assert client.get(f"{PREFIX}/flows", headers=auth_headers(token)).status_code == 403

    def test_create_requires_permission(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("cb_list_only", "outbound:callback:list")
        response = client.post(
            f"{PREFIX}/flows",
            headers=auth_headers(token),
            json={"tenant_id": tenant.id, "code": "CB-X", "name": "无权限"},
        )
        assert response.status_code == 403

    def test_execute_requires_permission(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("cb_exec_denied", "outbound:callback:list")
        task = _create_task(
            client, auth_headers(user_token("cb_exec_lister", *ALL_CALLBACK_PERMS)), tenant.id
        )
        response = client.post(
            f"{PREFIX}/tasks/{task['id']}/cancel", headers=auth_headers(token), json={}
        )
        assert response.status_code == 403


class TestFlowCrud:
    def test_create_list_and_update(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("cb_flow_admin", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        flow = _create_flow(
            client,
            headers,
            tenant.id,
            trigger_condition={"triggers": ["KEY"], "keys": ["0"], "delay_seconds": 120},
        )

        listed = client.get(
            f"{PREFIX}/flows", headers=headers, params={"tenant_id": tenant.id}
        )
        assert listed.status_code == 200
        assert listed.json()["data"]["total"] == 1
        assert listed.json()["data"]["items"][0]["trigger_condition"]["keys"] == ["0"]

        updated = client.put(
            f"{PREFIX}/flows/{flow['id']}",
            headers=headers,
            json={"name": "改名后的流程", "trigger_condition": {"triggers": ["NO_ANSWER"]}},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["name"] == "改名后的流程"
        assert updated.json()["data"]["trigger_condition"] == {"triggers": ["NO_ANSWER"]}

    def test_duplicate_code_rejected(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("cb_flow_dup", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _create_flow(client, headers, tenant.id, code="CB-DUP")
        response = client.post(
            f"{PREFIX}/flows",
            headers=headers,
            json={"tenant_id": tenant.id, "code": "CB-DUP", "name": "重复"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40901

    def test_ivr_flow_must_match_tenant(
        self, client: TestClient, user_token, tenant, ivr_flow, db_session
    ) -> None:
        token = user_token("cb_flow_ivr", *ALL_CALLBACK_PERMS)
        another = _make_tenant(db_session, "TENANT-IVR")
        response = client.post(
            f"{PREFIX}/flows",
            headers=auth_headers(token),
            json={
                "tenant_id": another.id,
                "code": "CB-IVR",
                "name": "跨租户 IVR",
                "ivr_flow_id": ivr_flow.id,
            },
        )
        assert response.status_code == 400
        assert "不属于同一租户" in response.json()["message"]

    def test_flow_with_tasks_cannot_be_disabled_or_deleted(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("cb_flow_lock", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        flow = _create_flow(client, headers, tenant.id)
        _create_task(client, headers, tenant.id, flow_id=flow["id"])

        disabled = client.put(
            f"{PREFIX}/flows/{flow['id']}/status", headers=headers, json={"status": "DISABLED"}
        )
        assert disabled.status_code == 409
        assert disabled.json()["code"] == 40904

        removed = client.delete(f"{PREFIX}/flows/{flow['id']}", headers=headers)
        assert removed.status_code == 409
        assert removed.json()["code"] == 40904

    def test_delete_unused_flow(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("cb_flow_delete", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        flow = _create_flow(client, headers, tenant.id, code="CB-FREE")
        response = client.delete(f"{PREFIX}/flows/{flow['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["flow_id"] == flow["id"]


class TestIvrTrigger:
    def test_matched_triggers_create_task(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("cb_ivr_hit", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        flow = _create_flow(client, headers, tenant.id, code="CB-IVR-HIT")
        session = _make_session(db_session, tenant)

        response = client.post(
            f"{PREFIX}/tasks/from-ivr",
            headers=headers,
            json={
                "tenant_id": tenant.id,
                "phone": PHONE_OK,
                "origin_session_id": session.id,
                "no_agent": True,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["created"] is True
        assert data["trigger_type"] == "NO_AGENT"
        assert data["flow_id"] == flow["id"]
        assert data["task"]["source"] == "IVR"
        assert data["task"]["status"] == "PENDING"
        assert "无可用坐席" in data["reason"]

    def test_second_call_is_idempotent(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("cb_ivr_idem", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _create_flow(client, headers, tenant.id, code="CB-IDEM")
        session = _make_session(db_session, tenant)
        body = {
            "tenant_id": tenant.id,
            "phone": PHONE_OK,
            "origin_session_id": session.id,
            "no_agent": True,
        }

        first = client.post(f"{PREFIX}/tasks/from-ivr", headers=headers, json=body)
        assert first.json()["data"]["created"] is True
        second = client.post(f"{PREFIX}/tasks/from-ivr", headers=headers, json=body)
        assert second.status_code == 200
        data = second.json()["data"]
        assert data["created"] is False
        assert "幂等" in data["reason"]
        assert data["task"]["id"] == first.json()["data"]["task"]["id"]

        listed = client.get(
            f"{PREFIX}/tasks",
            headers=headers,
            params={"tenant_id": tenant.id, "origin_session_id": session.id},
        )
        assert listed.json()["data"]["total"] == 1

    def test_not_matched_when_no_flow_configured(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("cb_ivr_no_flow", *ALL_CALLBACK_PERMS)
        session = _make_session(db_session, tenant)
        response = client.post(
            f"{PREFIX}/tasks/from-ivr",
            headers=auth_headers(token),
            json={
                "tenant_id": tenant.id,
                "phone": PHONE_OK,
                "origin_session_id": session.id,
                "no_agent": True,
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["created"] is False
        assert data["task"] is None
        assert "没有启用中的回呼流程" in data["reason"]

    def test_disabled_flow_rejected_when_explicit(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("cb_ivr_disabled", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        flow = _create_flow(client, headers, tenant.id, code="CB-OFF", status="DISABLED")
        session = _make_session(db_session, tenant)

        response = client.post(
            f"{PREFIX}/tasks/from-ivr",
            headers=headers,
            json={
                "tenant_id": tenant.id,
                "phone": PHONE_OK,
                "origin_session_id": session.id,
                "flow_id": flow["id"],
                "no_agent": True,
            },
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_unknown_origin_session_returns_404_not_500(
        self, client: TestClient, user_token, tenant
    ) -> None:
        """回归：原会话不存在时必须前置校验，不能落库时才抛外键冲突（曾返回 500）。"""
        token = user_token("cb_ivr_bad_session", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _create_flow(client, headers, tenant.id, code="CB-BAD-SESSION")

        response = client.post(
            f"{PREFIX}/tasks/from-ivr",
            headers=headers,
            json={
                "tenant_id": tenant.id,
                "phone": PHONE_OK,
                "origin_session_id": 999999,
                "no_agent": True,
            },
        )
        assert response.status_code == 404
        assert response.json()["code"] == 40401
        assert "原会话不存在" in response.json()["message"]

    def test_origin_session_of_other_tenant_rejected(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        """回归：跨租户的原会话同样必须前置拦截。"""
        token = user_token("cb_ivr_cross_session", *ALL_CALLBACK_PERMS)
        another = _make_tenant(db_session, "TENANT-SESSION")
        foreign_session = _make_session(db_session, another)

        response = client.post(
            f"{PREFIX}/tasks/from-ivr",
            headers=auth_headers(token),
            json={
                "tenant_id": tenant.id,
                "phone": PHONE_OK,
                "origin_session_id": foreign_session.id,
                "no_agent": True,
            },
        )
        assert response.status_code == 400
        assert "不属于同一租户" in response.json()["message"]

    def test_delay_sets_scheduled_at(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("cb_ivr_delay", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _create_flow(
            client,
            headers,
            tenant.id,
            code="CB-DELAY",
            trigger_condition={"triggers": ["NO_AGENT"], "delay_seconds": 600},
        )
        session = _make_session(db_session, tenant)

        response = client.post(
            f"{PREFIX}/tasks/from-ivr",
            headers=headers,
            json={
                "tenant_id": tenant.id,
                "phone": PHONE_OK,
                "origin_session_id": session.id,
                "no_agent": True,
            },
        )
        task_id = response.json()["data"]["task"]["id"]
        db_session.expire_all()
        task = db_session.get(CallbackTask, task_id)
        assert task.scheduled_at is not None
        assert task.scheduled_at > datetime.now(timezone.utc) + timedelta(seconds=500)

    def test_priority_picks_lower_value_flow(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("cb_ivr_priority", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _create_flow(
            client,
            headers,
            tenant.id,
            code="CB-P10",
            trigger_condition={"triggers": ["NO_AGENT"], "priority": 10},
        )
        high = _create_flow(
            client,
            headers,
            tenant.id,
            code="CB-P1",
            trigger_condition={"triggers": ["NO_AGENT"], "priority": 1},
        )
        session = _make_session(db_session, tenant)

        response = client.post(
            f"{PREFIX}/tasks/from-ivr",
            headers=headers,
            json={
                "tenant_id": tenant.id,
                "phone": PHONE_OK,
                "origin_session_id": session.id,
                "no_agent": True,
            },
        )
        assert response.json()["data"]["flow_id"] == high["id"]

    def test_business_hours_gate_blocks_trigger(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("cb_ivr_hours", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _create_flow(
            client,
            headers,
            tenant.id,
            code="CB-HOURS",
            trigger_condition={
                "triggers": ["NO_AGENT"],
                "business_hours": ["09:00-18:00"],
            },
        )
        session = _make_session(db_session, tenant)

        response = client.post(
            f"{PREFIX}/tasks/from-ivr",
            headers=headers,
            json={
                "tenant_id": tenant.id,
                "phone": PHONE_OK,
                "origin_session_id": session.id,
                "no_agent": True,
                "current_time": "22:00",
            },
        )
        data = response.json()["data"]
        assert data["created"] is False
        assert "不在业务时段" in data["reason"]


class TestManualTask:
    def test_manual_task_succeeds_without_session(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("cb_manual", *ALL_CALLBACK_PERMS)
        task = _create_task(
            client, auth_headers(token), tenant.id, remark="客户要求下午回电"
        )
        assert task["source"] == "MANUAL"
        assert task["status"] == "PENDING"
        assert task["origin_session_id"] is None
        assert task["remark"] == "客户要求下午回电"

    def test_ivr_source_requires_origin_session(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("cb_ivr_no_session", *ALL_CALLBACK_PERMS)
        response = client.post(
            f"{PREFIX}/tasks",
            headers=auth_headers(token),
            json={"tenant_id": tenant.id, "source": "IVR", "phone": PHONE_OK},
        )
        assert response.status_code == 400
        assert "原会话 ID" in response.json()["message"]

    def test_invalid_phone_rejected(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("cb_bad_phone", *ALL_CALLBACK_PERMS)
        response = client.post(
            f"{PREFIX}/tasks",
            headers=auth_headers(token),
            json={"tenant_id": tenant.id, "source": "MANUAL", "phone": "abc"},
        )
        assert response.status_code == 400
        assert "格式不合法" in response.json()["message"]

    def test_task_with_agent_is_assigned_immediately(
        self, client: TestClient, user_token, tenant, make_user, db_session
    ) -> None:
        token = user_token("cb_task_agent", *ALL_CALLBACK_PERMS)
        user = make_user("cb_agent_user")
        agent = _make_agent(db_session, tenant, user.id)

        task = _create_task(
            client, auth_headers(token), tenant.id, agent_id=agent.id
        )
        assert task["status"] == "ASSIGNED"
        assert task["agent_id"] == agent.id
        assert task["assigned_at"] is not None

    def test_cross_tenant_task_reference_rejected(
        self, client: TestClient, user_token, tenant, outbound_task, db_session
    ) -> None:
        token = user_token("cb_cross_tenant", *ALL_CALLBACK_PERMS)
        another = _make_tenant(db_session, "TENANT-CB")
        response = client.post(
            f"{PREFIX}/tasks",
            headers=auth_headers(token),
            json={
                "tenant_id": another.id,
                "source": "MANUAL",
                "phone": PHONE_OK,
                "task_id": outbound_task.id,
            },
        )
        assert response.status_code == 400
        assert "不属于同一租户" in response.json()["message"]


class TestAssignAndDispatch:
    def test_assign_to_specific_agent(
        self, client: TestClient, user_token, tenant, make_user, db_session
    ) -> None:
        token = user_token("cb_assign", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        user = make_user("cb_assign_user")
        agent = _make_agent(db_session, tenant, user.id)
        task = _create_task(client, headers, tenant.id)

        response = client.post(
            f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={"agent_id": agent.id}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["agent_id"] == agent.id
        assert data["auto_assigned"] is False

    def test_assign_auto_picks_idle_agent(
        self, client: TestClient, user_token, tenant, make_user, db_session
    ) -> None:
        token = user_token("cb_assign_auto", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        first = _make_agent(db_session, tenant, make_user("cb_auto_a").id)
        _make_agent(db_session, tenant, make_user("cb_auto_b").id)
        task = _create_task(client, headers, tenant.id)

        response = client.post(f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["agent_id"] == first.id  # 按坐席 ID 升序，结果确定
        assert data["auto_assigned"] is True

    def test_assign_without_idle_agent_rejected(
        self, client: TestClient, user_token, tenant, make_user, db_session
    ) -> None:
        token = user_token("cb_assign_none", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _make_agent(
            db_session, tenant, make_user("cb_offline").id, status=AgentStatus.OFFLINE
        )
        task = _create_task(client, headers, tenant.id)

        response = client.post(f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={})
        assert response.status_code == 409
        assert "没有空闲坐席" in response.json()["message"]

    def test_assign_twice_rejected(
        self, client: TestClient, user_token, tenant, make_user, db_session
    ) -> None:
        token = user_token("cb_assign_twice", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        agent = _make_agent(db_session, tenant, make_user("cb_twice").id)
        task = _create_task(client, headers, tenant.id)
        client.post(f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={})

        again = client.post(
            f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={"agent_id": agent.id}
        )
        assert again.status_code == 409
        assert again.json()["code"] == 40902

    def test_dispatch_due_assigns_pending_tasks(
        self, client: TestClient, user_token, tenant, make_user, db_session
    ) -> None:
        token = user_token("cb_dispatch", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _make_agent(db_session, tenant, make_user("cb_dispatch_agent").id)
        _create_task(client, headers, tenant.id)

        response = client.post(
            f"{PREFIX}/tasks/dispatch", headers=headers, params={"tenant_id": tenant.id}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["scanned"] == 1
        assert data["assigned"] == 1
        assert data["skipped"] == 0

    def test_dispatch_skips_future_scheduled(
        self, client: TestClient, user_token, tenant, make_user, db_session
    ) -> None:
        token = user_token("cb_dispatch_future", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _make_agent(db_session, tenant, make_user("cb_future_agent").id)
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        _create_task(client, headers, tenant.id, scheduled_at=future)

        response = client.post(
            f"{PREFIX}/tasks/dispatch", headers=headers, params={"tenant_id": tenant.id}
        )
        data = response.json()["data"]
        assert data["scanned"] == 0
        assert data["assigned"] == 0

    def test_dispatch_skips_without_idle_agent(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("cb_dispatch_none", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _create_task(client, headers, tenant.id)

        response = client.post(
            f"{PREFIX}/tasks/dispatch", headers=headers, params={"tenant_id": tenant.id}
        )
        data = response.json()["data"]
        assert data["scanned"] == 1
        assert data["assigned"] == 0
        assert data["skipped"] == 1


class TestCallExecution:
    def _assigned_task(
        self, client: TestClient, headers: dict, tenant, db_session, user_id: int, **overrides
    ) -> dict:
        _make_agent(db_session, tenant, user_id)
        task = _create_task(client, headers, tenant.id, **overrides)
        response = client.post(f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={})
        assert response.status_code == 200, response.text
        return task

    def test_call_success_writes_history_and_consumes_number(
        self,
        client: TestClient,
        user_token,
        tenant,
        db_session,
        make_user,
        outbound_number,
    ) -> None:
        token = user_token("cb_call_ok", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        task = self._assigned_task(
            client, headers, tenant, db_session, make_user("cb_call_ok_agent").id
        )

        response = client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "SUCCESS"
        assert data["call_status"] == "CONNECTED"
        assert data["attempt_count"] == 1
        assert data["calling_number"] == outbound_number.caller_number
        assert data["history_id"] is not None

        db_session.expire_all()
        history = db_session.get(CallHistory, data["history_id"])
        assert history.callback_task_id == task["id"]
        assert history.phone == PHONE_OK
        assert history.agent_id is not None
        assert db_session.get(CallbackTask, task["id"]).status == CallbackStatus.SUCCESS
        assert outbound_number.used_count == 1

    def test_call_failure_marks_failed(
        self, client: TestClient, user_token, tenant, db_session, make_user, outbound_number
    ) -> None:
        del outbound_number
        token = user_token("cb_call_fail", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        task = self._assigned_task(
            client,
            headers,
            tenant,
            db_session,
            make_user("cb_call_fail_agent").id,
            phone=PHONE_NO_ANSWER,
        )

        response = client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)
        data = response.json()["data"]
        assert data["status"] == "FAILED"
        assert data["call_status"] == "NO_ANSWER"
        assert "无人接听" in data["failure_reason"]

    def test_call_without_agent_rejected(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        del outbound_number
        token = user_token("cb_call_no_agent", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        task = _create_task(client, headers, tenant.id)

        response = client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_call_twice_after_success_rejected(
        self, client: TestClient, user_token, tenant, db_session, make_user, outbound_number
    ) -> None:
        del outbound_number
        token = user_token("cb_call_twice", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        task = self._assigned_task(
            client, headers, tenant, db_session, make_user("cb_twice_call").id
        )
        client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)

        again = client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)
        assert again.status_code == 409
        assert again.json()["code"] == 40902

    def test_call_without_available_number_marks_failed(
        self, client: TestClient, user_token, tenant, db_session, make_user, outbound_number
    ) -> None:
        """号码已耗尽时不应抛出 500，而是把回呼任务置为失败并说明原因。"""
        token = user_token("cb_call_no_number", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        task = self._assigned_task(
            client, headers, tenant, db_session, make_user("cb_no_number").id
        )
        outbound_number.used_count = outbound_number.usage_limit
        db_session.flush()

        response = client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "FAILED"
        assert "全部不可用" in data["failure_reason"]
        assert data["history_id"] is None


class TestLifecycle:
    def test_finish_success_and_failure(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        token = user_token("cb_finish", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _make_agent(db_session, tenant, make_user("cb_finish_agent").id)
        task = _create_task(client, headers, tenant.id)
        client.post(f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={})

        done = client.post(
            f"{PREFIX}/tasks/{task['id']}/finish",
            headers=headers,
            json={"success": True, "remark": "已沟通完成"},
        )
        assert done.status_code == 200
        assert done.json()["data"]["status"] == "SUCCESS"
        assert done.json()["data"]["remark"] == "已沟通完成"

    def test_cancel_pending_task(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("cb_cancel", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        task = _create_task(client, headers, tenant.id)

        response = client.post(
            f"{PREFIX}/tasks/{task['id']}/cancel",
            headers=headers,
            json={"reason": "客户已自行来电"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "CANCELLED"
        assert response.json()["data"]["remark"] == "客户已自行来电"

    def test_cancel_finished_task_rejected(
        self, client: TestClient, user_token, tenant, db_session, make_user, outbound_number
    ) -> None:
        del outbound_number
        token = user_token("cb_cancel_done", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _make_agent(db_session, tenant, make_user("cb_cancel_agent").id)
        task = _create_task(client, headers, tenant.id)
        client.post(f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={})
        client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)

        response = client.post(f"{PREFIX}/tasks/{task['id']}/cancel", headers=headers, json={})
        assert response.status_code == 409

    def test_requeue_failed_task(
        self, client: TestClient, user_token, tenant, db_session, make_user, outbound_number
    ) -> None:
        del outbound_number
        token = user_token("cb_requeue", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _make_agent(db_session, tenant, make_user("cb_requeue_agent").id)
        task = _create_task(client, headers, tenant.id, phone=PHONE_NO_ANSWER)
        client.post(f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={})
        client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)

        response = client.post(
            f"{PREFIX}/tasks/{task['id']}/requeue", headers=headers, json={"reason": "改时段重呼"}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "PENDING"
        assert data["finished_at"] is None
        assert data["assigned_at"] is None
        assert data["remark"] == "改时段重呼"

    def test_requeue_pending_rejected(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("cb_requeue_bad", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        task = _create_task(client, headers, tenant.id)

        response = client.post(
            f"{PREFIX}/tasks/{task['id']}/requeue", headers=headers, json={}
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902


class TestTaskQuery:
    def test_filter_by_source_and_status(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        token = user_token("cb_query", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        manual = _create_task(client, headers, tenant.id)
        session = _make_session(db_session, tenant)
        ivr = _create_task(
            client,
            headers,
            tenant.id,
            source="IVR",
            origin_session_id=session.id,
            phone="13700000002",
        )
        client.post(f"{PREFIX}/tasks/{ivr['id']}/cancel", headers=headers, json={})

        manual_only = client.get(
            f"{PREFIX}/tasks",
            headers=headers,
            params={"tenant_id": tenant.id, "source": "MANUAL"},
        )
        assert manual_only.json()["data"]["total"] == 1
        assert manual_only.json()["data"]["items"][0]["id"] == manual["id"]

        cancelled = client.get(
            f"{PREFIX}/tasks",
            headers=headers,
            params={"tenant_id": tenant.id, "status": "CANCELLED"},
        )
        assert cancelled.json()["data"]["total"] == 1
        assert cancelled.json()["data"]["items"][0]["id"] == ivr["id"]

    def test_get_task_detail(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("cb_detail", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        task = _create_task(client, headers, tenant.id)

        response = client.get(f"{PREFIX}/tasks/{task['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == task["id"]

        missing = client.get(f"{PREFIX}/tasks/999999", headers=headers)
        assert missing.status_code == 404

    def test_history_linked_to_callback(
        self, client: TestClient, user_token, tenant, db_session, make_user, outbound_number
    ) -> None:
        """回呼拨打记录必须能从呼叫历史里按 callback_task_id 查出来（供报表区分）。"""
        token = user_token("cb_history", *ALL_CALLBACK_PERMS)
        headers = auth_headers(token)
        _make_agent(db_session, tenant, make_user("cb_history_agent").id)
        task = _create_task(client, headers, tenant.id)
        client.post(f"{PREFIX}/tasks/{task['id']}/assign", headers=headers, json={})
        client.post(f"{PREFIX}/tasks/{task['id']}/call", headers=headers)

        db_session.expire_all()
        rows = list(
            db_session.execute(
                select(CallHistory).where(CallHistory.callback_task_id == task["id"])
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].provider == "mock"
