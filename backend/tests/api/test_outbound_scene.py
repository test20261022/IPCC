"""外呼场景接口测试（OB-003）。"""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbound import OutboundScene
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound/scenes"

ALL_SCENE_PERMS = (
    "outbound:scene:list",
    "outbound:scene:create",
    "outbound:scene:update",
    "outbound:scene:delete",
)


def _first_level(tenant_id: int, type_id: int, name: str, **overrides) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "type_id": type_id,
        "level": 1,
        "name": name,
    }
    payload.update(overrides)
    return payload


def _second_level(tenant_id: int, type_id: int, parent_id: int, name: str, **overrides) -> dict:
    payload = _first_level(tenant_id, type_id, name, level=2, parent_id=parent_id)
    payload.update(overrides)
    return payload


class TestScenePermissions:
    def test_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("scene_no_perm", "outbound:type:list")
        assert client.get(PREFIX, headers=auth_headers(token)).status_code == 403

    def test_delete_requires_permission(
        self, client: TestClient, user_token, outbound_scene
    ) -> None:
        token = user_token("scene_list_only", "outbound:scene:list")
        response = client.delete(f"{PREFIX}/{outbound_scene.id}", headers=auth_headers(token))
        assert response.status_code == 403
        assert response.json()["code"] == 40301


class TestSceneCreate:
    def test_create_first_and_second_level(
        self, client: TestClient, user_token, tenant, outbound_type
    ) -> None:
        token = user_token("scene_creator", *ALL_SCENE_PERMS)

        parent = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(tenant.id, outbound_type.id, "一级-新客"),
        )
        assert parent.status_code == 200
        assert parent.json()["data"]["level"] == 1

        child = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_second_level(
                tenant.id, outbound_type.id, parent.json()["data"]["id"], "二级-首次触达"
            ),
        )
        assert child.status_code == 200
        assert child.json()["data"]["level"] == 2
        assert child.json()["data"]["parent_id"] == parent.json()["data"]["id"]

    def test_second_level_requires_parent(
        self, client: TestClient, user_token, tenant, outbound_type
    ) -> None:
        token = user_token("scene_no_parent", *ALL_SCENE_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(tenant.id, outbound_type.id, "缺父场景", level=2),
        )
        assert response.status_code == 400
        assert "父场景" in response.json()["message"]

    def test_first_level_rejects_parent(
        self, client: TestClient, user_token, tenant, outbound_type, outbound_scene
    ) -> None:
        token = user_token("scene_l1_parent", *ALL_SCENE_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(
                tenant.id, outbound_type.id, "带父的一级", parent_id=outbound_scene.id
            ),
        )
        assert response.status_code == 400

    def test_second_level_type_must_match_parent(
        self, client: TestClient, user_token, tenant, outbound_type, outbound_scene
    ) -> None:
        token = user_token(
            "scene_type_mismatch", *ALL_SCENE_PERMS, "outbound:type:create"
        )
        other_type = client.post(
            f"{settings.API_V1_PREFIX}/outbound/types",
            headers=auth_headers(token),
            json={"tenant_id": tenant.id, "code": "TP-OTHER", "name": "另一类型", "level": 1},
        ).json()["data"]

        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_second_level(tenant.id, other_type["id"], outbound_scene.id, "类型不匹配"),
        )
        assert response.status_code == 400
        assert "类型" in response.json()["message"]

    def test_duplicate_name_under_same_parent(
        self, client: TestClient, user_token, tenant, outbound_type
    ) -> None:
        token = user_token("scene_dup", *ALL_SCENE_PERMS)
        body = _first_level(tenant.id, outbound_type.id, "重复场景")
        assert client.post(PREFIX, headers=auth_headers(token), json=body).status_code == 200

        response = client.post(PREFIX, headers=auth_headers(token), json=body)
        assert response.status_code == 409
        assert response.json()["code"] == 40901

    def test_create_with_unknown_type(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("scene_bad_type", *ALL_SCENE_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(tenant.id, 999999, "无类型场景"),
        )
        assert response.status_code == 404


class TestSceneQuery:
    def test_list_filters(self, client: TestClient, user_token, tenant, outbound_scene) -> None:
        token = user_token("scene_lister", *ALL_SCENE_PERMS)
        response = client.get(
            PREFIX,
            headers=auth_headers(token),
            params={"tenant_id": tenant.id, "type_id": outbound_scene.type_id, "level": 1},
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["total"] == 1
        assert body["items"][0]["name"] == outbound_scene.name

    def test_tree_structure(
        self, client: TestClient, user_token, tenant, outbound_type, db_session: Session
    ) -> None:
        token = user_token("scene_tree", *ALL_SCENE_PERMS)
        parent = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(tenant.id, outbound_type.id, "树-一级"),
        ).json()["data"]
        client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_second_level(tenant.id, outbound_type.id, parent["id"], "树-二级A"),
        )
        client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_second_level(tenant.id, outbound_type.id, parent["id"], "树-二级B"),
        )

        response = client.get(
            PREFIX + "/tree", headers=auth_headers(token), params={"tenant_id": tenant.id}
        )
        assert response.status_code == 200
        roots = response.json()["data"]
        assert len(roots) == 1
        assert roots[0]["name"] == "树-一级"
        assert sorted(child["name"] for child in roots[0]["children"]) == ["树-二级A", "树-二级B"]

    def test_tree_route_not_shadowed_by_id_route(
        self, client: TestClient, user_token, tenant
    ) -> None:
        """确认 /tree 不会被 /{scene_id} 抢先匹配。"""
        token = user_token("scene_tree_route", *ALL_SCENE_PERMS)
        response = client.get(
            PREFIX + "/tree", headers=auth_headers(token), params={"tenant_id": tenant.id}
        )
        assert response.status_code == 200
        assert response.json()["data"] == []


class TestSceneEditRules:
    def test_referenced_scene_cannot_be_edited(
        self, client: TestClient, user_token, outbound_scene, outbound_task
    ) -> None:
        token = user_token("scene_edit_ref", *ALL_SCENE_PERMS)
        response = client.put(
            f"{PREFIX}/{outbound_scene.id}",
            headers=auth_headers(token),
            json={"name": "试图改名"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40904
        assert "禁止编辑" in response.json()["message"]

    def test_unreferenced_scene_can_be_edited(
        self, client: TestClient, user_token, outbound_scene
    ) -> None:
        token = user_token("scene_edit_ok", *ALL_SCENE_PERMS)
        response = client.put(
            f"{PREFIX}/{outbound_scene.id}",
            headers=auth_headers(token),
            json={"name": "新名字", "status": "DISABLED"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "新名字"
        assert response.json()["data"]["status"] == "DISABLED"

    def test_status_change_with_permission(
        self, client: TestClient, user_token, outbound_type, tenant
    ) -> None:
        token = user_token("scene_status", *ALL_SCENE_PERMS)
        created = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(tenant.id, outbound_type.id, "状态场景"),
        ).json()["data"]

        response = client.put(
            f"{PREFIX}/{created['id']}/status",
            headers=auth_headers(token),
            json={"status": "DISABLED"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "DISABLED"


class TestSceneDeleteRules:
    def test_delete_first_level_cascades_children(
        self, client: TestClient, user_token, tenant, outbound_type, db_session: Session
    ) -> None:
        token = user_token("scene_cascade", *ALL_SCENE_PERMS)
        parent = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(tenant.id, outbound_type.id, "级联-一级"),
        ).json()["data"]
        for name in ("级联-二级A", "级联-二级B"):
            client.post(
                PREFIX,
                headers=auth_headers(token),
                json=_second_level(tenant.id, outbound_type.id, parent["id"], name),
            )

        response = client.delete(f"{PREFIX}/{parent['id']}", headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["data"] == {"requested": 1, "deleted": 3}

        remaining = db_session.execute(
            select(func.count())
            .select_from(OutboundScene)
            .where(OutboundScene.parent_id == parent["id"], OutboundScene.is_deleted.is_(False))
        ).scalar_one()
        assert remaining == 0

    def test_cannot_delete_scene_referenced_by_task(
        self, client: TestClient, user_token, outbound_scene, outbound_task
    ) -> None:
        token = user_token("scene_del_ref", *ALL_SCENE_PERMS)
        response = client.delete(f"{PREFIX}/{outbound_scene.id}", headers=auth_headers(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40904
        assert outbound_task.task_name in response.json()["message"]

    def test_cannot_delete_parent_when_child_referenced(
        self, client: TestClient, user_token, tenant, outbound_type, db_session: Session
    ) -> None:
        """一级场景自身未被引用，但二级场景被任务引用时，整体拒绝。"""
        token = user_token("scene_del_child_ref", *ALL_SCENE_PERMS)
        parent = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(tenant.id, outbound_type.id, "引用-一级"),
        ).json()["data"]
        child = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_second_level(tenant.id, outbound_type.id, parent["id"], "引用-二级"),
        ).json()["data"]

        from app.models.outbound import OutboundTask

        db_session.add(
            OutboundTask(
                tenant_id=tenant.id,
                task_name="引用二级场景的任务",
                type_id=outbound_type.id,
                scene_id=child["id"],
            )
        )
        db_session.flush()

        response = client.delete(f"{PREFIX}/{parent['id']}", headers=auth_headers(token))
        assert response.status_code == 409
        assert "引用二级场景的任务" in response.json()["message"]

    def test_batch_delete_all_or_nothing(
        self, client: TestClient, user_token, tenant, outbound_type, outbound_task, outbound_scene
    ) -> None:
        token = user_token("scene_batch", *ALL_SCENE_PERMS)
        free = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_first_level(tenant.id, outbound_type.id, "可删除场景"),
        ).json()["data"]

        # 其中一个被任务引用 -> 整体拒绝
        response = client.post(
            f"{PREFIX}/batch-delete",
            headers=auth_headers(token),
            json={"scene_ids": [free["id"], outbound_scene.id]},
        )
        assert response.status_code == 409
        assert outbound_task.task_name in response.json()["message"]

        # 只删未被引用的 -> 成功
        response = client.post(
            f"{PREFIX}/batch-delete", headers=auth_headers(token), json={"scene_ids": [free["id"]]}
        )
        assert response.status_code == 200
        assert response.json()["data"] == {"requested": 1, "deleted": 1}

    def test_batch_delete_empty_payload(self, client: TestClient, user_token) -> None:
        token = user_token("scene_batch_empty", *ALL_SCENE_PERMS)
        response = client.post(
            f"{PREFIX}/batch-delete", headers=auth_headers(token), json={"scene_ids": []}
        )
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_delete_unknown_scene(self, client: TestClient, user_token) -> None:
        token = user_token("scene_del_unknown", *ALL_SCENE_PERMS)
        response = client.delete(f"{PREFIX}/999999", headers=auth_headers(token))
        assert response.status_code == 404
