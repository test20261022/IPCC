"""会话与看板接口（OB-021 外呼会话 / OB-023 任务看板）。"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok
from app.db.session import get_db
from app.models.outbound.enums import SessionStatus
from app.schemas.common import PageParams
from app.schemas.outbound.execution import (
    CallHistoryOut,
    OutboundAgentWorklistItemOut,
    OutboundBoardOut,
    OutboundListPhonesOut,
    OutboundSessionDetailOut,
    OutboundSessionOut,
    ServiceSummaryCreate,
    ServiceSummaryOut,
    ServiceSummaryUpdate,
)
from app.services.outbound.board_service import OutboundBoardService
from app.services.outbound.common import build_page
from app.services.outbound.session_service import OutboundSessionService

router = APIRouter(prefix="/outbound", tags=["外呼-会话"])


@router.get(
    "/sessions",
    response_model=ApiResponse[PageData[OutboundSessionOut]],
    summary="外呼会话列表",
    description="§37：按任务 / 坐席 / 名单 / 状态筛选会话。",
    dependencies=[Depends(require_permission("outbound:session:list"))],
)
def list_sessions(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    task_id: int | None = Query(default=None, gt=0, description="外呼任务"),
    agent_id: int | None = Query(default=None, gt=0, description="坐席"),
    list_id: int | None = Query(default=None, gt=0, description="名单"),
    status: SessionStatus | None = Query(default=None, description="会话状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundSessionService(db).list_sessions(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        task_id=task_id,
        agent_id=agent_id,
        list_id=list_id,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.get(
    "/sessions/{session_id}",
    response_model=ApiResponse[OutboundSessionDetailOut],
    summary="外呼会话详情",
    description="§37 / §40：会话 + 名单信息 + 呼叫号码 + 拨打历史 + 服务小结；缺失字段返回 null。",
    dependencies=[Depends(require_permission("outbound:session:list"))],
)
def get_session_detail(session_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundSessionService(db).get_session_detail(session_id))


@router.get(
    "/sessions/{session_id}/summary",
    response_model=ApiResponse[ServiceSummaryOut | None],
    summary="查询服务小结",
    description="§40：未填写时返回 null，前端显示 '-'。",
    dependencies=[Depends(require_permission("outbound:session:list"))],
)
def get_session_summary(session_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundSessionService(db).get_summary(session_id))


@router.post(
    "/sessions/{session_id}/summary",
    response_model=ApiResponse[ServiceSummaryOut],
    summary="提交服务小结",
    description="§40：一会话一条，重复提交为覆盖。",
    dependencies=[Depends(require_permission("outbound:session:call"))],
)
def submit_session_summary(
    session_id: int, payload: ServiceSummaryCreate, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundSessionService(db).upsert_summary(session_id, payload))


@router.put(
    "/sessions/{session_id}/summary",
    response_model=ApiResponse[ServiceSummaryOut],
    summary="更新服务小结",
    description="仅更新显式传入的字段；尚无小结时返回 400。",
    dependencies=[Depends(require_permission("outbound:session:call"))],
)
def update_session_summary(
    session_id: int, payload: ServiceSummaryUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundSessionService(db).upsert_summary(session_id, payload))


@router.get(
    "/agents/{agent_id}/worklist",
    response_model=ApiResponse[PageData[OutboundAgentWorklistItemOut]],
    summary="坐席名下待呼名单",
    description=(
        "OB-021-1：展示坐席名下名单，含按任务配置解析的号码数量与来源顺序、"
        "以及「是否已呼叫成功」与重试信息。"
    ),
    dependencies=[Depends(require_permission("outbound:session:list"))],
)
def get_agent_worklist(
    agent_id: int,
    page: PageParams = Depends(),
    include_finished: bool = Query(default=False, description="是否包含已结束的名单"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundSessionService(db).list_agent_worklist(
        agent_id, page=page.page, page_size=page.page_size, include_finished=include_finished
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.get(
    "/lists/{list_id}/phones",
    response_model=ApiResponse[OutboundListPhonesOut],
    summary="名单呼叫号码解析",
    description=(
        "OB-021-1.2/1.3/1.4/2.1/2.3：按任务配置的 OrderID / UserID / 收件人号码顺序解析号码，"
        "并返回第三方电话簿结果、是否已呼叫成功、重试次数与下次可重试时间。"
    ),
    dependencies=[Depends(require_permission("outbound:session:list"))],
)
def resolve_list_phones(list_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundSessionService(db).resolve_list_phones(list_id))


@router.get(
    "/lists/{list_id}/histories",
    response_model=ApiResponse[list[CallHistoryOut]],
    summary="名单拨打历史",
    description="OB-023-2：返回该名单的全部拨打记录。",
    dependencies=[Depends(require_permission("outbound:session:list"))],
)
def list_list_histories(list_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundBoardService(db).list_histories(list_id))


@router.get(
    "/lists/{list_id}/board",
    response_model=ApiResponse[OutboundBoardOut],
    summary="外呼任务看板",
    description=(
        "OB-023：聚合导入名单详细信息（UserID / OrderID / 电话号码接口信息）、"
        "按任务配置顺序的呼叫号码、拨打历史、关联会话、服务小结与第三方接口信息。"
    ),
    dependencies=[Depends(require_permission("outbound:list:list"))],
)
def get_list_board(list_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundBoardService(db).build_board(list_id))
