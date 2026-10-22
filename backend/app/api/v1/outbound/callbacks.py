"""回呼接口（OB-029 IVR 回呼流程 / OB-030 人工回呼流程）。"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok
from app.db.session import get_db
from app.models.outbound.enums import CallbackSource, CallbackStatus, CommonStatus
from app.schemas.common import PageParams
from app.schemas.outbound import (
    CallbackAssignOut,
    CallbackCallOut,
    CallbackDispatchResultOut,
    CallbackFlowCreate,
    CallbackFlowDeleteResult,
    CallbackFlowOut,
    CallbackFlowUpdate,
    CallbackTaskCreate,
    CallbackTaskOut,
    CallbackTriggerContextIn,
    CallbackTriggerResultOut,
    CommonStatusChange,
)
from app.services.outbound.callback_service import CallbackService
from app.services.outbound.common import build_page

router = APIRouter(prefix="/outbound/callback", tags=["外呼-回呼"])


# ---------------- 回呼流程 ----------------


@router.get(
    "/flows",
    response_model=ApiResponse[PageData[CallbackFlowOut]],
    summary="回呼流程列表",
    description="OB-029：分页查询回呼流程（触发条件配置），支持名称 / 编码 / 状态筛选。",
    dependencies=[Depends(require_permission("outbound:callback:list"))],
)
def list_flows(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    code: str | None = Query(default=None, max_length=64, description="流程编码，模糊匹配"),
    name: str | None = Query(default=None, max_length=128, description="流程名称，模糊匹配"),
    status: CommonStatus | None = Query(default=None, description="状态"),
    ivr_flow_id: int | None = Query(default=None, gt=0, description="关联 IVR 流程"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = CallbackService(db).list_flows(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        code=code,
        name=name,
        status=status,
        ivr_flow_id=ivr_flow_id,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "/flows",
    response_model=ApiResponse[CallbackFlowOut],
    summary="新增回呼流程",
    description=(
        "OB-029：配置回呼触发条件——triggers（NO_AGENT 无可用坐席 / NO_ANSWER 未接通坐席 / "
        "KEY 按键命中 / OUT_OF_HOURS 非业务时段）任一命中即触发，"
        "配合 business_hours、delay_seconds、max_attempts、priority 使用。"
    ),
    dependencies=[Depends(require_permission("outbound:callback:create"))],
)
def create_flow(payload: CallbackFlowCreate, db: Session = Depends(get_db)) -> Any:
    return ok(CallbackService(db).create_flow(payload))


@router.put(
    "/flows/{flow_id}",
    response_model=ApiResponse[CallbackFlowOut],
    summary="编辑回呼流程",
    description="可调整流程名称、触发条件、关联 IVR 流程与状态；编码创建后不可修改。",
    dependencies=[Depends(require_permission("outbound:callback:create"))],
)
def update_flow(
    flow_id: int, payload: CallbackFlowUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(CallbackService(db).update_flow(flow_id, payload))


@router.put(
    "/flows/{flow_id}/status",
    response_model=ApiResponse[CallbackFlowOut],
    summary="启用 / 停用回呼流程",
    description="已产生回呼任务的流程禁止停用（返回 40904）。",
    dependencies=[Depends(require_permission("outbound:callback:create"))],
)
def change_flow_status(
    flow_id: int, payload: CommonStatusChange, db: Session = Depends(get_db)
) -> Any:
    return ok(CallbackService(db).set_flow_status(flow_id, payload.status))


@router.delete(
    "/flows/{flow_id}",
    response_model=ApiResponse[CallbackFlowDeleteResult],
    summary="删除回呼流程",
    description="已产生回呼任务的流程禁止删除（返回 40904）。",
    dependencies=[Depends(require_permission("outbound:callback:create"))],
)
def delete_flow(flow_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(CallbackService(db).delete_flow(flow_id))


# ---------------- 回呼任务 ----------------


@router.get(
    "/tasks",
    response_model=ApiResponse[PageData[CallbackTaskOut]],
    summary="回呼任务列表",
    description="§46：按来源 / 状态 / 流程 / 任务 / 名单 / 坐席 / 号码筛选回呼任务。",
    dependencies=[Depends(require_permission("outbound:callback:list"))],
)
def list_tasks(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    source: CallbackSource | None = Query(default=None, description="来源：IVR / MANUAL"),
    status: CallbackStatus | None = Query(default=None, description="回呼状态"),
    flow_id: int | None = Query(default=None, gt=0, description="回呼流程"),
    task_id: int | None = Query(default=None, gt=0, description="关联外呼任务"),
    list_id: int | None = Query(default=None, gt=0, description="关联名单"),
    agent_id: int | None = Query(default=None, gt=0, description="执行坐席"),
    phone: str | None = Query(default=None, max_length=32, description="回呼号码，模糊匹配"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = CallbackService(db).list_tasks(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        source=source,
        status=status,
        flow_id=flow_id,
        task_id=task_id,
        list_id=list_id,
        agent_id=agent_id,
        phone=phone,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "/tasks",
    response_model=ApiResponse[CallbackTaskOut],
    summary="创建回呼任务（人工回呼 OB-030）",
    description=(
        "人工创建回呼任务：填写回呼号码与备注，可选关联外呼任务 / 名单 / 执行坐席；"
        "带 origin_session_id 时命中 §78 幂等，直接返回已存在的回呼任务。"
    ),
    dependencies=[Depends(require_permission("outbound:callback:create"))],
)
def create_task(payload: CallbackTaskCreate, db: Session = Depends(get_db)) -> Any:
    return ok(CallbackService(db).create_task(payload))


@router.post(
    "/tasks/from-ivr",
    response_model=ApiResponse[CallbackTriggerResultOut],
    summary="IVR 会话结束时生成回呼任务（OB-029）",
    description=(
        "按 §45 触发条件匹配启用中的回呼流程并生成回呼任务："
        "同一 origin_session_id 只生成一条（§78 幂等）；"
        "未命中任何触发条件时 created=false 并回显原因，便于排查配置。"
    ),
    dependencies=[Depends(require_permission("outbound:callback:create"))],
)
def create_task_from_ivr(
    payload: CallbackTriggerContextIn, db: Session = Depends(get_db)
) -> Any:
    return ok(CallbackService(db).create_from_ivr(payload))


@router.get(
    "/tasks/{task_id}",
    response_model=ApiResponse[CallbackTaskOut],
    summary="回呼任务详情",
    description="返回单个回呼任务的完整字段及其来源会话 / 名单 / 坐席信息。",
    dependencies=[Depends(require_permission("outbound:callback:list"))],
)
def get_task(task_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(CallbackService(db).get_task(task_id))


@router.post(
    "/tasks/dispatch",
    response_model=ApiResponse[CallbackDispatchResultOut],
    summary="批量派单到期待回呼任务",
    description=(
        "§46：把已到计划时间（或未设计划时间）的待回呼任务分配给空闲坐席；"
        "定时任务每 60 秒自动执行一次，此为手动触发入口。"
    ),
    dependencies=[Depends(require_permission("outbound:callback:execute"))],
)
def dispatch_tasks(
    tenant_id: int | None = Depends(tenant_scope_optional),
    limit: int = Query(default=50, ge=1, le=200, description="本次最多处理条数"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(CallbackService(db).dispatch_due(tenant_id=tenant_id, limit=limit))


@router.post(
    "/tasks/{task_id}/assign",
    response_model=ApiResponse[CallbackAssignOut],
    summary="回呼任务派单",
    description="指定坐席，或在未指定时由系统挑选空闲坐席（按坐席 ID 升序，结果确定）。",
    dependencies=[Depends(require_permission("outbound:callback:execute"))],
)
def assign_task(
    task_id: int,
    agent_id: int | None = Body(default=None, embed=True, gt=0, description="执行坐席"),
    db: Session = Depends(get_db),
) -> Any:
    task = CallbackService(db).assign_task(task_id, agent_id=agent_id)
    return ok(
        {
            "task_id": task.id,
            "agent_id": task.agent_id,
            "assigned_at": task.assigned_at,
            "auto_assigned": agent_id is None,
        }
    )


@router.post(
    "/tasks/{task_id}/call",
    response_model=ApiResponse[CallbackCallOut],
    summary="发起回呼",
    description=(
        "§46：仅「已分配」状态可发起；校验坐席在线、占用一个可用主叫号码并扣减次数，"
        "呼叫结果写入呼叫历史（call_histories.callback_task_id），成功置为已成功、失败置为已失败。"
    ),
    dependencies=[Depends(require_permission("outbound:callback:execute"))],
)
def call_task(task_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(CallbackService(db).call_task(task_id))


@router.post(
    "/tasks/{task_id}/finish",
    response_model=ApiResponse[CallbackTaskOut],
    summary="登记回呼结果",
    description="坐席线下沟通后回填结果；success=true 置为已成功，false 置为已失败。",
    dependencies=[Depends(require_permission("outbound:callback:execute"))],
)
def finish_task(
    task_id: int,
    success: bool = Body(embed=True, description="是否成功"),
    remark: str | None = Body(default=None, embed=True, max_length=255, description="备注"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(CallbackService(db).finish_task(task_id, success=success, remark=remark))


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=ApiResponse[CallbackTaskOut],
    summary="取消回呼任务",
    description="把未结束的回呼任务置为已取消；已成功 / 已失败的任务不允许取消。",
    dependencies=[Depends(require_permission("outbound:callback:execute"))],
)
def cancel_task(
    task_id: int,
    reason: str | None = Body(default=None, embed=True, max_length=255, description="取消原因"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(CallbackService(db).cancel_task(task_id, reason=reason or ""))


@router.post(
    "/tasks/{task_id}/requeue",
    response_model=ApiResponse[CallbackTaskOut],
    summary="重新入队（重呼）",
    description="把已失败的回呼任务退回待回呼，等待重新派单与呼出。",
    dependencies=[Depends(require_permission("outbound:callback:execute"))],
)
def requeue_task(
    task_id: int,
    reason: str | None = Body(default=None, embed=True, max_length=255, description="重呼原因"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(CallbackService(db).requeue_task(task_id, reason=reason or ""))
