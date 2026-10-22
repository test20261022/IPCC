"""坐席 CRUD 接口测试（规则 8 确认结果：只补坐席）。"""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.outbound import AgentAssignment, OutboundSession
from app.models.outbound.enums import (
    AgentStatus,
    AssignmentStatus,
    SessionStatus,
)
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound/agents"

ALL_AGENT_PERMS = (
    "outbound:agent:list",
    "outbound:agent:create",
    "outbound:agent:update",
    "outbound:agent:delete",
)


def _payload(user_id: int, tenant_id: int, **overrides) -> dict:
    body = {"user_id": user_id, "tenant_id": tenant_id}
    body.update(overrides)
    return body


class TestAgentCrudPermissions:
    def test_create_requires_permission(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("agent_list_only", "outbound:agent:list")
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(1, tenant.id)
        )
        assert response.status_code == 403

    def test_delete_requires_permission(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        user = make_user("agent_del_user")
        from app.models.outbound import Agent

        agent = Agent(tenant_id=tenant.id, user_id=user.id, status=AgentStatus.IDLE)
        db_session.add(agent)
        db_session.flush()

        token = user_token("agent_del_denied", "outbound:agent:list")
        response = client.delete(f"{PREFIX}/{agent.id}", headers=auth_headers(token))
        assert response.status_code == 403


class TestAgentCreate:
    def test_create_success_and_offline(
        self, client: TestClient, user_token, tenant, site, skill_queue, make_user
    ) -> None:
        user = make_user("agent_new_user")
        token = user_token("agent_creator", *ALL_AGENT_PERMS)

        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(
                user.id,
                tenant.id,
                site_id=site.id,
                skill_queue_id=skill_queue.id,
                extension="8001",
            ),
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["user_id"] == user.id
        assert data["tenant_id"] == tenant.id
        assert data["skill_queue_id"] == skill_queue.id
        assert data["extension"] == "8001"
        # 新建坐席默认离线，需要显式示闲才会接单
        assert data["status"] == "OFFLINE"

    def test_user_not_found(self, client: TestClient, user_token, tenant) -> None:
        token = user_token("agent_bad_user", *ALL_AGENT_PERMS)
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(999999, tenant.id)
        )
        assert response.status_code == 404
        assert "关联用户不存在" in response.json()["message"]

    def test_duplicate_user_rejected(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        user = make_user("agent_dup_user")
        from app.models.outbound import Agent

        db_session.add(
            Agent(tenant_id=tenant.id, user_id=user.id, status=AgentStatus.OFFLINE)
        )
        db_session.flush()

        token = user_token("agent_dup", *ALL_AGENT_PERMS)
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(user.id, tenant.id)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40901
        assert "最多一个坐席" in response.json()["message"]

    def test_inactive_user_rejected(
        self, client: TestClient, user_token, tenant, db_session
    ) -> None:
        from app.core.security import hash_password
        from app.repositories.user_repository import UserRepository

        user = UserRepository(db_session).create_user(
            username="agent_inactive_user",
            password_hash=hash_password("User@123456"),
            nickname="停用用户",
            is_active=False,
        )
        token = user_token("agent_inactive", *ALL_AGENT_PERMS)
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(user.id, tenant.id)
        )
        assert response.status_code == 400
        assert "已停用" in response.json()["message"]

    def test_site_of_other_tenant_rejected(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        from app.models.outbound import Site, Tenant

        other = Tenant(code="TENANT-SITE", name="站点第二租户")
        db_session.add(other)
        db_session.flush()
        foreign_site = Site(tenant_id=other.id, code="SITE-X", name="外部站点")
        db_session.add(foreign_site)
        db_session.flush()

        user = make_user("agent_bad_site")
        token = user_token("agent_bad_site_tok", *ALL_AGENT_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(user.id, tenant.id, site_id=foreign_site.id),
        )
        assert response.status_code == 400
        assert "站点与坐席不属于同一租户" in response.json()["message"]

    def test_queue_must_belong_to_site(
        self, client: TestClient, user_token, tenant, site, skill_queue, db_session, make_user
    ) -> None:
        from app.models.outbound import Site

        other_site = Site(tenant_id=tenant.id, code="SITE-2", name="站点二")
        db_session.add(other_site)
        db_session.flush()

        user = make_user("agent_bad_queue")
        token = user_token("agent_bad_queue_tok", *ALL_AGENT_PERMS)
        response = client.post(
            PREFIX,
            headers=auth_headers(token),
            json=_payload(
                user.id,
                tenant.id,
                site_id=other_site.id,
                skill_queue_id=skill_queue.id,
            ),
        )
        assert response.status_code == 400
        assert "不属于所选站点" in response.json()["message"]

    def test_disabled_tenant_rejected(
        self, client: TestClient, user_token, disabled_tenant, make_user
    ) -> None:
        user = make_user("agent_disabled_tenant")
        token = user_token("agent_disabled_tenant_tok", *ALL_AGENT_PERMS)
        response = client.post(
            PREFIX, headers=auth_headers(token), json=_payload(user.id, disabled_tenant.id)
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902


class TestAgentUpdate:
    def test_update_placement_and_extension(
        self, client: TestClient, user_token, tenant, site, skill_queue, db_session, make_user
    ) -> None:
        from app.models.outbound import Agent

        user = make_user("agent_upd_user")
        agent = Agent(
            tenant_id=tenant.id, user_id=user.id, status=AgentStatus.IDLE, extension="8000"
        )
        db_session.add(agent)
        db_session.flush()

        token = user_token("agent_updater", *ALL_AGENT_PERMS)
        response = client.put(
            f"{PREFIX}/{agent.id}",
            headers=auth_headers(token),
            json={"site_id": site.id, "skill_queue_id": skill_queue.id, "extension": "8002"},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["site_id"] == site.id
        assert data["extension"] == "8002"
        # 编辑接口不应改动状态
        assert data["status"] == "IDLE"

    def test_update_agent_not_found(self, client: TestClient, user_token) -> None:
        token = user_token("agent_upd_missing", *ALL_AGENT_PERMS)
        response = client.put(
            f"{PREFIX}/999999", headers=auth_headers(token), json={"extension": "9"}
        )
        assert response.status_code == 404


class TestAgentDelete:
    def test_delete_success(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        from app.models.outbound import Agent

        user = make_user("agent_del_ok_user")
        agent = Agent(tenant_id=tenant.id, user_id=user.id, status=AgentStatus.OFFLINE)
        db_session.add(agent)
        db_session.flush()
        agent_id = agent.id

        token = user_token("agent_deleter", *ALL_AGENT_PERMS)
        response = client.delete(f"{PREFIX}/{agent_id}", headers=auth_headers(token))
        assert response.status_code == 200

        db_session.expire_all()
        assert db_session.get(Agent, agent_id).is_deleted is True
        # 删除后不再出现在列表里
        listing = client.get(PREFIX, headers=auth_headers(token))
        assert agent_id not in [item["id"] for item in listing.json()["data"]["items"]]

    def test_delete_with_open_assignment_rejected(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        from app.models.outbound import Agent

        user = make_user("agent_open_assign")
        agent = Agent(tenant_id=tenant.id, user_id=user.id, status=AgentStatus.RESERVED)
        db_session.add(agent)
        db_session.flush()
        db_session.add(
            AgentAssignment(
                tenant_id=tenant.id,
                agent_id=agent.id,
                status=AssignmentStatus.RESERVED,
            )
        )
        db_session.flush()

        token = user_token("agent_del_blocked", *ALL_AGENT_PERMS)
        response = client.delete(f"{PREFIX}/{agent.id}", headers=auth_headers(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40904
        assert "预占" in response.json()["message"]

    def test_delete_with_active_session_rejected(
        self, client: TestClient, user_token, tenant, db_session, make_user
    ) -> None:
        from app.models.outbound import Agent

        user = make_user("agent_active_session")
        agent = Agent(tenant_id=tenant.id, user_id=user.id, status=AgentStatus.BUSY)
        db_session.add(agent)
        db_session.flush()
        db_session.add(
            OutboundSession(
                tenant_id=tenant.id,
                agent_id=agent.id,
                status=SessionStatus.CALLING,
            )
        )
        db_session.flush()

        token = user_token("agent_del_session", *ALL_AGENT_PERMS)
        response = client.delete(f"{PREFIX}/{agent.id}", headers=auth_headers(token))
        assert response.status_code == 409
        assert response.json()["code"] == 40904
        assert "进行中的外呼会话" in response.json()["message"]


class TestUserOptions:
    def test_user_options_available(self, client: TestClient, user_token, make_user) -> None:
        make_user("user_option_target")
        token = user_token("agent_option_user", "outbound:agent:list")

        response = client.get(
            f"{settings.API_V1_PREFIX}/outbound/options/users", headers=auth_headers(token)
        )
        assert response.status_code == 200
        usernames = [item["username"] for item in response.json()["data"]]
        assert "user_option_target" in usernames
