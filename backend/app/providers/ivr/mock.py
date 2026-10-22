"""Mock IVR Provider（§30）：返回确定性的流程执行结果，不做真实按键交互。"""

from app.providers.ivr.base import IvrExecuteResult, IvrProvider


class MockIvrProvider(IvrProvider):
    name = "mock"

    async def execute(
        self, *, flow_id: int, session_id: int | None = None
    ) -> IvrExecuteResult:
        return IvrExecuteResult(
            success=True,
            final_node_key=f"flow-{flow_id}-end",
            collected_keys=[],
            transferred=False,
        )
