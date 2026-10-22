"""IVR 域 Schema（OB-017）。"""

from typing import Any, Literal

from pydantic import Field

from app.models.outbound.enums import (
    CommonStatus,
    IvrConditionType,
    IvrNodeType,
    NoAgentAction,
)
from app.schemas.outbound.base import OutboundOutBase, OutboundSchemaBase, OutboundUpdateBase


class IvrFlowCreate(OutboundSchemaBase):
    tenant_id: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    entry_node_key: str | None = Field(default=None, max_length=64, description="入口节点 key")
    status: CommonStatus = CommonStatus.ENABLED
    description: str = Field(default="", max_length=255)


class IvrFlowUpdate(OutboundUpdateBase):
    name: str | None = Field(default=None, max_length=128)
    entry_node_key: str | None = Field(default=None, max_length=64)
    status: CommonStatus | None = None
    description: str | None = Field(default=None, max_length=255)


class IvrFlowOut(OutboundOutBase):
    tenant_id: int
    code: str
    name: str
    entry_node_key: str | None
    status: CommonStatus
    description: str


class IvrNodeCreate(OutboundSchemaBase):
    """§31：节点类型 + 话术 + 转人工兜底动作。

    flow_id 由创建接口的路径参数决定，故此处不含（避免与路径不一致）。
    """

    tenant_id: int = Field(gt=0)
    node_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    node_type: IvrNodeType = Field(description="节点类型")
    content: str = Field(default="", description="播报话术 / 提示音")
    config: dict[str, Any] = Field(default_factory=dict, description="节点扩展配置")
    max_replay: int = Field(default=3, ge=0, description="最大重播次数，超过则挂断")
    no_agent_action: NoAgentAction | None = Field(
        default=None, description="转人工无可用坐席时的动作（§32）"
    )
    sort_order: int = 0


class IvrNodeUpdate(OutboundUpdateBase):
    name: str | None = Field(default=None, max_length=128)
    node_type: IvrNodeType | None = None
    content: str | None = None
    config: dict[str, Any] | None = None
    max_replay: int | None = Field(default=None, ge=0)
    no_agent_action: NoAgentAction | None = None
    sort_order: int | None = None


class IvrNodeOut(OutboundOutBase):
    flow_id: int
    tenant_id: int
    node_key: str
    name: str
    node_type: IvrNodeType
    content: str
    config: dict[str, Any] | None
    max_replay: int
    no_agent_action: NoAgentAction | None
    sort_order: int


class IvrTransitionCreate(OutboundSchemaBase):
    """§31：有效按键 / 非法按键 / 识别结果 / 时段 / 队列条件的流转。

    flow_id 由创建接口的路径参数决定，故此处不含（避免与路径不一致）。
    """

    tenant_id: int = Field(gt=0)
    from_node_id: int = Field(gt=0)
    to_node_id: int | None = Field(default=None, gt=0, description="目标节点，空表示结束")
    condition_type: IvrConditionType = Field(description="条件类型")
    condition_value: str | None = Field(default=None, max_length=255, description="条件值")
    priority: int = Field(default=0, description="命中优先级，越小越先匹配")


class IvrTransitionUpdate(OutboundUpdateBase):
    to_node_id: int | None = Field(default=None, gt=0)
    condition_type: IvrConditionType | None = None
    condition_value: str | None = Field(default=None, max_length=255)
    priority: int | None = None


class IvrTransitionOut(OutboundOutBase):
    flow_id: int
    tenant_id: int
    from_node_id: int
    to_node_id: int | None
    condition_type: IvrConditionType
    condition_value: str | None
    priority: int


class IvrFlowDetailOut(IvrFlowOut):
    """流程详情：附带节点与流转，便于编辑器一次拉全。"""

    nodes: list[IvrNodeOut] = Field(default_factory=list)
    transitions: list[IvrTransitionOut] = Field(default_factory=list)


# ---------------- 删除结果 ----------------


class IvrFlowDeleteResult(OutboundSchemaBase):
    """流程删除结果：联动软删除的节点与流转条数。"""

    flow_id: int
    removed_nodes: int = Field(default=0, description="联动软删除的节点数")
    removed_transitions: int = Field(default=0, description="联动软删除的流转数")


class IvrNodeDeleteResult(OutboundSchemaBase):
    """节点删除结果。"""

    node_id: int
    removed_transitions: int = Field(default=0, description="联动软删除的相关流转数")


# ---------------- 结构校验（OB-017） ----------------


class IvrValidationIssueOut(OutboundSchemaBase):
    """一条校验问题：ERROR 阻断发布，WARNING 仅提示。"""

    level: Literal["ERROR", "WARNING"] = Field(description="级别")
    code: str = Field(description="问题码")
    target: str = Field(description="问题定位：节点 key / 流程编码 / 流转 ID")
    message: str = Field(description="中文说明")


class IvrValidationResultOut(OutboundSchemaBase):
    """流程结构校验结果。"""

    valid: bool = Field(description="是否存在 ERROR 级问题")
    issues: list[IvrValidationIssueOut] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    node_count: int = 0
    transition_count: int = 0


# ---------------- 模拟运行（OB-017） ----------------


class IvrSimulationInputIn(OutboundSchemaBase):
    """一次模拟输入：DTMF 按键或 ASR 识别结果。"""

    input_type: Literal["KEY", "ASR"] = Field(default="KEY", description="输入类型")
    value: str = Field(min_length=1, max_length=64, description="按键值或识别文本")


class IvrSimulationRequest(OutboundSchemaBase):
    """IVR 流程模拟运行请求。"""

    inputs: list[IvrSimulationInputIn] = Field(
        default_factory=list, description="按发生顺序排列的输入序列"
    )
    current_time: str | None = Field(
        default=None, pattern=r"^\d{2}:\d{2}$", description="模拟当前时间 HH:MM，用于时段条件"
    )
    queue_available: bool | None = Field(
        default=None, description="模拟技能队列是否有空闲坐席；空表示按真实坐席状态推断"
    )
    skill_queue_id: int | None = Field(
        default=None, gt=0, description="按该队列判断可用性，空表示按租户整体判断"
    )
    max_steps: int | None = Field(default=None, ge=1, le=200, description="推演步数上限")


class IvrSimulationStepOut(OutboundSchemaBase):
    """推演轨迹的一步。"""

    index: int
    node_key: str
    node_name: str
    node_type: str
    action: str = Field(
        description="动作：PLAY/COLLECT/MOVE/TRANSFER/QUEUE/CALLBACK/REPLAY/HANGUP 等"
    )
    detail: str
    from_node_key: str | None = None
    to_node_key: str | None = None
    condition_type: str | None = None
    condition_value: str | None = None
    replay_count: int = 0


class IvrSimulationResultOut(OutboundSchemaBase):
    """IVR 流程模拟运行结果。"""

    flow_id: int
    flow_name: str
    entry_node_key: str | None
    final_node_key: str | None
    ended: bool
    transferred: bool = Field(description="是否成功转接人工坐席")
    no_agent_action: str | None = Field(
        default=None, description="无可用坐席时实际执行的兜底动作（§32）"
    )
    collected_keys: list[str] = Field(default_factory=list)
    replay_count: int = 0
    end_reason: str = Field(
        description="结束原因：TRANSFERRED/QUEUE/CALLBACK/HANGUP/FLOW_END/NO_INPUT/MAX_STEPS/ENTRY_NOT_FOUND"
    )
    queue_available: bool | None = None
    steps: list[IvrSimulationStepOut] = Field(default_factory=list)


# ---------------- 下拉选项 ----------------


class IvrFlowOptionOut(OutboundSchemaBase):
    """IVR 流程下拉选项（外呼任务表单使用）。"""

    id: int
    tenant_id: int
    code: str
    name: str
    entry_node_key: str | None = None


__all__ = [
    "IvrFlowCreate",
    "IvrFlowDeleteResult",
    "IvrFlowDetailOut",
    "IvrFlowOptionOut",
    "IvrFlowOut",
    "IvrFlowUpdate",
    "IvrNodeCreate",
    "IvrNodeDeleteResult",
    "IvrNodeOut",
    "IvrNodeUpdate",
    "IvrSimulationInputIn",
    "IvrSimulationRequest",
    "IvrSimulationResultOut",
    "IvrSimulationStepOut",
    "IvrTransitionCreate",
    "IvrTransitionOut",
    "IvrTransitionUpdate",
    "IvrValidationIssueOut",
    "IvrValidationResultOut",
]
