"""外呼基础配置域：租户 / 站点 / 技能队列 / 坐席 / 外呼类型 / 外呼场景 / 外呼号码。

对应需求：OB-001 外呼号码管理、OB-003 外呼场景管理、OB-004 外呼类型管理、OB-005 主叫号码使用规则。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin
from app.models.outbound.enums import AgentStatus, CommonStatus, enum_type


class Tenant(Base, TimestampMixin, SoftDeleteMixin):
    """租户（§60 数据权限的第一层）。"""

    __tablename__ = "tenants"
    __table_args__ = (
        Index(
            "uq_tenants_code_active",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="租户编码")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="租户名称")
    status: Mapped[CommonStatus] = mapped_column(
        enum_type(CommonStatus), default=CommonStatus.ENABLED, nullable=False, comment="状态"
    )
    remark: Mapped[str] = mapped_column(String(255), default="", nullable=False, comment="备注")


class Site(Base, TimestampMixin, SoftDeleteMixin):
    """站点。"""

    __tablename__ = "sites"
    __table_args__ = (
        Index("ix_sites_tenant_id", "tenant_id"),
        Index(
            "uq_sites_tenant_code",
            "tenant_id",
            "code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, comment="租户"
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="站点编码")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="站点名称")
    status: Mapped[CommonStatus] = mapped_column(
        enum_type(CommonStatus), default=CommonStatus.ENABLED, nullable=False
    )
    remark: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class SkillQueue(Base, TimestampMixin, SoftDeleteMixin):
    """技能队列。"""

    __tablename__ = "skill_queues"
    __table_args__ = (
        Index("ix_skill_queues_tenant_id", "tenant_id"),
        Index("ix_skill_queues_site_id", "site_id"),
        Index(
            "uq_skill_queues_tenant_code",
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
    site_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, comment="所属站点"
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="队列编码")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="队列名称")
    status: Mapped[CommonStatus] = mapped_column(
        enum_type(CommonStatus), default=CommonStatus.ENABLED, nullable=False
    )
    remark: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class Agent(Base, TimestampMixin, SoftDeleteMixin):
    """坐席。

    §3.1：必须关联 users.id，禁止建立第二套账号体系。
    """

    __tablename__ = "agents"
    __table_args__ = (
        # 一个用户最多对应一个坐席
        Index(
            "uq_agents_user_active",
            "user_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_agents_tenant_id", "tenant_id"),
        Index("ix_agents_skill_queue_id", "skill_queue_id"),
        Index("ix_agents_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntCol,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="关联 users.id",
    )
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("sites.id", ondelete="RESTRICT"), nullable=True
    )
    skill_queue_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("skill_queues.id", ondelete="RESTRICT"),
        nullable=True,
        comment="技能队列",
    )
    status: Mapped[AgentStatus] = mapped_column(
        enum_type(AgentStatus), default=AgentStatus.OFFLINE, nullable=False, comment="坐席状态"
    )
    extension: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="分机号")
    last_idle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_busy_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentStatusLog(Base, TimestampMixin):
    """坐席状态变更历史（§11：所有状态变化必须记录历史）。"""

    __tablename__ = "agent_status_logs"
    __table_args__ = (Index("ix_agent_status_logs_agent_created", "agent_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[AgentStatus | None] = mapped_column(
        enum_type(AgentStatus), nullable=True, comment="变更前状态"
    )
    to_status: Mapped[AgentStatus] = mapped_column(
        enum_type(AgentStatus), nullable=False, comment="变更后状态"
    )
    reason: Mapped[str] = mapped_column(String(255), default="", nullable=False, comment="变更原因")
    operator_id: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="操作人"
    )


class OutboundType(Base, TimestampMixin, SoftDeleteMixin):
    """外呼类型（OB-004）。

    ASSUMPTION-009：OB-025 报表需要「外呼类型 / 子类型」筛选，故采用 parent_id 两级自关联，
    一级为类型、二级为子类型；若子类型另有来源，仅需调整本表即可。
    """

    __tablename__ = "outbound_types"
    __table_args__ = (
        Index("ix_outbound_types_tenant_id", "tenant_id"),
        Index("ix_outbound_types_parent_id", "parent_id"),
        Index(
            "uq_outbound_types_tenant_code",
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
    parent_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_types.id", ondelete="RESTRICT"),
        nullable=True,
        comment="父类型",
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="类型编码")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="类型名称")
    level: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="层级：1 类型 / 2 子类型"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="排序")
    status: Mapped[CommonStatus] = mapped_column(
        enum_type(CommonStatus), default=CommonStatus.ENABLED, nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    children: Mapped[list["OutboundType"]] = relationship(back_populates="parent")
    parent: Mapped["OutboundType | None"] = relationship(
        back_populates="children", remote_side="OutboundType.id"
    )


class OutboundScene(Base, TimestampMixin, SoftDeleteMixin):
    """外呼场景（OB-003）。

    两级结构：parent_id 为空即一级场景；删除一级场景时联动软删除其下全部二级场景。
    """

    __tablename__ = "outbound_scenes"
    __table_args__ = (
        Index("ix_outbound_scenes_tenant_id", "tenant_id"),
        # OB-003：列表按外呼类型筛选 / 一级场景联动二级场景
        Index("ix_outbound_scenes_type_id", "type_id"),
        Index("ix_outbound_scenes_parent_id", "parent_id"),
        Index("ix_outbound_scenes_level", "level"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    type_id: Mapped[int] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_types.id", ondelete="RESTRICT"),
        nullable=False,
        comment="所属外呼类型",
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("outbound_scenes.id", ondelete="RESTRICT"),
        nullable=True,
        comment="父场景，空表示一级场景",
    )
    level: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="层级：1 一级场景 / 2 二级场景"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="场景名称")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[CommonStatus] = mapped_column(
        enum_type(CommonStatus), default=CommonStatus.ENABLED, nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class OutboundNumber(Base, TimestampMixin, SoftDeleteMixin):
    """外呼号码（主叫号码，OB-001 / OB-005）。

    §12 业务规则：display_name 必填、caller_number 格式校验、tenant_id 匹配、status 可用、
    used_count < usage_limit。次数扣减必须走原子 UPDATE（§13），禁止读改写。
    """

    __tablename__ = "outbound_numbers"
    __table_args__ = (
        Index("ix_outbound_numbers_tenant_id", "tenant_id"),
        Index("ix_outbound_numbers_status", "status"),
        Index(
            "uq_outbound_numbers_tenant_caller",
            "tenant_id",
            "caller_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, comment="归属租户"
    )
    display_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="外显名称（必填）"
    )
    caller_number: Mapped[str] = mapped_column(String(32), nullable=False, comment="主叫号码")
    number_type: Mapped[str] = mapped_column(
        String(32),
        default="",
        nullable=False,
        comment="号码类型（ASSUMPTION-010：需求未定义取值，暂存自由文本）",
    )
    usage_limit: Mapped[int | None] = mapped_column(
        BigIntCol, nullable=True, comment="使用次数上限，空表示不限"
    )
    used_count: Mapped[int] = mapped_column(
        BigIntCol, default=0, nullable=False, comment="已使用次数（仅原子自增）"
    )
    status: Mapped[CommonStatus] = mapped_column(
        enum_type(CommonStatus), default=CommonStatus.ENABLED, nullable=False
    )
    remark: Mapped[str] = mapped_column(String(255), default="", nullable=False)


# 供 Alembic / 其他模块引用的导出列表
__all__ = [
    "Agent",
    "AgentStatusLog",
    "OutboundNumber",
    "OutboundScene",
    "OutboundType",
    "Site",
    "SkillQueue",
    "Tenant",
]
