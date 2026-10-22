"""TTS（语音合成）Provider 抽象。"""

from abc import ABC, abstractmethod


class TtsProvider(ABC):
    """文本转语音。"""

    name: str = "base"

    @abstractmethod
    async def synthesize(self, *, text: str) -> str:
        """返回合成音频的存储路径。"""
