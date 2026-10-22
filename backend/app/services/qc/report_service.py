"""质检报表服务（概览 / 按天完成情况）。

只读；按天序列必须补零，保证前端可直接画折线。
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import ParamError
from app.repositories.qc.qc_report_repository import QcReportRepository

logger = logging.getLogger(__name__)


class QcReportService:
    """质检报表业务。只读，不产生写操作。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = QcReportRepository(db)

    def overview(self, *, task_id: int | None = None, tenant_id: int | None = None) -> dict:
        """概览：总量 / 状态分布 / 完成率 / 等级分布 / 参与专家数。"""
        counts = self.repo.overview(task_id=task_id, tenant_id=tenant_id)
        total = counts["total"]
        completed = counts["completed"]
        return {
            "task_id": task_id,
            "total": total,
            "completed": completed,
            "pending": counts["pending"],
            "reviewing": counts["reviewing"],
            "completion_rate": round(completed / total, 4) if total else 0.0,
            "grade_counts": {
                "EXCELLENT": counts["excellent"],
                "PASS": counts["pass"],
                "FAIL": counts["fail"],
            },
            "reviewer_count": counts["reviewer_count"],
        }

    def daily_completion(
        self,
        *,
        date_from: date,
        date_to: date,
        task_id: int | None = None,
        tenant_id: int | None = None,
    ) -> dict:
        """按天完成情况：连续自然日序列，无数据的日期补零。"""
        if date_from > date_to:
            raise ParamError("日期区间非法：date_from 不能晚于 date_to")

        rows = self.repo.daily_completion(
            date_from=date_from, date_to=date_to, task_id=task_id, tenant_id=tenant_id
        )
        buckets: dict[str, dict] = {}
        for row in rows:
            buckets[self._bucket_key(row["bucket"])] = {
                "total": row["total"],
                "excellent": row["excellent"],
                "pass": row["pass"],
                "fail": row["fail"],
            }

        items: list[dict] = []
        cursor = date_from
        while cursor <= date_to:
            key = cursor.isoformat()
            counts = buckets.get(key, {"total": 0, "excellent": 0, "pass": 0, "fail": 0})
            items.append({"bucket": key, **counts})
            cursor += timedelta(days=1)

        logger.info(
            "质检按天报表：task=%s tenant=%s 区间=%s~%s 天数=%s",
            task_id,
            tenant_id,
            date_from,
            date_to,
            len(items),
        )
        return {"items": items, "date_from": date_from, "date_to": date_to}

    @staticmethod
    def _bucket_key(bucket: datetime | date) -> str:
        if isinstance(bucket, datetime):
            return bucket.date().isoformat()
        return bucket.isoformat()


__all__ = ["QcReportService"]