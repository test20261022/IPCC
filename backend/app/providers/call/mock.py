"""Mock 呼叫网关（§30）。

**号码规则是确定性的**（刻意不用随机，保证测试可复现）：
- 以 `0000` 开头  → 网关失败        FAILED
- 以 `1111` 结尾  → 无人接听        NO_ANSWER
- 以 `2222` 结尾  → 占线            BUSY
- 以 `3333` 结尾  → 拒接            REJECTED
- 其他           → 接通            CONNECTED（时长取 MOCK_CALL_CONNECT_DURATION）

未接通的号码在业务上属于「可重试失败」，会驱动 §20 的多号码顺序尝试与 §21 的重试阶梯。
"""

import uuid

from app.core.config import settings
from app.models.outbound.enums import CallStatus
from app.providers.call.base import CallGatewayProvider, CallResult

_FAIL_PREFIX = "0000"
_NO_ANSWER_SUFFIX = "1111"
_BUSY_SUFFIX = "2222"
_REJECTED_SUFFIX = "3333"


class MockCallProvider(CallGatewayProvider):
    name = "mock"

    async def make_call(
        self,
        *,
        phone: str,
        agent_id: int | None = None,
        session_id: int | None = None,
    ) -> CallResult:
        provider_call_id = f"mock-{uuid.uuid4().hex[:16]}"

        if phone.startswith(_FAIL_PREFIX):
            return CallResult(
                success=False,
                call_status=CallStatus.FAILED,
                provider_call_id=provider_call_id,
                failure_reason="网关呼叫失败（Mock 规则：0000 前缀）",
            )
        if phone.endswith(_NO_ANSWER_SUFFIX):
            return CallResult(
                success=False,
                call_status=CallStatus.NO_ANSWER,
                provider_call_id=provider_call_id,
                failure_reason="无人接听（Mock 规则：1111 结尾）",
            )
        if phone.endswith(_BUSY_SUFFIX):
            return CallResult(
                success=False,
                call_status=CallStatus.BUSY,
                provider_call_id=provider_call_id,
                failure_reason="用户占线（Mock 规则：2222 结尾）",
            )
        if phone.endswith(_REJECTED_SUFFIX):
            return CallResult(
                success=False,
                call_status=CallStatus.REJECTED,
                provider_call_id=provider_call_id,
                failure_reason="用户拒接（Mock 规则：3333 结尾）",
            )

        return CallResult(
            success=True,
            call_status=CallStatus.CONNECTED,
            provider_call_id=provider_call_id,
            duration=settings.MOCK_CALL_CONNECT_DURATION,
            recording_path=f"mock/recordings/{provider_call_id}.wav",
        )
