"""质检执行域接口（质检-执行）：我的工作台、领取 / 释放 / 提交。"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.response import ApiResponse, PageData, ok, page_data
from app.db.session import get_db
from app.models.qc.enums import QcItemStatus
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.qc.review import (
    QcItemDetailOut,
    QcItemSubmitRequest,
    QcItemSubmitResult,
    QcTaskItemOut,
)
from app.services.qc.review_service import QcReviewService

router = APIRouter(prefix="/qc", tags=["质检-执行"])


@router.get(
    "/my/items",
    response_model=ApiResponse[PageData[QcTaskItemOut]],
    summary="我的质检明细",
    description=(
        "以当前登录用户作为质检人过滤；不需要 tenant_id 参数，"
        "若当前用户已绑定租户则同时按该租户收敛可见范围。"
    ),
    dependencies=[Depends(require_permission("qc:review:work"))],
)
def list_my_items(
    page: PageParams = Depends(),
    status: QcItemStatus | None = Query(default=None, description="明细状态"),
    current_user: User = Depends(require_permission("qc:review:work")),
    db: Session = Depends(get_db),
) -> Any:
    items, total = QcReviewService(db).list_my_items(
        current_user=current_user,
        page=page.page,
        page_size=page.page_size,
        status=status,
    )
    return ok(page_data(items, total, page.page, page.page_size))


@router.get(
    "/items/{item_id}",
    response_model=ApiResponse[QcItemDetailOut],
    summary="质检明细详情",
    description="返回明细、被质检对话与对话消息（按 seq 升序）。",
    dependencies=[Depends(require_permission("qc:review:work"))],
)
def get_item_detail(
    item_id: int,
    current_user: User = Depends(require_permission("qc:review:work")),
    db: Session = Depends(get_db),
) -> Any:
    return ok(QcReviewService(db).get_item_detail(item_id, current_user))


@router.post(
    "/items/{item_id}/claim",
    response_model=ApiResponse[QcTaskItemOut],
    summary="领取质检明细",
    description="乐观锁领取：仅 PENDING 可领取，写入锁定与超时时间；已被领取返回 40902。",
    dependencies=[Depends(require_permission("qc:review:work"))],
)
def claim_item(
    item_id: int,
    current_user: User = Depends(require_permission("qc:review:work")),
    db: Session = Depends(get_db),
) -> Any:
    return ok(QcReviewService(db).claim(item_id, current_user))


@router.post(
    "/items/{item_id}/release",
    response_model=ApiResponse[QcTaskItemOut],
    summary="释放质检明细",
    description="仅本人持有的质检中明细可释放回待质检。",
    dependencies=[Depends(require_permission("qc:review:work"))],
)
def release_item(
    item_id: int,
    current_user: User = Depends(require_permission("qc:review:work")),
    db: Session = Depends(get_db),
) -> Any:
    return ok(QcReviewService(db).release(item_id, current_user))


@router.post(
    "/items/{item_id}/submit",
    response_model=ApiResponse[QcItemSubmitResult],
    summary="提交质检结果",
    description=(
        "仅本人持有的质检中明细可提交；等级由得分按配置阈值判定，不接受直传；"
        "重复提交由唯一索引兜底返回 40902。"
    ),
    dependencies=[Depends(require_permission("qc:review:submit"))],
)
def submit_item(
    item_id: int,
    payload: QcItemSubmitRequest,
    current_user: User = Depends(require_permission("qc:review:submit")),
    db: Session = Depends(get_db),
) -> Any:
    return ok(QcReviewService(db).submit(item_id, current_user, payload))