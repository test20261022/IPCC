"""回呼域 Schema（OB-029 IVR 回呼 / OB-030 人工回呼）。"""

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.models.outbound.enums import (
    CallbackSource,
    CallbackStatus,
    CallbackTriggerType,
    CommonStatus,
)
from app.schemas.outbound.base import OutboundOutBase, OutboundSchemaBase, OutboundUpdateBase


class CallbackFlowCreate(OutboundSchemaBase):
    """§45：回呼流程触发条件配置。"""

    tenant_id: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    trigger_condition: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "触发条件：triggers（NO_AGENT/NO_ANSWER/KEY/OUT_OF_HOURS，任一命中即触发）、"
            "keys（KEY 触发的按键）、business_hours（业务时段）、delay_seconds（延迟回呼秒数）、"
            "max_attempts（最大尝试次数）、priority（越小越优先）"
        ),
    )
    ivr_flow_id: int | None = Field(default=None, gt=0, description="关联 IVR 流程")
    status: CommonStatus = CommonStatus.ENABLED
    description: str = Field(default="", max_length=255)


class CallbackFlowUpdate(OutboundUpdateBase):
    name: str | None = Field(default=None, max_length=128)
    trigger_condition: dict[str, Any] | None = None
    ivr_flow_id: int | None = Field(default=None, gt=0)
    status: CommonStatus | None = None
    description: str | None = Field(default=None, max_length=255)


class CallbackFlowOut(OutboundOutBase):
    tenant_id: int
    code: str
    name: str
    trigger_condition: dict[str, Any] | None
    ivr_flow_id: int | None
    status: CommonStatus
    description: str


class CallbackFlowDeleteResult(OutboundSchemaBase):
    """回呼流程删除结果。"""

    flow_id: int


class CallbackTaskCreate(OutboundSchemaBase):
    """生成回呼任务（§45 / §46）。

    IVR 回呼必须带 origin_session_id，由数据库部分唯一索引保证同一会话只生成一条（§78 幂等）。
    """

    tenant_id: int = Field(gt=0)
    source: CallbackSource = Field(description="来源：IVR / MANUAL")
    phone: str = Field(min_length=1, max_length=32, description="回呼号码")
    flow_id: int | None = Field(default=None, gt=0)
    task_id: int | None = Field(default=None, gt=0)
    list_id: int | None = Field(default=None, gt=0)
    origin_session_id: int | None = Field(default=None, gt=0, description="原会话（IVR 幂等键）")
    trigger_type: CallbackTriggerType | None = Field(
        default=None, description="命中的自动触发条件（§45）；人工回呼留空"
    )
    scheduled_at: datetime | None = Field(
        default=None, description="计划回呼时间；留空表示立即回呼"
    )
    agent_id: int | None = Field(default=None, gt=0, description="可选的执行坐席")
    remark: str = Field(default="", max_length=255)

    @field_validator("phone")
    @classmethod
    def _strip_phone(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("回呼号码不能为空白")
        return stripped


class CallbackTaskUpdate(OutboundUpdateBase):
    agent_id: int | None = Field(default=None, gt=0)
    status: CallbackStatus | None = None
    remark: str | None = Field(default=None, max_length=255)


class CallbackTaskOut(OutboundOutBase):
    tenant_id: int
    flow_id: int | None
    source: CallbackSource
    task_id: int | None
    list_id: int | None
    origin_session_id: int | None
    agent_id: int | None
    phone: str
    status: CallbackStatus
    trigger_type: CallbackTriggerType | None
    scheduled_at: datetime | None
    attempt_count: int
    assigned_at: datetime | None
    last_call_at: datetime | None
    finished_at: datetime | None
    remark: str


# ---------------- 自动触发（OB-029） ----------------


class CallbackTriggerContextIn(OutboundSchemaBase):
    """IVR 会话结束时上报的触发上下文（供 §45 触发条件匹配）。"""

    tenant_id: int = Field(gt=0)
    phone: str = Field(min_length=1, max_length=32, description="回呼号码")
    origin_session_id: int = Field(gt=0, description="原会话 ID（§78 幂等键）")
    flow_id: int | None = Field(
        default=None, gt=0, description="指定回呼流程；留空则按优先级自动匹配"
    )
    task_id: int | None = Field(default=None, gt=0, description="关联外呼任务")
    list_id: int | None = Field(default=None, gt=0, description="关联名单")
    keys: list[str] = Field(default_factory=list, description="客户在 IVR 中按下的键")
    no_agent: bool = Field(default=False, description="转人工时是否无可用坐席")
    no_answer: bool = Field(default=False, description="是否未接通坐席即挂断")
    current_time: str | None = Field(
        default=None, pattern=r"^\d{2}:\d{2}$", description="来电时间 HH:MM，用于时段判定"
    )
    attempt_count: int = Field(default=0, ge=0, description="该号码已回呼次数")
    remark: str = Field(default="", max_length=255)


class CallbackTriggerResultOut(OutboundSchemaBase):
    """自动触发结果：created=false 表示命中幂等或未满足触发条件。"""

    created: bool = Field(description="是否新建了回呼任务")
    reason: str = Field(description="中文说明：未触发原因 / 命中说明 / 幂等命中")
    flow_id: int | None = Field(default=None, description="命中的回呼流程")
    flow_name: str | None = None
    trigger_type: CallbackTriggerType | None = Field(
        default=None, description="命中的触发条件"
    )
    task: CallbackTaskOut | None = Field(default=None, description="新建或已存在的回呼任务")


# ---------------- 派单与执行 ----------------


class CallbackAssignOut(OutboundSchemaBase):
    """派单结果。"""

    task_id: int
    agent_id: int
    assigned_at: datetime | None
    auto_assigned: bool = Field(description="true=系统自动挑选空闲坐席；false=指定坐席")


class CallbackDispatchResultOut(OutboundSchemaBase):
    """批量到期回呼派单统计。"""

    scanned: int = Field(description="扫描到的到期待回呼任务数")
    assigned: int = Field(description="成功派单数")
    skipped: int = Field(description="无可用坐席而跳过数")


class CallbackCallOut(OutboundSchemaBase):
    """一次回呼的执行结果。"""

    task_id: int
    status: CallbackStatus
    attempt_count: int
    call_status: str | None = Field(default=None, description="网关返回的呼叫结果")
    failure_reason: str | None = None
    calling_number: str | None = Field(default=None, description="使用的主叫号码")
    history_id: int | None = Field(default=None, description="写入的呼叫历史 ID")


__all__ = [
    "CallbackAssignOut",
    "CallbackCallOut",
    "CallbackDispatchResultOut",
    "CallbackFlowCreate",
    "CallbackFlowDeleteResult",
    "CallbackFlowOut",
    "CallbackFlowUpdate",
    "CallbackTaskCreate",
    "CallbackTaskOut",
    "CallbackTaskUpdate",
    "CallbackTriggerContextIn",
    "CallbackTriggerResultOut",
]
