"""外呼场景接口（OB-003）。"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok
from app.db.session import get_db
from app.models.outbound.enums import CommonStatus
from app.schemas.common import PageParams
from app.schemas.outbound import (
    BatchDeleteResult,
    CommonStatusChange,
    OutboundSceneCreate,
    OutboundSceneOut,
    OutboundSceneTreeOut,
    OutboundSceneUpdate,
)
from app.services.outbound.common import build_page
from app.services.outbound.scene_service import OutboundSceneService

router = APIRouter(prefix="/outbound/scenes", tags=["外呼-场景"])


def _to_tree_node(node: dict) -> dict[str, Any]:
    """把 Service 的树节点转成响应结构。"""
    scene = node["scene"]
    payload = OutboundSceneOut.model_validate(scene).model_dump()
    payload["children"] = [_to_tree_node(child) for child in node["children"]]
    return payload


@router.get(
    "",
    response_model=ApiResponse[PageData[OutboundSceneOut]],
    summary="外呼场景列表",
    description="分页查询，支持名称 / 外呼类型 / 层级 / 父场景 / 状态筛选。",
    dependencies=[Depends(require_permission("outbound:scene:list"))],
)
def list_scenes(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    type_id: int | None = Query(default=None, gt=0, description="外呼类型"),
    parent_id: int | None = Query(default=None, gt=0, description="父场景"),
    name: str | None = Query(default=None, max_length=128, description="名称，模糊匹配"),
    level: int | None = Query(default=None, ge=1, le=2, description="层级：1 一级 / 2 二级"),
    status: CommonStatus | None = Query(default=None, description="状态"),
    db: Session = Depends(get_db),
) -> Any:
    service = OutboundSceneService(db)
    items, total = service.list_scenes(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        type_id=type_id,
        parent_id=parent_id,
        name=name,
        level=level,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.get(
    "/tree",
    response_model=ApiResponse[list[OutboundSceneTreeOut]],
    summary="外呼场景两级树",
    description="返回一级场景及其二级子场景，供下拉选择与树形展示使用。",
    dependencies=[Depends(require_permission("outbound:scene:list"))],
)
def scene_tree(
    tenant_id: int | None = Depends(tenant_scope_optional),
    type_id: int | None = Query(default=None, gt=0),
    status: CommonStatus | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Any:
    roots = OutboundSceneService(db).build_tree(
        tenant_id=tenant_id, type_id=type_id, status=status
    )
    return ok([_to_tree_node(node) for node in roots])


@router.post(
    "",
    response_model=ApiResponse[OutboundSceneOut],
    summary="新增外呼场景",
    description="选择外呼类型并输入一级 / 二级场景；二级场景必须指定同级类型下的一级父场景。",
    dependencies=[Depends(require_permission("outbound:scene:create"))],
)
def create_scene(payload: OutboundSceneCreate, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundSceneService(db).create_scene(payload))


@router.post(
    "/batch-delete",
    response_model=ApiResponse[BatchDeleteResult],
    summary="批量删除外呼场景",
    description="任一场景被外呼任务引用则整体拒绝并回显引用任务名称；删除一级场景会联动删除其二级场景。",
    dependencies=[Depends(require_permission("outbound:scene:delete"))],
)
def batch_delete_scenes(
    scene_ids: list[int] = Body(embed=True, description="待删除场景 ID 列表"),
    db: Session = Depends(get_db),
) -> Any:
    return ok(OutboundSceneService(db).batch_delete_scenes(scene_ids))


@router.get(
    "/{scene_id}",
    response_model=ApiResponse[OutboundSceneOut],
    summary="外呼场景详情",
    description="返回单个外呼场景的完整字段，供编辑表单回显。",
    dependencies=[Depends(require_permission("outbound:scene:list"))],
)
def get_scene(scene_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundSceneService(db).get_scene(scene_id))


@router.put(
    "/{scene_id}",
    response_model=ApiResponse[OutboundSceneOut],
    summary="编辑外呼场景",
    description="被外呼任务引用过的场景不可编辑，返回 40904。",
    dependencies=[Depends(require_permission("outbound:scene:update"))],
)
def update_scene(
    scene_id: int, payload: OutboundSceneUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundSceneService(db).update_scene(scene_id, payload))


@router.put(
    "/{scene_id}/status",
    response_model=ApiResponse[OutboundSceneOut],
    summary="启用 / 停用外呼场景",
    description="停用后不可被新任务选择；历史任务已引用的场景不受影响。",
    dependencies=[Depends(require_permission("outbound:scene:update"))],
)
def change_scene_status(
    scene_id: int, payload: CommonStatusChange, db: Session = Depends(get_db)
) -> Any:
    return ok(OutboundSceneService(db).set_status(scene_id, payload.status))


@router.delete(
    "/{scene_id}",
    response_model=ApiResponse[BatchDeleteResult],
    summary="删除外呼场景",
    description="删除一级场景会联动删除其下二级场景；被任务引用时返回 40904。",
    dependencies=[Depends(require_permission("outbound:scene:delete"))],
)
def delete_scene(scene_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundSceneService(db).delete_scene(scene_id))
