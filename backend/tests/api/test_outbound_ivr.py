"""IVR 外呼策略接口测试（OB-017）。"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import IvrNode, IvrTransition

PREFIX = f"{settings.API_V1_PREFIX}/outbound/ivr"
OPTIONS_PREFIX = f"{settings.API_V1_PREFIX}/outbound/options"

ALL_IVR_PERMS = (
    "outbound:ivr:list",
    "outbound:ivr:create",
    "outbound:ivr:update",
    "outbound:ivr:delete",
)


def _create_flow(client: TestClient, headers: dict, tenant_id: int, code: str = "IVR-NEW"):
    response = client.post(
        f"{PREFIX}/flows",
        headers=headers,
        json={"tenant_id": tenant_id, "code": code, "name": f"流程-{code}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_node(client: TestClient, headers: dict, flow: dict, **overrides) -> dict:
    payload = {
        "tenant_id": flow["tenant_id"],
        "node_key": "menu",
        "name": "主菜单",
        "node_type": "COLLECT_DTMF",
        "content": "请按 1 转人工",
        "max_replay": 2,
    }
    payload.update(overrides)
    response = client.post(f"{PREFIX}/flows/{flow['id']}/nodes", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_transition(
    client: TestClient, headers: dict, flow: dict, **overrides
) -> dict:
    payload = {
        "tenant_id": flow["tenant_id"],
        "from_node_id": 0,
        "to_node_id": None,
        "condition_type": "KEY",
        "condition_value": "1",
        "priority": 0,
    }
    payload.update(overrides)
    response = client.post(
        f"{PREFIX}/flows/{flow['id']}/transitions", headers=headers, json=payload
    )
    return response


class TestIvrPermissions:
    def test_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("ivr_no_perm", "outbound:type:list")
        assert client.get(f"{PREFIX}/flows", headers=_auth(token)).status_code == 403

    def test_create_requires_permission(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = user_token("ivr_list_only", "outbound:ivr:list")
        response = client.post(
            f"{PREFIX}/flows",
            headers=_auth(token),
            json={"tenant_id": tenant.id, "code": "IVR-X", "name": "无权限"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == 40301

    def test_delete_requires_permission(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_delete_denied", "outbound:ivr:list")
        response = client.delete(f"{PREFIX}/flows/{ivr_flow.id}", headers=_auth(token))
        assert response.status_code == 403


def _auth(token: str) -> dict[str, str]:
    from tests.conftest import auth_headers

    return auth_headers(token)


class TestFlowCrud:
    def test_create_and_list(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("ivr_admin", *ALL_IVR_PERMS)
        flow = _create_flow(client, _auth(token), tenant.id, code="IVR-LIST")

        listed = client.get(
            f"{PREFIX}/flows",
            headers=_auth(token),
            params={"tenant_id": tenant.id, "code": "IVR-LIST"},
        )
        assert listed.status_code == 200
        data = listed.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["id"] == flow["id"]

    def test_duplicate_code_rejected(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("ivr_dup", *ALL_IVR_PERMS)
        _create_flow(client, _auth(token), tenant.id, code="IVR-DUP")

        again = client.post(
            f"{PREFIX}/flows",
            headers=_auth(token),
            json={"tenant_id": tenant.id, "code": "IVR-DUP", "name": "重复"},
        )
        assert again.status_code == 409
        assert again.json()["code"] == 40901

    def test_create_requires_active_tenant(self, client: TestClient, user_token) -> None:
        token = user_token("ivr_tenant_check", *ALL_IVR_PERMS)
        response = client.post(
            f"{PREFIX}/flows",
            headers=_auth(token),
            json={"tenant_id": 999999, "code": "IVR-NO-TENANT", "name": "租户不存在"},
        )
        assert response.status_code == 404
        assert response.json()["code"] == 40401

    def test_update_entry_node_validates_existence(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_entry", *ALL_IVR_PERMS)
        response = client.put(
            f"{PREFIX}/flows/{ivr_flow.id}",
            headers=_auth(token),
            json={"entry_node_key": "not-exist"},
        )
        assert response.status_code == 400
        assert "入口节点不存在" in response.json()["message"]

    def test_detail_returns_nodes_and_transitions(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_detail", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = ivr_flow
        menu = _create_node(client, headers, _flow_payload(flow), node_key="menu")
        bye = _create_node(
            client, headers, _flow_payload(flow), node_key="bye", node_type="HANGUP"
        )
        created = _create_transition(
            client,
            headers,
            _flow_payload(flow),
            from_node_id=menu["id"],
            to_node_id=bye["id"],
        )
        assert created.status_code == 200, created.text

        client.put(
            f"{PREFIX}/flows/{flow.id}",
            headers=headers,
            json={"entry_node_key": "menu"},
        )

        detail = client.get(f"{PREFIX}/flows/{flow.id}", headers=headers)
        assert detail.status_code == 200
        data = detail.json()["data"]
        assert data["entry_node_key"] == "menu"
        assert len(data["nodes"]) == 2
        assert len(data["transitions"]) == 1
        assert data["transitions"][0]["to_node_id"] == bye["id"]

    def test_delete_flow_cascades(
        self, client: TestClient, user_token, ivr_flow, db_session
    ) -> None:
        token = user_token("ivr_delete", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        menu = _create_node(client, headers, flow, node_key="menu")
        bye = _create_node(client, headers, flow, node_key="bye", node_type="HANGUP")
        transition = _create_transition(
            client, headers, flow, from_node_id=menu["id"], to_node_id=bye["id"]
        ).json()["data"]

        response = client.delete(f"{PREFIX}/flows/{ivr_flow.id}", headers=headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["removed_nodes"] == 2
        assert data["removed_transitions"] == 1

        db_session.expire_all()
        assert db_session.get(IvrNode, menu["id"]).is_deleted is True
        assert db_session.get(IvrTransition, transition["id"]).is_deleted is True
        assert ivr_flow.is_deleted is True

    def test_delete_referenced_flow_rejected(
        self, client: TestClient, user_token, ivr_flow, outbound_task, db_session
    ) -> None:
        token = user_token("ivr_ref", *ALL_IVR_PERMS)
        outbound_task.ivr_flow_id = ivr_flow.id
        db_session.flush()

        response = client.delete(f"{PREFIX}/flows/{ivr_flow.id}", headers=_auth(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40904
        assert outbound_task.task_name in response.json()["message"]

    def test_disable_referenced_flow_rejected(
        self, client: TestClient, user_token, ivr_flow, outbound_task, db_session
    ) -> None:
        token = user_token("ivr_disable", *ALL_IVR_PERMS)
        outbound_task.ivr_flow_id = ivr_flow.id
        db_session.flush()

        response = client.put(
            f"{PREFIX}/flows/{ivr_flow.id}/status",
            headers=_auth(token),
            json={"status": "DISABLED"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40904

    def test_disable_unreferenced_flow(self, client: TestClient, user_token, ivr_flow) -> None:
        token = user_token("ivr_disable_ok", *ALL_IVR_PERMS)
        response = client.put(
            f"{PREFIX}/flows/{ivr_flow.id}/status",
            headers=_auth(token),
            json={"status": "DISABLED"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "DISABLED"


def _flow_payload(ivr_flow) -> dict:
    """把 fixture 的 ORM 对象转成测试辅助函数需要的字典。"""
    return {"id": ivr_flow.id, "tenant_id": ivr_flow.tenant_id}


class TestNodeRules:
    def test_transfer_agent_requires_fallback_action(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_transfer", *ALL_IVR_PERMS)
        payload = {
            "tenant_id": ivr_flow.tenant_id,
            "node_key": "transfer",
            "name": "转人工",
            "node_type": "TRANSFER_AGENT",
        }
        response = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/nodes", headers=_auth(token), json=payload
        )
        assert response.status_code == 400
        assert "无可用坐席动作" in response.json()["message"]

        payload["no_agent_action"] = "CALLBACK"
        ok = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/nodes", headers=_auth(token), json=payload
        )
        assert ok.status_code == 200
        assert ok.json()["data"]["no_agent_action"] == "CALLBACK"

    def test_duplicate_node_key_rejected(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_node_dup", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        _create_node(client, headers, flow, node_key="menu")

        again = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/nodes",
            headers=headers,
            json={
                "tenant_id": ivr_flow.tenant_id,
                "node_key": "menu",
                "name": "重复节点",
                "node_type": "HANGUP",
            },
        )
        assert again.status_code == 409
        assert again.json()["code"] == 40901

    def test_update_node_clears_required_action(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        """把节点改成转人工但未给兜底动作时必须被拒绝。"""
        token = user_token("ivr_node_switch", *ALL_IVR_PERMS)
        headers = _auth(token)
        node = _create_node(client, headers, _flow_payload(ivr_flow), node_key="menu")

        response = client.put(
            f"{PREFIX}/nodes/{node['id']}",
            headers=headers,
            json={"node_type": "TRANSFER_AGENT"},
        )
        assert response.status_code == 400
        assert "无可用坐席动作" in response.json()["message"]

    def test_create_node_tenant_mismatch(
        self, client: TestClient, user_token, ivr_flow, disabled_tenant
    ) -> None:
        token = user_token("ivr_node_tenant", *ALL_IVR_PERMS)
        response = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/nodes",
            headers=_auth(token),
            json={
                "tenant_id": disabled_tenant.id,
                "node_key": "x",
                "name": "跨租户",
                "node_type": "HANGUP",
            },
        )
        assert response.status_code == 400
        assert "不属于同一租户" in response.json()["message"]

    def test_delete_node_cascades_and_clears_entry(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_node_delete", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        menu = _create_node(client, headers, flow, node_key="menu")
        bye = _create_node(client, headers, flow, node_key="bye", node_type="HANGUP")
        _create_transition(
            client,
            headers,
            flow,
            from_node_id=menu["id"],
            to_node_id=bye["id"],
        )
        client.put(
            f"{PREFIX}/flows/{ivr_flow.id}", headers=headers, json={"entry_node_key": "menu"}
        )

        response = client.delete(f"{PREFIX}/nodes/{menu['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["removed_transitions"] == 1

        detail = client.get(f"{PREFIX}/flows/{ivr_flow.id}", headers=headers)
        data = detail.json()["data"]
        assert data["entry_node_key"] is None
        assert [node["node_key"] for node in data["nodes"]] == ["bye"]
        assert data["transitions"] == []


class TestTransitionRules:
    def test_from_node_must_belong_to_flow(
        self, client: TestClient, user_token, ivr_flow, tenant
    ) -> None:
        token = user_token("ivr_tr_cross", *ALL_IVR_PERMS)
        other = _create_flow(client, _auth(token), tenant.id, code="IVR-OTHER")
        other_node = _create_node(client, _auth(token), other, node_key="menu")

        response = _create_transition(
            client,
            _auth(token),
            _flow_payload(ivr_flow),
            from_node_id=other_node["id"],
        )
        assert response.status_code == 400
        assert "源节点不属于该 IVR 流程" in response.json()["message"]

    def test_duplicate_condition_rejected(self, client: TestClient, user_token, ivr_flow) -> None:
        token = user_token("ivr_tr_dup", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        menu = _create_node(client, headers, flow, node_key="menu")
        bye = _create_node(client, headers, flow, node_key="bye", node_type="HANGUP")

        first = _create_transition(
            client, headers, flow, from_node_id=menu["id"], to_node_id=bye["id"]
        )
        assert first.status_code == 200
        second = _create_transition(
            client, headers, flow, from_node_id=menu["id"], to_node_id=bye["id"]
        )
        assert second.status_code == 409
        assert second.json()["code"] == 40901

    def test_invalid_time_range_rejected(self, client: TestClient, user_token, ivr_flow) -> None:
        token = user_token("ivr_tr_time", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        menu = _create_node(client, headers, flow, node_key="menu")

        response = _create_transition(
            client,
            headers,
            flow,
            from_node_id=menu["id"],
            condition_type="TIME_RANGE",
            condition_value="09:00",
        )
        assert response.status_code == 400
        assert "时段条件无法解析" in response.json()["message"]

    def test_invalid_queue_condition_rejected(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_tr_queue", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        menu = _create_node(client, headers, flow, node_key="menu")

        response = _create_transition(
            client,
            headers,
            flow,
            from_node_id=menu["id"],
            condition_type="QUEUE_AVAILABLE",
            condition_value="maybe",
        )
        assert response.status_code == 400
        assert "队列可用性取值非法" in response.json()["message"]

    def test_update_and_delete_transition(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_tr_crud", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        menu = _create_node(client, headers, flow, node_key="menu")
        bye = _create_node(client, headers, flow, node_key="bye", node_type="HANGUP")
        created = _create_transition(
            client, headers, flow, from_node_id=menu["id"], to_node_id=bye["id"]
        ).json()["data"]

        updated = client.put(
            f"{PREFIX}/transitions/{created['id']}",
            headers=headers,
            json={"condition_value": "2", "priority": 3},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["condition_value"] == "2"
        assert updated.json()["data"]["priority"] == 3

        removed = client.delete(f"{PREFIX}/transitions/{created['id']}", headers=headers)
        assert removed.status_code == 200
        detail = client.get(f"{PREFIX}/flows/{ivr_flow.id}", headers=headers)
        assert detail.json()["data"]["transitions"] == []


class TestValidation:
    def _full_flow(self, client: TestClient, headers: dict, ivr_flow, **transfer_overrides):
        flow = _flow_payload(ivr_flow)
        menu = _create_node(client, headers, flow, node_key="menu")
        transfer = _create_node(
            client,
            headers,
            flow,
            node_key="transfer",
            node_type="TRANSFER_AGENT",
            no_agent_action="CALLBACK",
            **transfer_overrides,
        )
        bye = _create_node(client, headers, flow, node_key="bye", node_type="HANGUP")
        _create_transition(
            client, headers, flow, from_node_id=menu["id"], to_node_id=transfer["id"]
        )
        _create_transition(
            client,
            headers,
            flow,
            from_node_id=menu["id"],
            to_node_id=bye["id"],
            condition_value="9",
        )
        client.put(
            f"{PREFIX}/flows/{ivr_flow.id}", headers=headers, json={"entry_node_key": "menu"}
        )
        return flow, menu, transfer, bye

    def test_valid_flow(self, client: TestClient, user_token, ivr_flow) -> None:
        token = user_token("ivr_validate_ok", *ALL_IVR_PERMS)
        headers = _auth(token)
        self._full_flow(client, headers, ivr_flow)

        response = client.get(f"{PREFIX}/flows/{ivr_flow.id}/validate", headers=headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["valid"] is True
        assert data["error_count"] == 0
        assert data["node_count"] == 3
        assert data["transition_count"] == 2

    def test_missing_entry_is_error(self, client: TestClient, user_token, ivr_flow) -> None:
        token = user_token("ivr_validate_entry", *ALL_IVR_PERMS)
        headers = _auth(token)
        _create_node(client, headers, _flow_payload(ivr_flow), node_key="menu")

        response = client.get(f"{PREFIX}/flows/{ivr_flow.id}/validate", headers=headers)
        data = response.json()["data"]
        assert data["valid"] is False
        assert any(item["code"] == "ENTRY_MISSING" for item in data["issues"])

    def test_empty_flow_is_error(self, client: TestClient, user_token, ivr_flow) -> None:
        token = user_token("ivr_validate_empty", *ALL_IVR_PERMS)
        response = client.get(
            f"{PREFIX}/flows/{ivr_flow.id}/validate", headers=_auth(token)
        )
        data = response.json()["data"]
        assert data["valid"] is False
        assert data["issues"][0]["code"] == "NO_NODE"

    def test_unreachable_node_is_warning(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_validate_unreach", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        _create_node(client, headers, flow, node_key="menu")
        _create_node(client, headers, flow, node_key="orphan", node_type="HANGUP")
        client.put(
            f"{PREFIX}/flows/{ivr_flow.id}", headers=headers, json={"entry_node_key": "menu"}
        )

        response = client.get(f"{PREFIX}/flows/{ivr_flow.id}/validate", headers=headers)
        data = response.json()["data"]
        assert data["valid"] is True
        assert any(
            item["code"] == "UNREACHABLE_NODE" and item["target"] == "orphan"
            for item in data["issues"]
        )
        assert data["warning_count"] >= 1

    def test_terminal_node_with_transition_is_warning(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_validate_terminal", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        menu = _create_node(client, headers, flow, node_key="menu")
        bye = _create_node(client, headers, flow, node_key="bye", node_type="HANGUP")
        _create_transition(
            client, headers, flow, from_node_id=bye["id"], to_node_id=menu["id"],
            condition_value="*",
        )
        client.put(
            f"{PREFIX}/flows/{ivr_flow.id}", headers=headers, json={"entry_node_key": "menu"}
        )

        response = client.get(f"{PREFIX}/flows/{ivr_flow.id}/validate", headers=headers)
        data = response.json()["data"]
        assert any(
            item["code"] == "TERMINAL_HAS_TRANSITION" and item["target"] == "bye"
            for item in data["issues"]
        )

    def test_transfer_without_action_on_legacy_data_is_error(
        self, client: TestClient, user_token, ivr_flow, db_session: Session
    ) -> None:
        """绕过接口直接写入历史数据，校验接口仍应报错（§32）。"""
        token = user_token("ivr_validate_legacy", *ALL_IVR_PERMS)
        db_session.add(
            IvrNode(
                tenant_id=ivr_flow.tenant_id,
                flow_id=ivr_flow.id,
                node_key="legacy-transfer",
                name="历史转人工节点",
                node_type="TRANSFER_AGENT",
            )
        )
        ivr_flow.entry_node_key = "legacy-transfer"
        db_session.flush()

        response = client.get(
            f"{PREFIX}/flows/{ivr_flow.id}/validate", headers=_auth(token)
        )
        data = response.json()["data"]
        assert data["valid"] is False
        assert any(
            item["code"] == "NO_AGENT_ACTION_MISSING" for item in data["issues"]
        )


class TestSimulation:
    def _menu_flow(self, client: TestClient, headers: dict, ivr_flow) -> dict:
        flow = _flow_payload(ivr_flow)
        menu = _create_node(
            client, headers, flow, node_key="menu", content="请按 0 转人工"
        )
        transfer = _create_node(
            client,
            headers,
            flow,
            node_key="transfer",
            node_type="TRANSFER_AGENT",
            no_agent_action="CALLBACK",
        )
        _create_transition(
            client,
            headers,
            flow,
            from_node_id=menu["id"],
            to_node_id=transfer["id"],
            condition_value="0",
        )
        client.put(
            f"{PREFIX}/flows/{ivr_flow.id}", headers=headers, json={"entry_node_key": "menu"}
        )
        return flow

    def test_simulate_transfer_success_when_queue_available(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_sim_transfer", *ALL_IVR_PERMS)
        headers = _auth(token)
        self._menu_flow(client, headers, ivr_flow)

        response = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/simulate",
            headers=headers,
            json={"inputs": [{"input_type": "KEY", "value": "0"}], "queue_available": True},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["transferred"] is True
        assert data["end_reason"] == "TRANSFERRED"
        assert data["collected_keys"] == ["0"]
        assert [step["action"] for step in data["steps"]] == ["PLAY", "MOVE", "TRANSFER"]

    def test_simulate_transfer_fallback_callback(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_sim_callback", *ALL_IVR_PERMS)
        headers = _auth(token)
        self._menu_flow(client, headers, ivr_flow)

        response = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/simulate",
            headers=headers,
            json={"inputs": [{"input_type": "KEY", "value": "0"}], "queue_available": False},
        )
        data = response.json()["data"]
        assert data["transferred"] is False
        assert data["end_reason"] == "CALLBACK"
        assert data["no_agent_action"] == "CALLBACK"

    def test_simulate_illegal_key_replays_and_hangs_up(
        self, client: TestClient, user_token, ivr_flow
    ) -> None:
        token = user_token("ivr_sim_illegal", *ALL_IVR_PERMS)
        headers = _auth(token)
        flow = _flow_payload(ivr_flow)
        _create_node(client, headers, flow, node_key="menu", max_replay=1)
        _create_node(client, headers, flow, node_key="bye", node_type="HANGUP")
        client.put(
            f"{PREFIX}/flows/{ivr_flow.id}", headers=headers, json={"entry_node_key": "menu"}
        )

        response = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/simulate",
            headers=headers,
            json={
                "inputs": [
                    {"input_type": "KEY", "value": "9"},
                    {"input_type": "KEY", "value": "8"},
                ]
            },
        )
        data = response.json()["data"]
        assert data["end_reason"] == "HANGUP"
        assert data["replay_count"] == 2
        assert data["collected_keys"] == ["9", "8"]
        assert [step["action"] for step in data["steps"]] == [
            "PLAY",
            "REPLAY",
            "PLAY",
            "HANGUP",
        ]

    def test_simulate_entry_not_found(self, client: TestClient, user_token, ivr_flow) -> None:
        token = user_token("ivr_sim_no_entry", *ALL_IVR_PERMS)
        response = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/simulate",
            headers=_auth(token),
            json={"inputs": []},
        )
        data = response.json()["data"]
        assert data["end_reason"] == "ENTRY_NOT_FOUND"

    def test_simulate_infers_queue_state_from_agents(
        self, client: TestClient, user_token, ivr_flow, tenant
    ) -> None:
        """未显式指定时按真实坐席状态推断：无坐席即视为不可用（ASSUMPTION-053）。"""
        token = user_token("ivr_sim_infer", *ALL_IVR_PERMS)
        headers = _auth(token)
        self._menu_flow(client, headers, ivr_flow)

        response = client.post(
            f"{PREFIX}/flows/{ivr_flow.id}/simulate",
            headers=headers,
            json={"inputs": [{"input_type": "KEY", "value": "0"}]},
        )
        data = response.json()["data"]
        assert tenant is not None
        assert data["queue_available"] is False
        assert data["end_reason"] == "CALLBACK"


class TestFlowOptions:
    def test_options_returns_enabled_flows_only(
        self, client: TestClient, user_token, ivr_flow, tenant
    ) -> None:
        token = user_token("ivr_options", "outbound:ivr:list", "outbound:ivr:update")
        headers = _auth(token)

        # 停用后的流程不应出现在下拉里
        client.put(
            f"{PREFIX}/flows/{ivr_flow.id}/status",
            headers=headers,
            json={"status": "DISABLED"},
        )
        response = client.get(
            f"{OPTIONS_PREFIX}/ivr-flows", headers=headers, params={"tenant_id": tenant.id}
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

        client.put(
            f"{PREFIX}/flows/{ivr_flow.id}/status",
            headers=headers,
            json={"status": "ENABLED"},
        )
        response = client.get(
            f"{OPTIONS_PREFIX}/ivr-flows", headers=headers, params={"tenant_id": tenant.id}
        )
        assert len(response.json()["data"]) == 1

    def test_options_requires_tenant_id(self, client: TestClient, user_token) -> None:
        token = user_token("ivr_options_bad", "outbound:ivr:list")
        response = client.get(f"{OPTIONS_PREFIX}/ivr-flows", headers=_auth(token))
        assert response.status_code == 400
        assert response.json()["code"] == 40001
