"""质检报表测试：完成率 / 等级分布 / 参与专家数 / 按天补零与时区（QC 一期）。"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.qc.enums import QcGrade, QcItemStatus
from app.models.qc.review import QcReviewResult, QcTask, QcTaskItem
from tests.conftest import auth_headers

REPORTS = f"{settings.API_V1_PREFIX}/qc/reports"
BASE = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)


def _token(user_token) -> str:
    return user_token("qc_report_admin", "qc:report:list")


def _make_task(db_session: Session, tenant_id: int) -> QcTask:
    task = QcTask(
        tenant_id=tenant_id,
        task_name=f"报表任务-{uuid4().hex[:6]}",
        time_from=BASE,
        time_to=BASE,
    )
    db_session.add(task)
    db_session.flush()
    return task


def _make_item(
    db_session: Session,
    tenant_id: int,
    task: QcTask,
    conversation_id: int,
    *,
    status: QcItemStatus,
    grade: QcGrade | None = None,
    reviewer_id: int | None = None,
) -> QcTaskItem:
    item = QcTaskItem(
        tenant_id=tenant_id,
        task_id=task.id,
        conversation_id=conversation_id,
        reviewer_id=reviewer_id,
        status=status,
        grade=grade,
    )
    db_session.add(item)
    db_session.flush()
    return item


class TestReportOverview:
    def test_overview_counts_and_rate(
        self, client: TestClient, user_token, tenant, make_user, make_qc_conversation,
        db_session: Session,
    ) -> None:
        token = _token(user_token)
        task = _make_task(db_session, tenant.id)
        u1 = make_user(f"qc_rep_u1_{uuid4().hex[:6]}", tenant_id=tenant.id)
        u2 = make_user(f"qc_rep_u2_{uuid4().hex[:6]}", tenant_id=tenant.id)
        convs = [make_qc_conversation(tenant.id, started_at=BASE) for _ in range(5)]

        _make_item(db_session, tenant.id, task, convs[0].id,
                   status=QcItemStatus.COMPLETED, grade=QcGrade.EXCELLENT, reviewer_id=u1.id)
        _make_item(db_session, tenant.id, task, convs[1].id,
                   status=QcItemStatus.COMPLETED, grade=QcGrade.PASS, reviewer_id=u1.id)
        _make_item(db_session, tenant.id, task, convs[2].id,
                   status=QcItemStatus.COMPLETED, grade=QcGrade.FAIL, reviewer_id=u2.id)
        _make_item(db_session, tenant.id, task, convs[3].id,
                   status=QcItemStatus.PENDING, reviewer_id=u1.id)
        _make_item(db_session, tenant.id, task, convs[4].id,
                   status=QcItemStatus.REVIEWING, reviewer_id=u2.id)

        response = client.get(
            f"{REPORTS}/overview",
            headers=auth_headers(token),
            params={"tenant_id": tenant.id, "task_id": task.id},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["total"] == 5
        assert data["completed"] == 3
        assert data["pending"] == 1
        assert data["reviewing"] == 1
        assert data["completion_rate"] == 0.6
        assert data["grade_counts"] == {"EXCELLENT": 1, "PASS": 1, "FAIL": 1}
        assert data["reviewer_count"] == 2

    def test_empty_overview_is_zero(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = _token(user_token)
        response = client.get(
            f"{REPORTS}/overview", headers=auth_headers(token), params={"tenant_id": tenant.id}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0
        assert data["completion_rate"] == 0.0
        assert data["grade_counts"] == {"EXCELLENT": 0, "PASS": 0, "FAIL": 0}


class TestDailyCompletion:
    def test_buckets_timezone_and_zero_fill(
        self, client: TestClient, user_token, tenant, make_user, make_qc_conversation,
        db_session: Session,
    ) -> None:
        token = _token(user_token)
        task = _make_task(db_session, tenant.id)
        reviewer = make_user(f"qc_rep_d_{uuid4().hex[:6]}", tenant_id=tenant.id)
        convs = [make_qc_conversation(tenant.id, started_at=BASE) for _ in range(3)]

        # 2026-03-01 16:30 UTC == 2026-03-02 00:30 Asia/Shanghai → 归入 03-02
        entries = [
            (datetime(2026, 3, 1, 16, 30, tzinfo=timezone.utc), QcGrade.EXCELLENT),
            (datetime(2026, 3, 2, 2, 0, tzinfo=timezone.utc), QcGrade.PASS),
            (datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc), QcGrade.FAIL),
        ]
        for conversation, (reviewed_at, grade) in zip(convs, entries, strict=True):
            item = _make_item(
                db_session, tenant.id, task, conversation.id,
                status=QcItemStatus.COMPLETED, grade=grade, reviewer_id=reviewer.id,
            )
            db_session.add(
                QcReviewResult(
                    tenant_id=tenant.id,
                    item_id=item.id,
                    conversation_id=conversation.id,
                    reviewer_id=reviewer.id,
                    score=90,
                    grade=grade,
                    comment="",
                    reviewed_at=reviewed_at,
                )
            )
        db_session.flush()

        response = client.get(
            f"{REPORTS}/daily-completion",
            headers=auth_headers(token),
            params={
                "date_from": "2026-03-01",
                "date_to": "2026-03-04",
                "tenant_id": tenant.id,
                "task_id": task.id,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        buckets = {item["bucket"]: item for item in data["items"]}
        assert [item["bucket"] for item in data["items"]] == [
            "2026-03-01",
            "2026-03-02",
            "2026-03-03",
            "2026-03-04",
        ]
        assert buckets["2026-03-01"]["total"] == 0  # 无数据补零
        assert buckets["2026-03-02"]["total"] == 2  # 跨零点归到报表时区次日
        assert buckets["2026-03-02"]["excellent"] == 1
        assert buckets["2026-03-02"]["pass"] == 1
        assert buckets["2026-03-03"]["total"] == 1
        assert buckets["2026-03-03"]["fail"] == 1
        assert buckets["2026-03-04"]["total"] == 0

    def test_invalid_range_rejected(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        response = client.get(
            f"{REPORTS}/daily-completion",
            headers=auth_headers(token),
            params={"date_from": "2026-03-05", "date_to": "2026-03-01", "tenant_id": tenant.id},
        )
        assert response.status_code == 400
        assert response.json()["code"] == 40001