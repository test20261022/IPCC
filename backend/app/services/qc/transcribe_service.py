"""对话语音转写服务：调用 ASR Provider 把录音转成分段消息写回对话。

仅语音对话（channel=VOICE 且有录音路径）可转写；转写成功写回消息并置 SUCCESS，
失败置 FAILED 并抛出 ParamError（消息中带原因）。
"""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, ParamError
from app.models.qc import QcConversation
from app.models.qc.enums import ConversationChannel, MessageSource, TranscriptStatus
from app.providers.asr.base import AsrSegment
from app.providers.factory import get_asr_provider
from app.repositories.qc.conversation_repository import QcConversationRepository
from app.utils.async_bridge import run_sync
from app.utils.storage import absolute_path

logger = logging.getLogger(__name__)


class QcTranscribeService:
    """语音对话转写。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = QcConversationRepository(db)

    def transcribe(self, conversation_id: int) -> dict[str, object]:
        conversation = self.repo.get_by_id(conversation_id)
        if conversation is None:
            raise NotFound("对话不存在")
        if conversation.channel != ConversationChannel.VOICE:
            raise ParamError("仅语音对话支持转写")
        if not conversation.recording_path:
            raise ParamError("对话没有录音文件，无法转写")

        conversation.transcript_status = TranscriptStatus.RUNNING
        self.db.commit()

        provider = get_asr_provider()
        try:
            segments = run_sync(
                provider.transcribe_segments(
                    audio_path=str(absolute_path(conversation.recording_path))
                )
            )
        except Exception as exc:  # noqa: BLE001 - 统一转成业务错误
            conversation.transcript_status = TranscriptStatus.FAILED
            self.db.commit()
            logger.exception("对话转写失败：conversation=%s", conversation_id)
            raise ParamError(f"语音转写失败：{exc}") from exc

        self._rewrite_asr_messages(conversation, segments)
        conversation.transcript_status = TranscriptStatus.SUCCESS
        conversation.transcript_engine = provider.name
        self.db.commit()

        logger.info(
            "对话转写完成：conversation=%s 引擎=%s 消息=%s",
            conversation_id,
            provider.name,
            conversation.msg_count,
        )
        return {
            "conversation_id": conversation_id,
            "transcript_status": conversation.transcript_status,
            "transcript_engine": conversation.transcript_engine,
            "message_count": conversation.msg_count,
        }

    def _rewrite_asr_messages(
        self, conversation: QcConversation, segments: list[AsrSegment]
    ) -> None:
        """删除旧的 ASR 消息后，按 seq 顺序写入新的转写消息。"""
        self.repo.delete_messages_by_source(conversation.id, MessageSource.ASR)
        base_seq = self.repo.max_message_seq(conversation.id)

        values = [
            {
                "tenant_id": conversation.tenant_id,
                "conversation_id": conversation.id,
                "seq": base_seq + index,
                "role": segment.role,
                "content": segment.text,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "source": MessageSource.ASR,
            }
            for index, segment in enumerate(segments, start=1)
        ]
        self.repo.bulk_insert_messages(values)
        conversation.msg_count = self.repo.count_messages(conversation.id)


__all__ = ["QcTranscribeService"]