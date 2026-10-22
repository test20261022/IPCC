"""质检任务接口（质检-任务）。"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok, page_data
from app.db.session import get_db
from app.models.qc.enums import QcGrade, QcItemStatus, QcTaskStatus
from app.schemas.common import PageParams
from app.schemas.qc.report import QcReportOverviewOut
from app.schemas.qc.review import (
    QcTaskCreate,
    QcTaskDeleteResult,
    QcTaskDetailOut,
    QcTaskDispatchResult,
    QcTaskItemOut,
    QcTaskOut,
    QcTaskUpdate,
)
from app.services.qc.task_service import QcTaskService

router = APIRouter(prefix="/qc/tasks", tags=["质检-任务"])


@router.get(
    "",
    response_model=ApiResponse[PageData[QcTaskOut]],
    summary="质检任务列表",
    description="支持按租户、状态与任务名模糊查询。",
    dependencies=[Depends(require_permission("qc:task:list"))],
)
def list_qc_tasks(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    status: QcTaskStatus | None = Query(default=None, description="任务状态"),
    keyword: str | None = Query(default=None, max_length=128, description="任务名模糊匹配"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = QcTaskService(db).list_tasks(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        status=status,
        keyword=keyword,
    )
    return ok(page_data(items, total, page.page, page.page_size))


@router.post(
    "",
    response_model=ApiResponse[QcTaskOut],
    summary="新增质检任务",
    description="以时间区间（对话开始时间）圈定质检范围，任务创建后为 DRAFT，派发时生成明细。",
    dependencies=[Depends(require_permission("qc:task:create"))],
)
def create_qc_task(payload: QcTaskCreate, db: Session = Depends(get_db)) -> Any:
    return ok(QcTaskService(db).create_task(payload))


@router.get(
    "/{task_id}",
    response_model=ApiResponse[QcTaskDetailOut],
    summary="质检任务详情",
    description="返回任务配置、明细总数 / 已完成数与完成率。",
    dependencies=[Depends(require_permission("qc:task:list"))],
)
def get_qc_task(task_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcTaskService(db).get_task_detail(task_id))


@router.put(
    "/{task_id}",
    response_model=ApiResponse[QcTaskOut],
    summary="编辑质检任务",
    description="仅 DRAFT 状态可编辑；派发后配置冻结。",
    dependencies=[Depends(require_permission("qc:task:update"))],
)
def update_qc_task(task_id: int, payload: QcTaskUpdate, db: Session = Depends(get_db)) -> Any:
    return ok(QcTaskService(db).update_task(task_id, payload))


@router.delete(
    "/{task_id}",
    response_model=ApiResponse[QcTaskDeleteResult],
    summary="删除质检任务",
    description="仅 DRAFT / CANCELLED 可删除；联动软删除任务下全部明细。",
    dependencies=[Depends(require_permission("qc:task:delete"))],
)
def delete_qc_task(task_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcTaskService(db).delete_task(task_id))


@router.post(
    "/{task_id}/dispatch",
    response_model=ApiResponse[QcTaskDispatchResult],
    summary="派发质检任务",
    description=(
        "把时间区间内的对话按专家组启用成员分批派发（ROUND_ROBIN 交替 / AVERAGE 均分）；"
        "超过「成员数 × QC_MAX_PER_REVIEWER」时拒绝并提示拆批；"
        "派发幂等（唯一索引 + ON CONFLICT），中断后仍为 DRAFT 可重复调用续跑。"
    ),
    dependencies=[Depends(require_permission("qc:task:dispatch"))],
)
def dispatch_qc_task(task_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcTaskService(db).dispatch(task_id))


@router.post(
    "/{task_id}/cancel",
    response_model=ApiResponse[QcTaskOut],
    summary="取消质检任务",
    description="按状态机流转到 CANCELLED 并写入 finished_at。",
    dependencies=[Depends(require_permission("qc:task:cancel"))],
)
def cancel_qc_task(task_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcTaskService(db).cancel_task(task_id))


@router.get(
    "/{task_id}/items",
    response_model=ApiResponse[PageData[QcTaskItemOut]],
    summary="任务明细列表",
    description="按状态 / 专家 / 等级筛选任务下的质检明细。",
    dependencies=[Depends(require_permission("qc:task:list"))],
)
def list_qc_task_items(
    task_id: int,
    page: PageParams = Depends(),
    status: QcItemStatus | None = Query(default=None, description="明细状态"),
    reviewer_id: int | None = Query(default=None, gt=0, description="专家用户 ID"),
    grade: QcGrade | None = Query(default=None, description="质检等级"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = QcTaskService(db).list_items(
        task_id=task_id,
        page=page.page,
        page_size=page.page_size,
        status=status,
        reviewer_id=reviewer_id,
        grade=grade,
    )
    return ok(page_data(items, total, page.page, page.page_size))


@router.get(
    "/{task_id}/report",
    response_model=ApiResponse[QcReportOverviewOut],
    summary="任务质检报表",
    description="任务维度的质检概览（与 /qc/reports/overview 同口径）。",
    dependencies=[Depends(require_permission("qc:report:list"))],
)
def get_qc_task_report(task_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcTaskService(db).task_report(task_id))