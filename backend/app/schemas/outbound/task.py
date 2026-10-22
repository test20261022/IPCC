"""外呼任务域 Schema。"""

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.models.outbound.enums import DispatchMode, NumberSelectStrategy, TaskStatus
from app.schemas.outbound.base import OutboundOutBase, OutboundSchemaBase, OutboundUpdateBase
from app.schemas.outbound.config import OutboundTaskNumberOut

#: 重试参数上限（ASSUMPTION-057：需求未定义上限，按「间隔不超过一天、次数不超过 10 次」收敛，
#: 避免误填超大值导致记录长期滞留重试队列）
MAX_RETRY_INTERVAL_SECONDS = 86400
MAX_RETRY_COUNT = 10


class OutboundTaskNumberItem(OutboundSchemaBase):
    """任务内嵌的号码配置项（task_id 由父级任务决定，故此处不含）。"""

    number_id: int = Field(gt=0, description="主叫号码")
    order_id: int | None = Field(default=None, ge=1, description="OrderID 来源顺序")
    user_id: int | None = Field(default=None, ge=1, description="UserID 来源顺序")
    recipient_number: int | None = Field(default=None, ge=1, description="收件人号码来源顺序")
    sort_order: int = 0
    priority: int = 0
    enabled: bool = True


class OutboundTaskCreate(OutboundSchemaBase):
    """§17：任务基础信息 + 策略 / 重试 / 超时 / IVR 配置一次性提交。"""

    tenant_id: int = Field(gt=0)
    task_name: str = Field(min_length=1, max_length=128, description="任务名称")
    site_id: int | None = Field(default=None, gt=0, description="站点（OB-006）")
    skill_queue_id: int | None = Field(default=None, gt=0, description="外呼技能队列")
    type_id: int | None = Field(default=None, gt=0, description="外呼类型")
    scene_id: int | None = Field(default=None, gt=0, description="外呼场景")
    dispatch_mode: DispatchMode = Field(default=DispatchMode.MANUAL, description="派单模式")
    number_select_strategy: NumberSelectStrategy = Field(
        default=NumberSelectStrategy.ORDER, description="主叫号码选取策略"
    )
    retry_interval: int = Field(
        default=60, ge=0, le=MAX_RETRY_INTERVAL_SECONDS, description="失败重试间隔（秒）"
    )
    max_retry_count: int = Field(
        default=3, ge=0, le=MAX_RETRY_COUNT, description="最大重试次数"
    )
    call_timeout_seconds: int = Field(default=60, ge=1, description="单次呼叫超时（秒）")
    max_concurrency: int = Field(default=10, ge=1, description="最大并发呼叫数")
    adjustment_factor: Decimal = Field(
        default=Decimal("1.00"), ge=0, le=99, description="预测外呼调整系数"
    )
    ivr_flow_id: int | None = Field(default=None, gt=0, description="IVR 流程")
    description: str = Field(default="", description="任务说明")
    priority: int = Field(
        default=0, ge=0, le=9999, description="任务优先级，数值越小越先派单（§34）"
    )
    numbers: list[OutboundTaskNumberItem] = Field(
        default_factory=list, description="任务号码配置（§19 多号码配置）"
    )


class OutboundTaskUpdate(OutboundUpdateBase):
    task_name: str | None = Field(default=None, min_length=1, max_length=128)
    site_id: int | None = Field(default=None, gt=0)
    skill_queue_id: int | None = Field(default=None, gt=0)
    type_id: int | None = Field(default=None, gt=0)
    scene_id: int | None = Field(default=None, gt=0)
    dispatch_mode: DispatchMode | None = None
    number_select_strategy: NumberSelectStrategy | None = None
    retry_interval: int | None = Field(default=None, ge=0, le=MAX_RETRY_INTERVAL_SECONDS)
    max_retry_count: int | None = Field(default=None, ge=0, le=MAX_RETRY_COUNT)
    call_timeout_seconds: int | None = Field(default=None, ge=1)
    max_concurrency: int | None = Field(default=None, ge=1)
    adjustment_factor: Decimal | None = Field(default=None, ge=0, le=99)
    ivr_flow_id: int | None = Field(default=None, gt=0)
    description: str | None = None
    priority: int | None = Field(default=None, ge=0, le=9999)


class OutboundTaskStatusChange(OutboundSchemaBase):
    """任务状态流转（非法流转由 Service 依据状态机拒绝）。"""

    status: TaskStatus = Field(description="目标状态")


class OutboundTaskCopyRequest(OutboundSchemaBase):
    """OB-020：复制任务生成新任务，新名称必填；不复制执行数据。"""

    task_name: str = Field(min_length=1, max_length=128, description="新任务名称")
    copy_numbers: bool = Field(default=True, description="是否复制号码配置")


class OutboundTaskOut(OutboundOutBase):
    tenant_id: int
    task_name: str
    site_id: int | None
    skill_queue_id: int | None
    type_id: int | None
    scene_id: int | None
    status: TaskStatus
    dispatch_mode: DispatchMode
    number_select_strategy: NumberSelectStrategy
    retry_interval: int
    max_retry_count: int
    call_timeout_seconds: int
    max_concurrency: int
    adjustment_factor: Decimal
    ivr_flow_id: int | None
    copied_from_id: int | None = Field(
        default=None, description="复制来源任务 ID（OB-020 追溯）"
    )
    priority: int = Field(description="任务优先级，数值越小越先派单")
    description: str
    started_at: datetime | None
    finished_at: datetime | None


class OutboundTaskDetailOut(OutboundTaskOut):
    """任务详情：附带号码配置。"""

    task_numbers: list[OutboundTaskNumberOut] = Field(default_factory=list)


class OutboundTaskCopyResult(OutboundSchemaBase):
    """OB-020 复制结果：created=false 表示命中幂等，返回的是已存在的副本。"""

    task: OutboundTaskOut = Field(description="复制生成（或已存在）的任务")
    created: bool = Field(description="true=本次新建；false=命中幂等返回已有副本")


class OutboundTaskDeleteResult(OutboundSchemaBase):
    """删除结果。"""

    task_id: int = Field(description="被删除的任务 ID")
    removed_task_numbers: int = Field(description="联动软删除的号码配置条数")


__all__ = [
    "OutboundTaskCopyRequest",
    "OutboundTaskCopyResult",
    "OutboundTaskCreate",
    "OutboundTaskDeleteResult",
    "OutboundTaskDetailOut",
    "OutboundTaskNumberItem",
    "OutboundTaskOut",
    "OutboundTaskStatusChange",
    "OutboundTaskUpdate",
]
