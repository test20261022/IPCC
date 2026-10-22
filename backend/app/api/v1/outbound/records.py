"""外呼执行接口（OB-008：策略执行 / 多号码 / 重试 / 超时回收）。"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.callback_signature import verify_callback_signature
from app.core.response import ApiResponse, PageData, ok
from app.db.session import get_db
from app.models.outbound.enums import RecordStatus
from app.schemas.common import PageParams
from app.schemas.outbound.execution import (
    CallResultCallbackIn,
    CallResultCallbackOut,
    OutboundBuildRecordsOut,
    OutboundExecuteSummaryOut,
    OutboundRecordCallOut,
    OutboundRecordOut,
    OutboundRecycleResultOut,
)
from app.services.outbound.common import build_page
from app.services.outbound.execution_service import OutboundExecutionService
from app.services.outbound.timeout_service import OutboundTimeoutService

router = APIRouter(prefix="/outbound", tags=["外呼-执行"])


@router.post(
    "/tasks/{task_id}/records/build",
    response_model=ApiResponse[OutboundBuildRecordsOut],
    summary="生成待执行记录",
    description=(
        "把任务下待执行的名单行转成执行记录（幂等：同一名单行在同一任务下只会有一条记录）。"
        "已完成或已取消的任务不允许再生成。"
    ),
    dependencies=[Depends(require_permission("outbound:task:execute"))],
)
def build_records(
    task_id: int,
    limit: int | None = Query(default=None, ge=1, le=500, description="本次最多生成条数"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundExecutionService(db).build_records(task_id, limit=limit))


@router.post(
    "/tasks/{task_id}/execute",
    response_model=ApiResponse[OutboundExecuteSummaryOut],
    summary="执行一批外呼",
    description=(
        "§20：对 PENDING 与到期 RETRY_WAITING 的记录逐条执行——"
        "按任务配置的号码来源顺序逐个尝试被叫号码，任一号码接通即成功；"
        "全部失败则按 §21 进入重试等待或标记耗尽。仅 RUNNING 状态任务可执行。"
    ),
    dependencies=[Depends(require_permission("outbound:task:execute"))],
)
def execute_task(
    task_id: int,
    limit: int | None = Query(default=None, ge=1, le=500, description="本次最多处理条数"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundExecutionService(db).execute_task(task_id, limit=limit))


@router.get(
    "/records",
    response_model=ApiResponse[PageData[OutboundRecordOut]],
    summary="执行记录列表",
    description="按任务 / 名单 / 坐席 / 状态筛选执行记录。",
    dependencies=[Depends(require_permission("outbound:task:list"))],
)
def list_records(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    task_id: int | None = Query(default=None, gt=0, description="外呼任务"),
    list_id: int | None = Query(default=None, gt=0, description="名单"),
    agent_id: int | None = Query(default=None, gt=0, description="坐席"),
    status: RecordStatus | None = Query(default=None, description="执行状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundExecutionService(db).list_records(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        task_id=task_id,
        list_id=list_id,
        agent_id=agent_id,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "/records/{record_id}/call",
    response_model=ApiResponse[OutboundRecordCallOut],
    summary="单条即时呼叫（人工外呼）",
    description=(
        "§38：人工外呼执行。校验记录与任务状态（任务需 RUNNING）、可选坐席归属与在线状态，"
        "随后按任务号码策略选主叫、扣次数、发起呼叫并记录结果。"
    ),
    dependencies=[Depends(require_permission("outbound:session:call"))],
)
def call_record(
    record_id: int,
    agent_id: int | None = Body(default=None, embed=True, gt=0, description="执行坐席"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundExecutionService(db).execute_record(record_id, agent_id=agent_id))


@router.post(
    "/timeout/recycle",
    response_model=ApiResponse[OutboundRecycleResultOut],
    summary="触发超时回收",
    description=(
        "§22：扫描 ASSIGNED / CALLING 且已超时的记录，加锁复核后标记 TIMEOUT、"
        "写呼叫历史、释放坐席预占并按重试阶梯重新入队。定时任务默认每 30 秒自动执行一次。"
    ),
    dependencies=[Depends(require_permission("outbound:task:execute"))],
)
def recycle_timeout(
    limit: int = Query(default=100, ge=1, le=500, description="本次最多回收条数"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundTimeoutService(db).recycle(limit=limit))


@router.post(
    "/call-result/callback",
    response_model=ApiResponse[CallResultCallbackOut],
    summary="呼叫网关结果回调",
    description=(
        "异步网关回写呼叫结果；已有最终结果的呼叫会被忽略（§78 幂等）。"
        "鉴权走共享密钥签名，网关无需登录态："
        "请求头 X-Callback-Timestamp + X-Callback-Signature，"
        "签名原文为 `{timestamp}.{请求体原文}`（HMAC-SHA256），"
        "密钥见配置 CALL_GATEWAY_CALLBACK_SECRET，时间戳超出容差按重放拒绝。"
    ),
    dependencies=[Depends(verify_callback_signature)],
)
def call_result_callback(payload: CallResultCallbackIn, db: Session = Depends(get_db)) -> Any:
    return ok(
        OutboundExecutionService(db).handle_call_result(
            provider_call_id=payload.provider_call_id,
            call_status=payload.call_status,
            duration=payload.duration,
            failure_reason=payload.failure_reason,
            recording_path=payload.recording_path,
        )
    )
