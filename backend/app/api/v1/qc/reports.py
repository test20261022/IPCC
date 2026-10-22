"""质检报表接口（质检-报表）。"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, ok
from app.db.session import get_db
from app.schemas.qc.report import QcDailyCompletionOut, QcReportOverviewOut
from app.services.qc.report_service import QcReportService

router = APIRouter(prefix="/qc/reports", tags=["质检-报表"])


@router.get(
    "/overview",
    response_model=ApiResponse[QcReportOverviewOut],
    summary="质检概览报表",
    description=(
        "返回总量 / 待质检 / 质检中 / 已完成 / 完成率 / 等级分布 / 参与专家数；"
        "task_id 为空时按租户汇总全部任务。"
    ),
    dependencies=[Depends(require_permission("qc:report:list"))],
)
def get_qc_overview(
    task_id: int | None = Query(default=None, gt=0, description="质检任务；为空按租户汇总"),
    tenant_id: int | None = Depends(tenant_scope_optional),
    db: Session = Depends(get_db),
) -> Any:
    return ok(QcReportService(db).overview(task_id=task_id, tenant_id=tenant_id))


@router.get(
    "/daily-completion",
    response_model=ApiResponse[QcDailyCompletionOut],
    summary="质检按天完成报表",
    description=(
        "按报表时区（QC_REPORT_TIMEZONE）自然日分桶统计提交量；"
        "无数据的日期补零，返回 date_from..date_to 的连续序列。"
    ),
    dependencies=[Depends(require_permission("qc:report:list"))],
)
def get_qc_daily_completion(
    date_from: date = Query(description="起始日期（含），YYYY-MM-DD"),
    date_to: date = Query(description="结束日期（含），YYYY-MM-DD"),
    task_id: int | None = Query(default=None, gt=0, description="质检任务；为空按租户汇总"),
    tenant_id: int | None = Depends(tenant_scope_optional),
    db: Session = Depends(get_db),
) -> Any:
    return ok(
        QcReportService(db).daily_completion(
            date_from=date_from, date_to=date_to, task_id=task_id, tenant_id=tenant_id
        )
    )