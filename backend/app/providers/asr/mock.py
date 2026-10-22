"""Mock ASR Provider（§30）：不解析真实音频，返回固定剧本的分段转写结果。

一期只要求跑通「录音 → 转写文本 → 质检」链路，故转写内容为确定性假数据，
便于前端联调与测试复现；真实引擎按 ASR_PROVIDER 配置切换。
"""

from app.models.qc.enums import MessageRole
from app.providers.asr.base import AsrProvider, AsrSegment

#: 固定剧本：(说话人, 文本, 时长毫秒)
_SCRIPT: tuple[tuple[MessageRole, str, int], ...] = (
    (MessageRole.AGENT, "您好，很高兴为您服务，请问有什么可以帮您？", 3000),
    (MessageRole.CUSTOMER, "你好，我想咨询一下我下单的商品什么时候发货。", 4000),
    (MessageRole.AGENT, "好的，我帮您查询一下订单状态，请您稍等。", 3500),
    (MessageRole.AGENT, "已经查到，您的订单预计明天上午发出，物流单号稍后短信通知您。", 6000),
    (MessageRole.CUSTOMER, "好的，谢谢。", 1500),
    (MessageRole.AGENT, "不客气，还有其他可以帮您的吗？", 2500),
)


class MockAsrProvider(AsrProvider):
    """返回固定剧本的分段转写结果。"""

    name = "mock"

    async def transcribe_segments(self, *, audio_path: str) -> list[AsrSegment]:
        cursor = 0
        segments: list[AsrSegment] = []
        for role, text, duration_ms in _SCRIPT:
            segments.append(
                AsrSegment(
                    role=role,
                    text=text,
                    start_ms=cursor,
                    end_ms=cursor + duration_ms,
                )
            )
            cursor += duration_ms
        return segments


__all__ = ["MockAsrProvider"]