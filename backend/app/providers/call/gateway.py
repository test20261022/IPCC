"""真实呼叫网关 Provider（httpx + 超时 / 重试 / 日志，§69）。

未配置 CALL_GATEWAY_URL 时直接报错。网关返回体约定：
    {"call_id": "...", "status": "CONNECTED|NO_ANSWER|BUSY|REJECTED|FAILED",
     "duration": 30, "reason": "...", "recording_path": "..."}
"""

import asyncio
import logging
from typing import Any

import httpx

from app.core.exceptions import AppException
from app.models.outbound.enums import CallStatus
from app.providers.call.base import CallGatewayProvider, CallResult

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "CONNECTED": CallStatus.CONNECTED,
    "INITIATED": CallStatus.INITIATED,
    "RINGING": CallStatus.RINGING,
    "NO_ANSWER": CallStatus.NO_ANSWER,
    "BUSY": CallStatus.BUSY,
    "REJECTED": CallStatus.REJECTED,
    "FAILED": CallStatus.FAILED,
    "TIMEOUT": CallStatus.TIMEOUT,
    "HANGUP": CallStatus.HANGUP,
}


class GatewayCallProvider(CallGatewayProvider):
    name = "gateway"

    def __init__(
        self, *, base_url: str, api_key: str, timeout: int, max_retries: int
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    async def make_call(
        self,
        *,
        phone: str,
        agent_id: int | None = None,
        session_id: int | None = None,
    ) -> CallResult:
        if not self.base_url:
            raise AppException("未配置 CALL_GATEWAY_URL，无法发起呼叫")

        payload = {"phone": phone, "agent_id": agent_id, "session_id": session_id}
        headers = {"X-Api-Key": self.api_key} if self.api_key else {}

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/calls", json=payload, headers=headers
                    )
                response.raise_for_status()
                data: Any = response.json()
                return self._to_result(data if isinstance(data, dict) else {})
            except Exception as exc:  # noqa: BLE001 - 统一重试与降级
                last_error = exc
                logger.warning(
                    "呼叫网关调用失败（第 %s 次）：phone=%s err=%s", attempt, phone, exc
                )
                if attempt <= self.max_retries:
                    await asyncio.sleep(min(0.5 * attempt, 2))

        return CallResult(
            success=False,
            call_status=CallStatus.FAILED,
            failure_reason=f"呼叫网关调用失败：{last_error}",
        )

    @staticmethod
    def _to_result(data: dict[str, Any]) -> CallResult:
        status = _STATUS_MAP.get(str(data.get("status", "")).upper(), CallStatus.FAILED)
        return CallResult(
            success=status == CallStatus.CONNECTED,
            call_status=status,
            provider_call_id=data.get("call_id"),
            duration=int(data.get("duration") or 0),
            failure_reason=data.get("reason"),
            recording_path=data.get("recording_path"),
        )
