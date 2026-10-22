"""坐席与自动分配接口（OB-018）。"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional, tenant_scope_required
from app.core.response import ApiResponse, PageData, ok
from app.db.session import get_db
from app.models.outbound.enums import AgentStatus, AssignmentStatus
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.outbound.config import (
    AgentCreate,
    AgentOut,
    AgentStatusChange,
    AgentStatusLogOut,
    AgentUpdate,
)
from app.schemas.outbound.execution import (
    AgentAssignmentOut,
    AgentDispatchResultOut,
    AgentReservationExpireOut,
    AgentStatusChangeResultOut,
    OutboundPredictionOut,
)
from app.services.outbound.agent_service import OutboundAgentService
from app.services.outbound.assignment_service import OutboundAssignmentService
from app.services.outbound.common import build_page
from app.services.outbound.prediction_service import OutboundPredictionService
from app.services.outbound.task_service import OutboundTaskService

router = APIRouter(prefix="/outbound", tags=["外呼-坐席"])


@router.get(
    "/agents",
    response_model=ApiResponse[PageData[AgentOut]],
    summary="坐席列表",
    description="按租户 / 站点 / 技能队列 / 状态筛选坐席。",
    dependencies=[Depends(require_permission("outbound:agent:list"))],
)
def list_agents(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    site_id: int | None = Query(default=None, gt=0, description="站点"),
    skill_queue_id: int | None = Query(default=None, gt=0, description="技能队列"),
    status: AgentStatus | None = Query(default=None, description="坐席状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundAgentService(db).list_agents(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        site_id=site_id,
        skill_queue_id=skill_queue_id,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "/agents",
    response_model=ApiResponse[AgentOut],
    summary="新增坐席（OB-018）",
    description=(
        "坐席必须关联既有 users 账号（§3.1 不建第二套账号体系），一个用户最多一个坐席；"
        "初始状态为离线（OFFLINE）；站点与技能队列需属于同一租户。"
    ),
    dependencies=[Depends(require_permission("outbound:agent:create"))],
)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundAgentService(db).create_agent(payload))


@router.put(
    "/agents/{agent_id}",
    response_model=ApiResponse[AgentOut],
    summary="编辑坐席",
    description="可调整站点、技能队列与分机号；关联用户与归属租户不可修改。",
    dependencies=[Depends(require_permission("outbound:agent:update"))],
)
def update_agent(
    agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundAgentService(db).update_agent(agent_id, payload))


@router.delete(
    "/agents/{agent_id}",
    response_model=ApiResponse[None],
    summary="删除坐席",
    description="存在未释放的派单预占或进行中的外呼会话时禁止删除（返回 40904）。",
    dependencies=[Depends(require_permission("outbound:agent:delete"))],
)
def delete_agent(agent_id: int, db: Session = Depends(get_db)) -> Any:
    OutboundAgentService(db).delete_agent(agent_id)
    return ok(None, message="删除成功")


@router.get(
    "/agents/status-summary",
    response_model=ApiResponse[dict],
    summary="坐席状态统计",
    description="按状态汇总坐席数量，供实时监控与预测外呼使用。",
    dependencies=[Depends(require_permission("outbound:agent:list"))],
)
def agent_status_summary(
    tenant_id: int = Depends(tenant_scope_required),
    skill_queue_id: int | None = Query(default=None, gt=0, description="技能队列"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(
        OutboundAgentService(db).count_status(
            tenant_id=tenant_id, skill_queue_id=skill_queue_id
        )
    )


@router.get(
    "/agents/{agent_id}",
    response_model=ApiResponse[AgentOut],
    summary="坐席详情",
    description="返回单个坐席关联的用户、站点、技能队列、分机号与实时状态。",
    dependencies=[Depends(require_permission("outbound:agent:list"))],
)
def get_agent(agent_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundAgentService(db).get_agent(agent_id))


@router.get(
    "/agents/{agent_id}/status-logs",
    response_model=ApiResponse[list[AgentStatusLogOut]],
    summary="坐席状态变更历史",
    description="§11：所有状态变化都必须留痕。",
    dependencies=[Depends(require_permission("outbound:agent:list"))],
)
def list_agent_status_logs(
    agent_id: int,
    limit: int = Query(default=50, ge=1, le=200, description="返回条数"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundAgentService(db).list_status_logs(agent_id, limit=limit))


@router.put(
    "/agents/{agent_id}/status",
    response_model=ApiResponse[AgentStatusChangeResultOut],
    summary="变更坐席状态",
    description=(
        "§11 状态机集中校验，非法流转返回 40902；"
        "§34：置为 IDLE（示闲）时立即触发自动分配并返回派单结果。"
    ),
)
def change_agent_status(
    agent_id: int,
    payload: AgentStatusChange,
    auto_assign: bool = Query(default=True, description="示闲后是否立即自动派单"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("outbound:agent:update")),
) -> Any:
    return ok(
        OutboundAgentService(db).change_status(
            agent_id,
            payload.status,
            reason=payload.reason,
            operator_id=current_user.id,
            auto_assign=auto_assign,
        )
    )


@router.get(
    "/assignments",
    response_model=ApiResponse[PageData[AgentAssignmentOut]],
    summary="坐席预占与派单列表",
    description="分页查询派单与坐席预占记录，支持按任务 / 坐席 / 状态筛选（OB-018）。",
    dependencies=[Depends(require_permission("outbound:assignment:list"))],
)
def list_assignments(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    agent_id: int | None = Query(default=None, gt=0, description="坐席"),
    task_id: int | None = Query(default=None, gt=0, description="任务"),
    status: AssignmentStatus | None = Query(default=None, description="预占状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundAssignmentService(db).list_assignments(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        agent_id=agent_id,
        task_id=task_id,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "/assignments/dispatch",
    response_model=ApiResponse[AgentDispatchResultOut],
    summary="触发批量自动派单",
    description=(
        "§33：遍历空闲坐席，按「技能队列 → 任务优先级 → 名单优先级」派单并预占。"
        "排序规则全部集中在分配服务内。"
    ),
    dependencies=[Depends(require_permission("outbound:assignment:dispatch"))],
)
def dispatch_assignments(
    tenant_id: int | None = Depends(tenant_scope_optional),
    limit: int = Query(default=50, ge=1, le=200, description="最多处理的坐席数"),
    db: Session = Depends(get_db),
) -> Any:
    service = OutboundAssignmentService(db)
    return ok(service.dispatch_pending(tenant_id=tenant_id, limit=limit))


@router.post(
    "/assignments/expire",
    response_model=ApiResponse[AgentReservationExpireOut],
    summary="释放超时预占",
    description=(
        "§35：预占必须带过期时间，超过即自动释放"
        "（定时任务每 30 秒执行一次，此为手动触发入口）。"
    ),
    dependencies=[Depends(require_permission("outbound:assignment:dispatch"))],
)
def expire_assignments(
    limit: int = Query(default=100, ge=1, le=500, description="本次最多释放条数"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundAssignmentService(db).expire_reservations(limit=limit))


@router.post(
    "/assignments/{assignment_id}/accept",
    response_model=ApiResponse[dict],
    summary="坐席接单",
    description="§11：RESERVED → ACCEPTED，坐席状态转为 BUSY。",
    dependencies=[Depends(require_permission("outbound:agent:update"))],
)
def accept_assignment(assignment_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundAssignmentService(db).accept(assignment_id))


@router.post(
    "/assignments/{assignment_id}/release",
    response_model=ApiResponse[dict],
    summary="释放预占",
    description="释放后坐席回到空闲，并尝试领取下一单。",
    dependencies=[Depends(require_permission("outbound:assignment:release"))],
)
def release_assignment(
    assignment_id: int,
    reason: str | None = Body(default=None, embed=True, max_length=255, description="释放原因"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundAssignmentService(db).release(assignment_id, reason=reason or ""))


@router.get(
    "/tasks/{task_id}/prediction",
    response_model=ApiResponse[OutboundPredictionOut],
    summary="预测外呼并发建议",
    description=(
        "§36：answer_rate = answered / total；"
        "target_concurrency = 空闲坐席数 × answer_rate × adjustment_factor（不超过任务并发上限）。"
    ),
    dependencies=[Depends(require_permission("outbound:task:list"))],
)
def get_prediction(task_id: int, db: Session = Depends(get_db)) -> Any:
    task = OutboundTaskService(db).get_task(task_id)
    return ok(OutboundPredictionService(db).target_concurrency(task))
