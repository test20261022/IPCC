"""智能外呼领域枚举。

§18 / §77：禁止魔法数字散落，状态一律使用 Enum，状态流转集中管理。
数据库侧统一使用 VARCHAR + Python 校验（native_enum=False），
避免 PostgreSQL 原生 ENUM 在新增状态时需要 ALTER TYPE 的迁移负担。
"""

from enum import Enum
from typing import Any

import sqlalchemy as sa


class OutboundStrEnum(str, Enum):
    """字符串枚举基类：成员值即入库值，便于迁移与人工排查。"""

    def __str__(self) -> str:
        return str(self.value)


# ---------------- 通用 ----------------


class CommonStatus(OutboundStrEnum):
    """通用启用 / 停用状态。"""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


# ---------------- 坐席 ----------------


class AgentStatus(OutboundStrEnum):
    """坐席状态机（§11）。非法转换由 Service 拒绝。"""

    OFFLINE = "OFFLINE"
    IDLE = "IDLE"
    BUSY = "BUSY"
    RESERVED = "RESERVED"
    PAUSED = "PAUSED"


class AssignmentStatus(OutboundStrEnum):
    """坐席预占用状态（§35）。"""

    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


# ---------------- 外呼任务 ----------------


class TaskStatus(OutboundStrEnum):
    """外呼任务状态（§18）。"""

    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class DispatchMode(OutboundStrEnum):
    """派单模式（§18 自动分配 / §36 预测外呼）。

    ASSUMPTION-008：需求未明确模式字段，自动分配、预占用、预测外呼需要显式开关，
    故在任务上提供 MANUAL / AUTO / PREDICTIVE 三档。
    """

    MANUAL = "MANUAL"
    AUTO = "AUTO"
    PREDICTIVE = "PREDICTIVE"


class NumberSelectStrategy(OutboundStrEnum):
    """主叫号码选取策略（§14）。"""

    ORDER = "ORDER"
    ROUND_ROBIN = "ROUND_ROBIN"
    AVAILABLE_FIRST = "AVAILABLE_FIRST"
    CUSTOM = "CUSTOM"


# ---------------- 名单与执行 ----------------


class ImportBatchStatus(OutboundStrEnum):
    """名单导入批次状态（OB-011）。"""

    PENDING = "PENDING"
    PARSING = "PARSING"
    VALIDATING = "VALIDATING"
    IMPORTING = "IMPORTING"
    SUCCESS = "SUCCESS"
    PARTIAL_FAILED = "PARTIAL_FAILED"
    FAILED = "FAILED"


class ListStatus(OutboundStrEnum):
    """名单行状态（汇总）。"""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXHAUSTED = "EXHAUSTED"
    CANCELLED = "CANCELLED"


class RecordStatus(OutboundStrEnum):
    """外呼执行记录状态（§20 / §21 / §22）。"""

    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    CALLING = "CALLING"
    RETRY_WAITING = "RETRY_WAITING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXHAUSTED = "EXHAUSTED"
    TIMEOUT = "TIMEOUT"


class SessionStatus(OutboundStrEnum):
    """外呼会话状态（§37）。"""

    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    CALLING = "CALLING"
    CONNECTED = "CONNECTED"
    ENDED = "ENDED"
    TIMEOUT = "TIMEOUT"
    RELEASED = "RELEASED"


class CallStatus(OutboundStrEnum):
    """单次呼叫结果（§39 CallHistory）。"""

    INITIATED = "INITIATED"
    RINGING = "RINGING"
    CONNECTED = "CONNECTED"
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    HANGUP = "HANGUP"


# ---------------- IVR ----------------


class IvrNodeType(OutboundStrEnum):
    """IVR 节点类型（§31）。"""

    PLAY = "PLAY"
    COLLECT_DTMF = "COLLECT_DTMF"
    TRANSFER_AGENT = "TRANSFER_AGENT"
    HANGUP = "HANGUP"
    CALLBACK = "CALLBACK"
    REPLAY = "REPLAY"


class IvrConditionType(OutboundStrEnum):
    """IVR 流转条件类型（§31）。"""

    KEY = "KEY"
    ASR_RESULT = "ASR_RESULT"
    TIME_RANGE = "TIME_RANGE"
    QUEUE_AVAILABLE = "QUEUE_AVAILABLE"


class NoAgentAction(OutboundStrEnum):
    """转人工无可用坐席时的动作（§32，禁止硬编码）。"""

    QUEUE = "QUEUE"
    CALLBACK = "CALLBACK"
    REPLAY = "REPLAY"
    HANGUP = "HANGUP"


# ---------------- 回呼 ----------------


class CallbackSource(OutboundStrEnum):
    """回呼来源：IVR 回呼（OB-029）/ 人工回呼（OB-030）。"""

    IVR = "IVR"
    MANUAL = "MANUAL"


class CallbackTriggerType(OutboundStrEnum):
    """回呼自动触发条件类型（§45）。

    ASSUMPTION-054：需求未定义触发条件的取值集合，此处按「为什么要回呼」的业务口径
    收敛为 4 类，避免把触发规则硬编码在代码里；具体条件参数存在
    CallbackFlow.trigger_condition（JSONB）中，由 callback_trigger 统一匹配。
    """

    NO_AGENT = "NO_AGENT"
    NO_ANSWER = "NO_ANSWER"
    KEY = "KEY"
    OUT_OF_HOURS = "OUT_OF_HOURS"


class CallbackStatus(OutboundStrEnum):
    """回呼任务状态（§46）。"""

    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    CALLING = "CALLING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def enum_type(enum_cls: type[Enum], **kwargs: Any) -> sa.Enum:
    """统一的枚举列类型：VARCHAR(32) + Python 侧取值校验，不建 PG 原生类型。"""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        length=32,
        validate_strings=True,
        name=enum_cls.__name__.lower(),
        **kwargs,
    )
