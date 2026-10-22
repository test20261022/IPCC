"""对话域服务：人工录入 / 编辑 / 删除 / 详情 / 消息读取。

删除保护（§）：对话一旦被质检明细引用或已进入案例库，即禁止删除，
避免质检结果与案例模板出现悬挂引用（数据库外键亦为 RESTRICT 兜底）。
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, StateNotAllowed
from app.models.qc import QcConversation, QcMessage
from app.models.qc.enums import (
    ConversationChannel,
    ConversationSource,
    MessageSource,
    TranscriptStatus,
)
from app.repositories.qc.conversation_repository import QcConversationRepository
from app.schemas.qc.conversation import (
    ConversationCreateIn,
    ConversationOut,
    ConversationUpdateIn,
    MessageOut,
)

logger = logging.getLogger(__name__)


class QcConversationService:
    """对话业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = QcConversationRepository(db)

    # ---------- 查询 ----------

    def list_conversations(
        self, *, page: int, page_size: int, **filters: object
    ) -> tuple[list[QcConversation], int]:
        items = self.repo.list_paged(page=page, page_size=page_size, **filters)
        total = self.repo.count(**filters)
        return items, total

    def get_conversation(self, conversation_id: int) -> QcConversation:
        conversation = self.repo.get_by_id(conversation_id)
        if conversation is None:
            raise NotFound("对话不存在")
        return conversation

    def get_detail(self, conversation_id: int) -> dict[str, Any]:
        """对话详情：主表字段 + 消息（按 seq 升序）。"""
        conversation = self.get_conversation(conversation_id)
        messages = self.repo.list_messages(conversation_id)
        data = ConversationOut.model_validate(conversation).model_dump()
        data["messages"] = [MessageOut.model_validate(message) for message in messages]
        return data

    def list_messages(self, conversation_id: int) -> list[QcMessage]:
        self.get_conversation(conversation_id)
        return self.repo.list_messages(conversation_id)

    # ---------- 新增 ----------

    def create_conversation(self, payload: ConversationCreateIn) -> QcConversation:
        """人工录入对话：主表 + 消息一次写入，seq 按入参顺序从 1 开始。"""
        data = payload.model_dump(exclude={"messages"})
        conversation = self.repo.create(
            **data,
            source=ConversationSource.MANUAL,
            transcript_status=self._initial_transcript_status(payload),
            msg_count=len(payload.messages),
        )
        self._insert_messages(conversation, payload, MessageSource.TEXT)
        self.db.commit()
        logger.info(
            "创建对话成功：id=%s tenant=%s 消息=%s",
            conversation.id,
            conversation.tenant_id,
            len(payload.messages),
        )
        return conversation

    # ---------- 编辑 ----------

    def update_conversation(
        self, conversation_id: int, payload: ConversationUpdateIn
    ) -> QcConversation:
        conversation = self.get_conversation(conversation_id)
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(conversation, field, value)
        # 录音路径 / 渠道变化后重算转写状态（纯文本无需转写）
        if "recording_path" in changes or "channel" in changes:
            conversation.transcript_status = self._resolve_transcript_status(
                conversation.channel, conversation.recording_path
            )
        self.db.commit()
        logger.info("更新对话成功：id=%s fields=%s", conversation_id, sorted(changes))
        return conversation

    # ---------- 删除 ----------

    def delete_conversation(self, conversation_id: int) -> None:
        conversation = self.get_conversation(conversation_id)
        if self.repo.count_task_items(conversation_id) > 0 or (
            self.repo.count_case_references(conversation_id) > 0
        ):
            raise StateNotAllowed("对话已被质检引用，禁止删除")
        conversation.mark_deleted()
        self.db.commit()
        logger.info("删除对话成功：id=%s", conversation_id)

    # ---------- 内部 ----------

    @staticmethod
    def _resolve_transcript_status(
        channel: ConversationChannel, recording_path: str | None
    ) -> TranscriptStatus:
        """有录音的语音对话需要转写，其余（纯文本）无需转写。"""
        if channel == ConversationChannel.VOICE and recording_path:
            return TranscriptStatus.PENDING
        return TranscriptStatus.NOT_REQUIRED

    def _initial_transcript_status(self, payload: ConversationCreateIn) -> TranscriptStatus:
        return self._resolve_transcript_status(payload.channel, payload.recording_path)

    def _insert_messages(
        self,
        conversation: QcConversation,
        payload: ConversationCreateIn,
        source: MessageSource,
    ) -> None:
        if not payload.messages:
            return
        values = [
            {
                "tenant_id": conversation.tenant_id,
                "conversation_id": conversation.id,
                "seq": seq,
                "role": message.role,
                "content": message.content,
                "start_ms": message.start_ms,
                "end_ms": message.end_ms,
                "source": source,
            }
            for seq, message in enumerate(payload.messages, start=1)
        ]
        self.repo.bulk_insert_messages(values)


__all__ = ["QcConversationService"]