"""IVR 外呼策略接口（OB-017：转人工路由策略、有效按键处理）。"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok
from app.db.session import get_db
from app.models.outbound.enums import CommonStatus
from app.schemas.common import PageParams
from app.schemas.outbound import (
    CommonStatusChange,
    IvrFlowCreate,
    IvrFlowDeleteResult,
    IvrFlowDetailOut,
    IvrFlowOut,
    IvrFlowUpdate,
    IvrNodeCreate,
    IvrNodeDeleteResult,
    IvrNodeOut,
    IvrNodeUpdate,
    IvrSimulationRequest,
    IvrSimulationResultOut,
    IvrTransitionCreate,
    IvrTransitionOut,
    IvrTransitionUpdate,
    IvrValidationResultOut,
)
from app.services.outbound.common import build_page
from app.services.outbound.ivr_service import IvrService
from app.services.outbound.ivr_strategy import IvrSimulationInput

router = APIRouter(prefix="/outbound/ivr", tags=["外呼-IVR 策略"])


# ---------------- 流程 ----------------


@router.get(
    "/flows",
    response_model=ApiResponse[PageData[IvrFlowOut]],
    summary="IVR 流程列表",
    description="OB-017：分页查询 IVR 流程，支持名称 / 编码 / 状态筛选。",
    dependencies=[Depends(require_permission("outbound:ivr:list"))],
)
def list_flows(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    code: str | None = Query(default=None, max_length=64, description="流程编码，模糊匹配"),
    name: str | None = Query(default=None, max_length=128, description="流程名称，模糊匹配"),
    status: CommonStatus | None = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = IvrService(db).list_flows(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        code=code,
        name=name,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "/flows",
    response_model=ApiResponse[IvrFlowOut],
    summary="新增 IVR 流程",
    description="同一租户下流程编码唯一；入口节点可在节点配置完成后回填。",
    dependencies=[Depends(require_permission("outbound:ivr:create"))],
)
def create_flow(payload: IvrFlowCreate, db: Session = Depends(get_db)) -> Any:
    return ok(IvrService(db).create_flow(payload))


@router.get(
    "/flows/{flow_id}",
    response_model=ApiResponse[IvrFlowDetailOut],
    summary="IVR 流程详情",
    description="返回流程配置及其全部节点与流转条件，供编辑器一次拉全。",
    dependencies=[Depends(require_permission("outbound:ivr:list"))],
)
def get_flow(flow_id: int, db: Session = Depends(get_db)) -> Any:
    detail = IvrService(db).get_flow_detail(flow_id)
    payload = IvrFlowDetailOut.model_validate(detail["flow"]).model_dump()
    payload["nodes"] = detail["nodes"]
    payload["transitions"] = detail["transitions"]
    return ok(payload)


@router.put(
    "/flows/{flow_id}",
    response_model=ApiResponse[IvrFlowOut],
    summary="编辑 IVR 流程",
    description="入口节点必须指向本流程内已存在的节点。",
    dependencies=[Depends(require_permission("outbound:ivr:update"))],
)
def update_flow(flow_id: int, payload: IvrFlowUpdate, db: Session = Depends(get_db)) -> Any:
    return ok(IvrService(db).update_flow(flow_id, payload))


@router.put(
    "/flows/{flow_id}/status",
    response_model=ApiResponse[IvrFlowOut],
    summary="启用 / 停用 IVR 流程",
    description="被外呼任务引用的流程禁止停用（返回 40904）。",
    dependencies=[Depends(require_permission("outbound:ivr:update"))],
)
def change_flow_status(
    flow_id: int, payload: CommonStatusChange, db: Session = Depends(get_db)
) -> Any:
    return ok(IvrService(db).set_flow_status(flow_id, payload.status))


@router.delete(
    "/flows/{flow_id}",
    response_model=ApiResponse[IvrFlowDeleteResult],
    summary="删除 IVR 流程",
    description="被外呼任务引用时禁止删除并回显引用任务名；删除会联动软删除节点与流转。",
    dependencies=[Depends(require_permission("outbound:ivr:delete"))],
)
def delete_flow(flow_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(IvrService(db).delete_flow(flow_id))


@router.get(
    "/flows/{flow_id}/validate",
    response_model=ApiResponse[IvrValidationResultOut],
    summary="IVR 流程结构校验",
    description=(
        "OB-017：校验入口节点、转人工兜底动作（§32）、流转节点归属、时段 / 队列条件取值等，"
        "并提示不可达节点、终结节点多余流转、自环等风险。ERROR 阻断发布，WARNING 仅提示。"
    ),
    dependencies=[Depends(require_permission("outbound:ivr:list"))],
)
def validate_flow(flow_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(IvrService(db).validate_flow(flow_id))


@router.post(
    "/flows/{flow_id}/simulate",
    response_model=ApiResponse[IvrSimulationResultOut],
    summary="IVR 流程模拟运行",
    description=(
        "OB-017：按流程结构推演一次执行过程——有效按键命中流转、非法按键重播与挂断、"
        "转人工路由（有可用坐席即转接，否则按节点的无坐席动作兜底）、"
        "以及 ASR / 时段 / 队列可用性条件。返回逐步轨迹便于核对配置。"
    ),
    dependencies=[Depends(require_permission("outbound:ivr:list"))],
)
def simulate_flow(
    flow_id: int, payload: IvrSimulationRequest, db: Session = Depends(get_db)
) -> Any:
    return ok(
        IvrService(db).simulate_flow(
            flow_id,
            inputs=[
                IvrSimulationInput(input_type=item.input_type, value=item.value)
                for item in payload.inputs
            ],
            current_time=payload.current_time,
            queue_available=payload.queue_available,
            skill_queue_id=payload.skill_queue_id,
            max_steps=payload.max_steps,
        )
    )


# ---------------- 节点 ----------------


@router.post(
    "/flows/{flow_id}/nodes",
    response_model=ApiResponse[IvrNodeOut],
    summary="新增 IVR 节点",
    description="节点标识在流程内唯一；转人工节点必须显式配置「无可用坐席动作」（§32）。",
    dependencies=[Depends(require_permission("outbound:ivr:create"))],
)
def create_node(
    flow_id: int, payload: IvrNodeCreate, db: Session = Depends(get_db)
) -> Any:
    return ok(IvrService(db).create_node(flow_id, payload))


@router.put(
    "/nodes/{node_id}",
    response_model=ApiResponse[IvrNodeOut],
    summary="编辑 IVR 节点",
    description="可调整节点名称、类型、话术、扩展配置、重播次数与排序；节点 key 创建后不可修改。",
    dependencies=[Depends(require_permission("outbound:ivr:update"))],
)
def update_node(node_id: int, payload: IvrNodeUpdate, db: Session = Depends(get_db)) -> Any:
    return ok(IvrService(db).update_node(node_id, payload))


@router.delete(
    "/nodes/{node_id}",
    response_model=ApiResponse[IvrNodeDeleteResult],
    summary="删除 IVR 节点",
    description="联动软删除以该节点为源或目标的流转；若删除的是入口节点则同时清空流程入口。",
    dependencies=[Depends(require_permission("outbound:ivr:delete"))],
)
def delete_node(node_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(IvrService(db).delete_node(node_id))


# ---------------- 流转 ----------------


@router.post(
    "/flows/{flow_id}/transitions",
    response_model=ApiResponse[IvrTransitionOut],
    summary="新增 IVR 流转条件",
    description=(
        "条件类型：KEY 按键 / ASR_RESULT 识别结果 / TIME_RANGE 时段 / QUEUE_AVAILABLE 队列可用。"
        "条件值留空或填 * 表示「无条件 / 任意按键」兜底流转。"
    ),
    dependencies=[Depends(require_permission("outbound:ivr:create"))],
)
def create_transition(
    flow_id: int, payload: IvrTransitionCreate, db: Session = Depends(get_db)
) -> Any:
    return ok(IvrService(db).create_transition(flow_id, payload))


@router.put(
    "/transitions/{transition_id}",
    response_model=ApiResponse[IvrTransitionOut],
    summary="编辑 IVR 流转条件",
    description="可调整目标节点、条件类型与取值、命中优先级；源节点创建后不可修改。",
    dependencies=[Depends(require_permission("outbound:ivr:update"))],
)
def update_transition(
    transition_id: int, payload: IvrTransitionUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(IvrService(db).update_transition(transition_id, payload))


@router.delete(
    "/transitions/{transition_id}",
    response_model=ApiResponse[None],
    summary="删除 IVR 流转条件",
    description="软删除指定流转条件，删除后该分支不再命中。",
    dependencies=[Depends(require_permission("outbound:ivr:delete"))],
)
def delete_transition(transition_id: int, db: Session = Depends(get_db)) -> Any:
    IvrService(db).delete_transition(transition_id)
    return ok(None, message="删除成功")
