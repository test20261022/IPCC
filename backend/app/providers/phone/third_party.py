"""真实第三方号码查询 Provider（httpx + 超时 / 重试 / 日志，§69）。

未配置 PHONE_PROVIDER_URL 时直接报错，避免「静默降级成 mock」导致线上误判。
"""

import asyncio
import logging
from typing import Any

import httpx

from app.core.exceptions import AppException
from app.providers.phone.base import PhoneProvider

logger = logging.getLogger(__name__)


class ThirdPartyPhoneProvider(PhoneProvider):
    name = "third_party"

    def __init__(
        self, *, base_url: str, api_key: str, timeout: int, max_retries: int
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    async def get_user_phones(
        self,
        *,
        user_id: str | None = None,
        order_id: str | None = None,
    ) -> list[str]:
        if not self.base_url:
            raise AppException("未配置 PHONE_PROVIDER_URL，无法调用第三方号码查询")

        payload = {"user_id": user_id, "order_id": order_id}
        headers = {"X-Api-Key": self.api_key} if self.api_key else {}

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/phones", json=payload, headers=headers
                    )
                response.raise_for_status()
                data: Any = response.json()
                phones = data.get("phones") if isinstance(data, dict) else None
                return [str(item) for item in phones] if isinstance(phones, list) else []
            except Exception as exc:  # noqa: BLE001 - 统一重试与降级
                last_error = exc
                logger.warning(
                    "第三方号码查询失败（第 %s 次）：user=%s order=%s err=%s",
                    attempt,
                    user_id,
                    order_id,
                    exc,
                )
                if attempt <= self.max_retries:
                    await asyncio.sleep(min(0.5 * attempt, 2))

        raise AppException(f"第三方号码查询失败：{last_error}")
