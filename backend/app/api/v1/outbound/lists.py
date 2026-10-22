"""名单接口（OB-011 名单导入 / OB-012 全场景变量）。"""

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional
from app.core.response import ApiResponse, PageData, ok
from app.db.session import get_db
from app.models.outbound.enums import ImportBatchStatus, ListStatus
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.outbound.name_list import (
    OutboundImportBatchDetailOut,
    OutboundImportBatchOut,
    OutboundImportResultOut,
    OutboundListOut,
    OutboundVariableOut,
)
from app.services.outbound.common import build_page
from app.services.outbound.list_service import OutboundListService

router = APIRouter(prefix="/outbound", tags=["外呼-名单"])


@router.post(
    "/lists/import",
    response_model=ApiResponse[OutboundImportResultOut],
    summary="导入外呼名单",
    description=(
        "支持 .xlsx / .csv；支持动态表头（非核心列全部落到动态字段）与多号码列。"
        "返回总行数 / 成功数 / 失败数与失败明细（行号、字段、原因、原始值）。"
        "同一任务下 (UserID, OrderID) 已存在的行按「重复导入」计入失败，不重复落库。"
    ),
)
async def import_lists(
    task_id: int = Form(gt=0, description="导入到哪个外呼任务"),
    file: UploadFile = File(description=".xlsx 或 .csv 名单文件"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("outbound:list:import")),
) -> Any:
    content = await file.read()
    result = OutboundListService(db).import_file(
        task_id=task_id,
        filename=file.filename or "",
        content=content,
        operator_id=current_user.id,
    )
    return ok(result)


@router.get(
    "/lists",
    response_model=ApiResponse[PageData[OutboundListOut]],
    summary="外呼名单列表",
    description="支持按任务、UserID、OrderID、导入批次、状态筛选。",
    dependencies=[Depends(require_permission("outbound:list:list"))],
)
def list_lists(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    task_id: int | None = Query(default=None, gt=0, description="外呼任务"),
    user_id: str | None = Query(default=None, max_length=64, description="业务 UserID"),
    order_id: str | None = Query(default=None, max_length=64, description="业务 OrderID"),
    import_batch_id: int | None = Query(default=None, gt=0, description="导入批次"),
    status: ListStatus | None = Query(default=None, description="名单状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundListService(db).list_lists(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        task_id=task_id,
        user_id=user_id,
        order_id=order_id,
        import_batch_id=import_batch_id,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.get(
    "/lists/{list_id}",
    response_model=ApiResponse[OutboundListOut],
    summary="名单详情",
    description="返回名单行详情，含被叫号码列表与导入的动态字段。",
    dependencies=[Depends(require_permission("outbound:list:list"))],
)
def get_list(list_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(OutboundListService(db).get_list(list_id))


@router.get(
    "/lists/{list_id}/variables",
    response_model=ApiResponse[OutboundVariableOut],
    summary="名单全场景变量",
    description=(
        "OB-012：合并名单字段、任务配置、类型 / 场景 / 站点信息，输出可直接用于话术、"
        "IVR、ASR/TTS、短信与服务小结的变量字典；名单动态字段平铺追加，不覆盖系统保留键。"
    ),
    dependencies=[Depends(require_permission("outbound:list:variable"))],
)
def get_list_variables(list_id: int, db: Session = Depends(get_db)) -> Any:
    return ok({"variables": OutboundListService(db).resolve_variables(list_id)})


@router.get(
    "/import-batches",
    response_model=ApiResponse[PageData[OutboundImportBatchOut]],
    summary="导入批次列表",
    description="分页查询名单导入批次，支持按任务 / 状态 / 租户筛选（OB-011）。",
    dependencies=[Depends(require_permission("outbound:list:list"))],
)
def list_batches(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    task_id: int | None = Query(default=None, gt=0, description="外呼任务"),
    status: ImportBatchStatus | None = Query(default=None, description="导入状态"),
    db: Session = Depends(get_db),
) -> Any:
    items, total = OutboundListService(db).list_batches(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        task_id=task_id,
        status=status,
    )
    return ok(build_page(items, total, page.page, page.page_size))


@router.get(
    "/import-batches/{batch_id}",
    response_model=ApiResponse[OutboundImportBatchDetailOut],
    summary="导入批次详情",
    description="返回导入统计与失败明细（明细超过上限时截断，计数以 failed_rows 为准）。",
    dependencies=[Depends(require_permission("outbound:list:list"))],
)
def get_batch(batch_id: int, db: Session = Depends(get_db)) -> Any:
    batch = OutboundListService(db).get_batch(batch_id)
    payload = OutboundImportBatchOut.model_validate(batch).model_dump()
    payload["failures"] = batch.failed_detail or []
    return ok(payload)


@router.get(
    "/import-batches/{batch_id}/failures/download",
    summary="下载失败明细 CSV",
    description="§25：把失败明细导出为 CSV（带 BOM，Excel 打开不乱码）。",
    dependencies=[Depends(require_permission("outbound:list:list"))],
    response_class=Response,
)
def download_failures(batch_id: int, db: Session = Depends(get_db)) -> Response:
    filename, content = OutboundListService(db).export_failures(batch_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
