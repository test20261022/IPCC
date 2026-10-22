"""质检报表数据访问。

- 完成率与等级：以 qc_task_items 为事实表（grade 已冗余在此表，避免回表 qc_review_results）；
- 按天分桶：以 qc_review_results.reviewed_at 为依据，必须先用 `timezone(tz, reviewed_at)`
  换算到报表时区再 `date_trunc('day', ...)`，否则跨零点错位（reviewed_at 存 UTC）。
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.qc.enums import QcGrade, QcItemStatus
from app.models.qc.review import QcReviewResult, QcTaskItem


class QcReportRepository:
    """质检报表聚合（只读）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 概览 ----------

    def overview(
        self, *, task_id: int | None = None, tenant_id: int | None = None
    ) -> dict[str, Any]:
        """总量 / 各状态量 / 各等级量 / 参与专家数（条件聚合，单次查询）。"""
        conditions = [QcTaskItem.is_deleted.is_(False)]
        if task_id is not None:
            conditions.append(QcTaskItem.task_id == task_id)
        if tenant_id is not None:
            conditions.append(QcTaskItem.tenant_id == tenant_id)

        stmt = (
            select(
                func.count().label("total"),
                func.count()
                .filter(QcTaskItem.status == QcItemStatus.COMPLETED)
                .label("completed"),
                func.count()
                .filter(QcTaskItem.status == QcItemStatus.PENDING)
                .label("pending"),
                func.count()
                .filter(QcTaskItem.status == QcItemStatus.REVIEWING)
                .label("reviewing"),
                func.count().filter(QcTaskItem.grade == QcGrade.EXCELLENT).label("excellent"),
                func.count().filter(QcTaskItem.grade == QcGrade.PASS).label("pass"),
                func.count().filter(QcTaskItem.grade == QcGrade.FAIL).label("fail"),
                func.count(func.distinct(QcTaskItem.reviewer_id)).label("reviewer_count"),
            )
            .select_from(QcTaskItem)
            .where(*conditions)
        )
        row = self.db.execute(stmt).one()
        return {
            "total": int(row.total or 0),
            "completed": int(row.completed or 0),
            "pending": int(row.pending or 0),
            "reviewing": int(row.reviewing or 0),
            "excellent": int(row.excellent or 0),
            "pass": int(getattr(row, "pass") or 0),
            "fail": int(row.fail or 0),
            "reviewer_count": int(row.reviewer_count or 0),
        }

    # ---------- 按天完成情况 ----------

    def daily_completion(
        self,
        *,
        date_from: date,
        date_to: date,
        task_id: int | None = None,
        tenant_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """按报表时区自然日分桶的提交量（稀疏，由服务层补零）。"""
        local_reviewed = func.timezone(
            settings.QC_REPORT_TIMEZONE, QcReviewResult.reviewed_at
        )
        bucket = func.date_trunc("day", local_reviewed).label("bucket")
        start = datetime.combine(date_from, time.min)
        end = datetime.combine(date_to + timedelta(days=1), time.min)

        stmt = select(
            bucket,
            func.count().label("total"),
            func.count().filter(QcReviewResult.grade == QcGrade.EXCELLENT).label("excellent"),
            func.count().filter(QcReviewResult.grade == QcGrade.PASS).label("pass"),
            func.count().filter(QcReviewResult.grade == QcGrade.FAIL).label("fail"),
        ).select_from(QcReviewResult)

        conditions = [
            QcReviewResult.is_deleted.is_(False),
            local_reviewed >= start,
            local_reviewed < end,
        ]
        if tenant_id is not None:
            conditions.append(QcReviewResult.tenant_id == tenant_id)
        if task_id is not None:
            stmt = stmt.join(QcTaskItem, QcTaskItem.id == QcReviewResult.item_id)
            conditions.append(QcTaskItem.is_deleted.is_(False))
            conditions.append(QcTaskItem.task_id == task_id)

        stmt = stmt.where(*conditions).group_by(bucket).order_by(bucket)
        return [
            {
                "bucket": row.bucket,
                "total": int(row.total or 0),
                "excellent": int(row.excellent or 0),
                "pass": int(getattr(row, "pass") or 0),
                "fail": int(row.fail or 0),
            }
            for row in self.db.execute(stmt).all()
        ]


__all__ = ["QcReportRepository"]