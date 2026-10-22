"""IVR 流程 Provider 抽象（§29 / §31）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class IvrExecuteResult:
    """IVR 执行结果。"""

    success: bool
    final_node_key: str | None = None
    collected_keys: list[str] = field(default_factory=list)
    transferred: bool = False
    failure_reason: str | None = None


class IvrProvider(ABC):
    """IVR 流程执行。"""

    name: str = "base"

    @abstractmethod
    async def execute(
        self, *, flow_id: int, session_id: int | None = None
    ) -> IvrExecuteResult:
        """执行 IVR 流程并返回最终节点与按键结果。"""
