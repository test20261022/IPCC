"""外呼类型接口（OB-004）。Router 只做 HTTP 层，业务在 Service（§54）。"""

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
    OutboundTypeCreate,
    OutboundTypeOut,
    OutboundTypeUpdate,
)
from app.services.outbound.common import build_page
from app.services.outbound.type_service import OutboundTypeService

router = APIRouter(prefix="/outbound/types", tags=["外呼-类型"])


@router.get(
    "",
    response_model=ApiResponse[PageData[OutboundTypeOut]],
    summary="外呼类型列表",
    description="分页查询外呼类型，支持名称 / 编码 / 父类型 / 层级 / 状态筛选。",
    dependencies=[Depends(require_permission("outbound:type:list"))],
)
def list_types(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    name: str | None = Query(default=None, max_length=128, description="名称，模糊匹配"),
    code: str | None = Query(default=None, max_length=64, description="编码，模糊匹配"),
    parent_id: int | None = Query(default=None, gt=0, description="父类型"),
    level: int | None = Query(default=None, ge=1, le=2, description="层级：1 类型 / 2 子类型"),
    status: CommonStatus | None = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundTypeService(db).list_types(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        name=name,
        code=code,
        parent_id=parent_id,
        level=level,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.post(
    "",
    response_model=ApiResponse[OutboundTypeOut],
    summary="新增外呼类型",
    description="新增一级类型或二级子类型；同一租户下编码唯一。",
    dependencies=[Depends(require_permission("outbound:type:create"))],
)
def create_type(payload: OutboundTypeCreate, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundTypeService(db).create_type(payload))


@router.get(
    "/{type_id}",
    response_model=ApiResponse[OutboundTypeOut],
    summary="外呼类型详情",
    description="返回单个外呼类型的完整字段，供编辑表单回显。",
    dependencies=[Depends(require_permission("outbound:type:list"))],
)
def get_type(type_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundTypeService(db).get_type(type_id))


@router.put(
    "/{type_id}",
    response_model=ApiResponse[OutboundTypeOut],
    summary="编辑外呼类型",
    description="被场景 / 任务引用的类型禁止修改编码、层级与父级（破坏性修改）。",
    dependencies=[Depends(require_permission("outbound:type:update"))],
)
def update_type(
    type_id: int, payload: OutboundTypeUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundTypeService(db).update_type(type_id, payload))


@router.put(
    "/{type_id}/status",
    response_model=ApiResponse[OutboundTypeOut],
    summary="启用 / 停用外呼类型",
    description="停用后不可被新任务选择；历史任务已引用的类型不受影响。",
    dependencies=[Depends(require_permission("outbound:type:update"))],
)
def change_type_status(
    type_id: int, payload: CommonStatusChange, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundTypeService(db).set_status(type_id, payload.status))


@router.delete(
    "/{type_id}",
    response_model=ApiResponse[None],
    summary="删除外呼类型",
    description="存在子类型、或已被场景 / 任务引用时返回 40904。",
    dependencies=[Depends(require_permission("outbound:type:delete"))],
)
def delete_type(type_id: int, db: Session = Depends(get_db)) -> Any:
    OutboundTypeService(db).delete_type(type_id)
    return ok(None, message="删除成功")
