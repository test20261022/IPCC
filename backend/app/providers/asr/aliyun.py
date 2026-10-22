"""模拟阿里云 ASR Provider（演示用，不发起任何真实请求）。

模拟阿里云智能语音交互「录音文件识别」的调用形态：提交任务 → 轮询结果 →
返回「说话人 + 文本 + 起止时间戳」的分段结果。真实接入时只需把
_submit_task / _poll_result 换成对阿里云 OpenAPI 的 HTTP 调用，
分段契约（AsrSegment）与日志、异常语义完全复用。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid

from app.core.config import settings
from app.models.qc.enums import MessageRole
from app.providers.asr.base import AsrProvider, AsrSegment

logger = logging.getLogger(__name__)

#: 台词本：(说话人, 文本, 时长毫秒)，模拟带说话人分离与时间戳的识别结果
_SCRIPTS: dict[str, tuple[tuple[MessageRole, str, int], ...]] = {
    "物流咨询": (
        (MessageRole.AGENT, "您好，很高兴为您服务，请问有什么可以帮您？", 3000),
        (MessageRole.CUSTOMER, "你好，我下单的商品什么时候能发货？", 4000),
        (MessageRole.AGENT, "好的，我帮您查一下订单状态，请您稍等。", 3500),
        (MessageRole.AGENT, "已查到，预计明天上午发出，物流单号稍后短信通知您。", 6000),
        (MessageRole.CUSTOMER, "好的，谢谢。", 1500),
        (MessageRole.AGENT, "不客气，还有其他可以帮您的吗？", 2500),
    ),
    "退款工单": (
        (MessageRole.AGENT, "您好，工号1024为您服务。", 2500),
        (MessageRole.CUSTOMER, "我要退款，收到的商品有破损。", 4500),
        (MessageRole.AGENT, "非常抱歉给您带来不便，我先核实一下您的订单号。", 5000),
        (MessageRole.CUSTOMER, "订单号是20241006001。", 3000),
        (MessageRole.AGENT, "已登记退款工单，预计3个工作日原路退回，请留意到账。", 6000),
    ),
    "宽带报修": (
        (MessageRole.AGENT, "您好，请问有什么可以帮您？", 2500),
        (MessageRole.CUSTOMER, "家里宽带上不去了，光猫一直闪红灯。", 4000),
        (MessageRole.AGENT, "请问您重启过光猫吗？", 2500),
        (MessageRole.CUSTOMER, "重启过了，还是不行。", 2500),
        (MessageRole.AGENT, "好的，我为您预约师傅上门，明天下午两点可以吗？", 5000),
        (MessageRole.CUSTOMER, "可以，谢谢。", 1500),
    ),
}


class AliyunAsrProvider(AsrProvider):
    """模拟阿里云录音文件识别（演示用，不发起真实请求）。

    演示开关（看录音路径即可）：
    - 路径含 ``_fail``：模拟识别失败，抛异常以演示 FAILED 状态；
    - 路径含 ``_mono``：模拟单声道无说话人分离，降级为单段 SYSTEM 消息。
    """

    name = "aliyun"

    async def transcribe_segments(self, *, audio_path: str) -> list[AsrSegment]:
        if "_fail" in audio_path:
            raise RuntimeError("阿里云识别失败：音频格式不支持（StatusCode=41050001）")

        task_id = await self._submit_task(audio_path)
        await self._poll_result(task_id)

        script = _SCRIPTS[self._pick_script(audio_path)]
        segments: list[AsrSegment] = []
        cursor = 0
        for role, text, duration_ms in script:
            segments.append(
                AsrSegment(role=role, text=text, start_ms=cursor, end_ms=cursor + duration_ms)
            )
            cursor += duration_ms

        if "_mono" in audio_path:
            merged = "".join(segment.text for segment in segments)
            return [AsrSegment(role=MessageRole.SYSTEM, text=merged, start_ms=0, end_ms=cursor)]
        return segments

    async def _submit_task(self, audio_path: str) -> str:
        """模拟「提交录音文件识别任务」并返回 TaskId。"""
        task_id = f"aliyun-asr-{uuid.uuid4().hex[:16]}"
        logger.info(
            "提交阿里云录音文件识别任务 taskId=%s 文件=%s appKey=%s",
            task_id,
            audio_path,
            settings.ASR_PROVIDER_API_KEY or "(未配置)",
        )
        await asyncio.sleep(0.3)  # 模拟网络往返
        return task_id

    async def _poll_result(self, task_id: str) -> None:
        """模拟「轮询识别结果」：两次 RUNNING 后 SUCCESS。"""
        for status in ("RUNNING", "RUNNING", "SUCCESS"):
            logger.info("轮询阿里云识别结果 taskId=%s status=%s", task_id, status)
            await asyncio.sleep(0.4)

    @staticmethod
    def _pick_script(audio_path: str) -> str:
        """按录音路径哈希选台词本：同一对话重复转写结果一致（便于演示幂等）。"""
        keys = sorted(_SCRIPTS)
        digest = hashlib.md5(audio_path.encode("utf-8")).hexdigest()
        return keys[int(digest, 16) % len(keys)]


__all__ = ["AliyunAsrProvider"]