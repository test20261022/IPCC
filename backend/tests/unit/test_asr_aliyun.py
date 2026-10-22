"""模拟阿里云 ASR Provider 单元测试（演示引擎须确定、可复现）。"""

import asyncio

import pytest

from app.models.qc.enums import MessageRole
from app.providers.asr.aliyun import AliyunAsrProvider
from app.utils.async_bridge import run_sync


@pytest.fixture(autouse=True)
def _no_poll_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """去掉模拟轮询延时，保证用例秒级完成。"""

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant)


class TestAliyunAsrProvider:
    def test_segments_deterministic_with_roles_and_timestamps(self) -> None:
        provider = AliyunAsrProvider()
        first = run_sync(provider.transcribe_segments(audio_path="qc_recordings/a.mp3"))
        second = run_sync(provider.transcribe_segments(audio_path="qc_recordings/a.mp3"))
        assert first == second  # 同一录音重复转写结果一致（幂等可演示）
        assert first
        assert first[0].start_ms == 0
        for segment in first:
            assert segment.role in {MessageRole.AGENT, MessageRole.CUSTOMER}
            assert segment.start_ms is not None and segment.end_ms is not None
            assert segment.end_ms > segment.start_ms

    def test_fail_switch_raises(self) -> None:
        with pytest.raises(RuntimeError):
            run_sync(
                AliyunAsrProvider().transcribe_segments(audio_path="qc_recordings/x_fail.mp3")
            )

    def test_mono_switch_degrades_to_single_system_segment(self) -> None:
        segments = run_sync(
            AliyunAsrProvider().transcribe_segments(audio_path="qc_recordings/x_mono.mp3")
        )
        assert len(segments) == 1
        assert segments[0].role is MessageRole.SYSTEM