"""ASR（语音识别）Provider 抽象。

只返回纯文本会丢失说话人与时间戳，导致质检时无法区分"客服说了什么"与
"客户说了什么"。因此一期即固定 AsrSegment 契约，真实引擎按同一契约实现，
避免二期返工。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.qc.enums import MessageRole


@dataclass(frozen=True)
class AsrSegment:
    """一段转写结果。"""

    role: MessageRole
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


class AsrProvider(ABC):
    """录音转写。"""

    name: str = "base"

    @abstractmethod
    async def transcribe_segments(self, *, audio_path: str) -> list[AsrSegment]:
        """返回分段转写结果（无内容时返回空列表）。"""

    async def transcribe(self, *, audio_path: str) -> str:
        """整体文本：默认由分段结果拼接，子类一般无需重写。"""
        segments = await self.transcribe_segments(audio_path=audio_path)
        return "\n".join(segment.text for segment in segments if segment.text)


__all__ = ["AsrProvider", "AsrSegment"]