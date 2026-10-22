"""呼叫网关 Provider 抽象（§29）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.outbound.enums import CallStatus


@dataclass
class CallResult:
    """一次呼叫的结果（§39 CallHistory 的数据来源）。"""

    success: bool
    call_status: CallStatus
    provider_call_id: str | None = None
    duration: int = 0
    failure_reason: str | None = None
    recording_path: str | None = None


class CallGatewayProvider(ABC):
    """外呼呼叫网关。"""

    name: str = "base"

    @abstractmethod
    async def make_call(
        self,
        *,
        phone: str,
        agent_id: int | None = None,
        session_id: int | None = None,
    ) -> CallResult:
        """发起呼叫并返回结果（同步语义；异步网关可通过回调接口回写结果）。"""
