"""质检执行域测试：领取 / 释放 / 提交 / 超时回收 / 数据范围（QC 一期）。

并发安全由「带状态条件的原子 UPDATE」保证，用例验证 rowcount 语义：
重复领取 / 重复提交 / 越权操作均被拒绝，超时明细可退回待质检。
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.qc.review import QcTaskItem
from app.services.qc.review_service import QcReviewService
from tests.conftest import DEFAULT_USER_PASSWORD, QC_ALL_PERMISSIONS, auth_headers, login

QC = f"{settings.API_V1_PREFIX}/qc"
TASKS = f"{QC}/tasks"
BASE = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)


def _admin_token(user_token) -> str:
    # 用户名带随机后缀：同一用例内可能多次取管理员 token，避免用户名唯一约束冲突
    return user_token(f"qc_review_admin_{uuid4().hex[:6]}", *QC_ALL_PERMISSIONS)


def _reviewer_token(client: TestClient, make_user, tenant, *extra_perms) -> tuple[int, str]:
    suffix = uuid4().hex[:6]
    user = make_user(
        f"qc_reviewer_{suffix}",
        "qc:review:work",
        "qc:review:submit",
        *extra_perms,
        tenant_id=tenant.id,
    )
    return user.id, login(client, user.username, DEFAULT_USER_PASSWORD)


def _setup(client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
           *, conversations=3, dispatch=True):
    """建专家组 + 对话 + 任务；默认派发，使全部明细落到唯一专家名下。"""
    reviewer_id, token = _reviewer_token(client, make_user, tenant)
    group = make_qc_reviewer_group(
        tenant.id, name=f"执行组-{uuid4().hex[:6]}", user_ids=(reviewer_id,)
    )
    for index in range(conversations):
        make_qc_conversation(tenant.id, started_at=BASE + timedelta(minutes=index))

    admin = _admin_token(user_token)
    created = client.post(
        TASKS,
        headers=auth_headers(admin),
        json={
            "tenant_id": tenant.id,
            "task_name": f"执行任务-{uuid4().hex[:8]}",
            "group_id": group.id,
            "time_from": (BASE - timedelta(hours=1)).isoformat(),
            "time_to": (BASE + timedelta(days=1)).isoformat(),
        },
    ).json()["data"]
    if dispatch:
        response = client.post(f"{TASKS}/{created['id']}/dispatch", headers=auth_headers(admin))
        assert response.status_code == 200, response.text
    return reviewer_id, token, created


def _item_ids(db_session: Session, task_id: int) -> list[int]:
    stmt = (
        select(QcTaskItem.id)
        .where(QcTaskItem.task_id == task_id, QcTaskItem.is_deleted.is_(False))
        .order_by(QcTaskItem.id.asc())
    )
    return list(db_session.execute(stmt).scalars().all())


class TestClaimRelease:
    def test_claim_sets_lock_and_timeout(self, client, user_token, tenant, make_user,
                                         make_qc_conversation, make_qc_reviewer_group,
                                         db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group
        )
        item_id = _item_ids(db_session, task["id"])[0]
        response = client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "REVIEWING"
        assert data["locked_at"] is not None
        assert data["timeout_at"] is not None

    def test_double_claim_rejected(self, client, user_token, tenant, make_user,
                                   make_qc_conversation, make_qc_reviewer_group,
                                   db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group
        )
        item_id = _item_ids(db_session, task["id"])[0]
        claimed = client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))
        assert claimed.status_code == 200
        second = client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))
        assert second.status_code == 409
        assert second.json()["code"] == 40902

    def test_release_returns_to_pending(self, client, user_token, tenant, make_user,
                                        make_qc_conversation, make_qc_reviewer_group,
                                        db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group
        )
        item_id = _item_ids(db_session, task["id"])[0]
        client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))
        response = client.post(f"{QC}/items/{item_id}/release", headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "PENDING"
        assert response.json()["data"]["locked_at"] is None

    def test_release_by_other_reviewer_rejected(self, client, user_token, tenant, make_user,
                                                make_qc_conversation, make_qc_reviewer_group,
                                                db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group
        )
        item_id = _item_ids(db_session, task["id"])[0]
        client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))

        _other_id, other_token = _reviewer_token(client, make_user, tenant)
        response = client.post(f"{QC}/items/{item_id}/release", headers=auth_headers(other_token))
        assert response.status_code == 409  # rowcount=0：非本人持有


class TestSubmit:
    def test_submit_writes_grade_from_score(self, client, user_token, tenant, make_user,
                                            make_qc_conversation, make_qc_reviewer_group,
                                            db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=1,
        )
        item_id = _item_ids(db_session, task["id"])[0]
        client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))
        response = client.post(
            f"{QC}/items/{item_id}/submit",
            headers=auth_headers(token),
            json={"score": 90, "comment": "表现优秀", "score_detail": {"专业度": 45}},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["grade"] == "EXCELLENT"  # 边界值 90 判为优秀
        assert data["status"] == "COMPLETED"
        assert data["task_completed"] is True

        item = db_session.get(QcTaskItem, item_id)
        db_session.refresh(item)
        assert item.grade is not None
        assert item.grade.value == "EXCELLENT"

        detail = client.get(f"{TASKS}/{task['id']}", headers=auth_headers(_admin_token(user_token)))
        assert detail.json()["data"]["status"] == "COMPLETED"
        assert detail.json()["data"]["completion_rate"] == 1.0

    def test_submit_without_claim_rejected(self, client, user_token, tenant, make_user,
                                           make_qc_conversation, make_qc_reviewer_group,
                                           db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=1,
        )
        item_id = _item_ids(db_session, task["id"])[0]
        response = client.post(
            f"{QC}/items/{item_id}/submit", headers=auth_headers(token), json={"score": 70}
        )
        assert response.status_code == 409
        assert response.json()["code"] == 40902

    def test_duplicate_submit_rejected(self, client, user_token, tenant, make_user,
                                       make_qc_conversation, make_qc_reviewer_group,
                                       db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=1,
        )
        item_id = _item_ids(db_session, task["id"])[0]
        client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))
        assert client.post(
            f"{QC}/items/{item_id}/submit", headers=auth_headers(token), json={"score": 59}
        ).status_code == 200
        again = client.post(
            f"{QC}/items/{item_id}/submit", headers=auth_headers(token), json={"score": 59}
        )
        assert again.status_code == 409
        assert again.json()["code"] == 40902

    def test_task_completes_only_after_last_item(self, client, user_token, tenant, make_user,
                                                 make_qc_conversation, make_qc_reviewer_group,
                                                 db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=2,
        )
        ids = _item_ids(db_session, task["id"])
        results = []
        for item_id in ids:
            client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))
            response = client.post(
                f"{QC}/items/{item_id}/submit", headers=auth_headers(token), json={"score": 75}
            )
            results.append(response.json()["data"]["task_completed"])
        assert results == [False, True]


class TestMyItemsAndScope:
    def test_my_items_only_own(self, client, user_token, tenant, make_user,
                               make_qc_conversation, make_qc_reviewer_group) -> None:
        _reviewer_id, token, _task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group
        )
        response = client.get(f"{QC}/my/items", headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 3

        _other_id, other_token = _reviewer_token(client, make_user, tenant)
        other = client.get(f"{QC}/my/items", headers=auth_headers(other_token))
        assert other.json()["data"]["total"] == 0

    def test_item_of_other_reviewer_forbidden(self, client, user_token, tenant, make_user,
                                              make_qc_conversation, make_qc_reviewer_group,
                                              db_session: Session) -> None:
        _reviewer_id, _token_v, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group
        )
        item_id = _item_ids(db_session, task["id"])[0]
        _other_id, other_token = _reviewer_token(client, make_user, tenant)
        response = client.get(f"{QC}/items/{item_id}", headers=auth_headers(other_token))
        assert response.status_code == 403
        assert response.json()["code"] == 40301

    def test_cross_tenant_item_not_found(self, client, user_token, tenant, make_user,
                                         make_qc_conversation, make_qc_reviewer_group,
                                         db_session: Session) -> None:
        from app.models.outbound import Tenant

        _reviewer_id, _token_v, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group
        )
        item_id = _item_ids(db_session, task["id"])[0]

        other_tenant = Tenant(code=f"TENANT-{uuid4().hex[:6]}", name="另一个租户")
        db_session.add(other_tenant)
        db_session.flush()
        _other_id, other_token = _reviewer_token(client, make_user, other_tenant)
        response = client.get(f"{QC}/items/{item_id}", headers=auth_headers(other_token))
        assert response.status_code == 404


class TestTimeoutRecycle:
    def test_recycle_timeout_item_back_to_pending(self, client, user_token, tenant, make_user,
                                                  make_qc_conversation, make_qc_reviewer_group,
                                                  db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=1,
        )
        item_id = _item_ids(db_session, task["id"])[0]
        client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))

        item = db_session.get(QcTaskItem, item_id)
        item.timeout_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.flush()

        result = QcReviewService(db_session).recycle_timeout_items()
        assert result["recycled"] == 1

        db_session.expire_all()
        fresh = db_session.get(QcTaskItem, item_id)
        assert fresh.status.value == "PENDING"
        assert fresh.locked_at is None
        assert fresh.timeout_at is None

    def test_recycle_is_idempotent(self, client, user_token, tenant, make_user,
                                   make_qc_conversation, make_qc_reviewer_group,
                                   db_session: Session) -> None:
        _reviewer_id, token, task = _setup(
            client, user_token, tenant, make_user, make_qc_conversation, make_qc_reviewer_group,
            conversations=1,
        )
        item_id = _item_ids(db_session, task["id"])[0]
        client.post(f"{QC}/items/{item_id}/claim", headers=auth_headers(token))
        item = db_session.get(QcTaskItem, item_id)
        item.timeout_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.flush()

        service = QcReviewService(db_session)
        assert service.recycle_timeout_items()["recycled"] == 1
        # 第二次扫描：已不在候选集合，无副作用
        assert service.recycle_timeout_items()["recycled"] == 0