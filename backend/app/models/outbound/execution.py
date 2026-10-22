"""执行域：执行记录 / 会话 / 呼叫历史 / 服务小结 / 坐席预占用。

对应需求：OB-008 策略执行、OB-018 自动分配、OB-021 外呼会话、OB-023 看板信息。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin
from app.models.outbound.enums import (
    AssignmentStatus,
    CallStatus,
    RecordStatus,
    SessionStatus,
    enum_type,
)


class OutboundRecord(Base, TimestampMixin, SoftDeleteMixin):
    """名单行的执行记录（§20 多号码执行 / §21 失败重试 / §22 超时回收）。

    §22 超时回收扫描的正是本表 status ∈ (ASSIGNED, CALLING) 且 timeout_at < now() 的行，
    回收必须幂等：同一行重复扫描只能产生一次有效回收。
    """

    __tablename__ = "outbound_records"
    __table_args__ = (
        # 同一名单行在同一任务下只允许一条执行记录，从数据库层杜绝重复执行（§73）
        Index(
            "uq_outbound_records_task_list",
            "task_id",
            "list_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_outbound_records_task_id", "task_id"),
        Index("ix_outbound_records_list_id", "list_id"),
        Index("ix_outbound_records_agent_id", "agent_id"),
        # 超时回收扫描索引（§22）
        Index("ix_outbound_records_status_timeout", "status", "timeout_at"),
        # 重试派发扫描索引（§21）
        Index("ix_outbound_records_status_retry", "status", "next_retry_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("outbound_tasks.id", ondelete="CASCADE"), nullable=False
    )
    list_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("outbound_lists.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, comment="执行坐席"
    )
    session_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_sessions.id", ondelete="SET NULL"),
        nullable=True,
        comment="当前会话",
    )

    status: Mapped[RecordStatus] = mapped_column(
        enum_type(RecordStatus), default=RecordStatus.PENDING, nullable=False
    )
    current_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="当前尝试的被叫号码"
    )
    current_attempt: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="本轮已尝试号码数"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="重试次数（§21）"
    )

    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="超时时间点，超过即回收"
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="下次重试时间（§21 失败后按间隔重试）"
    )
    last_call_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OutboundSession(Base, TimestampMixin, SoftDeleteMixin):
    """外呼会话（§37）：一次坐席呼叫过程，承载号码、呼叫状态、服务小结与录音。"""

    __tablename__ = "outbound_sessions"
    __table_args__ = (
        Index("ix_outbound_sessions_tenant_id", "tenant_id"),
        # OB-023 会话与外呼任务关联展示；OB-021 坐席名下名单
        Index("ix_outbound_sessions_task_id", "task_id"),
        Index("ix_outbound_sessions_list_id", "list_id"),
        Index("ix_outbound_sessions_agent_id", "agent_id"),
        Index("ix_outbound_sessions_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("outbound_tasks.id", ondelete="SET NULL"), nullable=True
    )
    list_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("outbound_lists.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[SessionStatus] = mapped_column(
        enum_type(SessionStatus), default=SessionStatus.CREATED, nullable=False
    )
    current_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="结束原因")

    histories: Mapped[list["CallHistory"]] = relationship(back_populates="session")


class CallHistory(Base, TimestampMixin):
    """呼叫历史（§39）：一次实际拨号一条，append-only，不做软删除。"""

    __tablename__ = "call_histories"
    __table_args__ = (
        # §25 报表按任务统计 / §51 号码维度查询 / §28 实时监控时间窗
        Index("ix_call_histories_task_id", "task_id"),
        Index("ix_call_histories_list_id", "list_id"),
        Index("ix_call_histories_record_id", "record_id"),
        Index("ix_call_histories_session_id", "session_id"),
        Index("ix_call_histories_phone", "phone"),
        Index("ix_call_histories_created_at", "created_at"),
        # 回呼拨打记录（OB-029 / OB-030），同时供报表区分外呼与回呼话务
        Index("ix_call_histories_callback_task_id", "callback_task_id"),
        # 网关结果回调按 provider_call_id 定位（§78 回调幂等）
        Index("ix_call_histories_provider_call_id", "provider_call_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("outbound_sessions.id", ondelete="SET NULL"), nullable=True
    )
    record_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("outbound_records.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(BigIntCol, nullable=True)
    list_id: Mapped[int | None] = mapped_column(BigIntCol, nullable=True)
    agent_id: Mapped[int | None] = mapped_column(BigIntCol, nullable=True)
    callback_task_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("callback_tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="所属回呼任务（OB-029 IVR 回呼 / OB-030 人工回呼）",
    )

    phone: Mapped[str] = mapped_column(String(32), nullable=False, comment="被叫号码")
    call_status: Mapped[CallStatus] = mapped_column(
        enum_type(CallStatus), default=CallStatus.INITIATED, nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="通话时长（秒）"
    )
    recording_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="录音路径，仅存路径不存二进制（§66）"
    )
    provider: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="呼叫网关 Provider"
    )
    provider_call_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="网关侧呼叫标识"
    )

    session: Mapped["OutboundSession | None"] = relationship(back_populates="histories")


class ServiceSummary(Base, TimestampMixin, SoftDeleteMixin):
    """服务小结（§40）：一次会话一条。"""

    __tablename__ = "service_summaries"
    __table_args__ = (
        Index(
            "uq_service_summaries_session",
            "session_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_service_summaries_agent_id", "agent_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("outbound_sessions.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False, comment="小结内容")
    result: Mapped[str] = mapped_column(String(64), default="", nullable=False, comment="处理结果")
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, comment="标签")


class AgentAssignment(Base, TimestampMixin, SoftDeleteMixin):
    """坐席预占用（§35）：预占必须带过期时间，且一个坐席同时只能被一个任务预占。"""

    __tablename__ = "agent_assignments"
    __table_args__ = (
        # 数据库层保证一个坐席不会被两个任务同时预占（§35 / §73）
        Index(
            "uq_agent_assignments_active_agent",
            "agent_id",
            unique=True,
            postgresql_where=text("is_deleted = false AND status IN ('RESERVED', 'ACCEPTED')"),
        ),
        Index("ix_agent_assignments_record_id", "record_id"),
        Index("ix_agent_assignments_task_id", "task_id"),
        Index("ix_agent_assignments_status", "status"),
        # 预占超时自动释放扫描
        Index("ix_agent_assignments_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    agent_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("outbound_tasks.id", ondelete="CASCADE"), nullable=True
    )
    record_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("outbound_records.id", ondelete="CASCADE"), nullable=True
    )

    status: Mapped[AssignmentStatus] = mapped_column(
        enum_type(AssignmentStatus), default=AssignmentStatus.RESERVED, nullable=False
    )
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="预占过期时间，超过即自动释放"
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


__all__ = [
    "AgentAssignment",
    "CallHistory",
    "OutboundRecord",
    "OutboundSession",
    "ServiceSummary",
]
