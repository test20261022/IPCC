"""外呼任务接口（OB-006 / OB-020）。"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok
from app.db.session import get_db
from app.models.outbound.enums import DispatchMode, TaskStatus
from app.schemas.common import PageParams
from app.schemas.outbound import OutboundTaskNumberItem
from app.schemas.outbound.config import OutboundTaskNumberOut
from app.schemas.outbound.task import (
    OutboundTaskCopyRequest,
    OutboundTaskCopyResult,
    OutboundTaskCreate,
    OutboundTaskDeleteResult,
    OutboundTaskDetailOut,
    OutboundTaskOut,
    OutboundTaskStatusChange,
    OutboundTaskUpdate,
)
from app.services.outbound.common import build_page
from app.services.outbound.task_service import OutboundTaskService

router = APIRouter(prefix="/outbound/tasks", tags=["外呼-任务"])


@router.get(
    "",
    response_model=ApiResponse[PageData[OutboundTaskOut]],
    summary="外呼任务列表",
    description="OB-006：支持按站点、技能队列、外呼类型查询，并可按场景、状态、派单模式筛选。",
    dependencies=[Depends(require_permission("outbound:task:list"))],
)
def list_tasks(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    task_name: str | None = Query(default=None, max_length=128, description="任务名称，模糊匹配"),
    site_id: int | None = Query(default=None, gt=0, description="站点（OB-006）"),
    skill_queue_id: int | None = Query(default=None, gt=0, description="技能队列（OB-006）"),
    type_id: int | None = Query(default=None, gt=0, description="外呼类型（OB-006）"),
    scene_id: int | None = Query(default=None, gt=0, description="外呼场景"),
    status: TaskStatus | None = Query(default=None, description="任务状态"),
    dispatch_mode: DispatchMode | None = Query(default=None, description="派单模式"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundTaskService(db).list_tasks(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        task_name=task_name,
        site_id=site_id,
        skill_queue_id=skill_queue_id,
        type_id=type_id,
        scene_id=scene_id,
        status=status,
        dispatch_mode=dispatch_mode,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "",
    response_model=ApiResponse[OutboundTaskOut],
    summary="新增外呼任务",
    description=(
        "一次性提交任务基础信息、策略 / 重试 / 超时 / 并发配置、IVR 配置与多号码配置。"
        "任务创建后状态为 DRAFT；同租户下任务名唯一。"
    ),
    dependencies=[Depends(require_permission("outbound:task:create"))],
)
def create_task(payload: OutboundTaskCreate, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundTaskService(db).create_task(payload))


@router.get(
    "/{task_id}",
    response_model=ApiResponse[OutboundTaskDetailOut],
    summary="外呼任务详情",
    description="返回任务配置与其号码配置明细。",
    dependencies=[Depends(require_permission("outbound:task:list"))],
)
def get_task(task_id: int, db: Session = Depends(get_db)) -> Any:
    task, numbers = OutboundTaskService(db).get_task_detail(task_id)
    payload = OutboundTaskDetailOut.model_validate(task).model_dump()
    payload["task_numbers"] = numbers
    return ok(payload)


@router.put(
    "/{task_id}",
    response_model=ApiResponse[OutboundTaskOut],
    summary="编辑外呼任务",
    description="仅 DRAFT / READY / PAUSED 状态可编辑；运行中请先暂停。",
    dependencies=[Depends(require_permission("outbound:task:update"))],
)
def update_task(
    task_id: int, payload: OutboundTaskUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundTaskService(db).update_task(task_id, payload))


@router.put(
    "/{task_id}/numbers",
    response_model=ApiResponse[list[OutboundTaskNumberOut]],
    summary="全量替换任务号码配置",
    description="§19 多号码配置：传入即全量覆盖，含 OrderID / UserID / 收件人号码的调用顺序。",
    dependencies=[Depends(require_permission("outbound:task:update"))],
)
def replace_task_numbers(
    task_id: int,
    numbers: list[OutboundTaskNumberItem] = Body(embed=True, description="号码配置列表"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundTaskService(db).replace_numbers(task_id, numbers))


@router.put(
    "/{task_id}/status",
    response_model=ApiResponse[OutboundTaskOut],
    summary="任务状态流转",
    description="§18 状态机集中管理，非法流转返回 40902；进入 READY 前需至少配置一个启用号码。",
    dependencies=[Depends(require_permission("outbound:task:update"))],
)
def change_task_status(
    task_id: int, payload: OutboundTaskStatusChange, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundTaskService(db).change_status(task_id, payload.status))


@router.post(
    "/{task_id}/copy",
    response_model=ApiResponse[OutboundTaskCopyResult],
    summary="复制外呼任务",
    description=(
        "OB-020：复制站点 / 队列 / 类型 / 场景 / 策略 / 号码配置 / IVR 配置，"
        "不复制名单与执行数据；副本状态为 DRAFT。同名副本重复提交会命中幂等，直接返回已存在的副本。"
    ),
    dependencies=[Depends(require_permission("outbound:task:copy"))],
)
def copy_task(
    task_id: int, payload: OutboundTaskCopyRequest, db: Session = Depends(get_db)
) -> Any:
    task, created = OutboundTaskService(db).copy_task(task_id, payload)
    return ok(
        {"task": task, "created": created},
        message="复制成功" if created else "已返回已存在的副本",
    )


@router.delete(
    "/{task_id}",
    response_model=ApiResponse[OutboundTaskDeleteResult],
    summary="删除外呼任务",
    description="仅 DRAFT / CANCELLED 可删除；已产生执行记录的任务返回 40904。",
    dependencies=[Depends(require_permission("outbound:task:delete"))],
)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundTaskService(db).delete_task(task_id))
