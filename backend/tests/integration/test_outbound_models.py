"""外呼模型与迁移验证（P1）。

覆盖：表是否全部建成、部分唯一索引是否真正生效、外键、枚举校验、级联删除。
所有断言都跑在真实 PostgreSQL 上（§98 禁止假测试）。
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.outbound import (
    Agent,
    AgentAssignment,
    CallbackTask,
    IvrFlow,
    IvrNode,
    IvrTransition,
    OutboundList,
    OutboundNumber,
    OutboundRecord,
    OutboundScene,
    OutboundSession,
    OutboundTask,
    OutboundTaskNumber,
    OutboundType,
    ServiceSummary,
    Site,
    SkillQueue,
    Tenant,
)
from app.models.outbound.enums import AssignmentStatus, CallbackSource, RecordStatus
from app.models.user import User

EXPECTED_TABLES = {
    "agent_assignments",
    "agent_status_logs",
    "agents",
    "call_histories",
    "callback_flows",
    "callback_tasks",
    "ivr_flows",
    "ivr_nodes",
    "ivr_transitions",
    "outbound_import_batches",
    "outbound_lists",
    "outbound_numbers",
    "outbound_records",
    "outbound_scenes",
    "outbound_sessions",
    "outbound_task_numbers",
    "outbound_tasks",
    "outbound_types",
    "service_summaries",
    "sites",
    "skill_queues",
    "tenants",
}


# ---------------- 夹具 ----------------


@pytest.fixture
def base_data(db_session: Session) -> dict:
    """最小可用主数据：租户 / 站点 / 队列 / 用户 / 坐席 / 类型 / 场景 / 号码 / 任务 / 名单。"""
    tenant = Tenant(code="T001", name="测试租户")
    db_session.add(tenant)
    db_session.flush()

    site = Site(tenant_id=tenant.id, code="S001", name="站点一")
    db_session.add(site)
    db_session.flush()

    queue = SkillQueue(tenant_id=tenant.id, site_id=site.id, code="Q001", name="外呼队列")
    db_session.add(queue)

    user = User(username="agent_user", password_hash=hash_password("Agent@123456"))
    db_session.add(user)
    db_session.flush()

    agent = Agent(user_id=user.id, tenant_id=tenant.id, site_id=site.id, skill_queue_id=queue.id)
    db_session.add(agent)
    db_session.flush()

    outbound_type = OutboundType(tenant_id=tenant.id, code="TP01", name="营销", level=1)
    db_session.add(outbound_type)
    db_session.flush()

    scene = OutboundScene(
        tenant_id=tenant.id, type_id=outbound_type.id, level=1, name="一级场景"
    )
    db_session.add(scene)
    db_session.flush()

    number = OutboundNumber(
        tenant_id=tenant.id,
        display_name="客服热线",
        caller_number="02188886666",
        usage_limit=100,
    )
    db_session.add(number)
    db_session.flush()

    task = OutboundTask(
        tenant_id=tenant.id, task_name="测试任务", type_id=outbound_type.id, scene_id=scene.id
    )
    db_session.add(task)
    db_session.flush()

    name_list = OutboundList(
        tenant_id=tenant.id, task_id=task.id, user_id="U10001", order_id="O20001"
    )
    db_session.add(name_list)

    second_list = OutboundList(
        tenant_id=tenant.id, task_id=task.id, user_id="U10002", order_id="O20002"
    )
    db_session.add(second_list)
    db_session.flush()

    session = OutboundSession(
        tenant_id=tenant.id, task_id=task.id, list_id=name_list.id, agent_id=agent.id
    )
    db_session.add(session)
    db_session.flush()

    return {
        "tenant": tenant,
        "site": site,
        "queue": queue,
        "user": user,
        "agent": agent,
        "type": outbound_type,
        "scene": scene,
        "number": number,
        "task": task,
        "list": name_list,
        "list2": second_list,
        "session": session,
    }


# ---------------- 表结构 ----------------


class TestSchema:
    def test_all_outbound_tables_exist(self, db_session: Session) -> None:
        rows = db_session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        existing = set(rows)
        missing = EXPECTED_TABLES - existing
        assert not missing, f"缺失表：{sorted(missing)}"

    def test_partial_unique_indexes_created(self, db_session: Session) -> None:
        rows = db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname LIKE 'uq_%' AND indexdef LIKE '%WHERE%'"
            )
        ).scalars()
        existing = set(rows)
        expected = {
            "uq_agents_user_active",
            "uq_agent_assignments_active_agent",
            "uq_callback_tasks_ivr_session",
            "uq_ivr_nodes_flow_key",
            "uq_outbound_numbers_tenant_caller",
            "uq_outbound_records_task_list",
            "uq_outbound_task_numbers_task_number",
            "uq_service_summaries_session",
        }
        assert expected <= existing, f"缺失部分唯一索引：{sorted(expected - existing)}"


# ---------------- 唯一性约束 ----------------


class TestUniqueConstraints:
    def test_same_user_cannot_have_two_agents(self, db_session: Session, base_data: dict) -> None:
        db_session.add(
            Agent(user_id=base_data["user"].id, tenant_id=base_data["tenant"].id)
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_same_tenant_caller_number_rejected(self, db_session: Session, base_data: dict) -> None:
        db_session.add(
            OutboundNumber(
                tenant_id=base_data["tenant"].id, display_name="另一个", caller_number="02188886666"
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_duplicate_task_number_binding_rejected(
        self, db_session: Session, base_data: dict
    ) -> None:
        db_session.add(
            OutboundTaskNumber(
                tenant_id=base_data["tenant"].id,
                task_id=base_data["task"].id,
                number_id=base_data["number"].id,
            )
        )
        db_session.flush()

        db_session.add(
            OutboundTaskNumber(
                tenant_id=base_data["tenant"].id,
                task_id=base_data["task"].id,
                number_id=base_data["number"].id,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_duplicate_record_for_same_list_rejected(
        self, db_session: Session, base_data: dict
    ) -> None:
        """§73：同一名单行在同一任务下不允许重复执行。"""
        db_session.add(
            OutboundRecord(
                tenant_id=base_data["tenant"].id,
                task_id=base_data["task"].id,
                list_id=base_data["list"].id,
            )
        )
        db_session.flush()

        db_session.add(
            OutboundRecord(
                tenant_id=base_data["tenant"].id,
                task_id=base_data["task"].id,
                list_id=base_data["list"].id,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_agent_cannot_be_reserved_by_two_assignments(
        self, db_session: Session, base_data: dict
    ) -> None:
        """§35：一个坐席不允许被同时预占。"""
        db_session.add(
            AgentAssignment(
                tenant_id=base_data["tenant"].id,
                agent_id=base_data["agent"].id,
                task_id=base_data["task"].id,
                status=AssignmentStatus.RESERVED,
            )
        )
        db_session.flush()

        db_session.add(
            AgentAssignment(
                tenant_id=base_data["tenant"].id,
                agent_id=base_data["agent"].id,
                task_id=base_data["task"].id,
                status=AssignmentStatus.ACCEPTED,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_released_assignment_does_not_block_new_reservation(
        self, db_session: Session, base_data: dict
    ) -> None:
        db_session.add(
            AgentAssignment(
                tenant_id=base_data["tenant"].id,
                agent_id=base_data["agent"].id,
                status=AssignmentStatus.RELEASED,
            )
        )
        db_session.flush()

        db_session.add(
            AgentAssignment(
                tenant_id=base_data["tenant"].id,
                agent_id=base_data["agent"].id,
                status=AssignmentStatus.RESERVED,
            )
        )
        db_session.flush()  # 不应报错

    def test_one_summary_per_session(self, db_session: Session, base_data: dict) -> None:
        db_session.add(
            ServiceSummary(tenant_id=base_data["tenant"].id, session_id=base_data["session"].id)
        )
        db_session.flush()

        db_session.add(
            ServiceSummary(tenant_id=base_data["tenant"].id, session_id=base_data["session"].id)
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_ivr_callback_idempotent_per_session(
        self, db_session: Session, base_data: dict
    ) -> None:
        """§78：同一 IVR 会话只允许生成一条回呼任务。"""
        db_session.add(
            CallbackTask(
                tenant_id=base_data["tenant"].id,
                source=CallbackSource.IVR,
                phone="13800001111",
                origin_session_id=base_data["session"].id,
            )
        )
        db_session.flush()

        db_session.add(
            CallbackTask(
                tenant_id=base_data["tenant"].id,
                source=CallbackSource.IVR,
                phone="13800001111",
                origin_session_id=base_data["session"].id,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_manual_callback_not_blocked_by_ivr_index(
        self, db_session: Session, base_data: dict
    ) -> None:
        """人工回呼不受 IVR 幂等索引限制。"""
        for _ in range(2):
            db_session.add(
                CallbackTask(
                    tenant_id=base_data["tenant"].id,
                    source=CallbackSource.MANUAL,
                    phone="13800002222",
                    origin_session_id=base_data["session"].id,
                )
            )
        db_session.flush()


# ---------------- 软删除与唯一索引 ----------------


class TestSoftDeleteReuse:
    def test_scene_code_can_be_reused_after_soft_delete(
        self, db_session: Session, base_data: dict
    ) -> None:
        old = OutboundNumber(
            tenant_id=base_data["tenant"].id, display_name="旧号码", caller_number="02177776666"
        )
        db_session.add(old)
        db_session.flush()

        old.mark_deleted()
        db_session.flush()

        new = OutboundNumber(
            tenant_id=base_data["tenant"].id, display_name="新号码", caller_number="02177776666"
        )
        db_session.add(new)
        db_session.flush()
        assert new.id != old.id


# ---------------- 外键与枚举 ----------------


class TestForeignKeys:
    def test_agent_requires_existing_user(self, db_session: Session, base_data: dict) -> None:
        db_session.add(Agent(user_id=999999, tenant_id=base_data["tenant"].id))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_task_requires_existing_tenant(self, db_session: Session) -> None:
        db_session.add(OutboundTask(tenant_id=999999, task_name="孤儿任务"))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_hard_delete_task_cascades_task_numbers(
        self, db_session: Session, base_data: dict
    ) -> None:
        db_session.add(
            OutboundTaskNumber(
                tenant_id=base_data["tenant"].id,
                task_id=base_data["task"].id,
                number_id=base_data["number"].id,
            )
        )
        db_session.flush()

        db_session.delete(base_data["task"])
        db_session.flush()

        remaining = db_session.execute(
            text("SELECT count(*) FROM outbound_task_numbers WHERE task_id = :tid"),
            {"tid": base_data["task"].id},
        ).scalar_one()
        assert remaining == 0


class TestEnums:
    def test_invalid_status_value_rejected_on_flush(self, db_session: Session) -> None:
        """枚举列只接受枚举成员，禁止魔法字符串。"""
        db_session.add(Tenant(code="T999", name="非法状态", status="NOT_A_STATUS"))
        with pytest.raises(StatementError) as exc_info:
            db_session.flush()
        assert isinstance(exc_info.value.orig, LookupError)

    def test_record_status_defaults_and_roundtrip(
        self, db_session: Session, base_data: dict
    ) -> None:
        record = OutboundRecord(
            tenant_id=base_data["tenant"].id,
            task_id=base_data["task"].id,
            list_id=base_data["list"].id,
        )
        db_session.add(record)
        db_session.flush()
        db_session.refresh(record)

        assert record.status is RecordStatus.PENDING
        assert record.retry_count == 0
        assert record.current_attempt == 0

    def test_stored_status_is_readable_text(self, db_session: Session, base_data: dict) -> None:
        raw = db_session.execute(
            text("SELECT status FROM outbound_tasks WHERE id = :tid"),
            {"tid": base_data["task"].id},
        ).scalar_one()
        assert raw == "DRAFT"


# ---------------- 关系 ----------------


class TestRelationships:
    def test_task_numbers_loaded_with_task(self, db_session: Session, base_data: dict) -> None:
        db_session.add(
            OutboundTaskNumber(
                tenant_id=base_data["tenant"].id,
                task_id=base_data["task"].id,
                number_id=base_data["number"].id,
                user_id=1,
                order_id=2,
            )
        )
        db_session.flush()
        db_session.expire_all()

        task = db_session.get(OutboundTask, base_data["task"].id)
        assert task is not None
        assert len(task.task_numbers) == 1
        assert task.task_numbers[0].user_id == 1
        assert task.task_numbers[0].order_id == 2

    def test_ivr_flow_nodes_and_transitions(self, db_session: Session, base_data: dict) -> None:
        flow = IvrFlow(
            tenant_id=base_data["tenant"].id, code="F001", name="回呼流程", entry_node_key="start"
        )
        db_session.add(flow)
        db_session.flush()

        welcome = IvrNode(
            tenant_id=base_data["tenant"].id,
            flow_id=flow.id,
            node_key="start",
            name="欢迎语",
            node_type="PLAY",
        )
        db_session.add(welcome)
        db_session.flush()

        transfer = IvrNode(
            tenant_id=base_data["tenant"].id,
            flow_id=flow.id,
            node_key="transfer",
            name="转人工",
            node_type="TRANSFER_AGENT",
        )
        db_session.add(transfer)
        db_session.flush()

        db_session.add(
            IvrTransition(
                tenant_id=base_data["tenant"].id,
                flow_id=flow.id,
                from_node_id=welcome.id,
                to_node_id=transfer.id,
                condition_type="KEY",
                condition_value="1",
            )
        )
        db_session.flush()
        db_session.expire_all()

        loaded = db_session.get(IvrFlow, flow.id)
        assert loaded is not None
        assert len(loaded.nodes) == 2
        assert len(loaded.transitions) == 1

    def test_duplicate_ivr_node_key_in_same_flow_rejected(
        self, db_session: Session, base_data: dict
    ) -> None:
        flow = IvrFlow(tenant_id=base_data["tenant"].id, code="F002", name="重复节点流程")
        db_session.add(flow)
        db_session.flush()

        for _ in range(2):
            db_session.add(
                IvrNode(
                    tenant_id=base_data["tenant"].id,
                    flow_id=flow.id,
                    node_key="dup",
                    name="重复",
                    node_type="PLAY",
                )
            )
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestTimeoutScanIndex:
    def test_timeout_scan_query_uses_expected_rows(
        self, db_session: Session, base_data: dict
    ) -> None:
        """§22 超时回收扫描：status ∈ (ASSIGNED, CALLING) 且 timeout_at < now()。"""
        past = datetime(2000, 1, 1, tzinfo=timezone.utc)
        db_session.add_all(
            [
                OutboundRecord(
                    tenant_id=base_data["tenant"].id,
                    task_id=base_data["task"].id,
                    list_id=base_data["list"].id,
                    status=RecordStatus.ASSIGNED,
                    timeout_at=past,
                ),
                OutboundRecord(
                    tenant_id=base_data["tenant"].id,
                    task_id=base_data["task"].id,
                    list_id=base_data["list2"].id,
                    status=RecordStatus.PENDING,
                    timeout_at=past,
                ),
            ]
        )
        db_session.flush()

        rows = db_session.execute(
            text(
                "SELECT count(*) FROM outbound_records "
                "WHERE status IN ('ASSIGNED', 'CALLING') AND timeout_at < now()"
            )
        ).scalar_one()
        assert rows == 1
