"""报表域 Schema（OB-025 话务流水报表 / OB-028 外呼实时监控报表）。"""

from datetime import datetime

from pydantic import Field

from app.models.outbound.enums import CallStatus
from app.schemas.outbound.base import OutboundSchemaBase


class CallFlowRecordOut(OutboundSchemaBase):
    """话务流水一行（呼叫历史 + 任务 / 场景 / 类型 / 坐席 / 名单归属）。"""

    id: int
    started_at: datetime | None
    phone: str = Field(description="被叫号码")
    source: str = Field(description="话务来源：OUTBOUND 外呼 / CALLBACK 回呼")
    task_id: int | None
    task_name: str | None
    scene_id: int | None
    scene_name: str | None
    type_id: int | None
    type_name: str | None
    type_level: int | None = Field(default=None, description="1 类型 / 2 子类型")
    agent_id: int | None
    agent_extension: str | None
    list_id: int | None
    user_id: str | None = Field(default=None, description="名单 UserID")
    order_id: str | None = Field(default=None, description="名单 OrderID")
    session_id: int | None
    callback_task_id: int | None
    call_status: CallStatus
    failure_reason: str | None
    connected_at: datetime | None
    ended_at: datetime | None
    duration: int = Field(description="通话时长（秒）")
    recording_path: str | None


class CallFlowSummaryOut(OutboundSchemaBase):
    """话务流水汇总（与明细同口径）。"""

    total: int = Field(description="话务总量")
    connected: int = Field(description="接通量")
    connect_rate: float = Field(description="接通率，0~1")
    total_duration: int = Field(description="通话总时长（秒）")
    avg_duration: int = Field(description="平均通话时长（秒，按接通量计算）")
    status_counts: dict[str, int] = Field(
        default_factory=dict, description="按呼叫结果分组计数"
    )


class CallFlowReportOut(OutboundSchemaBase):
    """话务流水报表：汇总 + 分页明细。"""

    summary: CallFlowSummaryOut
    items: list[CallFlowRecordOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


# ---------------- 实时监控（OB-028） ----------------


class MonitorCallStatsOut(OutboundSchemaBase):
    """监控窗口内的呼叫统计。"""

    initiated: int = Field(description="发起呼叫数")
    connected: int = Field(description="接通数")
    connect_rate: float = Field(description="接通率，0~1")
    total_duration: int = Field(description="通话总时长（秒）")
    avg_duration: int = Field(description="平均通话时长（秒）")


class MonitorTrendPointOut(OutboundSchemaBase):
    """按分钟分桶的趋势点。"""

    bucket: datetime = Field(description="时间桶起点")
    initiated: int = 0
    connected: int = 0


class MonitorTopTaskOut(OutboundSchemaBase):
    """窗口内呼叫量最高的任务。"""

    task_id: int
    task_name: str | None
    initiated: int = 0
    connected: int = 0
    connect_rate: float = 0.0


class RealtimeMonitorOut(OutboundSchemaBase):
    """外呼实时监控快照。"""

    tenant_id: int
    generated_at: datetime = Field(description="快照生成时间")
    window_minutes: int = Field(description="统计窗口（分钟）")
    calls: MonitorCallStatsOut = Field(description="窗口内呼叫统计")
    agent_status: dict[str, int] = Field(default_factory=dict, description="坐席各状态数量")
    task_status: dict[str, int] = Field(default_factory=dict, description="任务各状态数量")
    record_status: dict[str, int] = Field(
        default_factory=dict, description="执行记录各状态数量"
    )
    callback_status: dict[str, int] = Field(
        default_factory=dict, description="回呼任务各状态数量，DUE 为已到期待派单"
    )
    active_sessions: int = Field(default=0, description="进行中的会话数")
    trend: list[MonitorTrendPointOut] = Field(
        default_factory=list, description="窗口内按分钟的呼叫趋势"
    )
    top_tasks: list[MonitorTopTaskOut] = Field(
        default_factory=list, description="窗口内呼叫量排行"
    )


# ---------------- 筛选选项在各自模块的接口中提供 ----------------
# 场景 / 类型复用 /outbound/scenes/tree 与 /outbound/types，任务复用 /outbound/tasks，
# 避免为报表再造一套重复的选项接口。


__all__ = [
    "CallFlowRecordOut",
    "CallFlowReportOut",
    "CallFlowSummaryOut",
    "MonitorCallStatsOut",
    "MonitorTopTaskOut",
    "MonitorTrendPointOut",
    "RealtimeMonitorOut",
]
