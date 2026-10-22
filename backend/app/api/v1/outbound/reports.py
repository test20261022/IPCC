"""报表接口（OB-025 话务流水报表 / OB-028 外呼实时监控报表）。"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional, tenant_scope_required
from app.core.response import ApiResponse, ok
from app.db.session import get_db
from app.models.outbound.enums import CallStatus
from app.schemas.common import PageParams
from app.schemas.outbound.report import CallFlowReportOut, RealtimeMonitorOut
from app.services.outbound.report_service import OutboundReportService

router = APIRouter(prefix="/outbound/reports", tags=["外呼-报表"])


@router.get(
    "/call-flow",
    response_model=ApiResponse[CallFlowReportOut],
    summary="话务流水报表",
    description=(
        "OB-025：以呼叫历史为事实表输出话务流水，支持按【外呼场景 / 外呼任务 / 外呼类型 / "
        "外呼子类型】以及时间范围、站点、技能队列、坐席、呼叫结果、号码、话务来源筛选；"
        "同时返回同口径的汇总（总量 / 接通量 / 接通率 / 通话时长 / 结果分布）。"
        "选择一级外呼类型时会自动纳入其全部二级子类型的任务。"
    ),
    dependencies=[Depends(require_permission("outbound:report:list"))],
)
def get_call_flow_report(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    started_from: datetime | None = Query(
        default=None, description="呼叫开始时间下界（含），ISO8601"
    ),
    started_to: datetime | None = Query(
        default=None, description="呼叫开始时间上界（含），ISO8601"
    ),
    scene_id: int | None = Query(default=None, gt=0, description="外呼场景（OB-025）"),
    task_id: int | None = Query(default=None, gt=0, description="外呼任务（OB-025）"),
    type_id: int | None = Query(default=None, gt=0, description="外呼类型（OB-025，含子类型）"),
    sub_type_id: int | None = Query(
        default=None, gt=0, description="外呼子类型（OB-025，二级类型）"
    ),
    site_id: int | None = Query(default=None, gt=0, description="站点"),
    skill_queue_id: int | None = Query(default=None, gt=0, description="技能队列"),
    agent_id: int | None = Query(default=None, gt=0, description="坐席"),
    call_status: CallStatus | None = Query(default=None, description="呼叫结果"),
    source: Literal["ALL", "OUTBOUND", "CALLBACK"] = Query(
        default="ALL", description="话务来源：全部 / 仅外呼 / 仅回呼"
    ),
    phone: str | None = Query(default=None, max_length=32, description="被叫号码，模糊匹配"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(
        OutboundReportService(db).call_flow_report(
            page=page.page,
            page_size=page.page_size,
            tenant_id=tenant_id,
            started_from=started_from,
            started_to=started_to,
            scene_id=scene_id,
            task_id=task_id,
            type_id=type_id,
            sub_type_id=sub_type_id,
            site_id=site_id,
            skill_queue_id=skill_queue_id,
            agent_id=agent_id,
            call_status=call_status,
            source=source,
            phone=phone,
        )
    )


@router.get(
    "/monitor",
    response_model=ApiResponse[RealtimeMonitorOut],
    summary="外呼实时监控报表",
    description=(
        "OB-028：返回实时监控快照——统计窗口内的呼叫量 / 接通量 / 接通率 / 通话时长、"
        "坐席 / 任务 / 执行记录 / 回呼任务的状态分布、进行中会话数、"
        "按分钟的呼叫趋势（已补零，可直接画折线）与窗口内任务呼叫量排行。"
    ),
    dependencies=[Depends(require_permission("outbound:monitor:view"))],
)
def get_realtime_monitor(
    tenant_id: int = Depends(tenant_scope_required),
    window_minutes: int = Query(
        default=30, ge=1, le=240, description="统计窗口（分钟），趋势按分钟分桶"
    ),
    db: Session = Depends(get_db),
) -> Any:
    return ok(
        OutboundReportService(db).realtime_monitor(
            tenant_id=tenant_id, window_minutes=window_minutes
        )
    )
