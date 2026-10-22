"""外呼任务域：任务主表与任务号码配置。

对应需求：OB-006 任务列表查询增强、OB-008 策略配置及执行、OB-017 IVR 策略、
OB-018 自动分配、OB-020 任务复制。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin
from app.models.outbound.enums import (
    DispatchMode,
    NumberSelectStrategy,
    TaskStatus,
    enum_type,
)


class OutboundTask(Base, TimestampMixin, SoftDeleteMixin):
    """外呼任务（§17）。

    策略 / 重试 / 超时配置集中在本表，禁止散落在执行代码中（§36）。
    """

    __tablename__ = "outbound_tasks"
    __table_args__ = (
        Index("ix_outbound_tasks_tenant_id", "tenant_id"),
        Index("ix_outbound_tasks_status", "status"),
        # OB-006 列表按站点 / 技能队列 / 外呼类型查询；OB-003 场景引用校验
        Index("ix_outbound_tasks_site_id", "site_id"),
        Index("ix_outbound_tasks_skill_queue_id", "skill_queue_id"),
        Index("ix_outbound_tasks_type_id", "type_id"),
        Index("ix_outbound_tasks_scene_id", "scene_id"),
        Index("ix_outbound_tasks_copied_from_id", "copied_from_id"),
        # 同租户内任务名唯一：同时让 OB-020 复制具备幂等语义（同名副本视为同一次复制）
        Index(
            "uq_outbound_tasks_tenant_name",
            "tenant_id",
            "task_name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称")
    site_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("sites.id", ondelete="RESTRICT"), nullable=True, comment="站点"
    )
    skill_queue_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("skill_queues.id", ondelete="RESTRICT"),
        nullable=True,
        comment="外呼技能队列（OB-008 / OB-018）",
    )
    type_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_types.id", ondelete="RESTRICT"),
        nullable=True,
        comment="外呼类型",
    )
    scene_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_scenes.id", ondelete="RESTRICT"),
        nullable=True,
        comment="外呼场景",
    )

    status: Mapped[TaskStatus] = mapped_column(
        enum_type(TaskStatus), default=TaskStatus.DRAFT, nullable=False, comment="任务状态"
    )
    dispatch_mode: Mapped[DispatchMode] = mapped_column(
        enum_type(DispatchMode),
        default=DispatchMode.MANUAL,
        nullable=False,
        comment="派单模式：MANUAL 人工 / AUTO 自动分配 / PREDICTIVE 预测外呼",
    )
    number_select_strategy: Mapped[NumberSelectStrategy] = mapped_column(
        enum_type(NumberSelectStrategy),
        default=NumberSelectStrategy.ORDER,
        nullable=False,
        comment="主叫号码选取策略（§14）",
    )

    # ---- 重试与超时策略（§20 / §21 / §22）----
    retry_interval: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False, comment="失败重试间隔（秒，ASSUMPTION-012）"
    )
    max_retry_count: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False, comment="最大重试次数"
    )
    call_timeout_seconds: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False, comment="单次呼叫超时（秒），超时进入回收流程"
    )
    max_concurrency: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False, comment="最大并发呼叫数（§43）"
    )
    adjustment_factor: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("1.00"), nullable=False, comment="预测外呼调整系数（§36）"
    )

    # ---- IVR 配置（OB-017）----
    ivr_flow_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("ivr_flows.id", ondelete="RESTRICT"),
        nullable=True,
        comment="IVR 流程",
    )
    copied_from_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="复制来源任务（OB-020，用于幂等与追溯）",
    )

    description: Mapped[str] = mapped_column(Text, default="", nullable=False, comment="任务说明")
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="任务优先级，数值越小越先派单（§34 排序维度）",
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task_numbers: Mapped[list["OutboundTaskNumber"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="selectin"
    )


class OutboundTaskNumber(Base, TimestampMixin, SoftDeleteMixin):
    """任务号码配置（§19）。

    一行同时承载两件事：
    1. 任务与主叫号码的绑定（number_id，多对多中的一条）；
    2. 被叫号码来源的启用与调用顺序（§20 / §23：OrderID / UserID / 收件人号码）。

    ASSUMPTION-011：需求 §19 未区分上述两者，故按字面实现——
    order_id / user_id / recipient_number 存该来源的调用顺序（1 起，NULL 表示该来源不启用），
    sort_order 为主叫号码选取顺序，priority 为整行优先级，enabled 为启用开关。
    """

    __tablename__ = "outbound_task_numbers"
    __table_args__ = (
        Index("ix_outbound_task_numbers_task_id", "task_id"),
        Index("ix_outbound_task_numbers_number_id", "number_id"),
        Index(
            "uq_outbound_task_numbers_task_number",
            "task_id",
            "number_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntCol, nullable=False, comment="归属租户")
    task_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("outbound_tasks.id", ondelete="CASCADE"), nullable=False
    )
    number_id: Mapped[int] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_numbers.id", ondelete="RESTRICT"),
        nullable=False,
        comment="主叫号码",
    )
    order_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="OrderID 来源顺序，NULL 表示不启用"
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="UserID 来源顺序，NULL 表示不启用"
    )
    recipient_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="收件人号码来源顺序，NULL 表示不启用"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="主叫号码选取顺序"
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="行优先级")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")

    task: Mapped["OutboundTask"] = relationship(back_populates="task_numbers")


__all__ = ["OutboundTask", "OutboundTaskNumber"]
