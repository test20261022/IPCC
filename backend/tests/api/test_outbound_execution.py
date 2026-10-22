"""外呼执行接口测试（OB-008：多号码顺序 / 重试阶梯 / 超时回收 / 回调幂等）。

Mock Provider 的号码规则是确定性的（见 app/providers/call/mock.py）：
  0000 前缀 → FAILED；1111 结尾 → NO_ANSWER；2222 结尾 → BUSY；其余 → CONNECTED
因此用例可以精确构造「第 1 个号码不通、第 2 个号码接通」等场景。
"""

import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.callback_signature import SIGNATURE_HEADER, TIMESTAMP_HEADER, build_signature
from app.core.config import settings
from app.models.outbound import (
    Agent,
    AgentAssignment,
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
    AssignmentStatus,
    CallStatus,
    ListStatus,
    NumberSelectStrategy,
    RecordStatus,
    SessionStatus,
    TaskStatus,
)
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound"
ALL_EXEC_PERMS = (
    "outbound:task:list",
    "outbound:task:execute",
    "outbound:session:call",
)

CONNECTED_PHONE = "13800000001"
NO_ANSWER_PHONE = "13800001111"
BUSY_PHONE = "13800002222"
FAIL_PHONE = "00001234567"


@pytest.fixture
def exec_env(db_session: Session, tenant, outbound_type, outbound_scene):
    """可执行任务：RUNNING + 绑定主叫号码 + 号码来源顺序（OrderID 优先）。"""
    number = OutboundNumber(
        tenant_id=tenant.id,
        display_name="执行号码",
        caller_number="02112349999",
        usage_limit=50,
    )
    db_session.add(number)
    db_session.flush()

    task = OutboundTask(
        tenant_id=tenant.id,
        task_name="执行任务",
        type_id=outbound_type.id,
        scene_id=outbound_scene.id,
        status=TaskStatus.RUNNING,
        max_retry_count=2,
        retry_interval=0,
        call_timeout_seconds=30,
        max_concurrency=5,
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
    db_session.flush()
    return {"tenant": tenant, "task": task, "number": number}


def make_list(db_session: Session, env: dict, **overrides) -> OutboundList:
    """构造名单行；入参用 `phones` 简写，落到模型的 phone_numbers。"""
    phones = overrides.pop("phones", [])
    values = {
        "tenant_id": env["tenant"].id,
        "task_id": env["task"].id,
        "user_id": None,
        "order_id": None,
        "recipient_name": None,
        "recipient_phone": None,
        "phone_numbers": phones,
        "dynamic_fields": {},
        "status": ListStatus.PENDING,
    }
    values.update(overrides)
    row = OutboundList(**values)
    db_session.add(row)
    db_session.flush()
    return row


def build_records(client: TestClient, token: str, task_id: int, **params) -> dict:
    response = client.post(
        f"{PREFIX}/tasks/{task_id}/records/build", headers=auth_headers(token), params=params
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def execute(client: TestClient, token: str, task_id: int, **params) -> dict:
    response = client.post(
        f"{PREFIX}/tasks/{task_id}/execute", headers=auth_headers(token), params=params
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ---------------- 呼叫网关回调：签名报文构造（§78） ----------------


def _callback_body(payload: dict) -> bytes:
    """回调报文原文：签名与报文必须是同一串字节，故手工序列化后按 content 发送。"""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def _callback_headers(
    payload: dict, *, timestamp: str | None = None, secret: str | None = None
) -> dict[str, str]:
    ts = timestamp if timestamp is not None else str(int(time.time()))
    signature = build_signature(
        secret if secret is not None else settings.CALL_GATEWAY_CALLBACK_SECRET,
        ts,
        _callback_body(payload),
    )
    return {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: signature,
    }


def post_callback(
    client: TestClient,
    payload: dict,
    *,
    timestamp: str | None = None,
    secret: str | None = None,
    headers: dict[str, str] | None = None,
):
    """以网关身份提交回调（带签名）；headers 可用于覆盖 / 删除签名头。"""
    merged = _callback_headers(payload, timestamp=timestamp, secret=secret)
    if headers is not None:
        merged.update(headers)
    return client.post(
        f"{PREFIX}/call-result/callback", content=_callback_body(payload), headers=merged
    )


class TestTaskAutoComplete:
    """规则 2 确认结果：全部名单到终态时任务自动置为已完成（ASSUMPTION-057）。"""

    def _task_status(self, client: TestClient, token: str, task_id: int) -> str:
        response = client.get(f"{PREFIX}/tasks/{task_id}", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        return response.json()["data"]["status"]

    def test_completed_when_all_records_succeed(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("auto_done", *ALL_EXEC_PERMS)
        task_id = exec_env["task"].id
        make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        make_list(db_session, exec_env, user_id="U2", phones=[CONNECTED_PHONE])
        build_records(client, token, task_id)

        summary = execute(client, token, task_id)
        assert summary["success"] == 2
        assert summary["task_completed"] is True
        assert self._task_status(client, token, task_id) == "COMPLETED"

    def test_not_completed_while_records_pending(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """只处理了一部分记录时任务不能完成。"""
        token = user_token("auto_partial", *ALL_EXEC_PERMS)
        task_id = exec_env["task"].id
        make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        make_list(db_session, exec_env, user_id="U2", phones=[CONNECTED_PHONE])
        build_records(client, token, task_id)

        summary = execute(client, token, task_id, limit=1)
        assert summary["processed"] == 1
        assert summary["task_completed"] is not True
        assert self._task_status(client, token, task_id) == "RUNNING"

    def test_not_completed_when_retry_waiting(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """记录进入重试等待说明还没结束，任务不能完成。"""
        token = user_token("auto_retry", *ALL_EXEC_PERMS)
        task_id = exec_env["task"].id
        # 不设置 user_id，避免 Mock 电话簿从 UserID 派生出一个能接通的号码
        make_list(db_session, exec_env, phones=[NO_ANSWER_PHONE])
        build_records(client, token, task_id)

        summary = execute(client, token, task_id)
        assert summary["retry_waiting"] == 1
        assert summary["task_completed"] is not True
        assert self._task_status(client, token, task_id) == "RUNNING"

    def test_not_completed_without_records(
        self, client: TestClient, user_token, exec_env
    ) -> None:
        """尚未生成执行记录时不应被误判为已完成。"""
        token = user_token("auto_empty", *ALL_EXEC_PERMS)
        task_id = exec_env["task"].id

        summary = execute(client, token, task_id)
        assert summary["processed"] == 0
        assert summary["task_completed"] is not True
        assert self._task_status(client, token, task_id) == "RUNNING"

    def test_completed_after_exhausted_failure(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """全部失败（重试耗尽）同样属于「已处理完」，任务自动完成。"""
        token = user_token("auto_failed", *ALL_EXEC_PERMS)
        task_id = exec_env["task"].id
        exec_env["task"].max_retry_count = 0
        db_session.flush()
        make_list(db_session, exec_env, phones=[NO_ANSWER_PHONE])
        build_records(client, token, task_id)

        summary = execute(client, token, task_id)
        assert summary["failed"] == 1
        assert summary["task_completed"] is True
        assert self._task_status(client, token, task_id) == "COMPLETED"

    def test_completed_after_timeout_recycle(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """超时回收把最后一条记录置为终态后，任务也要自动完成。"""
        token = user_token("auto_timeout", *ALL_EXEC_PERMS)
        task = exec_env["task"]
        # 让超时直接进入终态（重试次数已用尽）
        task.max_retry_count = 1
        make_list(db_session, exec_env, phones=[CONNECTED_PHONE])
        build_records(client, token, task.id)

        record = (
            db_session.query(OutboundRecord)
            .filter(OutboundRecord.task_id == task.id)
            .one()
        )
        record.status = RecordStatus.ASSIGNED
        record.retry_count = 1
        record.timeout_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db_session.flush()

        response = client.post(
            f"{PREFIX}/timeout/recycle", headers=auth_headers(token), params={"limit": 10}
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["recycled"] == 1
        assert data["task_completed"] == 1
        assert self._task_status(client, token, task.id) == "COMPLETED"

    def test_completed_task_rejects_new_import(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """任务完成后不再接收名单导入，避免落入无法执行的死数据。"""
        token = user_token("auto_import", *ALL_EXEC_PERMS, "outbound:list:import")
        task_id = exec_env["task"].id
        make_list(db_session, exec_env, phones=[CONNECTED_PHONE])
        build_records(client, token, task_id)
        execute(client, token, task_id)
        assert self._task_status(client, token, task_id) == "COMPLETED"

        response = client.post(
            f"{PREFIX}/lists/import",
            headers=auth_headers(token),
            data={"task_id": str(task_id)},
            files={"file": ("list.csv", b"UserID,OrderID\nU99,O99\n", "text/csv")},
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902
        assert "不允许再导入名单" in response.json()["message"]



class TestBuildRecords:
    def test_build_then_idempotent(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_build", *ALL_EXEC_PERMS)
        make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        make_list(db_session, exec_env, user_id="U2", phones=[CONNECTED_PHONE])

        first = build_records(client, token, exec_env["task"].id)
        assert first == {"task_id": exec_env["task"].id, "created": 2, "skipped": 0}

        second = build_records(client, token, exec_env["task"].id)
        assert second["created"] == 0
        assert second["skipped"] == 2

    def test_build_rejected_on_completed_task(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_build_completed", *ALL_EXEC_PERMS)
        exec_env["task"].status = TaskStatus.COMPLETED
        db_session.flush()

        response = client.post(
            f"{PREFIX}/tasks/{exec_env['task'].id}/records/build", headers=auth_headers(token)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_build_requires_permission(self, client: TestClient, user_token, exec_env) -> None:
        token = user_token("exec_no_perm", "outbound:task:list")
        response = client.post(
            f"{PREFIX}/tasks/{exec_env['task'].id}/records/build", headers=auth_headers(token)
        )
        assert response.status_code == 403


class TestExecuteSuccess:
    def test_connected_on_first_phone(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_ok", *ALL_EXEC_PERMS)
        row = make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        build_records(client, token, exec_env["task"].id)

        summary = execute(client, token, exec_env["task"].id)
        assert summary == {
            "task_id": exec_env["task"].id,
            "processed": 1,
            "success": 1,
            "retry_waiting": 0,
            "exhausted": 0,
            "failed": 0,
            # 唯一一条记录已成功，任务随之自动完成（规则 2）
            "task_completed": True,
        }

        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()
        assert record.status == RecordStatus.SUCCESS
        assert record.current_attempt == 1
        assert record.current_phone == CONNECTED_PHONE
        assert record.finished_at is not None

        history = db_session.query(CallHistory).filter_by(record_id=record.id).one()
        assert history.call_status == CallStatus.CONNECTED
        assert history.duration > 0
        assert history.provider_call_id
        assert history.provider == "mock"

        session = db_session.get(OutboundSession, record.session_id)
        assert session is not None
        assert session.status == SessionStatus.ENDED

        # 主叫号码次数被原子扣减一次（§13）
        db_session.refresh(exec_env["number"])
        assert exec_env["number"].used_count == 1

        db_session.refresh(row)
        assert row.status == ListStatus.SUCCESS

    def test_multi_phone_falls_through_to_second(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """§20：第 1 个号码不通则继续尝试第 2 个，任一接通即成功。"""
        token = user_token("exec_multi", *ALL_EXEC_PERMS)
        row = make_list(
            db_session, exec_env, user_id="U1", phones=[NO_ANSWER_PHONE, CONNECTED_PHONE]
        )
        build_records(client, token, exec_env["task"].id)

        summary = execute(client, token, exec_env["task"].id)
        assert summary["success"] == 1

        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()
        assert record.current_attempt == 2
        # current_phone 必须落在最后尝试的号码上，超时回收写出的历史才不会缺号码
        assert record.current_phone == CONNECTED_PHONE

        histories = (
            db_session.query(CallHistory)
            .filter_by(record_id=record.id)
            .order_by(CallHistory.id.asc())
            .all()
        )
        assert [item.phone for item in histories] == [NO_ANSWER_PHONE, CONNECTED_PHONE]
        assert [item.call_status for item in histories] == [
            CallStatus.NO_ANSWER,
            CallStatus.CONNECTED,
        ]
        # 每个被叫号码尝试都消耗一次主叫次数
        db_session.refresh(exec_env["number"])
        assert exec_env["number"].used_count == 2

    def test_order_id_source_tried_before_user_id(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """§23：号码来源顺序按任务配置（本例 OrderID 优先）。"""
        token = user_token("exec_source_order", *ALL_EXEC_PERMS)
        # OrderID 派生号码 13700001111（1111 结尾 → 不通）；UserID 派生 13800000001（接通）
        row = make_list(db_session, exec_env, user_id="U1", order_id="O1111")
        build_records(client, token, exec_env["task"].id)

        assert execute(client, token, exec_env["task"].id)["success"] == 1

        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()
        histories = (
            db_session.query(CallHistory)
            .filter_by(record_id=record.id)
            .order_by(CallHistory.id.asc())
            .all()
        )
        assert [item.phone for item in histories] == ["13700001111", "13800000001"]

    def test_recipient_phone_used_when_no_other_source(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_recipient", *ALL_EXEC_PERMS)
        row = make_list(db_session, exec_env, recipient_phone=CONNECTED_PHONE)
        build_records(client, token, exec_env["task"].id)

        assert execute(client, token, exec_env["task"].id)["success"] == 1
        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()
        assert record.status == RecordStatus.SUCCESS


class TestExecuteFailureLadder:
    def test_all_phones_fail_then_exhausted(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """§21：max_retry_count=2 → 第 1 轮 RETRY_WAITING，第 2 轮 EXHAUSTED。"""
        token = user_token("exec_ladder", *ALL_EXEC_PERMS)
        # 不设置 user_id / order_id，避免 Mock 电话簿派生出发起得通的号码
        row = make_list(db_session, exec_env, phones=[NO_ANSWER_PHONE, BUSY_PHONE])
        build_records(client, token, exec_env["task"].id)

        first = execute(client, token, exec_env["task"].id)
        assert first["retry_waiting"] == 1, first

        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()
        assert record.status == RecordStatus.RETRY_WAITING
        assert record.retry_count == 1
        assert record.next_retry_at is not None

        second = execute(client, token, exec_env["task"].id)
        assert second["exhausted"] == 1, second

        db_session.refresh(record)
        assert record.status == RecordStatus.EXHAUSTED
        assert record.retry_count == 2
        assert record.next_retry_at is None

        db_session.refresh(row)
        assert row.status == ListStatus.EXHAUSTED
        # 两轮 × 两个号码 = 4 次呼叫尝试
        assert db_session.query(CallHistory).filter_by(record_id=record.id).count() == 4

    def test_no_retry_configured_marks_failed(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_no_retry", *ALL_EXEC_PERMS)
        exec_env["task"].max_retry_count = 0
        db_session.flush()
        row = make_list(db_session, exec_env, phones=[FAIL_PHONE])
        build_records(client, token, exec_env["task"].id)

        summary = execute(client, token, exec_env["task"].id)
        assert summary["failed"] == 1, summary

        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()
        assert record.status == RecordStatus.FAILED
        assert record.next_retry_at is None

    def test_no_phone_available_is_permanent_failure(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """名单无号码且 UserID/OrderID 为空 → 第三方也拿不到号码 → 直接 FAILED，不进入重试。"""
        token = user_token("exec_no_phone", *ALL_EXEC_PERMS)
        row = make_list(db_session, exec_env)
        build_records(client, token, exec_env["task"].id)

        assert execute(client, token, exec_env["task"].id)["failed"] == 1

        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()
        assert record.status == RecordStatus.FAILED
        assert "无可呼叫号码" in (record.failure_reason or "")
        assert db_session.query(CallHistory).filter_by(record_id=record.id).count() == 0

    def test_exhausted_caller_number_blocks_call(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """主叫号码次数耗尽 → 无法发起呼叫（§13 / §14 → 40903 语义）。"""
        token = user_token("exec_number_exhausted", *ALL_EXEC_PERMS)
        exec_env["number"].usage_limit = 0
        db_session.flush()
        row = make_list(db_session, exec_env, phones=[CONNECTED_PHONE])
        build_records(client, token, exec_env["task"].id)

        summary = execute(client, token, exec_env["task"].id)
        assert summary["failed"] == 1, summary

        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()
        assert "外呼号码已全部不可用" in (record.failure_reason or "")

    def test_execute_requires_running_task(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_not_running", *ALL_EXEC_PERMS)
        exec_env["task"].status = TaskStatus.PAUSED
        db_session.flush()

        response = client.post(
            f"{PREFIX}/tasks/{exec_env['task'].id}/execute", headers=auth_headers(token)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902
        assert "RUNNING" in response.json()["message"]

    def test_execute_requires_permission(self, client: TestClient, user_token, exec_env) -> None:
        token = user_token("exec_perm_denied", "outbound:task:list")
        response = client.post(
            f"{PREFIX}/tasks/{exec_env['task'].id}/execute", headers=auth_headers(token)
        )
        assert response.status_code == 403


class TestSingleCall:
    def test_call_record_with_agent(
        self, client: TestClient, user_token, exec_env, db_session: Session, make_user
    ) -> None:
        token = user_token("exec_call", *ALL_EXEC_PERMS)
        agent_user = make_user("agent_for_call")
        agent = Agent(
            user_id=agent_user.id, tenant_id=exec_env["tenant"].id, status=AgentStatus.IDLE
        )
        db_session.add(agent)
        db_session.flush()

        row = make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        build_records(client, token, exec_env["task"].id)
        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()

        response = client.post(
            f"{PREFIX}/records/{record.id}/call",
            headers=auth_headers(token),
            json={"agent_id": agent.id},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "SUCCESS"
        assert data["session_id"] is not None

        db_session.refresh(record)
        assert record.agent_id == agent.id

    def test_call_record_with_unknown_agent(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_call_bad_agent", *ALL_EXEC_PERMS)
        row = make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        build_records(client, token, exec_env["task"].id)
        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()

        response = client.post(
            f"{PREFIX}/records/{record.id}/call",
            headers=auth_headers(token),
            json={"agent_id": 999999},
        )
        assert response.status_code == 404

    def test_call_record_with_offline_agent(
        self, client: TestClient, user_token, exec_env, db_session: Session, make_user
    ) -> None:
        token = user_token("exec_call_offline", *ALL_EXEC_PERMS)
        agent_user = make_user("agent_offline")
        agent = Agent(user_id=agent_user.id, tenant_id=exec_env["tenant"].id)
        db_session.add(agent)
        db_session.flush()

        row = make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        build_records(client, token, exec_env["task"].id)
        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()

        response = client.post(
            f"{PREFIX}/records/{record.id}/call",
            headers=auth_headers(token),
            json={"agent_id": agent.id},
        )
        assert response.status_code == 409
        assert "离线" in response.json()["message"]

    def test_duplicate_call_on_success_rejected(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_call_dup", *ALL_EXEC_PERMS)
        row = make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        build_records(client, token, exec_env["task"].id)
        record = db_session.query(OutboundRecord).filter_by(list_id=row.id).one()

        assert (
            client.post(
                f"{PREFIX}/records/{record.id}/call", headers=auth_headers(token), json={}
            ).status_code
            == 200
        )
        second = client.post(
            f"{PREFIX}/records/{record.id}/call", headers=auth_headers(token), json={}
        )
        assert second.status_code == 409
        assert "已呼叫成功" in second.json()["message"]


class TestTimeoutRecycle:
    def _make_calling_record(
        self, db_session: Session, exec_env: dict, *, timed_out: bool = True
    ) -> OutboundRecord:
        row = make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        record = OutboundRecord(
            tenant_id=exec_env["tenant"].id,
            task_id=exec_env["task"].id,
            list_id=row.id,
            status=RecordStatus.CALLING,
            current_phone=CONNECTED_PHONE,
            current_attempt=1,
            retry_count=0,
            last_call_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            timeout_at=(
                datetime.now(timezone.utc) - timedelta(minutes=1)
                if timed_out
                else datetime.now(timezone.utc) + timedelta(minutes=5)
            ),
        )
        db_session.add(record)
        db_session.flush()
        return record

    def test_recycle_timed_out_record(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_recycle", *ALL_EXEC_PERMS)
        record = self._make_calling_record(db_session, exec_env)

        response = client.post(f"{PREFIX}/timeout/recycle", headers=auth_headers(token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["scanned"] == 1
        assert data["recycled"] == 1

        db_session.refresh(record)
        # max_retry_count=2 → 回收后还有重试机会，重新入队
        assert record.status == RecordStatus.RETRY_WAITING
        assert record.retry_count == 1

        history = db_session.query(CallHistory).filter_by(record_id=record.id).one()
        assert history.call_status == CallStatus.TIMEOUT
        assert history.provider == "timeout-recycler"

    def test_recycle_is_idempotent(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        """§22：同一条记录重复扫描只能产生一次有效回收。"""
        token = user_token("exec_recycle_idem", *ALL_EXEC_PERMS)
        record = self._make_calling_record(db_session, exec_env)

        first = client.post(
            f"{PREFIX}/timeout/recycle", headers=auth_headers(token)
        ).json()["data"]
        second = client.post(
            f"{PREFIX}/timeout/recycle", headers=auth_headers(token)
        ).json()["data"]

        assert first["recycled"] == 1
        assert second["recycled"] == 0
        assert db_session.query(CallHistory).filter_by(record_id=record.id).count() == 1

    def test_recycle_keeps_timeout_as_terminal_when_retry_used_up(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_recycle_terminal", *ALL_EXEC_PERMS)
        exec_env["task"].max_retry_count = 1
        db_session.flush()
        record = self._make_calling_record(db_session, exec_env)
        record.retry_count = 1
        db_session.flush()

        assert (
            client.post(f"{PREFIX}/timeout/recycle", headers=auth_headers(token))
            .json()["data"]["recycled"]
            == 1
        )

        db_session.refresh(record)
        assert record.status == RecordStatus.TIMEOUT
        assert record.next_retry_at is None

    def test_recycle_skips_non_timed_out(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_recycle_skip", *ALL_EXEC_PERMS)
        self._make_calling_record(db_session, exec_env, timed_out=False)

        data = client.post(f"{PREFIX}/timeout/recycle", headers=auth_headers(token)).json()["data"]
        assert data["scanned"] == 0
        assert data["recycled"] == 0

    def test_recycle_releases_active_assignment(
        self, client: TestClient, user_token, exec_env, db_session: Session, make_user
    ) -> None:
        """§22：回收时必须释放坐席预占。"""
        token = user_token("exec_recycle_release", *ALL_EXEC_PERMS)
        agent_user = make_user("agent_release")
        agent = Agent(user_id=agent_user.id, tenant_id=exec_env["tenant"].id)
        db_session.add(agent)
        db_session.flush()

        record = self._make_calling_record(db_session, exec_env)
        assignment = AgentAssignment(
            tenant_id=exec_env["tenant"].id,
            agent_id=agent.id,
            task_id=exec_env["task"].id,
            record_id=record.id,
            status=AssignmentStatus.RESERVED,
            reserved_at=datetime.now(timezone.utc),
        )
        db_session.add(assignment)
        db_session.flush()

        client.post(f"{PREFIX}/timeout/recycle", headers=auth_headers(token))

        db_session.refresh(assignment)
        assert assignment.status == AssignmentStatus.RELEASED
        assert assignment.released_at is not None
        assert assignment.release_reason is not None


class TestCallResultCallback:
    def test_callback_updates_record_and_is_idempotent(
        self, client: TestClient, exec_env, db_session: Session
    ) -> None:
        row = make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        record = OutboundRecord(
            tenant_id=exec_env["tenant"].id,
            task_id=exec_env["task"].id,
            list_id=row.id,
            status=RecordStatus.CALLING,
            current_phone=CONNECTED_PHONE,
            retry_count=0,
            timeout_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db_session.add(record)
        db_session.flush()

        session = OutboundSession(
            tenant_id=exec_env["tenant"].id,
            task_id=exec_env["task"].id,
            list_id=row.id,
            status="CALLING",
        )
        db_session.add(session)
        db_session.flush()
        record.session_id = session.id

        history = CallHistory(
            tenant_id=exec_env["tenant"].id,
            session_id=session.id,
            record_id=record.id,
            task_id=exec_env["task"].id,
            list_id=row.id,
            phone=CONNECTED_PHONE,
            call_status=CallStatus.INITIATED,
            provider_call_id="gw-callback-001",
        )
        db_session.add(history)
        db_session.flush()

        payload = {
            "provider_call_id": "gw-callback-001",
            "call_status": "CONNECTED",
            "duration": 42,
            "recording_path": "gw/rec/001.wav",
        }
        first = post_callback(client, payload)
        assert first.status_code == 200
        assert first.json()["data"]["updated"] is True

        db_session.refresh(record)
        assert record.status == RecordStatus.SUCCESS
        db_session.refresh(history)
        assert history.duration == 42
        assert history.ended_at is not None

        # §78：重复回调必须被幂等忽略
        second = post_callback(client, payload)
        assert second.status_code == 200
        assert second.json()["data"]["updated"] is False

    def test_callback_unknown_call_id(self, client: TestClient) -> None:
        response = post_callback(
            client,
            {"provider_call_id": "not-exist", "call_status": "CONNECTED"},
        )
        assert response.status_code == 404


class TestCallResultCallbackAuth:
    """回调鉴权走共享密钥签名（不再依赖登录态）。"""

    PAYLOAD = {"provider_call_id": "gw-any", "call_status": "CONNECTED"}

    def test_login_token_alone_is_not_enough(self, client: TestClient, user_token) -> None:
        """旧的「带登录态即可回调」已废弃：只有 JWT、没有签名必须被拒。"""
        token = user_token("exec_callback_jwt", *ALL_EXEC_PERMS)
        response = post_callback(
            client,
            self.PAYLOAD,
            headers={TIMESTAMP_HEADER: "", SIGNATURE_HEADER: ""},
        )
        assert response.status_code == 401
        assert response.json()["code"] == 40101

        # 带 token 同样无效
        signed_but_no_token = client.post(
            f"{PREFIX}/call-result/callback",
            headers=auth_headers(token),
            content=_callback_body(self.PAYLOAD),
        )
        assert signed_but_no_token.status_code == 401

    def test_missing_signature_headers(self, client: TestClient) -> None:
        response = client.post(f"{PREFIX}/call-result/callback", json=self.PAYLOAD)
        assert response.status_code == 401
        assert response.json()["message"] == "回调签名缺失"

    def test_wrong_secret_rejected(self, client: TestClient) -> None:
        response = post_callback(client, self.PAYLOAD, secret="wrong-secret")
        assert response.status_code == 401
        assert response.json()["message"] == "回调签名校验失败"

    def test_stale_timestamp_rejected(self, client: TestClient) -> None:
        stale = str(int(time.time()) - settings.CALL_GATEWAY_CALLBACK_TOLERANCE_SECONDS - 10)
        response = post_callback(client, self.PAYLOAD, timestamp=stale)
        assert response.status_code == 401
        assert "重放" in response.json()["message"]

    def test_not_configured_secret_rejected(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "CALL_GATEWAY_CALLBACK_SECRET", "")
        response = post_callback(client, self.PAYLOAD, secret="")
        assert response.status_code == 500
        assert response.json()["code"] == 50000

    def test_valid_signature_passes_auth(
        self, client: TestClient, exec_env, db_session: Session
    ) -> None:
        """签名正确时不再要求任何权限码（网关侧没有用户身份）。"""
        row = make_list(db_session, exec_env, phones=[CONNECTED_PHONE])
        history = CallHistory(
            tenant_id=exec_env["tenant"].id,
            session_id=None,
            record_id=None,
            task_id=exec_env["task"].id,
            list_id=row.id,
            phone=CONNECTED_PHONE,
            call_status=CallStatus.INITIATED,
            provider_call_id="gw-signature-ok",
        )
        db_session.add(history)
        db_session.flush()

        response = post_callback(
            client,
            {"provider_call_id": "gw-signature-ok", "call_status": "NO_ANSWER"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["updated"] is True
        db_session.refresh(history)
        assert history.call_status == CallStatus.NO_ANSWER


class TestRecordQuery:
    def test_list_records_with_filters(
        self, client: TestClient, user_token, exec_env, db_session: Session
    ) -> None:
        token = user_token("exec_list", *ALL_EXEC_PERMS)
        make_list(db_session, exec_env, user_id="U1", phones=[CONNECTED_PHONE])
        list_row = make_list(db_session, exec_env, user_id="U2", phones=[CONNECTED_PHONE])
        build_records(client, token, exec_env["task"].id)

        response = client.get(
            f"{PREFIX}/records",
            headers=auth_headers(token),
            params={"task_id": exec_env["task"].id},
        )
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 2

        response = client.get(
            f"{PREFIX}/records",
            headers=auth_headers(token),
            params={"list_id": list_row.id},
        )
        assert response.json()["data"]["total"] == 1

        response = client.get(
            f"{PREFIX}/records",
            headers=auth_headers(token),
            params={"task_id": exec_env["task"].id, "status": "SUCCESS"},
        )
        assert response.json()["data"]["total"] == 0
