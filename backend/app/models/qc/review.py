"""质检任务域：专家组 / 组成员 / 质检任务 / 质检明细项 / 评分结果。

10 万条记录的派发落在 qc_task_items：该表刻意保持"窄"（只有约 10 个短列），
grade 直接冗余在此表上，使完成率与等级聚合不必回表 qc_review_results。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntCol, BigIntPK, SoftDeleteMixin, TimestampMixin
from app.models.outbound.enums import enum_type
from app.models.qc.enums import QcDispatchMode, QcGrade, QcItemStatus, QcTaskStatus


class QcReviewerGroup(Base, TimestampMixin, SoftDeleteMixin):
    """专家组：一组承担质检工作的用户（成员见 QcReviewerGroupMember）。"""

    __tablename__ = "qc_reviewer_groups"
    __table_args__ = (
        Index(
            "uq_qc_reviewer_groups_tenant_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="专家组名称")
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class QcReviewerGroupMember(Base, TimestampMixin, SoftDeleteMixin):
    """专家组成员。

    user_id 只读引用 users.id（models/user.py 为基线冻结，不新增专家表）。
    """

    __tablename__ = "qc_reviewer_group_members"
    __table_args__ = (
        Index(
            "uq_qc_reviewer_group_members_group_user",
            "group_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_qc_reviewer_group_members_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntCol, nullable=False, comment="归属租户")
    group_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("qc_reviewer_groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, comment="专家账号"
    )
    is_active: Mapped[bool] = mapped_column(
        default=True, nullable=False, comment="是否参与派发"
    )
    max_concurrent: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False, comment="单轮质检上限（默认 50 条/人）"
    )


class QcTask(Base, TimestampMixin, SoftDeleteMixin):
    """质检任务：以时间区间从对话池中圈定范围，一次派发产生全部明细项。"""

    __tablename__ = "qc_tasks"
    __table_args__ = (Index("ix_qc_tasks_tenant_status", "tenant_id", "status"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称")
    group_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("qc_reviewer_groups.id", ondelete="RESTRICT"),
        nullable=True,
        comment="承接专家组",
    )

    time_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="对话开始时间下界（含）"
    )
    time_to: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="对话开始时间上界（含）"
    )

    status: Mapped[QcTaskStatus] = mapped_column(
        enum_type(QcTaskStatus), default=QcTaskStatus.DRAFT, nullable=False
    )
    dispatch_mode: Mapped[QcDispatchMode] = mapped_column(
        enum_type(QcDispatchMode), default=QcDispatchMode.ROUND_ROBIN, nullable=False
    )
    total_items: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="明细项总数"
    )
    completed_items: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="已完成数"
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        BigIntCol, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class QcTaskItem(Base, TimestampMixin, SoftDeleteMixin):
    """质检明细项：一条对话在某个任务下只允许一条明细（数据库层杜绝重复派发）。"""

    __tablename__ = "qc_task_items"
    __table_args__ = (
        # 派发幂等的唯一目标（ON CONFLICT 的 index_where 必须与此处完全一致）
        Index(
            "uq_qc_task_items_task_conversation",
            "task_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_qc_task_items_task_status", "task_id", "status"),
        Index("ix_qc_task_items_reviewer_status", "reviewer_id", "status"),
        # 超时回收扫描
        Index("ix_qc_task_items_status_timeout", "status", "timeout_at"),
        Index("ix_qc_task_items_task_grade", "task_id", "grade"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntCol, nullable=False, comment="归属租户")
    task_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("qc_tasks.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        BigIntCol,
        ForeignKey("qc_conversations.id", ondelete="RESTRICT"),
        nullable=False,
        comment="被质检对话；RESTRICT 防止误删在检对话",
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        BigIntCol,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        comment="派发/领取到的专家；派发时即写入",
    )

    status: Mapped[QcItemStatus] = mapped_column(
        enum_type(QcItemStatus), default=QcItemStatus.PENDING, nullable=False
    )
    grade: Mapped[QcGrade | None] = mapped_column(
        enum_type(QcGrade), nullable=True, comment="质检等级，提交时由 score 判定写回"
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="领取时间"
    )
    timeout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="领取超时时间点，超过即回收"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QcReviewResult(Base, TimestampMixin, SoftDeleteMixin):
    """质检评分结果：一条明细一条，承载评分明细与评语（宽字段集中在此，不拖累明细表）。"""

    __tablename__ = "qc_review_results"
    __table_args__ = (
        Index(
            "uq_qc_review_results_item",
            "item_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_qc_review_results_reviewer_reviewed_at", "reviewer_id", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigIntCol, nullable=False, comment="归属租户")
    item_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("qc_task_items.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        BigIntCol, nullable=False, comment="冗余便于报表连表"
    )
    reviewer_id: Mapped[int] = mapped_column(
        BigIntCol, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    score: Mapped[int] = mapped_column(Integer, nullable=False, comment="百分制得分")
    grade: Mapped[QcGrade] = mapped_column(enum_type(QcGrade), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False, comment="评语")
    score_detail: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="分项得分明细"
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="提交时间（日报分桶依据，存 UTC）"
    )


__all__ = [
    "QcReviewResult",
    "QcReviewerGroup",
    "QcReviewerGroupMember",
    "QcTask",
    "QcTaskItem",
]