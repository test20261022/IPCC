"""对话质检：专家组 / 质检任务 / 执行域 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.qc.enums import (
    ConversationChannel,
    ConversationSource,
    MessageRole,
    MessageSource,
    QcDispatchMode,
    QcGrade,
    QcItemStatus,
    QcTaskStatus,
)


class QcSchemaBase(BaseModel):
    """质检模块 Schema 基类：允许从 ORM 对象直接构造。"""

    model_config = ConfigDict(from_attributes=True)


class QcOutBase(QcSchemaBase):
    """出参基类：统一带上主键与时间戳。"""

    id: int = Field(description="主键")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class QcUpdateBase(QcSchemaBase):
    """入参基类：更新语义为「只更新显式传入的字段」。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ---------------- 专家组 ----------------


class ReviewerUserOut(QcSchemaBase):
    """可入组用户（专家就是 users 表的用户）。"""

    id: int
    username: str
    nickname: str = ""
    is_active: bool = True


class ReviewerGroupCreate(QcSchemaBase):
    """新增专家组：可同时指定初始成员。"""

    tenant_id: int = Field(gt=0, description="归属租户")
    name: str = Field(min_length=1, max_length=128, description="专家组名称")
    description: str = Field(default="", description="说明")
    member_user_ids: list[int] = Field(default_factory=list, description="初始成员用户 ID")


class ReviewerGroupUpdate(QcUpdateBase):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None


class ReviewerGroupMemberItem(QcSchemaBase):
    """成员项：max_concurrent 缺省时由服务层填默认额度。"""

    user_id: int = Field(gt=0, description="专家账号 ID")
    is_active: bool = Field(default=True, description="是否参与派发")
    max_concurrent: int | None = Field(default=None, ge=1, description="单轮质检上限")


class ReviewerGroupMembersUpdate(QcSchemaBase):
    """全量覆盖组成员（未出现在列表中的成员将被移除）。"""

    members: list[ReviewerGroupMemberItem] = Field(default_factory=list)


class ReviewerGroupMemberOut(QcSchemaBase):
    user_id: int
    is_active: bool = True
    max_concurrent: int = 50
    username: str = ""
    nickname: str = ""


class ReviewerGroupOut(QcOutBase):
    tenant_id: int
    name: str
    description: str = ""
    member_count: int = 0


class ReviewerGroupDetailOut(ReviewerGroupOut):
    """组详情：附带成员（含 username / nickname）。"""

    members: list[ReviewerGroupMemberOut] = Field(default_factory=list)


# ---------------- 质检任务 ----------------


class QcTaskCreate(QcSchemaBase):
    """新增质检任务：以时间区间从对话池圈定范围，派发时生成全部明细。"""

    tenant_id: int = Field(gt=0, description="归属租户")
    task_name: str = Field(min_length=1, max_length=128, description="任务名称")
    group_id: int = Field(gt=0, description="承接专家组")
    time_from: datetime = Field(description="对话开始时间下界（含）")
    time_to: datetime = Field(description="对话开始时间上界（含）")
    dispatch_mode: QcDispatchMode = Field(
        default=QcDispatchMode.ROUND_ROBIN, description="派发分片方式"
    )


class QcTaskUpdate(QcUpdateBase):
    task_name: str | None = Field(default=None, min_length=1, max_length=128)
    group_id: int | None = Field(default=None, gt=0)
    time_from: datetime | None = None
    time_to: datetime | None = None
    dispatch_mode: QcDispatchMode | None = None


class QcTaskOut(QcOutBase):
    tenant_id: int
    task_name: str
    group_id: int | None
    time_from: datetime
    time_to: datetime
    status: QcTaskStatus
    dispatch_mode: QcDispatchMode
    total_items: int
    completed_items: int
    dispatched_at: datetime | None
    finished_at: datetime | None


class QcTaskDetailOut(QcTaskOut):
    """任务详情：附加完成率。"""

    completion_rate: float = Field(default=0.0, description="完成率，0~1")


class QcTaskDeleteResult(QcSchemaBase):
    task_id: int = Field(description="被删除的任务 ID")
    removed_items: int = Field(default=0, description="联动软删除的明细条数")


class QcTaskDispatchResult(QcSchemaBase):
    """派发结果。"""

    task_id: int
    total_items: int = Field(description="回填后的明细总数")
    dispatched_at: datetime | None
    reviewer_count: int = Field(description="参与派发的专家数")


# ---------------- 执行域 ----------------


class QcTaskItemOut(QcOutBase):
    tenant_id: int
    task_id: int
    conversation_id: int
    reviewer_id: int | None
    status: QcItemStatus
    grade: QcGrade | None
    locked_at: datetime | None
    timeout_at: datetime | None
    submitted_at: datetime | None


class QcMessageOut(QcSchemaBase):
    """对话消息（按 seq 升序）。"""

    seq: int
    role: MessageRole
    content: str
    start_ms: int | None
    end_ms: int | None
    source: MessageSource


class QcConversationOut(QcSchemaBase):
    id: int
    ext_ref_no: str | None
    agent_name: str
    customer_id: str | None
    channel: ConversationChannel
    source: ConversationSource
    started_at: datetime
    ended_at: datetime | None
    duration: int
    msg_count: int


class QcItemDetailOut(QcSchemaBase):
    """质检工作台详情：明细 + 对话 + 对话消息。"""

    item: QcTaskItemOut
    conversation: QcConversationOut | None = None
    messages: list[QcMessageOut] = Field(default_factory=list)


class QcItemSubmitRequest(QcSchemaBase):
    """提交质检结果：等级由 score 判定，不接受直传。"""

    score: int = Field(ge=0, le=100, description="百分制得分")
    comment: str = Field(default="", description="评语")
    score_detail: dict[str, Any] | None = Field(default=None, description="分项得分明细")


class QcItemSubmitResult(QcSchemaBase):
    item_id: int
    grade: QcGrade
    status: QcItemStatus
    submitted_at: datetime | None
    task_completed: bool = Field(default=False, description="本此提交是否使整单完成")


__all__ = [
    "QcConversationOut",
    "QcItemDetailOut",
    "QcItemSubmitRequest",
    "QcItemSubmitResult",
    "QcMessageOut",
    "QcSchemaBase",
    "QcTaskCreate",
    "QcTaskDeleteResult",
    "QcTaskDetailOut",
    "QcTaskDispatchResult",
    "QcTaskItemOut",
    "QcTaskOut",
    "QcTaskUpdate",
    "ReviewerGroupCreate",
    "ReviewerGroupDetailOut",
    "ReviewerGroupMemberItem",
    "ReviewerGroupMemberOut",
    "ReviewerGroupMembersUpdate",
    "ReviewerGroupOut",
    "ReviewerGroupUpdate",
    "ReviewerUserOut",
]