"""质检任务批量派发测试：均分误差、幂等、分批计数与容量校验（QC 一期）。"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.qc.review import QcTaskItem
from app.repositories.qc.task_repository import QcTaskRepository
from tests.conftest import QC_ALL_PERMISSIONS, auth_headers

TASKS = f"{settings.API_V1_PREFIX}/qc/tasks"
BASE = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


def _token(user_token) -> str:
    return user_token("qc_dispatch_admin", *QC_ALL_PERMISSIONS)


def _create_task(
    client: TestClient, token: str, tenant_id: int, group_id: int, **overrides
) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "task_name": f"派发任务-{uuid4().hex[:8]}",
        "group_id": group_id,
        "time_from": (BASE - timedelta(hours=1)).isoformat(),
        "time_to": (BASE + timedelta(days=1)).isoformat(),
        "dispatch_mode": "ROUND_ROBIN",
    }
    payload.update(overrides)
    response = client.post(TASKS, headers=auth_headers(token), json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _count_by_reviewer(db_session: Session, task_id: int) -> dict[int, int]:
    stmt = (
        select(QcTaskItem.reviewer_id, func.count())
        .where(QcTaskItem.task_id == task_id, QcTaskItem.is_deleted.is_(False))
        .group_by(QcTaskItem.reviewer_id)
    )
    return {int(row[0]): int(row[1]) for row in db_session.execute(stmt).all()}


def _env(
    client: TestClient,
    token: str,
    tenant,
    make_user,
    make_qc_conversation,
    make_qc_reviewer_group,
    *,
    conversations: int = 10,
    reviewers: int = 3,
    mode: str = "ROUND_ROBIN",
):
    suffix = uuid4().hex[:6]
    users = [make_user(f"qc_rev_{suffix}_{i}", tenant_id=tenant.id) for i in range(reviewers)]
    group = make_qc_reviewer_group(
        tenant.id, name=f"组-{suffix}", user_ids=tuple(u.id for u in users)
    )
    for index in range(conversations):
        make_qc_conversation(tenant.id, started_at=BASE + timedelta(minutes=index))
    task = _create_task(client, token, tenant.id, group.id, dispatch_mode=mode)
    return users, group, task


class TestRoundRobinDispatch:
    def test_even_split_within_one(
        self, client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
        db_session: Session,
    ) -> None:
        token = _token(user_token)
        users, _group, task = _env(
            client, token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=10, reviewers=3,
        )
        response = client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["total_items"] == 10
        assert data["reviewer_count"] == 3

        counts = _count_by_reviewer(db_session, task["id"])
        assert sum(counts.values()) == 10
        assert max(counts.values()) - min(counts.values()) <= 1
        assert set(counts) == {user.id for user in users}

        detail = client.get(f"{TASKS}/{task['id']}", headers=auth_headers(token)).json()["data"]
        assert detail["status"] == "DISPATCHED"
        assert detail["dispatched_at"] is not None
        assert detail["total_items"] == 10

    def test_average_mode_contiguous_chunks(
        self, client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
        db_session: Session,
    ) -> None:
        token = _token(user_token)
        users, _group, task = _env(
            client, token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=10, reviewers=3, mode="AVERAGE",
        )
        response = client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        counts = _count_by_reviewer(db_session, task["id"])
        # chunk = ceil(10/3) = 4 → 4 / 4 / 2（按专家 id 升序）
        ordered = [counts[user.id] for user in sorted(users, key=lambda u: u.id)]
        assert ordered == [4, 4, 2]

    def test_repeat_dispatch_rejected(self, client, user_token, tenant, make_user,
                                      make_qc_conversation, make_qc_reviewer_group) -> None:
        token = _token(user_token)
        _users, _group, task = _env(
            client, token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=4, reviewers=2,
        )
        assert (
            client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token)).status_code
            == 200
        )
        second = client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token))
        assert second.status_code == 409
        assert second.json()["code"] == 40902


class TestDispatchIdempotency:
    def test_repo_dispatch_batch_is_idempotent(
        self, client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
        db_session: Session,
    ) -> None:
        """中断续跑：任务仍为 DRAFT 时重复执行 INSERT ... SELECT 不产生重复明细。"""
        token = _token(user_token)
        users, _group, task = _env(
            client, token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=7, reviewers=2,
        )
        repo = QcTaskRepository(db_session)
        kwargs = {
            "task_id": task["id"],
            "tenant_id": tenant.id,
            "time_from": BASE - timedelta(hours=1),
            "time_to": BASE + timedelta(days=1),
            "reviewer_ids": sorted(user.id for user in users),
            "dispatch_mode": task["dispatch_mode"],
            "total": 7,
            "batch_size": 100,
        }
        assert repo.dispatch_batch(**kwargs) == 7
        # 幂等：NOT EXISTS + ON CONFLICT 双兜底，第二次插入 0 行
        assert repo.dispatch_batch(**kwargs) == 0
        assert repo.count_task_items(task["id"]) == 7

    def test_multi_batch_count_matches_count_star(
        self, client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
        db_session: Session, monkeypatch,
    ) -> None:
        """分批提交后 total_items 以 count(*) 回填，与真实行数一致。"""
        monkeypatch.setattr(settings, "QC_DISPATCH_BATCH_SIZE", 3)
        token = _token(user_token)
        _users, _group, task = _env(
            client, token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=11, reviewers=3,
        )
        response = client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        assert response.json()["data"]["total_items"] == 11

        total = db_session.execute(
            select(func.count()).select_from(QcTaskItem).where(
                QcTaskItem.task_id == task["id"], QcTaskItem.is_deleted.is_(False)
            )
        ).scalar_one()
        assert total == 11


class TestDispatchValidation:
    def test_over_capacity_rejected(
        self, client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
        monkeypatch,
    ) -> None:
        monkeypatch.setattr(settings, "QC_MAX_PER_REVIEWER", 2)
        token = _token(user_token)
        _users, _group, task = _env(
            client, token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=5, reviewers=1,
        )
        response = client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token))
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_empty_range_rejected(self, client, user_token, tenant, make_user,
                                  make_qc_reviewer_group) -> None:
        token = _token(user_token)
        suffix = uuid4().hex[:6]
        user = make_user(f"qc_rev_empty_{suffix}", tenant_id=tenant.id)
        group = make_qc_reviewer_group(tenant.id, name=f"空组-{suffix}", user_ids=(user.id,))
        task = _create_task(client, token, tenant.id, group.id)
        response = client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token))
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_group_without_active_member_rejected(
        self, client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
    ) -> None:
        token = _token(user_token)
        suffix = uuid4().hex[:6]
        user = make_user(f"qc_rev_inactive_{suffix}", tenant_id=tenant.id)
        group = make_qc_reviewer_group(
            tenant.id, name=f"停用组-{suffix}", user_ids=(user.id,), is_active=False
        )
        make_qc_conversation(tenant.id, started_at=BASE)
        task = _create_task(client, token, tenant.id, group.id)
        response = client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token))
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_out_of_range_conversations_excluded(
        self, client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
        db_session: Session,
    ) -> None:
        token = _token(user_token)
        suffix = uuid4().hex[:6]
        user = make_user(f"qc_rev_range_{suffix}", tenant_id=tenant.id)
        group = make_qc_reviewer_group(tenant.id, name=f"区间组-{suffix}", user_ids=(user.id,))
        make_qc_conversation(tenant.id, started_at=BASE)
        make_qc_conversation(tenant.id, started_at=BASE + timedelta(days=10))  # 区间外

        task = _create_task(client, token, tenant.id, group.id)
        response = client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        assert response.json()["data"]["total_items"] == 1


class TestTaskLifecycle:
    def test_cancel_then_delete(self, client, user_token, tenant, make_user,
                                make_qc_conversation, make_qc_reviewer_group, db_session) -> None:
        token = _token(user_token)
        _users, _group, task = _env(
            client, token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=3, reviewers=1,
        )
        assert (
            client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token)).status_code
            == 200
        )
        cancelled = client.post(f"{TASKS}/{task['id']}/cancel", headers=auth_headers(token))
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["status"] == "CANCELLED"
        assert cancelled.json()["data"]["finished_at"] is not None

        deleted = client.delete(f"{TASKS}/{task['id']}", headers=auth_headers(token))
        assert deleted.status_code == 200
        assert deleted.json()["data"]["removed_items"] == 3

    def test_edit_frozen_after_dispatch(self, client, user_token, tenant, make_user,
                                        make_qc_conversation, make_qc_reviewer_group) -> None:
        token = _token(user_token)
        _users, _group, task = _env(
            client, token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=2, reviewers=1,
        )
        assert (
            client.post(f"{TASKS}/{task['id']}/dispatch", headers=auth_headers(token)).status_code
            == 200
        )
        response = client.put(
            f"{TASKS}/{task['id']}", headers=auth_headers(token), json={"task_name": "改名"}
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902