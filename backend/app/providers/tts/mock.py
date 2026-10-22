"""Mock TTS Provider（§30）：返回确定性的音频路径，不生成真实音频。"""

import hashlib

from app.providers.tts.base import TtsProvider


class MockTtsProvider(TtsProvider):
    name = "mock"

    async def synthesize(self, *, text: str) -> str:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        return f"mock/tts/{digest}.wav"
