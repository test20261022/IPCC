"""IVR 域：流程 / 节点 / 流转条件。

对应需求：OB-017 IVR 外呼策略（转人工路由策略、IVR 有效按键处理）。
"""

from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin
from app.models.outbound.enums import (
    CommonStatus,
    IvrConditionType,
    IvrNodeType,
    NoAgentAction,
    enum_type,
)


class IvrFlow(Base, TimestampMixin, SoftDeleteMixin):
    """IVR 流程（§31）。

    入口节点用 entry_node_key 引用节点 key，避免 flow ↔ node 循环外键。
    """

    __tablename__ = "ivr_flows"
    __table_args__ = (
        Index("ix_ivr_flows_tenant_id", "tenant_id"),
        Index("ix_ivr_flows_status", "status"),
        Index(
            "uq_ivr_flows_tenant_code",
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
    entry_node_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="入口节点 key"
    )
    status: Mapped[CommonStatus] = mapped_column(
        enum_type(CommonStatus), default=CommonStatus.ENABLED, nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    nodes: Mapped[list["IvrNode"]] = relationship(
        back_populates="flow", cascade="all, delete-orphan"
    )
    transitions: Mapped[list["IvrTransition"]] = relationship(
        back_populates="flow", cascade="all, delete-orphan"
    )


class IvrNode(Base, TimestampMixin, SoftDeleteMixin):
    """IVR 节点（§31）。

    PLAY / COLLECT_DTMF / TRANSFER_AGENT / HANGUP / CALLBACK / REPLAY。
    非法按键重播超过 max_replay 次后挂断（§31 非法按键处理）。
    """

    __tablename__ = "ivr_nodes"
    __table_args__ = (
        Index(
            "uq_ivr_nodes_flow_key",
            "flow_id",
            "node_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_ivr_nodes_node_type", "node_type"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    flow_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("ivr_flows.id", ondelete="CASCADE"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="节点标识")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="节点名称")
    node_type: Mapped[IvrNodeType] = mapped_column(
        enum_type(IvrNodeType), nullable=False, comment="节点类型"
    )
    content: Mapped[str] = mapped_column(
        Text, default="", nullable=False, comment="播报话术 / 提示音"
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="节点扩展配置"
    )
    max_replay: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False, comment="最大重播次数，超过则挂断"
    )
    no_agent_action: Mapped[NoAgentAction | None] = mapped_column(
        enum_type(NoAgentAction),
        nullable=True,
        comment="转人工无可用坐席时的动作（§32，仅 TRANSFER_AGENT 节点使用）",
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    flow: Mapped["IvrFlow"] = relationship(back_populates="nodes")


class IvrTransition(Base, TimestampMixin, SoftDeleteMixin):
    """IVR 流转条件（§31）：按键 / 识别结果 / 时段 / 队列可用。"""

    __tablename__ = "ivr_transitions"
    __table_args__ = (
        Index("ix_ivr_transitions_flow_id", "flow_id"),
        Index("ix_ivr_transitions_from_node_id", "from_node_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    flow_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("ivr_flows.id", ondelete="CASCADE"), nullable=False
    )
    from_node_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("ivr_nodes.id", ondelete="CASCADE"), nullable=False
    )
    to_node_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("ivr_nodes.id", ondelete="SET NULL"),
        nullable=True,
        comment="目标节点，空表示结束",
    )
    condition_type: Mapped[IvrConditionType] = mapped_column(
        enum_type(IvrConditionType), nullable=False, comment="条件类型"
    )
    condition_value: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="条件值：按键值 / ASR 关键字 / 时段 / 队列"
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="命中优先级，越小越先匹配"
    )

    flow: Mapped["IvrFlow"] = relationship(back_populates="transitions")


__all__ = ["IvrFlow", "IvrNode", "IvrTransition"]
