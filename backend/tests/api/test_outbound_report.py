"""报表接口测试（OB-025 话务流水 / OB-028 实时监控）。"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import (
    Agent,
    CallHistory,
    OutboundList,
    OutboundRecord,
    OutboundSession,
    OutboundTask,
    OutboundType,
)
from app.models.outbound.enums import (
    AgentStatus,
    CallStatus,
    ListStatus,
    RecordStatus,
    SessionStatus,
    TaskStatus,
)

PREFIX = f"{settings.API_V1_PREFIX}/outbound/reports"
REPORT_PERMS = ("outbound:report:list",)
MONITOR_PERMS = ("outbound:monitor:view",)


# ---------------- 造数辅助 ----------------


def _make_type(db: Session, tenant, *, code: str, name: str, parent_id: int | None, level: int):
    entity = OutboundType(
        tenant_id=tenant.id,
        code=code,
        name=name,
        level=level,
        parent_id=parent_id,
    )
    db.add(entity)
    db.flush()
    return entity


def _make_task(db: Session, tenant, *, name: str, **overrides) -> OutboundTask:
    values: dict = {
        "tenant_id": tenant.id,
        "task_name": name,
        "status": TaskStatus.RUNNING,
    }
    values.update(overrides)
    task = OutboundTask(**values)
    db.add(task)
    db.flush()
    return task


def _make_history(
    db: Session,
    tenant,
    *,
    phone: str,
    call_status: CallStatus,
    minutes_ago: int = 1,
    duration: int = 0,
    **overrides,
) -> CallHistory:
    now = datetime.now(timezone.utc)
    started = now - timedelta(minutes=minutes_ago)
    values: dict = {
        "tenant_id": tenant.id,
        "phone": phone,
        "call_status": call_status,
        "started_at": started,
        "ended_at": started + timedelta(seconds=duration),
        "duration": duration,
    }
    values.update(overrides)
    history = CallHistory(**values)
    db.add(history)
    db.flush()
    return history


def _call_flow(client: TestClient, token: str, **params):
    return client.get(
        f"{PREFIX}/call-flow",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )


class TestReportPermissions:
    def test_call_flow_requires_permission(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("rep_no_perm", "outbound:type:list")
        response = _call_flow(client, token, tenant_id=tenant.id)
        assert response.status_code == 403

    def test_monitor_requires_permission(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("mon_no_perm", "outbound:report:list")
        response = client.get(
            f"{PREFIX}/monitor",
            headers={"Authorization": f"Bearer {token}"},
            params={"tenant_id": tenant.id},
        )
        assert response.status_code == 403

    def test_monitor_requires_tenant(self, client: TestClient, user_token) -> None:
        token = user_token("mon_ok", *MONITOR_PERMS)
        response = client.get(
            f"{PREFIX}/monitor", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 400


class TestCallFlowBasic:
    def test_empty_report(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("rep_empty", *REPORT_PERMS)
        response = _call_flow(client, token, tenant_id=tenant.id)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []
        assert data["summary"]["total"] == 0
        assert data["summary"]["connect_rate"] == 0.0

    def test_summary_and_records(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("rep_basic", *REPORT_PERMS)
        task = _make_task(db_session, tenant, name="报表任务")
        _make_history(
            db_session, tenant, phone="13700000001", call_status=CallStatus.CONNECTED,
            duration=30, task_id=task.id,
        )
        _make_history(
            db_session, tenant, phone="13700001111", call_status=CallStatus.NO_ANSWER,
            task_id=task.id,
        )

        response = _call_flow(client, token, tenant_id=tenant.id)
        data = response.json()["data"]
        assert data["total"] == 2
        summary = data["summary"]
        assert summary["total"] == 2
        assert summary["connected"] == 1
        assert summary["connect_rate"] == 0.5
        assert summary["total_duration"] == 30
        assert summary["avg_duration"] == 30
        assert summary["status_counts"] == {"CONNECTED": 1, "NO_ANSWER": 1}

        first = data["items"][0]
        assert first["task_id"] == task.id
        assert first["task_name"] == "报表任务"
        assert first["source"] == "OUTBOUND"

    def test_pagination(self, client: TestClient, user_token, tenant, db_session) -> None:
        token = user_token("rep_page", *REPORT_PERMS)
        for index in range(5):
            _make_history(
                db_session,
                tenant,
                phone=f"1370000000{index}",
                call_status=CallStatus.CONNECTED,
                minutes_ago=index + 1,
            )

        response = _call_flow(client, token, tenant_id=tenant.id, page=2, page_size=2)
        data = response.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 2
        # 明细按呼叫时间倒序，最新一条在第一页
        assert data["items"][0]["phone"] == "13700000002"


class TestCallFlowFilters:
    @staticmethod
    def _seed(db: Session, tenant):
        """造两级外呼类型：T1（营销）→ T1-1（新客），以及独立的一级类型 T2（催收）。"""
        parent = _make_type(db, tenant, code="T1", name="营销外呼", parent_id=None, level=1)
        child = _make_type(
            db, tenant, code="T1-1", name="新客外呼", parent_id=parent.id, level=2
        )
        other = _make_type(db, tenant, code="T2", name="催收外呼", parent_id=None, level=1)
        return parent, child, other

    def test_filter_by_scene(
        self, client: TestClient, user_token, tenant, db_session, outbound_scene
    ) -> None:
        token = user_token("rep_scene", *REPORT_PERMS)
        hit = _make_task(
            db_session, tenant, name="命中任务", scene_id=outbound_scene.id
        )
        miss = _make_task(db_session, tenant, name="未命中任务")
        _make_history(
            db_session, tenant, phone="13700000001",
            call_status=CallStatus.CONNECTED, task_id=hit.id,
        )
        _make_history(
            db_session, tenant, phone="13700000002",
            call_status=CallStatus.CONNECTED, task_id=miss.id,
        )

        response = _call_flow(
            client, token, tenant_id=tenant.id, scene_id=outbound_scene.id
        )
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["phone"] == "13700000001"
        assert data["items"][0]["scene_name"] == outbound_scene.name

    def test_filter_by_task(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("rep_task", *REPORT_PERMS)
        task = _make_task(db_session, tenant, name="目标任务")
        _make_history(
            db_session, tenant, phone="13700000001",
            call_status=CallStatus.CONNECTED, task_id=task.id,
        )
        _make_history(
            db_session, tenant, phone="13700000002", call_status=CallStatus.CONNECTED
        )

        response = _call_flow(client, token, tenant_id=tenant.id, task_id=task.id)
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["task_name"] == "目标任务"

    def test_type_filter_includes_subtypes(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        """选一级类型时，其二级子类型的任务话务也要被纳入（OB-025 需求）。"""
        token = user_token("rep_type", *REPORT_PERMS)
        parent, child, other = self._seed(db_session, tenant)

        child_task = _make_task(db_session, tenant, name="子类型任务", type_id=child.id)
        parent_task = _make_task(db_session, tenant, name="一级类型任务", type_id=parent.id)
        other_task = _make_task(db_session, tenant, name="其他类型任务", type_id=other.id)
        for index, task in enumerate((child_task, parent_task, other_task), start=1):
            _make_history(
                db_session,
                tenant,
                phone=f"1370000000{index}",
                call_status=CallStatus.CONNECTED,
                task_id=task.id,
            )

        response = _call_flow(client, token, tenant_id=tenant.id, type_id=parent.id)
        data = response.json()["data"]
        assert data["total"] == 2
        assert {item["task_name"] for item in data["items"]} == {
            "子类型任务",
            "一级类型任务",
        }

    def test_sub_type_filter_is_exact(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("rep_subtype", *REPORT_PERMS)
        parent, child, _ = self._seed(db_session, tenant)
        child_task = _make_task(db_session, tenant, name="子类型任务", type_id=child.id)
        parent_task = _make_task(db_session, tenant, name="一级类型任务", type_id=parent.id)
        _make_history(
            db_session, tenant, phone="13700000001",
            call_status=CallStatus.CONNECTED, task_id=child_task.id,
        )
        _make_history(
            db_session, tenant, phone="13700000002",
            call_status=CallStatus.CONNECTED, task_id=parent_task.id,
        )

        response = _call_flow(client, token, tenant_id=tenant.id, sub_type_id=child.id)
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["type_name"] == "新客外呼"
        assert data["items"][0]["type_level"] == 2

    def test_sub_type_must_be_second_level(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("rep_subtype_bad", *REPORT_PERMS)
        parent, _, _ = self._seed(db_session, tenant)
        response = _call_flow(client, token, tenant_id=tenant.id, sub_type_id=parent.id)
        assert response.status_code == 400
        assert "不是二级类型" in response.json()["message"]

    def test_type_not_found(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("rep_type_missing", *REPORT_PERMS)
        response = _call_flow(client, token, tenant_id=tenant.id, type_id=999999)
        assert response.status_code == 404

    def test_filter_by_call_status_and_phone(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("rep_status", *REPORT_PERMS)
        _make_history(
            db_session, tenant, phone="13700000001", call_status=CallStatus.CONNECTED
        )
        _make_history(
            db_session, tenant, phone="13700001111", call_status=CallStatus.NO_ANSWER
        )

        by_status = _call_flow(
            client, token, tenant_id=tenant.id, call_status="NO_ANSWER"
        ).json()["data"]
        assert by_status["total"] == 1
        assert by_status["items"][0]["phone"] == "13700001111"

        by_phone = _call_flow(client, token, tenant_id=tenant.id, phone="1111").json()[
            "data"
        ]
        assert by_phone["total"] == 1
        assert by_phone["items"][0]["phone"] == "13700001111"

    def test_filter_by_source(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("rep_source", *REPORT_PERMS)
        _make_history(
            db_session, tenant, phone="13700000001", call_status=CallStatus.CONNECTED
        )
        _make_history(
            db_session,
            tenant,
            phone="13700000002",
            call_status=CallStatus.CONNECTED,
            callback_task_id=None,
        )
        _make_history(
            db_session,
            tenant,
            phone="13700000003",
            call_status=CallStatus.CONNECTED,
            callback_task_id=None,
        )
        # 造一条回呼话务（callback_task_id 非空即可区分来源）
        callback_history = _make_history(
            db_session, tenant, phone="13700000004", call_status=CallStatus.CONNECTED
        )
        callback_history.callback_task_id = _make_callback_task(db_session, tenant).id
        db_session.flush()

        outbound_only = _call_flow(
            client, token, tenant_id=tenant.id, source="OUTBOUND"
        ).json()["data"]
        assert outbound_only["total"] == 3

        callback_only = _call_flow(
            client, token, tenant_id=tenant.id, source="CALLBACK"
        ).json()["data"]
        assert callback_only["total"] == 1
        assert callback_only["items"][0]["source"] == "CALLBACK"

    def test_filter_by_time_range(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("rep_time", *REPORT_PERMS)
        _make_history(
            db_session, tenant, phone="13700000001",
            call_status=CallStatus.CONNECTED, minutes_ago=5,
        )
        _make_history(
            db_session, tenant, phone="13700000002",
            call_status=CallStatus.CONNECTED, minutes_ago=120,
        )

        since = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        response = _call_flow(client, token, tenant_id=tenant.id, started_from=since)
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["phone"] == "13700000001"

    def test_filter_by_agent(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        token = user_token("rep_agent", *REPORT_PERMS)
        agent = Agent(
            tenant_id=tenant.id,
            user_id=make_user("rep_agent_user").id,
            status=AgentStatus.IDLE,
            extension="8001",
        )
        db_session.add(agent)
        db_session.flush()
        _make_history(
            db_session, tenant, phone="13700000001",
            call_status=CallStatus.CONNECTED, agent_id=agent.id,
        )
        _make_history(
            db_session, tenant, phone="13700000002", call_status=CallStatus.CONNECTED
        )

        response = _call_flow(client, token, tenant_id=tenant.id, agent_id=agent.id)
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["agent_extension"] == "8001"

    def test_tenant_isolation(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("rep_tenant", *REPORT_PERMS)
        from app.models.outbound import Tenant

        another = Tenant(code="TENANT-REP", name="报表第二租户")
        db_session.add(another)
        db_session.flush()
        _make_history(
            db_session, another, phone="13700009999", call_status=CallStatus.CONNECTED
        )
        _make_history(
            db_session, tenant, phone="13700000001", call_status=CallStatus.CONNECTED
        )

        response = _call_flow(client, token, tenant_id=tenant.id)
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["phone"] == "13700000001"


class TestRealtimeMonitor:
    def test_snapshot_shape(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("mon_shape", *MONITOR_PERMS)
        response = client.get(
            f"{PREFIX}/monitor",
            headers={"Authorization": f"Bearer {token}"},
            params={"tenant_id": tenant.id, "window_minutes": 10},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["tenant_id"] == tenant.id
        assert data["window_minutes"] == 10
        assert set(data["calls"]) == {
            "initiated",
            "connected",
            "connect_rate",
            "total_duration",
            "avg_duration",
        }
        # 趋势已补零：窗口 10 分钟 → 11 个分钟桶
        assert len(data["trend"]) == 11
        assert data["top_tasks"] == []

    def test_window_call_stats(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("mon_calls", *MONITOR_PERMS)
        _make_history(
            db_session, tenant, phone="13700000001",
            call_status=CallStatus.CONNECTED, minutes_ago=2, duration=60,
        )
        _make_history(
            db_session, tenant, phone="13700001111",
            call_status=CallStatus.NO_ANSWER, minutes_ago=2,
        )
        # 窗口外，不应计入
        _make_history(
            db_session, tenant, phone="13700000003",
            call_status=CallStatus.CONNECTED, minutes_ago=90, duration=99,
        )

        response = client.get(
            f"{PREFIX}/monitor",
            headers={"Authorization": f"Bearer {token}"},
            params={"tenant_id": tenant.id, "window_minutes": 30},
        )
        calls = response.json()["data"]["calls"]
        assert calls["initiated"] == 2
        assert calls["connected"] == 1
        assert calls["connect_rate"] == 0.5
        assert calls["total_duration"] == 60
        assert calls["avg_duration"] == 60

    def test_trend_counts_by_minute(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("mon_trend", *MONITOR_PERMS)
        _make_history(
            db_session, tenant, phone="13700000001",
            call_status=CallStatus.CONNECTED, minutes_ago=1,
        )
        _make_history(
            db_session, tenant, phone="13700001111",
            call_status=CallStatus.NO_ANSWER, minutes_ago=1,
        )

        response = client.get(
            f"{PREFIX}/monitor",
            headers={"Authorization": f"Bearer {token}"},
            params={"tenant_id": tenant.id, "window_minutes": 5},
        )
        trend = response.json()["data"]["trend"]
        assert sum(point["initiated"] for point in trend) == 2
        assert sum(point["connected"] for point in trend) == 1

    def test_status_distributions(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        token = user_token("mon_status", *MONITOR_PERMS)
        agent = Agent(
            tenant_id=tenant.id,
            user_id=make_user("mon_agent_user").id,
            status=AgentStatus.IDLE,
        )
        db_session.add(agent)
        task = _make_task(db_session, tenant, name="监控任务")
        db_session.add(
            OutboundSession(tenant_id=tenant.id, status=SessionStatus.CALLING)
        )
        db_session.add(
            OutboundRecord(
                tenant_id=tenant.id,
                task_id=task.id,
                list_id=_make_list(db_session, tenant, task).id,
                status=RecordStatus.PENDING,
            )
        )
        db_session.flush()

        response = client.get(
            f"{PREFIX}/monitor",
            headers={"Authorization": f"Bearer {token}"},
            params={"tenant_id": tenant.id},
        )
        data = response.json()["data"]
        assert data["agent_status"].get("IDLE") == 1
        assert data["task_status"].get("RUNNING") == 1
        assert data["record_status"].get("PENDING") == 1
        assert data["active_sessions"] == 1
        assert "DUE" in data["callback_status"]

    def test_top_tasks_ranking(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        token = user_token("mon_top", *MONITOR_PERMS)
        busy = _make_task(db_session, tenant, name="繁忙任务")
        quiet = _make_task(db_session, tenant, name="冷清任务")
        for index in range(3):
            _make_history(
                db_session,
                tenant,
                phone=f"1370000000{index}",
                call_status=CallStatus.CONNECTED,
                minutes_ago=1,
                task_id=busy.id,
            )
        _make_history(
            db_session, tenant, phone="13700000009",
            call_status=CallStatus.NO_ANSWER, minutes_ago=1, task_id=quiet.id,
        )

        response = client.get(
            f"{PREFIX}/monitor",
            headers={"Authorization": f"Bearer {token}"},
            params={"tenant_id": tenant.id, "window_minutes": 30},
        )
        top = response.json()["data"]["top_tasks"]
        assert [item["task_name"] for item in top] == ["繁忙任务", "冷清任务"]
        assert top[0]["initiated"] == 3
        assert top[0]["connected"] == 3
        assert top[0]["connect_rate"] == 1.0


def _make_list(db: Session, tenant, task: OutboundTask) -> OutboundList:
    entity = OutboundList(
        tenant_id=tenant.id,
        task_id=task.id,
        user_id="U1",
        order_id="O1",
        status=ListStatus.PENDING,
    )
    db.add(entity)
    db.flush()
    return entity


def _make_callback_task(db: Session, tenant):
    from app.models.outbound import CallbackFlow, CallbackTask
    from app.models.outbound.enums import CallbackSource, CallbackStatus

    flow = CallbackFlow(
        tenant_id=tenant.id, code=f"CB-REP-{tenant.id}", name="报表回呼流程"
    )
    db.add(flow)
    db.flush()
    task = CallbackTask(
        tenant_id=tenant.id,
        flow_id=flow.id,
        source=CallbackSource.IVR,
        phone="13700000004",
        status=CallbackStatus.SUCCESS,
    )
    db.add(task)
    db.flush()
    return task
