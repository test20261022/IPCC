"""外呼号码接口（OB-001 号码管理 / OB-005 主叫号码使用规则）。"""

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
    OutboundNumberCreate,
    OutboundNumberOut,
    OutboundNumberUpdate,
)
from app.services.outbound.common import build_page
from app.services.outbound.number_service import OutboundNumberService

router = APIRouter(prefix="/outbound/numbers", tags=["外呼-号码"])


@router.get(
    "",
    response_model=ApiResponse[PageData[OutboundNumberOut]],
    summary="外呼号码列表",
    description="分页查询号码，返回 used_count / usage_limit 用于次数显示（OB-001）。",
    dependencies=[Depends(require_permission("outbound:number:list"))],
)
def list_numbers(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    caller_number: str | None = Query(
        default=None, max_length=32, description="主叫号码，模糊匹配"
    ),
    display_name: str | None = Query(
        default=None, max_length=128, description="外显名称，模糊匹配"
    ),
    status: CommonStatus | None = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundNumberService(db).list_numbers(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        caller_number=caller_number,
        display_name=display_name,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "",
    response_model=ApiResponse[OutboundNumberOut],
    summary="新增外呼号码",
    description="外显名称必填、主叫号码格式校验、校验租户存在且启用；同一租户下主叫号码唯一。",
    dependencies=[Depends(require_permission("outbound:number:create"))],
)
def create_number(payload: OutboundNumberCreate, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundNumberService(db).create_number(payload))


@router.get(
    "/{number_id}",
    response_model=ApiResponse[OutboundNumberOut],
    summary="外呼号码详情",
    description="返回单个外呼号码的完整字段与剩余可用次数（OB-001 / OB-005）。",
    dependencies=[Depends(require_permission("outbound:number:list"))],
)
def get_number(number_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundNumberService(db).get_number(number_id))


@router.put(
    "/{number_id}",
    response_model=ApiResponse[OutboundNumberOut],
    summary="编辑外呼号码",
    description="主叫号码与归属租户创建后不可修改，仅可调整外显名称、类型、次数上限、状态与备注。",
    dependencies=[Depends(require_permission("outbound:number:update"))],
)
def update_number(
    number_id: int, payload: OutboundNumberUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundNumberService(db).update_number(number_id, payload))


@router.put(
    "/{number_id}/status",
    response_model=ApiResponse[OutboundNumberOut],
    summary="启用 / 停用外呼号码",
    description="停用后不再被任务选取为主叫号码，剩余次数保留。",
    dependencies=[Depends(require_permission("outbound:number:update"))],
)
def change_number_status(
    number_id: int, payload: CommonStatusChange, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundNumberService(db).set_status(number_id, payload.status))


@router.delete(
    "/{number_id}",
    response_model=ApiResponse[None],
    summary="删除外呼号码",
    description="被外呼任务配置引用的号码禁止删除，返回 40904。",
    dependencies=[Depends(require_permission("outbound:number:delete"))],
)
def delete_number(number_id: int, db: Session = Depends(get_db)) -> Any:
    OutboundNumberService(db).delete_number(number_id)
    return ok(None, message="删除成功")


@router.post(
    "/{number_id}/consume",
    response_model=ApiResponse[OutboundNumberOut],
    summary="扣减主叫号码使用次数",
    description=(
        "原子扣减 used_count（§13）。号码停用返回 40902；次数耗尽返回 40903；号码不存在返回 40401。"
    ),
    dependencies=[Depends(require_permission("outbound:number:use"))],
)
def consume_number(
    number_id: int,
    step: int = Query(default=1, ge=1, le=100, description="扣减次数"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundNumberService(db).consume(number_id, step=step))
