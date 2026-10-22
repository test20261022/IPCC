"""外呼任务接口测试（OB-006 / OB-020 / §18 状态机）。"""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import OutboundList, OutboundRecord
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound/tasks"

ALL_TASK_PERMS = (
    "outbound:task:list",
    "outbound:task:create",
    "outbound:task:update",
    "outbound:task:delete",
    "outbound:task:copy",
)


def _payload(tenant_id: int, task_name: str, **overrides) -> dict:
    payload = {"tenant_id": tenant_id, "task_name": task_name}
    payload.update(overrides)
    return payload


def _create_task(client: TestClient, token: str, tenant_id: int, name: str, **overrides) -> dict:
    response = client.post(
        PREFIX, headers=auth_headers(token), json=_payload(tenant_id, name, **overrides)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _change_status(client: TestClient, token: str, task_id: int, status: str):
    return client.put(
        f"{PREFIX}/{task_id}/status", headers=auth_headers(token), json={"status": status}
    )


def _make_running_task(
    client: TestClient, token: str, tenant_id: int, number_id: int, name: str
) -> dict:
    task = _create_task(client, token, tenant_id, name, numbers=[{"number_id": number_id}])
    assert _change_status(client, token, task["id"], "READY").status_code == 200
    assert _change_status(client, token, task["id"], "RUNNING").status_code == 200
    return task


class TestTaskPermissions:
    def test_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("task_no_perm", "outbound:number:list")
        assert client.get(PREFIX, headers=auth_headers(token)).status_code == 403

    def test_create_requires_permission(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("task_only_list", "outbound:task:list")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(tenant.id, "无权限任务")
        )
        assert response.status_code == 403
        assert response.json()["code"] == 40301

    def test_copy_requires_permission(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        token = user_token("task_no_copy", "outbound:task:list", "outbound:task:create")
        response = client.post(
            f"{PREFIX}/{outbound_task.id}/copy",
            headers=auth_headers(token),
            json={"task_name": "复制品"},
        )
        assert response.status_code == 403

    def test_delete_requires_permission(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        token = user_token("task_no_delete", "outbound:task:update")
        assert (
            client.delete(f"{PREFIX}/{outbound_task.id}", headers=auth_headers(token)).status_code
            == 403
        )


class TestTaskCreate:
    def test_create_minimal(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("task_creator", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(tenant.id, "最小任务")
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "DRAFT"
        assert data["dispatch_mode"] == "MANUAL"
        assert data["number_select_strategy"] == "ORDER"
        assert data["max_retry_count"] == 3
        assert data["copied_from_id"] is None

    def test_create_with_all_references(
        self,
        client: TestClient,
        user_token,
        tenant,
        site,
        skill_queue,
        outbound_type,
        outbound_scene,
        ivr_flow,
    ) -> None:
        token = user_token("task_full", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(
                tenant.id,
                "全配置任务",
                site_id=site.id,
                skill_queue_id=skill_queue.id,
                type_id=outbound_type.id,
                scene_id=outbound_scene.id,
                ivr_flow_id=ivr_flow.id,
                dispatch_mode="PREDICTIVE",
                number_select_strategy="ROUND_ROBIN",
                retry_interval=30,
                max_retry_count=5,
                call_timeout_seconds=45,
                max_concurrency=20,
            ),
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["site_id"] == site.id
        assert data["skill_queue_id"] == skill_queue.id
        assert data["dispatch_mode"] == "PREDICTIVE"
        assert data["max_concurrency"] == 20

    def test_duplicate_name_conflict(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("task_dup", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(outbound_task.tenant_id, outbound_task.task_name),
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40901

    def test_create_with_numbers(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_with_numbers", *ALL_TASK_PERMS)
        task = _create_task(
            client,
            token,
            tenant.id,
            "带号码任务",
            numbers=[{"number_id": outbound_number.id, "user_id": 1, "order_id": 2}],
        )
        detail = client.get(f"{PREFIX}/{task['id']}", headers=auth_headers(token)).json()["data"]
        assert len(detail["task_numbers"]) == 1
        assert detail["task_numbers"][0]["user_id"] == 1
        assert detail["task_numbers"][0]["order_id"] == 2

    def test_duplicate_number_in_payload(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_dup_number", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(
                tenant.id,
                "重复号码任务",
                numbers=[{"number_id": outbound_number.id}, {"number_id": outbound_number.id}],
            ),
        )
        assert response.status_code == 400
        assert "重复" in response.json()["message"]

    def test_unknown_number(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("task_bad_number", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(tenant.id, "号码不存在", numbers=[{"number_id": 999999}]),
        )
        assert response.status_code == 404

    def test_number_from_other_tenant(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        from app.models.outbound import OutboundNumber, Tenant

        other = Tenant(code="TENANT-OTHER", name="其他租户")
        db_session.add(other)
        db_session.flush()
        foreign_number = OutboundNumber(
            tenant_id=other.id, display_name="外部号码", caller_number="02111112222"
        )
        db_session.add(foreign_number)
        db_session.flush()

        token = user_token("task_cross_number", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(tenant.id, "跨租户号码", numbers=[{"number_id": foreign_number.id}]),
        )
        assert response.status_code == 400
        assert "同一租户" in response.json()["message"]

    def test_unknown_site(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("task_bad_site", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(tenant.id, "站点不存在", site_id=999999),
        )
        assert response.status_code == 404

    def test_scene_type_mismatch(
        self, client: TestClient, user_token, tenant, outbound_type, outbound_scene
    ) -> None:
        token = user_token("task_scene_mismatch", *ALL_TASK_PERMS, "outbound:type:create")
        other_type = client.post(
            f"{settings.API_V1_PREFIX}/outbound/types",
            headers=auth_headers(token),
            json={"tenant_id": tenant.id, "code": "TP-MISMATCH", "name": "另一类型", "level": 1},
        ).json()["data"]

        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(
                tenant.id,
                "场景类型不一致",
                type_id=other_type["id"],
                scene_id=outbound_scene.id,
            ),
        )
        assert response.status_code == 400
        assert "场景" in response.json()["message"]

    def test_queue_site_mismatch(
        self, client: TestClient, user_token, tenant, site, skill_queue, db_session: Session
    ) -> None:
        from app.models.outbound import Site

        other_site = Site(tenant_id=tenant.id, code="SITE-002", name="站点二")
        db_session.add(other_site)
        db_session.flush()

        token = user_token("task_queue_mismatch", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(
                tenant.id,
                "队列站点不匹配",
                site_id=other_site.id,
                skill_queue_id=skill_queue.id,
            ),
        )
        assert response.status_code == 400
        assert "站点" in response.json()["message"]

    def test_unknown_tenant(self, client: TestClient, user_token) -> None:
        token = user_token("task_bad_tenant", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(999999, "孤儿任务")
        )
        assert response.status_code == 404


class TestTaskQuery:
    """OB-006：站点 / 技能队列 / 外呼类型查询。"""

    def test_filter_by_site_queue_and_type(
        self,
        client: TestClient,
        user_token,
        tenant,
        site,
        skill_queue,
        outbound_type,
    ) -> None:
        token = user_token("task_filter", *ALL_TASK_PERMS)
        _create_task(
            client,
            token,
            tenant.id,
            "筛选-全配置",
            site_id=site.id,
            skill_queue_id=skill_queue.id,
            type_id=outbound_type.id,
        )
        _create_task(client, token, tenant.id, "筛选-无配置")

        for params, expected in (
            ({"site_id": site.id}, 1),
            ({"skill_queue_id": skill_queue.id}, 1),
            ({"type_id": outbound_type.id}, 1),
            ({"site_id": 999999}, 0),
        ):
            response = client.get(
                PREFIX,
                headers=auth_headers(token),
                params={"tenant_id": tenant.id, **params},
            )
            assert response.status_code == 200
            assert response.json()["data"]["total"] == expected, params

    def test_filter_by_status_and_name(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("task_filter_status", *ALL_TASK_PERMS)
        _create_task(client, token, tenant.id, "状态-A")

        response = client.get(
            PREFIX,
            headers=auth_headers(token),
            params={"tenant_id": tenant.id, "status": "DRAFT", "task_name": "状态"},
        )
        assert response.json()["data"]["total"] == 1

        response = client.get(
            PREFIX,
            headers=auth_headers(token),
            params={"tenant_id": tenant.id, "status": "RUNNING"},
        )
        assert response.json()["data"]["total"] == 0

    def test_detail_unknown_task(self, client: TestClient, user_token) -> None:
        token = user_token("task_detail_404", "outbound:task:list")
        assert client.get(f"{PREFIX}/999999", headers=auth_headers(token)).status_code == 404


class TestTaskUpdate:
    def test_update_name(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("task_rename", *ALL_TASK_PERMS)
        response = client.put(
            f"{PREFIX}/{outbound_task.id}",
            headers=auth_headers(token),
            json={"task_name": "改名任务", "max_retry_count": 9},
        )
        assert response.status_code == 200
        assert response.json()["data"]["task_name"] == "改名任务"
        assert response.json()["data"]["max_retry_count"] == 9

    def test_rename_to_existing_name(
        self, client: TestClient, user_token, tenant, outbound_task
    ) -> None:
        token = user_token("task_rename_dup", *ALL_TASK_PERMS)
        _create_task(client, token, tenant.id, "已存在的名字")

        response = client.put(
            f"{PREFIX}/{outbound_task.id}",
            headers=auth_headers(token),
            json={"task_name": "已存在的名字"},
        )
        assert response.status_code == 409

    def test_cannot_update_running_task(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_update_running", *ALL_TASK_PERMS)
        task = _make_running_task(client, token, tenant.id, outbound_number.id, "运行中任务")

        response = client.put(
            f"{PREFIX}/{task['id']}", headers=auth_headers(token), json={"max_retry_count": 7}
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_reference_validation_on_update(
        self, client: TestClient, user_token, outbound_task, site
    ) -> None:
        token = user_token("task_update_ref", *ALL_TASK_PERMS)
        assert (
            client.put(
                f"{PREFIX}/{outbound_task.id}",
                headers=auth_headers(token),
                json={"site_id": site.id},
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"{PREFIX}/{outbound_task.id}",
                headers=auth_headers(token),
                json={"site_id": 999999},
            ).status_code
            == 404
        )


class TestTaskStatusMachine:
    def test_ready_requires_enabled_number(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("task_ready_no_number", *ALL_TASK_PERMS)
        task = _create_task(client, token, tenant.id, "无号码不允许就绪")

        response = _change_status(client, token, task["id"], "READY")
        assert response.status_code == 409
        assert response.json()["code"] == 40902
        assert "号码" in response.json()["message"]

    def test_draft_to_running_rejected(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_skip_ready", *ALL_TASK_PERMS)
        task = _create_task(
            client, token, tenant.id, "跳级任务", numbers=[{"number_id": outbound_number.id}]
        )

        response = _change_status(client, token, task["id"], "RUNNING")
        assert response.status_code == 409
        assert "DRAFT" in response.json()["message"]

    def test_happy_path_records_timestamps(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_happy", *ALL_TASK_PERMS)
        task = _create_task(
            client, token, tenant.id, "主流程任务", numbers=[{"number_id": outbound_number.id}]
        )

        ready = _change_status(client, token, task["id"], "READY")
        assert ready.status_code == 200
        assert ready.json()["data"]["started_at"] is None

        running = _change_status(client, token, task["id"], "RUNNING")
        assert running.status_code == 200
        assert running.json()["data"]["started_at"] is not None

        paused = _change_status(client, token, task["id"], "PAUSED")
        assert paused.status_code == 200

        resumed = _change_status(client, token, task["id"], "RUNNING")
        assert resumed.status_code == 200

        completed = _change_status(client, token, task["id"], "COMPLETED")
        assert completed.status_code == 200
        assert completed.json()["data"]["finished_at"] is not None

    def test_completed_is_terminal(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_terminal", *ALL_TASK_PERMS)
        task = _create_task(
            client, token, tenant.id, "终结任务", numbers=[{"number_id": outbound_number.id}]
        )
        _change_status(client, token, task["id"], "READY")
        _change_status(client, token, task["id"], "RUNNING")
        _change_status(client, token, task["id"], "COMPLETED")

        response = _change_status(client, token, task["id"], "READY")
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_same_status_rejected(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("task_same_status", *ALL_TASK_PERMS)
        task = _create_task(client, token, tenant.id, "同状态任务")

        response = _change_status(client, token, task["id"], "DRAFT")
        assert response.status_code == 409
        assert "已处于" in response.json()["message"]

    def test_invalid_status_value(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("task_bad_status", *ALL_TASK_PERMS)
        task = _create_task(client, token, tenant.id, "非法状态任务")

        response = _change_status(client, token, task["id"], "NOT_A_STATUS")
        assert response.status_code == 400


class TestTaskNumbers:
    def test_replace_numbers(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        from app.models.outbound import OutboundNumber

        first = OutboundNumber(
            tenant_id=tenant.id, display_name="号码一", caller_number="02112340001"
        )
        second = OutboundNumber(
            tenant_id=tenant.id, display_name="号码二", caller_number="02112340002"
        )
        db_session.add_all([first, second])
        db_session.flush()

        token = user_token("task_replace_numbers", *ALL_TASK_PERMS)
        task = _create_task(client, token, tenant.id, "替换号码任务")

        response = client.put(
            f"{PREFIX}/{task['id']}/numbers",
            headers=auth_headers(token),
            json={"numbers": [{"number_id": first.id}, {"number_id": second.id, "sort_order": 1}]},
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 2

        response = client.put(
            f"{PREFIX}/{task['id']}/numbers",
            headers=auth_headers(token),
            json={"numbers": [{"number_id": second.id}]},
        )
        assert response.status_code == 200
        assert [item["number_id"] for item in response.json()["data"]] == [second.id]

    def test_replace_with_invalid_number_keeps_originals(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_replace_bad", *ALL_TASK_PERMS)
        task = _create_task(
            client, token, tenant.id, "替换失败任务", numbers=[{"number_id": outbound_number.id}]
        )

        response = client.put(
            f"{PREFIX}/{task['id']}/numbers",
            headers=auth_headers(token),
            json={"numbers": [{"number_id": 999999}]},
        )
        assert response.status_code == 404

        detail = client.get(f"{PREFIX}/{task['id']}", headers=auth_headers(token)).json()["data"]
        assert [item["number_id"] for item in detail["task_numbers"]] == [outbound_number.id]

    def test_replace_rejected_in_running(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_replace_running", *ALL_TASK_PERMS)
        task = _make_running_task(client, token, tenant.id, outbound_number.id, "运行中改号码")

        response = client.put(
            f"{PREFIX}/{task['id']}/numbers",
            headers=auth_headers(token),
            json={"numbers": [{"number_id": outbound_number.id}]},
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902


class TestTaskCopy:
    """OB-020 任务复制。"""

    def test_copy_creates_draft_with_config(
        self, client: TestClient, user_token, tenant, outbound_number, site, skill_queue
    ) -> None:
        token = user_token("task_copy", *ALL_TASK_PERMS)
        source = _create_task(
            client,
            token,
            tenant.id,
            "源任务",
            site_id=site.id,
            skill_queue_id=skill_queue.id,
            retry_interval=15,
            max_retry_count=4,
            numbers=[{"number_id": outbound_number.id, "user_id": 1}],
        )

        response = client.post(
            f"{PREFIX}/{source['id']}/copy",
            headers=auth_headers(token),
            json={"task_name": "副本任务"},
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["created"] is True

        copy = client.get(
            f"{PREFIX}/{body['task']['id']}", headers=auth_headers(token)
        ).json()["data"]
        assert copy["status"] == "DRAFT"
        assert copy["copied_from_id"] == source["id"]
        assert copy["retry_interval"] == 15
        assert copy["max_retry_count"] == 4
        assert copy["site_id"] == site.id
        assert copy["skill_queue_id"] == skill_queue.id
        assert [item["number_id"] for item in copy["task_numbers"]] == [outbound_number.id]
        assert copy["started_at"] is None
        assert copy["finished_at"] is None

    def test_copy_is_idempotent(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        """§78：同名副本重复提交必须返回同一条，不得产生第二份。"""
        token = user_token("task_copy_idem", *ALL_TASK_PERMS)
        source = _create_task(client, token, tenant.id, "幂等源任务")

        first = client.post(
            f"{PREFIX}/{source['id']}/copy",
            headers=auth_headers(token),
            json={"task_name": "幂等副本"},
        ).json()["data"]
        second = client.post(
            f"{PREFIX}/{source['id']}/copy",
            headers=auth_headers(token),
            json={"task_name": "幂等副本"},
        ).json()["data"]

        assert first["created"] is True
        assert second["created"] is False
        assert first["task"]["id"] == second["task"]["id"]

        listing = client.get(
            PREFIX,
            headers=auth_headers(token),
            params={"tenant_id": tenant.id, "task_name": "幂等副本"},
        ).json()["data"]
        assert listing["total"] == 1

    def test_copy_to_taken_name_conflicts(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("task_copy_conflict", *ALL_TASK_PERMS)
        source = _create_task(client, token, tenant.id, "冲突源任务")
        _create_task(client, token, tenant.id, "已被占用")

        response = client.post(
            f"{PREFIX}/{source['id']}/copy",
            headers=auth_headers(token),
            json={"task_name": "已被占用"},
        )
        assert response.status_code == 409

    def test_copy_without_numbers(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_copy_nonumbers", *ALL_TASK_PERMS)
        source = _create_task(
            client, token, tenant.id, "不复制号码源", numbers=[{"number_id": outbound_number.id}]
        )

        created = client.post(
            f"{PREFIX}/{source['id']}/copy",
            headers=auth_headers(token),
            json={"task_name": "不复制号码副本", "copy_numbers": False},
        ).json()["data"]

        detail = client.get(
            f"{PREFIX}/{created['task']['id']}", headers=auth_headers(token)
        ).json()["data"]
        assert detail["task_numbers"] == []

    def test_copy_does_not_copy_execution_data(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        """§23：名单 / 执行记录等执行数据绝不复制。"""
        token = user_token("task_copy_execution", *ALL_TASK_PERMS)
        source = _create_task(client, token, tenant.id, "带执行数据的源任务")

        name_list = OutboundList(tenant_id=tenant.id, task_id=source["id"], user_id="U-COPY")
        db_session.add(name_list)
        db_session.flush()
        db_session.add(
            OutboundRecord(tenant_id=tenant.id, task_id=source["id"], list_id=name_list.id)
        )
        db_session.flush()

        created = client.post(
            f"{PREFIX}/{source['id']}/copy",
            headers=auth_headers(token),
            json={"task_name": "无执行数据的副本"},
        ).json()["data"]
        new_task_id = created["task"]["id"]

        list_count = db_session.execute(
            select(func.count())
            .select_from(OutboundList)
            .where(OutboundList.task_id == new_task_id)
        ).scalar_one()
        record_count = db_session.execute(
            select(func.count())
            .select_from(OutboundRecord)
            .where(OutboundRecord.task_id == new_task_id)
        ).scalar_one()
        assert list_count == 0
        assert record_count == 0

    def test_copy_unknown_task(self, client: TestClient, user_token) -> None:
        token = user_token("task_copy_404", *ALL_TASK_PERMS)
        response = client.post(
            f"{PREFIX}/999999/copy", headers=auth_headers(token), json={"task_name": "幽灵副本"}
        )
        assert response.status_code == 404


class TestTaskDelete:
    def test_delete_draft_task_removes_numbers(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_delete", *ALL_TASK_PERMS)
        task = _create_task(
            client, token, tenant.id, "待删除任务", numbers=[{"number_id": outbound_number.id}]
        )

        response = client.delete(f"{PREFIX}/{task['id']}", headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["data"] == {"task_id": task["id"], "removed_task_numbers": 1}
        assert client.get(f"{PREFIX}/{task['id']}", headers=auth_headers(token)).status_code == 404

    def test_delete_running_task_rejected(
        self, client: TestClient, user_token, tenant, outbound_number
    ) -> None:
        token = user_token("task_delete_running", *ALL_TASK_PERMS)
        task = _make_running_task(client, token, tenant.id, outbound_number.id, "运行中禁删")

        response = client.delete(f"{PREFIX}/{task['id']}", headers=auth_headers(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40902
        assert "取消" in response.json()["message"]

    def test_delete_task_with_execution_records_rejected(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        token = user_token("task_delete_records", *ALL_TASK_PERMS)
        task = _create_task(client, token, tenant.id, "有执行记录的任务")

        name_list = OutboundList(tenant_id=tenant.id, task_id=task["id"], user_id="U-DEL")
        db_session.add(name_list)
        db_session.flush()
        db_session.add(
            OutboundRecord(tenant_id=tenant.id, task_id=task["id"], list_id=name_list.id)
        )
        db_session.flush()

        response = client.delete(f"{PREFIX}/{task['id']}", headers=auth_headers(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40904
        assert "执行记录" in response.json()["message"]

    def test_delete_cancelled_task_allowed(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("task_delete_cancelled", *ALL_TASK_PERMS)
        task = _create_task(client, token, tenant.id, "取消后可删")
        assert _change_status(client, token, task["id"], "CANCELLED").status_code == 200

        response = client.delete(f"{PREFIX}/{task['id']}", headers=auth_headers(token))
        assert response.status_code == 200

    def test_delete_unknown_task(self, client: TestClient, user_token) -> None:
        token = user_token("task_delete_404", *ALL_TASK_PERMS)
        assert client.delete(f"{PREFIX}/999999", headers=auth_headers(token)).status_code == 404


class TestRetryLimits:
    """规则 4 确认结果：重试间隔 ≤ 24h、最大重试次数 ≤ 10（ASSUMPTION-057）。"""

    def test_create_accepts_boundary_values(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("retry_boundary", *ALL_TASK_PERMS)
        task = _create_task(
            client,
            token,
            tenant.id,
            "边界重试任务",
            retry_interval=86400,
            max_retry_count=10,
        )
        assert task["retry_interval"] == 86400
        assert task["max_retry_count"] == 10

    def test_create_rejects_retry_interval_over_limit(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("retry_interval_over", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(tenant.id, "间隔超限任务", retry_interval=86401),
        )
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_create_rejects_retry_count_over_limit(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("retry_count_over", *ALL_TASK_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(tenant.id, "次数超限任务", max_retry_count=11),
        )
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_update_rejects_over_limit(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("retry_update_over", *ALL_TASK_PERMS)
        task = _create_task(client, token, tenant.id, "更新超限任务")

        over_interval = client.put(
            f"{PREFIX}/{task['id']}",
            headers=auth_headers(token),
            json={"retry_interval": 999999},
        )
        assert over_interval.status_code == 400

        over_count = client.put(
            f"{PREFIX}/{task['id']}",
            headers=auth_headers(token),
            json={"max_retry_count": 99},
        )
        assert over_count.status_code == 400

    def test_zero_retry_is_allowed(
        self, client: TestClient, user_token, tenant
    ) -> None:
        """0 表示不重试，属于合法配置（不可用 ge=1 卡掉）。"""
        token = user_token("retry_zero", *ALL_TASK_PERMS)
        task = _create_task(
            client, token, tenant.id, "不重试任务", retry_interval=0, max_retry_count=0
        )
        assert task["max_retry_count"] == 0
        assert task["retry_interval"] == 0
