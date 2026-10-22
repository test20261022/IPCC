"""专家组接口（质检-专家组）。"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok, page_data
from app.db.session import get_db
from app.schemas.common import PageParams
from app.schemas.qc.review import (
    ReviewerGroupCreate,
    ReviewerGroupDetailOut,
    ReviewerGroupMembersUpdate,
    ReviewerGroupOut,
    ReviewerGroupUpdate,
    ReviewerUserOut,
)
from app.services.qc.reviewer_service import QcReviewerService

router = APIRouter(prefix="/qc", tags=["质检-专家组"])


@router.get(
    "/reviewers",
    response_model=ApiResponse[PageData[ReviewerUserOut]],
    summary="可入组专家列表",
    description="从 users 表中挑选可加入专家组的用户（启用且未删除），支持用户名 / 昵称模糊匹配。",
    dependencies=[Depends(require_permission("qc:reviewer:list"))],
)
def list_assignable_reviewers(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    keyword: str | None = Query(default=None, max_length=64, description="用户名 / 昵称模糊匹配"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = QcReviewerService(db).list_assignable_users(
        page=page.page, page_size=page.page_size, tenant_id=tenant_id, keyword=keyword
    )
    return ok(page_data(items, total, page.page, page.page_size))


@router.get(
    "/reviewer-groups",
    response_model=ApiResponse[PageData[ReviewerGroupOut]],
    summary="专家组列表",
    description="分页返回专家组，并附带 member_count（未删除的成员数）。",
    dependencies=[Depends(require_permission("qc:reviewer:list"))],
)
def list_reviewer_groups(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    keyword: str | None = Query(default=None, max_length=128, description="组名模糊匹配"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = QcReviewerService(db).list_groups(
        page=page.page, page_size=page.page_size, tenant_id=tenant_id, keyword=keyword
    )
    return ok(page_data(items, total, page.page, page.page_size))


@router.post(
    "/reviewer-groups",
    response_model=ApiResponse[ReviewerGroupOut],
    summary="新增专家组",
    description="同租户下组名唯一；可在创建时直接指定初始成员。",
    dependencies=[Depends(require_permission("qc:reviewer:create"))],
)
def create_reviewer_group(payload: ReviewerGroupCreate, db: Session = Depends(get_db)) -> Any:
    return ok(QcReviewerService(db).create_group(payload))


@router.get(
    "/reviewer-groups/{group_id}",
    response_model=ApiResponse[ReviewerGroupDetailOut],
    summary="专家组详情",
    description="返回组信息与成员列表（含用户 username / nickname）。",
    dependencies=[Depends(require_permission("qc:reviewer:list"))],
)
def get_reviewer_group(group_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcReviewerService(db).get_group_detail(group_id))


@router.put(
    "/reviewer-groups/{group_id}",
    response_model=ApiResponse[ReviewerGroupOut],
    summary="编辑专家组",
    description="仅更新显式传入的字段；组名唯一。",
    dependencies=[Depends(require_permission("qc:reviewer:update"))],
)
def update_reviewer_group(
    group_id: int, payload: ReviewerGroupUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(QcReviewerService(db).update_group(group_id, payload))


@router.put(
    "/reviewer-groups/{group_id}/members",
    response_model=ApiResponse[ReviewerGroupDetailOut],
    summary="全量覆盖专家组成员",
    description=(
        "传入即全量覆盖：未出现在列表中的成员会被移除；"
        "max_concurrent 为空时使用默认单轮额度（QC_DEFAULT_QUOTA_PER_REVIEWER）。"
    ),
    dependencies=[Depends(require_permission("qc:reviewer:update"))],
)
def replace_reviewer_group_members(
    group_id: int, payload: ReviewerGroupMembersUpdate, db: Session = Depends(get_db)
) -> Any:
    return ok(QcReviewerService(db).replace_members(group_id, payload))