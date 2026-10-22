"""智能外呼领域模型包（22 张表）。

配置域 config / 任务域 task / 名单域 name_list / 执行域 execution / IVR 域 ivr / 回呼域 callback。
"""

from app.models.outbound.callback import CallbackFlow, CallbackTask
from app.models.outbound.config import (
    Agent,
    AgentStatusLog,
    OutboundNumber,
    OutboundScene,
    OutboundType,
    Site,
    SkillQueue,
    Tenant,
)
from app.models.outbound.execution import (
    AgentAssignment,
    CallHistory,
    OutboundRecord,
    OutboundSession,
    ServiceSummary,
)
from app.models.outbound.ivr import IvrFlow, IvrNode, IvrTransition
from app.models.outbound.name_list import OutboundImportBatch, OutboundList
from app.models.outbound.task import OutboundTask, OutboundTaskNumber

__all__ = [
    "Agent",
    "AgentAssignment",
    "AgentStatusLog",
    "CallbackFlow",
    "CallbackTask",
    "CallHistory",
    "IvrFlow",
    "IvrNode",
    "IvrTransition",
    "OutboundImportBatch",
    "OutboundList",
    "OutboundNumber",
    "OutboundRecord",
    "OutboundScene",
    "OutboundSession",
    "OutboundTask",
    "OutboundTaskNumber",
    "OutboundType",
    "ServiceSummary",
    "Site",
    "SkillQueue",
    "Tenant",
]
