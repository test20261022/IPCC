"""执行域 Schema：记录 / 会话 / 呼叫历史 / 服务小结 / 坐席预占用 / 任务看板。"""

from datetime import datetime

from pydantic import Field

from app.models.outbound.enums import (
    AgentStatus,
    AssignmentStatus,
    CallStatus,
    RecordStatus,
    SessionStatus,
)
from app.schemas.outbound.base import OutboundOutBase, OutboundSchemaBase, OutboundUpdateBase
from app.schemas.outbound.name_list import OutboundListOut


class OutboundRecordOut(OutboundOutBase):
    tenant_id: int
    task_id: int
    list_id: int
    agent_id: int | None
    session_id: int | None
    status: RecordStatus
    current_phone: str | None
    current_attempt: int
    retry_count: int
    assigned_at: datetime | None
    timeout_at: datetime | None
    last_call_at: datetime | None
    finished_at: datetime | None
    failure_reason: str | None


class OutboundSessionCreate(OutboundSchemaBase):
    """发起会话（人工外呼，OB-021）。"""

    tenant_id: int = Field(gt=0)
    task_id: int | None = Field(default=None, gt=0)
    list_id: int | None = Field(default=None, gt=0)
    agent_id: int | None = Field(default=None, gt=0)


class OutboundSessionEnd(OutboundSchemaBase):
    """结束会话。"""

    status: SessionStatus = Field(default=SessionStatus.ENDED, description="结束状态")
    end_reason: str = Field(default="", max_length=255, description="结束原因")


class OutboundSessionOut(OutboundOutBase):
    tenant_id: int
    task_id: int | None
    list_id: int | None
    agent_id: int | None
    status: SessionStatus
    current_phone: str | None
    current_attempt: int
    started_at: datetime | None
    finished_at: datetime | None
    timeout_at: datetime | None
    end_reason: str | None


class CallHistoryCreate(OutboundSchemaBase):
    """记录一次拨号（内部 / Provider 回调用）。"""

    tenant_id: int = Field(gt=0)
    session_id: int | None = Field(default=None, gt=0)
    record_id: int | None = Field(default=None, gt=0)
    task_id: int | None = Field(default=None, gt=0)
    list_id: int | None = Field(default=None, gt=0)
    agent_id: int | None = Field(default=None, gt=0)
    phone: str = Field(min_length=1, max_length=32, description="被叫号码")
    call_status: CallStatus = CallStatus.INITIATED
    failure_reason: str | None = Field(default=None, max_length=255)
    started_at: datetime | None = None
    connected_at: datetime | None = None
    ended_at: datetime | None = None
    duration: int = Field(default=0, ge=0, description="通话时长（秒）")
    recording_path: str | None = Field(default=None, max_length=512)
    provider: str | None = Field(default=None, max_length=32)
    provider_call_id: str | None = Field(default=None, max_length=64)


class CallHistoryOut(OutboundOutBase):
    tenant_id: int
    session_id: int | None
    record_id: int | None
    task_id: int | None
    list_id: int | None
    agent_id: int | None
    phone: str
    call_status: CallStatus
    failure_reason: str | None
    started_at: datetime | None
    connected_at: datetime | None
    ended_at: datetime | None
    duration: int
    recording_path: str | None
    provider: str | None
    provider_call_id: str | None


class ServiceSummaryCreate(OutboundSchemaBase):
    """服务小结（§40）：一次会话一条。"""

    session_id: int = Field(gt=0)
    summary: str = Field(default="", description="小结内容")
    result: str = Field(default="", max_length=64, description="处理结果")
    tags: list[str] = Field(default_factory=list, description="标签")


class ServiceSummaryUpdate(OutboundUpdateBase):
    summary: str | None = None
    result: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = None


class ServiceSummaryOut(OutboundOutBase):
    tenant_id: int
    session_id: int
    agent_id: int | None
    summary: str
    result: str
    tags: list[str] | None


class AgentAssignmentCreate(OutboundSchemaBase):
    """坐席预占用（§35）：必须带过期时间。"""

    tenant_id: int = Field(gt=0)
    agent_id: int = Field(gt=0)
    task_id: int | None = Field(default=None, gt=0)
    record_id: int | None = Field(default=None, gt=0)
    expires_at: datetime | None = Field(default=None, description="预占过期时间")


class AgentAssignmentOut(OutboundOutBase):
    tenant_id: int
    agent_id: int
    task_id: int | None
    record_id: int | None
    status: AssignmentStatus
    reserved_at: datetime | None
    expires_at: datetime | None
    released_at: datetime | None
    release_reason: str | None


# ---------------- 执行引擎（P5）----------------


class OutboundBuildRecordsOut(OutboundSchemaBase):
    """生成待执行记录的幂等结果。"""

    task_id: int = Field(description="任务 ID")
    created: int = Field(description="本次新建的执行记录数")
    skipped: int = Field(description="已存在记录而跳过的名单行数")


class OutboundExecuteSummaryOut(OutboundSchemaBase):
    """一次批量执行的统计结果。"""

    task_id: int = Field(description="任务 ID")
    processed: int = Field(description="本次处理记录数")
    success: int = Field(description="呼叫成功")
    retry_waiting: int = Field(description="进入重试等待")
    exhausted: int = Field(description="重试已耗尽")
    failed: int = Field(description="失败（未配置重试或永久性失败）")
    task_completed: bool | None = Field(
        default=None,
        description="本次执行后任务是否已处理完毕并自动置为已完成（规则 2）",
    )


class OutboundRecordCallOut(OutboundSchemaBase):
    """单条记录的即时呼叫结果。"""

    record_id: int
    status: RecordStatus
    session_id: int | None = Field(default=None, description="本次呼叫所属会话")
    current_attempt: int = Field(description="本轮已尝试号码数")
    retry_count: int = Field(description="累计重试轮次")
    failure_reason: str | None = None


class OutboundRecycleResultOut(OutboundSchemaBase):
    """超时回收结果（§22）。"""

    scanned: int = Field(description="扫描到的超时记录数")
    recycled: int = Field(description="实际回收数（幂等：重复扫描不重复回收）")
    skipped: int = Field(description="复核后被跳过数")
    task_completed: int | None = Field(
        default=None, description="回收后自动完成的任务数（规则 2）"
    )


class CallResultCallbackIn(OutboundSchemaBase):
    """呼叫网关异步结果回调（§78 幂等）。

    NOTE：当前由内部调用方带登录态提交；接入真实网关时需改为签名校验（见报告 TODO）。
    """

    provider_call_id: str = Field(min_length=1, max_length=64, description="网关侧呼叫标识")
    call_status: CallStatus = Field(description="呼叫结果")
    duration: int = Field(default=0, ge=0, description="通话时长（秒）")
    failure_reason: str | None = Field(default=None, max_length=255)
    recording_path: str | None = Field(default=None, max_length=512)


class CallResultCallbackOut(OutboundSchemaBase):
    """回调处理结果。"""

    updated: bool = Field(description="是否更新了结果；false 表示命中幂等")
    record_status: str | None = Field(default=None, description="更新后的执行记录状态")
    reason: str | None = Field(default=None, description="未更新原因")


# ---------------- 坐席与自动分配（P6 / OB-018）----------------


class AgentDispatchItemOut(OutboundSchemaBase):
    """单次派单结果（示闲触发的返回值）。"""

    agent_id: int
    task_id: int
    record_id: int
    assignment_id: int
    expires_at: datetime | None = Field(default=None, description="预占过期时间")


class AgentStatusChangeResultOut(OutboundSchemaBase):
    """坐席状态变更结果；assignment 非空表示示闲后已自动派单。"""

    agent_id: int
    from_status: AgentStatus
    to_status: AgentStatus
    assignment: AgentDispatchItemOut | None = Field(
        default=None, description="示闲触发自动分配时返回派单结果"
    )


class AgentDispatchResultOut(OutboundSchemaBase):
    """批量自动派单统计。"""

    agents_scanned: int = Field(description="扫描到的空闲坐席数")
    assigned: int = Field(description="成功派单数")
    skipped: int = Field(description="无可派数据而跳过数")


class AgentReservationExpireOut(OutboundSchemaBase):
    """预占超时释放统计（§35）。"""

    scanned: int = Field(description="扫描到的过期预占数")
    released: int = Field(description="实际释放数（幂等）")
    skipped: int = Field(description="复核后跳过数")


class OutboundPredictionOut(OutboundSchemaBase):
    """预测外呼结果（§36）。"""

    task_id: int
    dispatch_mode: str = Field(description="派单模式")
    available_agents: int = Field(description="空闲坐席数")
    answer_rate: float = Field(description="统计窗口内的接通率")
    adjustment_factor: float = Field(description="任务配置的调整系数")
    max_concurrency: int = Field(description="任务配置的并发上限")
    target_concurrency: int = Field(description="建议并发（不超过任务并发上限）")
    uncapped_target: int = Field(description="未受并发上限约束前的建议并发")


# ---------------- 会话与看板（P7 / OB-021 / OB-023）----------------


class OutboundAgentWorklistItemOut(OutboundSchemaBase):
    """坐席工作台的待呼名单行（OB-021-1）。"""

    record_id: int
    record_status: RecordStatus
    task_id: int
    task_name: str
    list_id: int
    user_id: str | None = None
    order_id: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    phone_count: int = Field(description="按任务配置解析出的号码数量")
    phone_source: str = Field(default="", description="号码来源顺序说明")
    has_success: bool = Field(description="该名单是否已有接通记录（OB-021-1.4）")
    current_attempt: int
    retry_count: int
    last_failure_reason: str | None = None
    next_retry_at: datetime | None = None
    session_id: int | None = None


class OutboundListPhonesOut(OutboundSchemaBase):
    """名单号码解析与呼叫校验结果（OB-021-1.2/1.3/1.4/2.1/2.3）。"""

    list_id: int
    task_id: int
    task_name: str | None = None
    user_id: str | None = None
    order_id: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    phones: list[str] = Field(default_factory=list, description="按任务配置顺序解析出的号码")
    phone_source: str = Field(default="", description="号码来源顺序说明")
    list_phones: list[str] = Field(default_factory=list, description="名单自带号码")
    provider_phones: dict[str, list[str]] = Field(
        default_factory=dict, description="第三方电话簿返回的号码（按来源分组）"
    )
    record_id: int | None = None
    record_status: RecordStatus | None = None
    has_success: bool = Field(description="是否已有呼叫成功")
    success_phone: str | None = Field(default=None, description="已成功的号码")
    current_attempt: int = 0
    retry_count: int = 0
    max_retry_count: int | None = None
    retry_interval: int | None = Field(default=None, description="失败重试间隔（秒）")
    last_failure_reason: str | None = None
    next_retry_at: datetime | None = Field(default=None, description="下次可重试时间")


class OutboundSessionDetailOut(OutboundSchemaBase):
    """会话详情（§37）：会话 + 名单 + 号码 + 拨打历史 + 服务小结。"""

    session: OutboundSessionOut
    list_info: OutboundListOut | None = Field(default=None, description="名单信息，缺失返回 null")
    task_name: str | None = None
    phones: list[str] = Field(default_factory=list)
    phone_source: str = ""
    histories: list[CallHistoryOut] = Field(default_factory=list)
    summary: ServiceSummaryOut | None = Field(
        default=None, description="服务小结，缺失返回 null 由前端显示 -"
    )


class OutboundBoardOut(OutboundSchemaBase):
    """OB-023 外呼任务看板：名单信息 + 号码 + 拨打历史 + 服务小结 + 会话。"""
    list_info: OutboundListOut = Field(description="导入名单详细信息")
    phones: list[str] = Field(default_factory=list, description="按任务配置顺序解析出的呼叫号码")
    phone_source: str = Field(
        default="", description="号码来源说明，如 UserID / OrderID / 收件号码"
    )
    histories: list[CallHistoryOut] = Field(default_factory=list, description="拨打历史")
    sessions: list[OutboundSessionOut] = Field(default_factory=list, description="关联会话")
    summaries: list[ServiceSummaryOut] = Field(default_factory=list, description="服务小结")
    external_info: dict = Field(
        default_factory=dict, description="第三方号码接口返回信息（缺失时为空）"
    )


__all__ = [
    "AgentAssignmentCreate",
    "AgentAssignmentOut",
    "AgentDispatchItemOut",
    "AgentDispatchResultOut",
    "AgentReservationExpireOut",
    "AgentStatusChangeResultOut",
    "CallHistoryCreate",
    "CallHistoryOut",
    "CallResultCallbackIn",
    "CallResultCallbackOut",
    "OutboundAgentWorklistItemOut",
    "OutboundBoardOut",
    "OutboundBuildRecordsOut",
    "OutboundExecuteSummaryOut",
    "OutboundListPhonesOut",
    "OutboundPredictionOut",
    "OutboundRecordCallOut",
    "OutboundRecordOut",
    "OutboundRecycleResultOut",
    "OutboundSessionCreate",
    "OutboundSessionDetailOut",
    "OutboundSessionEnd",
    "OutboundSessionOut",
    "ServiceSummaryCreate",
    "ServiceSummaryOut",
    "ServiceSummaryUpdate",
]
