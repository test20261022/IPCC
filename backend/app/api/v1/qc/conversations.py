"""对话接口（对话质检-对话域）。

路径顺序：静态路径 /import、/import-batches 必须声明在 /{conversation_id} 之前，
否则会被路径参数吞掉导致 422。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_permission, tenant_scope_optional, tenant_scope_required
from app.core.response import ApiResponse, PageData, ok, page_data
from app.db.session import get_db
from app.models.qc.enums import ConversationChannel, ConversationSource, TranscriptStatus
from app.schemas.common import PageParams
from app.schemas.qc.conversation import (
    ConversationCreateIn,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdateIn,
    MessageOut,
    QcImportBatchOut,
    TranscribeResultOut,
)
from app.services.qc.conversation_import import QcConversationImportService
from app.services.qc.conversation_service import QcConversationService
from app.services.qc.transcribe_service import QcTranscribeService

router = APIRouter(prefix="/qc/conversations", tags=["质检-对话"])


@router.get(
    "",
    response_model=ApiResponse[PageData[ConversationOut]],
    summary="对话列表",
    description="支持按客服 / 渠道 / 来源 / 转写状态 / 时间区间与关键词筛选。",
    dependencies=[Depends(require_permission("qc:conversation:list"))],
)
def list_conversations(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    agent_name: str | None = Query(default=None, max_length=64, description="客服名称，模糊匹配"),
    channel: ConversationChannel | None = Query(default=None, description="对话渠道"),
    source: ConversationSource | None = Query(default=None, description="对话来源"),
    transcript_status: TranscriptStatus | None = Query(default=None, description="转写状态"),
    started_from: datetime | None = Query(
        default=None, description="对话开始时间下界（含），ISO8601"
    ),
    started_to: datetime | None = Query(
        default=None, description="对话开始时间上界（含），ISO8601"
    ),
    keyword: str | None = Query(
        default=None, max_length=64, description="ext_ref_no / customer_id / agent_name 模糊匹配"
    ),
    db: Session = Depends(get_db),
) -> Any:
    items, total = QcConversationService(db).list_conversations(
        page=page.page,
        page_size=page.page_size,
        tenant_id=tenant_id,
        agent_name=agent_name,
        channel=channel,
        source=source,
        transcript_status=transcript_status,
        started_from=started_from,
        started_to=started_to,
        keyword=keyword,
    )
    return ok(page_data(items, total, page.page, page.page_size))


@router.post(
    "",
    response_model=ApiResponse[ConversationOut],
    summary="新增对话",
    description="人工录入一条对话及其消息（来源固定为 MANUAL）。",
    dependencies=[Depends(require_permission("qc:conversation:create"))],
)
def create_conversation(payload: ConversationCreateIn, db: Session = Depends(get_db)) -> Any:
    return ok(QcConversationService(db).create_conversation(payload))


@router.post(
    "/import",
    response_model=ApiResponse[QcImportBatchOut],
    summary="导入对话",
    description=(
        "支持 .json / .txt / .xlsx 三种格式；同租户 ext_ref_no 已存在的对话按「已存在」"
        "计入失败明细且不中断整批。返回导入批次统计与失败明细。"
    ),
    dependencies=[Depends(require_permission("qc:conversation:import"))],
)
async def import_conversations(
    file: UploadFile = File(description=".json / .txt / .xlsx 对话文件"),
    tenant_id: int = Depends(tenant_scope_required),
    db: Session = Depends(get_db),
) -> Any:
    content = await file.read()
    batch = QcConversationImportService(db).import_file(
        tenant_id=tenant_id,
        filename=file.filename or "",
        content=content,
    )
    return ok(batch)


@router.get(
    "/import-batches",
    response_model=ApiResponse[PageData[QcImportBatchOut]],
    summary="导入批次列表",
    description="分页查询对话导入批次。",
    dependencies=[Depends(require_permission("qc:conversation:import"))],
)
def list_import_batches(
    page: PageParams = Depends(),
    tenant_id: int | None = Depends(tenant_scope_optional),
    db: Session = Depends(get_db),
) -> Any:
    items, total = QcConversationImportService(db).list_batches(
        page=page.page, page_size=page.page_size, tenant_id=tenant_id
    )
    return ok(page_data(items, total, page.page, page.page_size))


@router.get(
    "/{conversation_id}",
    response_model=ApiResponse[ConversationDetailOut],
    summary="对话详情",
    description="返回对话主表字段与全部消息（按 seq 升序）。",
    dependencies=[Depends(require_permission("qc:conversation:list"))],
)
def get_conversation(conversation_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcConversationService(db).get_detail(conversation_id))


@router.put(
    "/{conversation_id}",
    response_model=ApiResponse[ConversationOut],
    summary="编辑对话",
    description="只更新显式传入的字段；修改渠道或录音路径会重算转写状态。",
    dependencies=[Depends(require_permission("qc:conversation:update"))],
)
def update_conversation(
    conversation_id: int, payload: ConversationUpdateIn, db: Session = Depends(get_db)
) -> Any:
    return ok(QcConversationService(db).update_conversation(conversation_id, payload))


@router.delete(
    "/{conversation_id}",
    response_model=ApiResponse[None],
    summary="删除对话",
    description="被质检明细引用或已进入案例库的对话禁止删除。",
    dependencies=[Depends(require_permission("qc:conversation:delete"))],
)
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)) -> Any:
    QcConversationService(db).delete_conversation(conversation_id)
    return ok(None)


@router.get(
    "/{conversation_id}/messages",
    response_model=ApiResponse[list[MessageOut]],
    summary="对话消息列表",
    description="按 seq 升序返回对话的全部消息。",
    dependencies=[Depends(require_permission("qc:conversation:list"))],
)
def list_messages(conversation_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcConversationService(db).list_messages(conversation_id))


@router.post(
    "/{conversation_id}/transcribe",
    response_model=ApiResponse[TranscribeResultOut],
    summary="对话语音转写",
    description="仅语音对话可转写：清理旧 ASR 消息后写入新的分段消息，失败抛参数错误。",
    dependencies=[Depends(require_permission("qc:conversation:transcribe"))],
)
def transcribe_conversation(conversation_id: int, db: Session = Depends(get_db)) -> Any:
    return ok(QcTranscribeService(db).transcribe(conversation_id))