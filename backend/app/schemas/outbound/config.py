"""外呼基础配置域 Schema：租户 / 站点 / 技能队列 / 坐席 / 类型 / 场景 / 号码。"""

from datetime import datetime

from pydantic import Field, field_validator

from app.models.outbound.enums import AgentStatus, CommonStatus
from app.schemas.outbound.base import OutboundOutBase, OutboundSchemaBase, OutboundUpdateBase

# 号码格式统一定义在 app.utils.validators，此处导入后再导出，保持既有引用不失效
from app.utils.validators import PHONE_PATTERN

# ---------------- 租户 ----------------


class TenantCreate(OutboundSchemaBase):
    code: str = Field(min_length=1, max_length=64, description="租户编码")
    name: str = Field(min_length=1, max_length=128, description="租户名称")
    status: CommonStatus = Field(default=CommonStatus.ENABLED, description="状态")
    remark: str = Field(default="", max_length=255, description="备注")


class TenantUpdate(OutboundUpdateBase):
    name: str | None = Field(default=None, max_length=128)
    status: CommonStatus | None = None
    remark: str | None = Field(default=None, max_length=255)


class TenantOut(OutboundOutBase):
    code: str
    name: str
    status: CommonStatus
    remark: str


# ---------------- 站点 ----------------


class SiteCreate(OutboundSchemaBase):
    tenant_id: int = Field(gt=0, description="租户")
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    status: CommonStatus = CommonStatus.ENABLED
    remark: str = Field(default="", max_length=255)


class SiteUpdate(OutboundUpdateBase):
    name: str | None = Field(default=None, max_length=128)
    status: CommonStatus | None = None
    remark: str | None = Field(default=None, max_length=255)


class SiteOut(OutboundOutBase):
    tenant_id: int
    code: str
    name: str
    status: CommonStatus
    remark: str


# ---------------- 技能队列 ----------------


class SkillQueueCreate(OutboundSchemaBase):
    tenant_id: int = Field(gt=0)
    site_id: int = Field(gt=0, description="所属站点")
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    status: CommonStatus = CommonStatus.ENABLED
    remark: str = Field(default="", max_length=255)


class SkillQueueUpdate(OutboundUpdateBase):
    name: str | None = Field(default=None, max_length=128)
    status: CommonStatus | None = None
    remark: str | None = Field(default=None, max_length=255)


class SkillQueueOut(OutboundOutBase):
    tenant_id: int
    site_id: int
    code: str
    name: str
    status: CommonStatus
    remark: str


# ---------------- 坐席 ----------------


class AgentCreate(OutboundSchemaBase):
    """§3.1：坐席通过 user_id 关联既有 users 表，不接受账号密码。"""

    user_id: int = Field(gt=0, description="关联 users.id")
    tenant_id: int = Field(gt=0)
    site_id: int | None = Field(default=None, gt=0)
    skill_queue_id: int | None = Field(default=None, gt=0)
    extension: str | None = Field(default=None, max_length=32, description="分机号")


class AgentUpdate(OutboundUpdateBase):
    site_id: int | None = Field(default=None, gt=0)
    skill_queue_id: int | None = Field(default=None, gt=0)
    extension: str | None = Field(default=None, max_length=32)


class AgentStatusChange(OutboundSchemaBase):
    """坐席状态变更请求（§11 非法转换由 Service 拒绝）。"""

    status: AgentStatus = Field(description="目标状态")
    reason: str = Field(default="", max_length=255, description="变更原因")


class AgentOut(OutboundOutBase):
    user_id: int
    tenant_id: int
    site_id: int | None
    skill_queue_id: int | None
    status: AgentStatus
    extension: str | None
    last_idle_at: datetime | None
    last_busy_at: datetime | None


class AgentStatusLogOut(OutboundOutBase):
    agent_id: int
    from_status: AgentStatus | None
    to_status: AgentStatus
    reason: str
    operator_id: int | None


# ---------------- 外呼类型 ----------------


class OutboundTypeCreate(OutboundSchemaBase):
    tenant_id: int = Field(gt=0)
    parent_id: int | None = Field(default=None, gt=0, description="父类型，空表示一级")
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    level: int = Field(default=1, ge=1, le=2, description="1 类型 / 2 子类型")
    sort_order: int = 0
    status: CommonStatus = CommonStatus.ENABLED
    description: str = Field(default="", max_length=255)


class OutboundTypeUpdate(OutboundUpdateBase):
    code: str | None = Field(
        default=None, min_length=1, max_length=64, description="编码（被引用后禁止修改）"
    )
    parent_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, max_length=128)
    sort_order: int | None = None
    status: CommonStatus | None = None
    description: str | None = Field(default=None, max_length=255)


class OutboundTypeOut(OutboundOutBase):
    tenant_id: int
    parent_id: int | None
    code: str
    name: str
    level: int
    sort_order: int
    status: CommonStatus
    description: str


# ---------------- 外呼场景 ----------------


class OutboundSceneCreate(OutboundSchemaBase):
    """OB-003：创建场景需选择外呼类型，并输入一级 / 二级场景。"""

    tenant_id: int = Field(gt=0)
    type_id: int = Field(gt=0, description="外呼类型")
    parent_id: int | None = Field(default=None, gt=0, description="父场景，空表示一级场景")
    level: int = Field(default=1, ge=1, le=2, description="1 一级场景 / 2 二级场景")
    name: str = Field(min_length=1, max_length=128, description="场景名称")
    sort_order: int = 0
    status: CommonStatus = CommonStatus.ENABLED
    description: str = Field(default="", max_length=255)


class OutboundSceneUpdate(OutboundUpdateBase):
    type_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, max_length=128)
    sort_order: int | None = None
    status: CommonStatus | None = None
    description: str | None = Field(default=None, max_length=255)


class OutboundSceneOut(OutboundOutBase):
    tenant_id: int
    type_id: int
    parent_id: int | None
    level: int
    name: str
    sort_order: int
    status: CommonStatus
    description: str


# ---------------- 外呼号码 ----------------


class OutboundNumberCreate(OutboundSchemaBase):
    """OB-001：外显名称必填、主叫号码格式校验、可设次数上限。"""

    tenant_id: int = Field(gt=0, description="归属租户（OB-001 租户设置与验证）")
    display_name: str = Field(min_length=1, max_length=128, description="外显名称（必填）")
    caller_number: str = Field(pattern=PHONE_PATTERN, description="主叫号码")
    number_type: str = Field(default="", max_length=32, description="号码类型")
    usage_limit: int | None = Field(default=None, ge=0, description="使用次数上限，空表示不限")
    status: CommonStatus = CommonStatus.ENABLED
    remark: str = Field(default="", max_length=255)

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("外显名称不能为空白")
        return stripped


class OutboundNumberUpdate(OutboundUpdateBase):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    number_type: str | None = Field(default=None, max_length=32)
    usage_limit: int | None = Field(default=None, ge=0)
    status: CommonStatus | None = None
    remark: str | None = Field(default=None, max_length=255)


class OutboundNumberOut(OutboundOutBase):
    tenant_id: int
    display_name: str
    caller_number: str
    number_type: str
    usage_limit: int | None
    used_count: int = Field(description="已使用次数（列表展示用，OB-001 次数显示）")
    status: CommonStatus
    remark: str


# ---------------- 任务号码配置 ----------------


class OutboundTaskNumberCreate(OutboundSchemaBase):
    task_id: int = Field(gt=0)
    number_id: int = Field(gt=0, description="主叫号码")
    order_id: int | None = Field(default=None, ge=1, description="OrderID 来源顺序，空表示不启用")
    user_id: int | None = Field(default=None, ge=1, description="UserID 来源顺序，空表示不启用")
    recipient_number: int | None = Field(
        default=None, ge=1, description="收件人号码来源顺序，空表示不启用"
    )
    sort_order: int = 0
    priority: int = 0
    enabled: bool = True


class OutboundTaskNumberUpdate(OutboundUpdateBase):
    order_id: int | None = Field(default=None, ge=1)
    user_id: int | None = Field(default=None, ge=1)
    recipient_number: int | None = Field(default=None, ge=1)
    sort_order: int | None = None
    priority: int | None = None
    enabled: bool | None = None


class OutboundTaskNumberOut(OutboundOutBase):
    task_id: int
    number_id: int
    order_id: int | None
    user_id: int | None
    recipient_number: int | None
    sort_order: int
    priority: int
    enabled: bool


# ---------------- 通用状态变更 ----------------


class CommonStatusChange(OutboundSchemaBase):
    """启用 / 停用请求（类型、场景、号码共用）。"""

    status: CommonStatus = Field(description="目标状态：ENABLED / DISABLED")


# ---------------- 下拉选项 ----------------


class TenantOptionOut(OutboundSchemaBase):
    """租户下拉选项（供表单选择，避免前端硬编码租户 ID）。"""

    id: int = Field(description="租户 ID")
    code: str = Field(description="租户编码")
    name: str = Field(description="租户名称")


class SiteOptionOut(OutboundSchemaBase):
    """站点下拉选项。"""

    id: int = Field(description="站点 ID")
    tenant_id: int
    code: str
    name: str


class SkillQueueOptionOut(OutboundSchemaBase):
    """技能队列下拉选项。"""

    id: int = Field(description="技能队列 ID")
    tenant_id: int
    site_id: int = Field(description="所属站点")
    code: str
    name: str


class AgentOptionOut(OutboundSchemaBase):
    """坐席下拉选项：只暴露派单 / 呼叫所需的最小字段。"""

    id: int = Field(description="坐席 ID")
    user_id: int = Field(description="关联用户")
    tenant_id: int
    site_id: int | None
    skill_queue_id: int | None
    extension: str | None
    status: AgentStatus


class UserOptionOut(OutboundSchemaBase):
    """用户下拉选项（开通坐席时选择关联账号）。"""

    id: int = Field(description="用户 ID")
    username: str
    nickname: str
    tenant_id: int | None = Field(default=None, description="所属租户；空表示平台账号")


class TaskOptionOut(OutboundSchemaBase):
    """任务下拉选项：只暴露筛选 / 展示需要的最小字段。"""

    id: int
    tenant_id: int
    task_name: str


# ---------------- 组合出参 ----------------


class OutboundSceneTreeOut(OutboundSceneOut):
    """场景两级树（OB-003）。"""

    children: list["OutboundSceneTreeOut"] = Field(default_factory=list)


__all__ = [
    "PHONE_PATTERN",
    "AgentCreate",
    "AgentOptionOut",
    "AgentOut",
    "AgentStatusChange",
    "AgentStatusLogOut",
    "AgentUpdate",
    "CommonStatusChange",
    "OutboundNumberCreate",
    "OutboundNumberOut",
    "OutboundNumberUpdate",
    "OutboundSceneCreate",
    "OutboundSceneOut",
    "OutboundSceneTreeOut",
    "OutboundSceneUpdate",
    "OutboundTaskNumberCreate",
    "OutboundTaskNumberOut",
    "OutboundTaskNumberUpdate",
    "OutboundTypeCreate",
    "OutboundTypeOut",
    "OutboundTypeUpdate",
    "PHONE_PATTERN",
    "SiteCreate",
    "SiteOptionOut",
    "SiteOut",
    "SiteUpdate",
    "SkillQueueCreate",
    "SkillQueueOptionOut",
    "SkillQueueOut",
    "SkillQueueUpdate",
    "TaskOptionOut",
    "TenantCreate",
    "TenantOptionOut",
    "TenantOut",
    "TenantUpdate",
    "UserOptionOut",
]
