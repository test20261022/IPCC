"""自动分配接口测试（OB-018 / §33 派单 / §34 示闲触发 / §35 预占 / §36 预测）。"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import (
    Agent,
    AgentAssignment,
    AgentStatusLog,
    CallHistory,
    OutboundList,
    OutboundNumber,
    OutboundRecord,
    OutboundTask,
    OutboundTaskNumber,
    SkillQueue,
)
from app.models.outbound.enums import (
    AgentStatus,
    AssignmentStatus,
    CallStatus,
    DispatchMode,
    ListStatus,
    NumberSelectStrategy,
    RecordStatus,
    TaskStatus,
)
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound"
ALL_ASSIGN_PERMS = (
    "outbound:agent:list",
    "outbound:agent:update",
    "outbound:assignment:list",
    "outbound:assignment:dispatch",
    "outbound:assignment:release",
    "outbound:task:list",
    "outbound:task:execute",
    "outbound:session:call",
)
CONNECTED_PHONE = "13800000001"


@pytest.fixture
def dispatch_env(
    db_session: Session, tenant, outbound_type, outbound_scene, site, skill_queue, make_user
):
    """可派单环境：RUNNING + AUTO 任务（挂队列）+ 号码 + 空闲坐席。"""
    number = OutboundNumber(
        tenant_id=tenant.id,
        display_name="派单号码",
        caller_number="02112348888",
        usage_limit=100,
    )
    db_session.add(number)

    task = OutboundTask(
        tenant_id=tenant.id,
        task_name="自动派单任务",
        type_id=outbound_type.id,
        scene_id=outbound_scene.id,
        site_id=site.id,
        skill_queue_id=skill_queue.id,
        status=TaskStatus.RUNNING,
        dispatch_mode=DispatchMode.AUTO,
        priority=0,
        max_retry_count=1,
        retry_interval=0,
        call_timeout_seconds=30,
        number_select_strategy=NumberSelectStrategy.ORDER,
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        OutboundTaskNumber(
            tenant_id=tenant.id, task_id=task.id, number_id=number.id, order_id=1, user_id=2
        )
    )

    agent_user = make_user("dispatch_agent_user")
    agent = Agent(
        user_id=agent_user.id,
        tenant_id=tenant.id,
        site_id=site.id,
        skill_queue_id=skill_queue.id,
        status=AgentStatus.IDLE,
    )
    db_session.add(agent)
    db_session.flush()
    return {
        "tenant": tenant,
        "task": task,
        "number": number,
        "agent": agent,
        "queue": skill_queue,
        "site": site,
        "type": outbound_type,
        "scene": outbound_scene,
    }


def add_pending_record(db_session: Session, env: dict, *, priority: int = 0) -> OutboundRecord:
    row = OutboundList(
        tenant_id=env["tenant"].id,
        task_id=env["task"].id,
        user_id="U1",
        phone_numbers=[CONNECTED_PHONE],
        dynamic_fields={},
        status=ListStatus.PENDING,
        priority=priority,
    )
    db_session.add(row)
    db_session.flush()
    record = OutboundRecord(
        tenant_id=env["tenant"].id,
        task_id=env["task"].id,
        list_id=row.id,
        status=RecordStatus.PENDING,
        retry_count=0,
    )
    db_session.add(record)
    db_session.flush()
    return record


def change_agent_status(client: TestClient, token: str, agent_id: int, status: str, **params):
    return client.put(
        f"{PREFIX}/agents/{agent_id}/status",
        headers=auth_headers(token),
        json={"status": status, "reason": "test"},
        params=params,
    )


class TestAgentStatusApi:
    def test_change_to_busy_records_history(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("agent_status", *ALL_ASSIGN_PERMS)
        agent = dispatch_env["agent"]

        response = change_agent_status(client, token, agent.id, "BUSY")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["from_status"] == "IDLE"
        assert data["to_status"] == "BUSY"
        assert data["assignment"] is None

        db_session.refresh(agent)
        assert agent.status == AgentStatus.BUSY
        assert agent.last_busy_at is not None

        logs = db_session.query(AgentStatusLog).filter_by(agent_id=agent.id).all()
        assert len(logs) == 1
        assert logs[0].from_status == AgentStatus.IDLE
        assert logs[0].to_status == AgentStatus.BUSY

    def test_illegal_transition_rejected(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        """§11：OFFLINE → BUSY 必须拒绝。"""
        token = user_token("agent_illegal", *ALL_ASSIGN_PERMS)
        agent = dispatch_env["agent"]
        agent.status = AgentStatus.OFFLINE
        db_session.flush()

        response = change_agent_status(client, token, agent.id, "BUSY")
        assert response.status_code == 409
        assert response.json()["code"] == 40902
        assert "离线" in response.json()["message"]

    def test_same_status_rejected(
        self, client: TestClient, user_token, dispatch_env
    ) -> None:
        token = user_token("agent_same", *ALL_ASSIGN_PERMS)
        response = change_agent_status(client, token, dispatch_env["agent"].id, "IDLE")
        assert response.status_code == 409
        assert "已处于" in response.json()["message"]

    def test_permission_required(self, client: TestClient, user_token, dispatch_env) -> None:
        token = user_token("agent_no_perm", "outbound:agent:list")
        response = change_agent_status(client, token, dispatch_env["agent"].id, "BUSY")
        assert response.status_code == 403

    def test_status_logs_endpoint(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("agent_logs", *ALL_ASSIGN_PERMS)
        agent = dispatch_env["agent"]
        change_agent_status(client, token, agent.id, "BUSY")
        change_agent_status(client, token, agent.id, "IDLE", auto_assign=False)

        response = client.get(
            f"{PREFIX}/agents/{agent.id}/status-logs", headers=auth_headers(token)
        )
        assert response.status_code == 200
        logs = response.json()["data"]
        assert len(logs) == 2
        assert logs[0]["to_status"] == "IDLE"

    def test_status_summary(
        self, client: TestClient, user_token, dispatch_env
    ) -> None:
        token = user_token("agent_summary", *ALL_ASSIGN_PERMS)
        response = client.get(
            f"{PREFIX}/agents/status-summary",
            headers=auth_headers(token),
            params={"tenant_id": dispatch_env["tenant"].id},
        )
        assert response.status_code == 200
        assert response.json()["data"] == {"IDLE": 1}

    def test_list_agents_with_filters(
        self, client: TestClient, user_token, dispatch_env
    ) -> None:
        token = user_token("agent_list", *ALL_ASSIGN_PERMS)
        response = client.get(
            f"{PREFIX}/agents",
            headers=auth_headers(token),
            params={"tenant_id": dispatch_env["tenant"].id, "status": "IDLE"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1


class TestIdleTriggerDispatch:
    """§34：坐席示闲立即触发自动分配。"""

    def test_idle_triggers_assignment(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("trigger_assign", *ALL_ASSIGN_PERMS)
        agent = dispatch_env["agent"]
        agent.status = AgentStatus.OFFLINE
        db_session.flush()
        record = add_pending_record(db_session, dispatch_env)

        response = change_agent_status(client, token, agent.id, "IDLE")
        assert response.status_code == 200, response.text
        assignment = response.json()["data"]["assignment"]
        assert assignment is not None
        assert assignment["record_id"] == record.id
        assert assignment["expires_at"] is not None

        db_session.refresh(agent)
        assert agent.status == AgentStatus.RESERVED
        db_session.refresh(record)
        assert record.status == RecordStatus.ASSIGNED
        assert record.agent_id == agent.id
        assert record.session_id is not None

        stored = db_session.get(AgentAssignment, assignment["assignment_id"])
        assert stored is not None
        assert stored.status == AssignmentStatus.RESERVED
        assert stored.expires_at is not None

    def test_idle_without_pending_data(
        self, client: TestClient, user_token, dispatch_env
    ) -> None:
        token = user_token("trigger_empty", *ALL_ASSIGN_PERMS)
        agent = dispatch_env["agent"]
        agent.status = AgentStatus.OFFLINE

        response = change_agent_status(client, token, agent.id, "IDLE")
        assert response.status_code == 200
        assert response.json()["data"]["assignment"] is None

    def test_skip_when_agent_already_reserved(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        """§35：坐席已有活跃预占时不得再派单。"""
        token = user_token("trigger_reserved", *ALL_ASSIGN_PERMS)
        env = dispatch_env
        add_pending_record(db_session, env)
        # 手工造一条活跃预占，同时把坐席状态摆成 IDLE 模拟不一致场景
        db_session.add(
            AgentAssignment(
                tenant_id=env["tenant"].id,
                agent_id=env["agent"].id,
                task_id=env["task"].id,
                status=AssignmentStatus.RESERVED,
            )
        )
        db_session.flush()

        response = client.post(
            f"{PREFIX}/assignments/dispatch",
            headers=auth_headers(token),
            params={"tenant_id": env["tenant"].id},
        )
        assert response.status_code == 200
        assert response.json()["data"]["assigned"] == 0
        assert response.json()["data"]["skipped"] == 1

    def test_skip_when_queue_not_matched(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("trigger_queue", *ALL_ASSIGN_PERMS)
        # 任务挂在「另一个队列」上，与坐席所在队列不匹配 → 不应派单
        other_queue = SkillQueue(
            tenant_id=dispatch_env["tenant"].id,
            site_id=dispatch_env["site"].id,
            code="QUEUE-OTHER",
            name="其他队列",
        )
        db_session.add(other_queue)
        db_session.flush()
        dispatch_env["task"].skill_queue_id = other_queue.id
        db_session.flush()
        add_pending_record(db_session, dispatch_env)

        response = client.post(
            f"{PREFIX}/assignments/dispatch",
            headers=auth_headers(token),
            params={"tenant_id": dispatch_env["tenant"].id},
        )
        assert response.json()["data"]["assigned"] == 0


class TestPriorityOrdering:
    """§34：技能队列 → 任务优先级 → 名单优先级。"""

    def test_lower_task_priority_dispatch_first(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("priority_task", *ALL_ASSIGN_PERMS)
        env = dispatch_env

        low_priority_task = OutboundTask(
            tenant_id=env["tenant"].id,
            task_name="低优先任务",
            type_id=env["type"].id,
            scene_id=env["scene"].id,
            skill_queue_id=env["queue"].id,
            status=TaskStatus.RUNNING,
            dispatch_mode=DispatchMode.AUTO,
            priority=5,
        )
        db_session.add(low_priority_task)
        db_session.flush()

        high_record = add_pending_record(db_session, env)
        low_row = OutboundList(
            tenant_id=env["tenant"].id,
            task_id=low_priority_task.id,
            user_id="U2",
            phone_numbers=[CONNECTED_PHONE],
            dynamic_fields={},
            status=ListStatus.PENDING,
        )
        db_session.add(low_row)
        db_session.flush()
        low_record = OutboundRecord(
            tenant_id=env["tenant"].id,
            task_id=low_priority_task.id,
            list_id=low_row.id,
            status=RecordStatus.PENDING,
            retry_count=0,
        )
        db_session.add(low_record)
        db_session.flush()

        response = client.post(
            f"{PREFIX}/assignments/dispatch",
            headers=auth_headers(token),
            params={"tenant_id": env["tenant"].id},
        )
        assert response.json()["data"]["assigned"] == 1

        db_session.refresh(high_record)
        db_session.refresh(low_record)
        assert high_record.status == RecordStatus.ASSIGNED  # priority=0 先派
        assert low_record.status == RecordStatus.PENDING

    def test_list_priority_used_within_task(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("priority_list", *ALL_ASSIGN_PERMS)
        env = dispatch_env
        normal = add_pending_record(db_session, env, priority=0)
        urgent = add_pending_record(db_session, env, priority=100)

        client.post(
            f"{PREFIX}/assignments/dispatch",
            headers=auth_headers(token),
            params={"tenant_id": env["tenant"].id},
        )

        db_session.refresh(normal)
        db_session.refresh(urgent)
        assert urgent.status == RecordStatus.ASSIGNED
        assert normal.status == RecordStatus.PENDING


class TestAcceptAndRelease:
    def test_accept_then_release(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("accept_release", *ALL_ASSIGN_PERMS)
        env = dispatch_env
        add_pending_record(db_session, env)

        dispatched = client.post(
            f"{PREFIX}/assignments/dispatch",
            headers=auth_headers(token),
            params={"tenant_id": env["tenant"].id},
        ).json()["data"]
        assert dispatched["assigned"] == 1

        assignment = (
            db_session.query(AgentAssignment)
            .filter_by(agent_id=env["agent"].id, status=AssignmentStatus.RESERVED)
            .one()
        )

        accept = client.post(
            f"{PREFIX}/assignments/{assignment.id}/accept", headers=auth_headers(token)
        )
        assert accept.status_code == 200
        assert accept.json()["data"]["status"] == "ACCEPTED"
        db_session.refresh(env["agent"])
        assert env["agent"].status == AgentStatus.BUSY

        release = client.post(
            f"{PREFIX}/assignments/{assignment.id}/release",
            headers=auth_headers(token),
            json={"reason": "测试释放"},
        )
        assert release.status_code == 200
        assert release.json()["data"]["status"] == "RELEASED"

        db_session.refresh(assignment)
        db_session.refresh(env["agent"])
        assert assignment.released_at is not None
        assert env["agent"].status == AgentStatus.IDLE

    def test_accept_requires_reserved(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("accept_bad", *ALL_ASSIGN_PERMS)
        assignment = AgentAssignment(
            tenant_id=dispatch_env["tenant"].id,
            agent_id=dispatch_env["agent"].id,
            status=AssignmentStatus.RELEASED,
        )
        db_session.add(assignment)
        db_session.flush()

        response = client.post(
            f"{PREFIX}/assignments/{assignment.id}/accept", headers=auth_headers(token)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_release_unknown_assignment(self, client: TestClient, user_token) -> None:
        token = user_token("release_404", *ALL_ASSIGN_PERMS)
        response = client.post(f"{PREFIX}/assignments/999999/release", headers=auth_headers(token))
        assert response.status_code == 404


class TestExpireReservations:
    def test_expired_reservation_released_once(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        """§35：预占带过期时间，超过即自动释放，且释放必须幂等。"""
        token = user_token("expire_reservation", *ALL_ASSIGN_PERMS)
        env = dispatch_env
        assignment = AgentAssignment(
            tenant_id=env["tenant"].id,
            agent_id=env["agent"].id,
            task_id=env["task"].id,
            status=AssignmentStatus.RESERVED,
            reserved_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db_session.add(assignment)
        env["agent"].status = AgentStatus.RESERVED
        db_session.flush()

        first = client.post(f"{PREFIX}/assignments/expire", headers=auth_headers(token))
        assert first.status_code == 200
        assert first.json()["data"]["released"] == 1

        second = client.post(f"{PREFIX}/assignments/expire", headers=auth_headers(token))
        assert second.json()["data"]["released"] == 0

        db_session.refresh(assignment)
        db_session.refresh(env["agent"])
        assert assignment.status == AssignmentStatus.EXPIRED
        assert assignment.release_reason is not None
        assert env["agent"].status == AgentStatus.IDLE

    def test_not_expired_reservation_kept(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("expire_future", *ALL_ASSIGN_PERMS)
        assignment = AgentAssignment(
            tenant_id=dispatch_env["tenant"].id,
            agent_id=dispatch_env["agent"].id,
            status=AssignmentStatus.RESERVED,
            reserved_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db_session.add(assignment)
        db_session.flush()

        response = client.post(f"{PREFIX}/assignments/expire", headers=auth_headers(token))
        assert response.json()["data"]["scanned"] == 0


class TestPrediction:
    def test_answer_rate_and_target_concurrency(
        self, client: TestClient, user_token, dispatch_env, db_session: Session, make_user
    ) -> None:
        """4 次呼叫中 2 次接通 → 接通率 0.5；2 个空闲坐席 × 0.5 × 1.0 = 1。"""
        token = user_token("prediction", *ALL_ASSIGN_PERMS)
        env = dispatch_env
        env["task"].adjustment_factor = 1.0
        env["task"].max_concurrency = 10
        db_session.flush()

        second_user = make_user("dispatch_agent_user_2")
        db_session.add(
            Agent(
                user_id=second_user.id,
                tenant_id=env["tenant"].id,
                skill_queue_id=env["queue"].id,
                status=AgentStatus.IDLE,
            )
        )
        for status in (
            CallStatus.CONNECTED,
            CallStatus.CONNECTED,
            CallStatus.NO_ANSWER,
            CallStatus.BUSY,
        ):
            db_session.add(
                CallHistory(
                    tenant_id=env["tenant"].id,
                    task_id=env["task"].id,
                    phone=CONNECTED_PHONE,
                    call_status=status,
                )
            )
        db_session.flush()

        response = client.get(
            f"{PREFIX}/tasks/{env['task'].id}/prediction", headers=auth_headers(token)
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["available_agents"] == 2
        assert data["answer_rate"] == 0.5
        assert data["adjustment_factor"] == 1.0
        assert data["target_concurrency"] == 1

    def test_target_capped_by_task_concurrency(
        self, client: TestClient, user_token, dispatch_env, db_session: Session, make_user
    ) -> None:
        token = user_token("prediction_cap", *ALL_ASSIGN_PERMS)
        env = dispatch_env
        env["task"].adjustment_factor = 2.0
        env["task"].max_concurrency = 1
        db_session.flush()

        for _ in range(3):
            db_session.add(
                CallHistory(
                    tenant_id=env["tenant"].id,
                    task_id=env["task"].id,
                    phone=CONNECTED_PHONE,
                    call_status=CallStatus.CONNECTED,
                )
            )
        db_session.flush()

        data = client.get(
            f"{PREFIX}/tasks/{env['task'].id}/prediction", headers=auth_headers(token)
        ).json()["data"]
        assert data["answer_rate"] == 1.0
        assert data["uncapped_target"] == 2
        assert data["target_concurrency"] == 1

    def test_no_history_returns_zero_rate(
        self, client: TestClient, user_token, dispatch_env
    ) -> None:
        token = user_token("prediction_zero", *ALL_ASSIGN_PERMS)
        data = client.get(
            f"{PREFIX}/tasks/{dispatch_env['task'].id}/prediction", headers=auth_headers(token)
        ).json()["data"]
        assert data["answer_rate"] == 0.0
        assert data["target_concurrency"] == 0


class TestExecutionIntegration:
    """P5 与 P6 联动：呼叫结束后释放预占、坐席回到空闲。"""

    def test_call_releases_assignment_and_agent(
        self, client: TestClient, user_token, dispatch_env, db_session: Session
    ) -> None:
        token = user_token("exec_integration", *ALL_ASSIGN_PERMS)
        env = dispatch_env
        record = add_pending_record(db_session, env)

        client.post(
            f"{PREFIX}/assignments/dispatch",
            headers=auth_headers(token),
            params={"tenant_id": env["tenant"].id},
        )
        db_session.refresh(record)
        assert record.status == RecordStatus.ASSIGNED

        response = client.post(
            f"{PREFIX}/records/{record.id}/call",
            headers=auth_headers(token),
            json={"agent_id": env["agent"].id},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "SUCCESS"

        db_session.refresh(record)
        assert record.status == RecordStatus.SUCCESS

        assignment = (
            db_session.query(AgentAssignment)
            .filter_by(record_id=record.id)
            .order_by(AgentAssignment.id.desc())
            .first()
        )
        assert assignment is not None
        assert assignment.status == AssignmentStatus.RELEASED

        db_session.refresh(env["agent"])
        assert env["agent"].status == AgentStatus.IDLE
