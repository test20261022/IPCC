"""对话质检：报表 Schema。"""

from datetime import date

from pydantic import Field

from app.schemas.qc.review import QcSchemaBase


class QcReportOverviewOut(QcSchemaBase):
    """质检概览：总量 / 状态分布 / 等级分布 / 参与专家数。"""

    task_id: int | None = Field(default=None, description="任务 ID；为空表示按租户汇总全部任务")
    total: int = Field(description="明细总数")
    completed: int = Field(description="已完成数")
    pending: int = Field(description="待质检数")
    reviewing: int = Field(description="质检中数")
    completion_rate: float = Field(description="完成率，0~1")
    grade_counts: dict[str, int] = Field(
        default_factory=dict, description="等级分布：EXCELLENT / PASS / FAIL"
    )
    reviewer_count: int = Field(description="参与质检的专家数")


class QcDailyCompletionItemOut(QcSchemaBase):
    """按天分桶的完成情况（bucket 形如 YYYY-MM-DD）。"""

    bucket: str = Field(description="自然日，YYYY-MM-DD")
    total: int = 0
    excellent: int = 0
    pass_count: int = Field(default=0, alias="pass", description="及格数")
    fail: int = 0


class QcDailyCompletionOut(QcSchemaBase):
    items: list[QcDailyCompletionItemOut] = Field(
        default_factory=list, description="连续自然日序列（无数据补零）"
    )
    date_from: date
    date_to: date


__all__ = [
    "QcDailyCompletionItemOut",
    "QcDailyCompletionOut",
    "QcReportOverviewOut",
]