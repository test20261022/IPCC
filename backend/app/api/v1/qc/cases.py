"""优秀案例库接口（对话质检-案例库）。"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok, page_data
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.qc.case import CaseCreateIn, CaseOut, CaseUpdateIn
from app.services.qc.case_service import QcCaseLibraryService

router = APIRouter(prefix="/qc/cases", tags=["质检-案例库"])


@router.get(
    "",
    response_model=ApiResponse[PageData[CaseOut]],
    summary="优秀案例列表",
    description="支持按发布状态 / 标签 / 关键词筛选。",
    dependencies=[Depends(require_permission("qc:case:list"))],
)
def list_cases(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    is_published: bool | None = Query(default=None, description="是否已发布为模板"),
    tag: str | None = Query(default=None, max_length=32, description="标签"),
    keyword: str | None = Query(default=None, max_length=64, description="标题 / 理由模糊匹配"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = QcCaseLibraryService(db).list_cases(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        is_published=is_published,
        tag=tag,
        keyword=keyword,
    )
    return ok(page_data(items, total, page.page, page.page_size))


@router.post(
    "",
    response_model=ApiResponse[CaseOut],
    summary="新增优秀案例",
    description="把一条对话沉淀为案例；同一对话重复入选抛数据冲突。",
)
def create_case(
    payload: CaseCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("qc:case:create")),
) -> Any:
    return ok(QcCaseLibraryService(db).create_case(payload, created_by=current_user.id))


@router.get(
    "/{case_id}",
    response_model=ApiResponse[CaseOut],
    summary="优秀案例详情",
    dependencies=[Depends(require_permission("qc:case:list"))],
)
def get_case(case_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcCaseLibraryService(db).get_case(case_id))


@router.put(
    "/{case_id}",
    response_model=ApiResponse[CaseOut],
    summary="编辑优秀案例",
    description="只更新显式传入的字段。",
    dependencies=[Depends(require_permission("qc:case:update"))],
)
def update_case(
    case_id: int, payload: CaseUpdateIn, db: Session = Depends(get_db)
) -> Any:
    return ok(QcCaseLibraryService(db).update_case(case_id, payload))


@router.delete(
    "/{case_id}",
    response_model=ApiResponse[None],
    summary="删除优秀案例",
    dependencies=[Depends(require_permission("qc:case:delete"))],
)
def delete_case(case_id: int, db: Session = Depends(get_db)) -> Any:
    QcCaseLibraryService(db).delete_case(case_id)
    return ok(None)


@router.post(
    "/{case_id}/publish",
    response_model=ApiResponse[CaseOut],
    summary="发布优秀案例",
    description="置 is_published=True 并记录发布时间（重复发布幂等）。",
    dependencies=[Depends(require_permission("qc:case:publish"))],
)
def publish_case(case_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcCaseLibraryService(db).publish_case(case_id))