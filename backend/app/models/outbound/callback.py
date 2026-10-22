"""回呼域：回呼流程与回呼任务。

对应需求：OB-029 IVR 回呼流程、OB-030 人工回呼流程。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin
from app.models.outbound.enums import (
    CallbackSource,
    CallbackStatus,
    CallbackTriggerType,
    CommonStatus,
    enum_type,
)


class CallbackFlow(Base, TimestampMixin, SoftDeleteMixin):
    """回呼流程配置（§45 触发条件）。"""

    __tablename__ = "callback_flows"
    __table_args__ = (
        Index("ix_callback_flows_tenant_id", "tenant_id"),
        Index("ix_callback_flows_status", "status"),
        Index(
            "uq_callback_flows_tenant_code",
            "tenant_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="流程编码")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="流程名称")
    trigger_condition: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="触发条件配置"
    )
    ivr_flow_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("ivr_flows.id", ondelete="RESTRICT"),
        nullable=True,
        comment="关联 IVR 流程",
    )
    status: Mapped[CommonStatus] = mapped_column(
        enum_type(CommonStatus), default=CommonStatus.ENABLED, nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class CallbackTask(Base, TimestampMixin, SoftDeleteMixin):
    """回呼任务（§46）。

    §78 幂等：同一 IVR 会话只能生成一条回呼任务，由部分唯一索引在数据库层兜底。
    """

    __tablename__ = "callback_tasks"
    __table_args__ = (
        Index("ix_callback_tasks_tenant_id", "tenant_id"),
        Index("ix_callback_tasks_status", "status"),
        Index("ix_callback_tasks_agent_id", "agent_id"),
        Index("ix_callback_tasks_phone", "phone"),
        Index("ix_callback_tasks_flow_id", "flow_id"),
        Index("ix_callback_tasks_task_id", "task_id"),
        # 到期回呼扫描（§45：到了计划时间就该派单）
        Index("ix_callback_tasks_scheduled_at", "scheduled_at"),
        Index(
            "uq_callback_tasks_ivr_session",
            "origin_session_id",
            unique=True,
            postgresql_where=text(
                "is_deleted = false AND source = 'IVR' AND origin_session_id IS NOT NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    flow_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("callback_flows.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[CallbackSource] = mapped_column(
        enum_type(CallbackSource), nullable=False, comment="来源：IVR 回呼 / 人工回呼"
    )
    task_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("outbound_tasks.id", ondelete="SET NULL"), nullable=True
    )
    list_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("outbound_lists.id", ondelete="SET NULL"), nullable=True
    )
    origin_session_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_sessions.id", ondelete="SET NULL"),
        nullable=True,
        comment="原会话（IVR 回呼幂等键）",
    )
    agent_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, comment="分配坐席"
    )

    phone: Mapped[str] = mapped_column(String(32), nullable=False, comment="回呼号码")
    status: Mapped[CallbackStatus] = mapped_column(
        enum_type(CallbackStatus), default=CallbackStatus.PENDING, nullable=False
    )
    trigger_type: Mapped[CallbackTriggerType | None] = mapped_column(
        enum_type(CallbackTriggerType),
        nullable=True,
        comment="命中的自动触发条件（§45）；人工回呼为空",
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="计划回呼时间，到期后才允许派单"
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str] = mapped_column(String(255), default="", nullable=False)


__all__ = ["CallbackFlow", "CallbackTask"]
