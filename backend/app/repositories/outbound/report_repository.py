"""报表数据访问（OB-025 话务流水 / OB-028 实时监控）。

设计要点：
- 报表只读，聚合与过滤集中在此，避免在 Router / Service 里拼 SQL（§60）。
- 话务流水以 call_histories 为事实表（append-only，§39），左连任务 / 场景 / 类型 / 坐席 / 名单；
  左连**不过滤软删除**，保证历史话务在任务被删后仍能显示当时的归属名称。
- 回呼话务通过 callback_task_id 区分（OB-029 / OB-030 产生的拨打）。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.outbound import (
    Agent,
    CallbackTask,
    CallHistory,
    OutboundList,
    OutboundRecord,
    OutboundScene,
    OutboundSession,
    OutboundTask,
    OutboundType,
)
from app.models.outbound.enums import CallbackStatus, CallStatus, SessionStatus

#: 话务来源：全部 / 仅外呼 / 仅回呼
SOURCE_ALL = "ALL"
SOURCE_OUTBOUND = "OUTBOUND"
SOURCE_CALLBACK = "CALLBACK"


class CallFlowReportRepository:
    """话务流水报表查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 公共查询骨架 ----------

    def _base(
        self,
        *,
        tenant_id: int | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        scene_id: int | None = None,
        task_id: int | None = None,
        type_ids: list[int] | None = None,
        site_id: int | None = None,
        skill_queue_id: int | None = None,
        agent_id: int | None = None,
        call_status: CallStatus | None = None,
        source: str | None = None,
        phone: str | None = None,
    ) -> Select:
        """构造带左连的事实查询；过滤条件同时用于明细与汇总，避免两处口径不一致。"""
        stmt = (
            select(
                CallHistory.id,
                CallHistory.phone,
                CallHistory.call_status,
                CallHistory.failure_reason,
                CallHistory.started_at,
                CallHistory.connected_at,
                CallHistory.ended_at,
                CallHistory.duration,
                CallHistory.recording_path,
                CallHistory.session_id,
                CallHistory.task_id,
                CallHistory.list_id,
                CallHistory.agent_id,
                CallHistory.callback_task_id,
                OutboundTask.task_name.label("task_name"),
                OutboundTask.scene_id.label("scene_id"),
                OutboundScene.name.label("scene_name"),
                OutboundTask.type_id.label("type_id"),
                OutboundType.name.label("type_name"),
                OutboundType.level.label("type_level"),
                Agent.extension.label("agent_extension"),
                OutboundList.user_id.label("user_id"),
                OutboundList.order_id.label("order_id"),
            )
            .select_from(CallHistory)
            .outerjoin(OutboundTask, OutboundTask.id == CallHistory.task_id)
            .outerjoin(OutboundScene, OutboundScene.id == OutboundTask.scene_id)
            .outerjoin(OutboundType, OutboundType.id == OutboundTask.type_id)
            .outerjoin(Agent, Agent.id == CallHistory.agent_id)
            .outerjoin(OutboundList, OutboundList.id == CallHistory.list_id)
        )

        if tenant_id is not None:
            stmt = stmt.where(CallHistory.tenant_id == tenant_id)
        if started_from is not None:
            stmt = stmt.where(CallHistory.started_at >= started_from)
        if started_to is not None:
            stmt = stmt.where(CallHistory.started_at <= started_to)
        if scene_id is not None:
            stmt = stmt.where(OutboundTask.scene_id == scene_id)
        if task_id is not None:
            stmt = stmt.where(CallHistory.task_id == task_id)
        if type_ids:
            stmt = stmt.where(OutboundTask.type_id.in_(type_ids))
        if site_id is not None:
            stmt = stmt.where(OutboundTask.site_id == site_id)
        if skill_queue_id is not None:
            stmt = stmt.where(OutboundTask.skill_queue_id == skill_queue_id)
        if agent_id is not None:
            stmt = stmt.where(CallHistory.agent_id == agent_id)
        if call_status is not None:
            stmt = stmt.where(CallHistory.call_status == call_status)
        if source == SOURCE_CALLBACK:
            stmt = stmt.where(CallHistory.callback_task_id.is_not(None))
        elif source == SOURCE_OUTBOUND:
            stmt = stmt.where(CallHistory.callback_task_id.is_(None))
        if phone:
            stmt = stmt.where(CallHistory.phone.ilike(f"%{phone}%"))
        return stmt

    @staticmethod
    def _count_query(stmt: Select) -> Select:
        """把带连表的查询改造为计数查询（子查询包一层，避免连表放大计数）。"""
        return select(func.count()).select_from(stmt.subquery())

    # ---------- 明细 ----------

    def list_flow(
        self, *, page: int, page_size: int, **filters: Any
    ) -> tuple[list[Any], int]:
        offset = (page - 1) * page_size
        stmt = self._base(**filters).order_by(
            CallHistory.started_at.desc().nullslast(), CallHistory.id.desc()
        )
        rows = list(self.db.execute(stmt.offset(offset).limit(page_size)).all())
        total = int(self.db.execute(self._count_query(self._base(**filters))).scalar_one())
        return rows, total

    # ---------- 汇总 ----------

    def summarize_flow(self, **filters: Any) -> dict[str, Any]:
        """汇总：总量 / 接通量 / 接通率 / 通话时长（与明细同口径）。"""
        inner = self._base(**filters).subquery()
        stmt = select(
            func.count().label("total"),
            func.count()
            .filter(inner.c.call_status == CallStatus.CONNECTED)
            .label("connected"),
            func.coalesce(func.sum(inner.c.duration), 0).label("total_duration"),
        )
        row = self.db.execute(stmt).one()
        total = int(row.total or 0)
        connected = int(row.connected or 0)
        total_duration = int(row.total_duration or 0)
        return {
            "total": total,
            "connected": connected,
            "connect_rate": round(connected / total, 4) if total else 0.0,
            "total_duration": total_duration,
            "avg_duration": round(total_duration / connected) if connected else 0,
        }

    def count_flow_by_status(self, **filters: Any) -> dict[str, int]:
        """按呼叫结果分组计数（供饼图 / 失败原因分析）。"""
        inner = self._base(**filters).subquery()
        stmt = select(inner.c.call_status, func.count()).group_by(inner.c.call_status)
        counts: dict[str, int] = {}
        for status_value, amount in self.db.execute(stmt).all():
            key = status_value.value if hasattr(status_value, "value") else str(status_value)
            counts[key] = int(amount)
        return counts

    # ---------- 实时监控 ----------

    def window_call_stats(
        self, *, tenant_id: int, started_from: datetime, started_to: datetime
    ) -> dict[str, Any]:
        """统计窗口内的呼叫量（不连表，仅看事实表，保证监控查询足够快）。"""
        stmt = select(
            func.count().label("initiated"),
            func.count()
            .filter(CallHistory.call_status == CallStatus.CONNECTED)
            .label("connected"),
            func.coalesce(
                func.sum(CallHistory.duration).filter(
                    CallHistory.call_status == CallStatus.CONNECTED
                ),
                0,
            ).label("total_duration"),
        ).where(
            CallHistory.tenant_id == tenant_id,
            CallHistory.started_at >= started_from,
            CallHistory.started_at <= started_to,
        )
        row = self.db.execute(stmt).one()
        initiated = int(row.initiated or 0)
        connected = int(row.connected or 0)
        total_duration = int(row.total_duration or 0)
        return {
            "initiated": initiated,
            "connected": connected,
            "connect_rate": round(connected / initiated, 4) if initiated else 0.0,
            "total_duration": total_duration,
            "avg_duration": round(total_duration / connected) if connected else 0,
        }

    def call_trend(
        self, *, tenant_id: int, started_from: datetime, started_to: datetime
    ) -> list[dict[str, Any]]:
        """按分钟分桶的呼叫趋势（供实时监控折线图）。"""
        bucket = func.date_trunc("minute", CallHistory.started_at).label("bucket")
        stmt = (
            select(
                bucket,
                func.count().label("initiated"),
                func.count()
                .filter(CallHistory.call_status == CallStatus.CONNECTED)
                .label("connected"),
            )
            .where(
                CallHistory.tenant_id == tenant_id,
                CallHistory.started_at >= started_from,
                CallHistory.started_at <= started_to,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        return [
            {
                "bucket": row.bucket,
                "initiated": int(row.initiated or 0),
                "connected": int(row.connected or 0),
            }
            for row in self.db.execute(stmt).all()
        ]

    def top_tasks(
        self, *, tenant_id: int, started_from: datetime, started_to: datetime, limit: int = 5
    ) -> list[dict[str, Any]]:
        """窗口内呼叫量最高的任务（供实时监控排行）。"""
        stmt = (
            select(
                CallHistory.task_id,
                OutboundTask.task_name,
                func.count().label("initiated"),
                func.count()
                .filter(CallHistory.call_status == CallStatus.CONNECTED)
                .label("connected"),
            )
            .select_from(CallHistory)
            .outerjoin(OutboundTask, OutboundTask.id == CallHistory.task_id)
            .where(
                CallHistory.tenant_id == tenant_id,
                CallHistory.started_at >= started_from,
                CallHistory.started_at <= started_to,
                CallHistory.task_id.is_not(None),
            )
            .group_by(CallHistory.task_id, OutboundTask.task_name)
            .order_by(func.count().desc(), CallHistory.task_id.asc())
            .limit(limit)
        )
        results: list[dict[str, Any]] = []
        for row in self.db.execute(stmt).all():
            initiated = int(row.initiated or 0)
            connected = int(row.connected or 0)
            results.append(
                {
                    "task_id": int(row.task_id),
                    "task_name": row.task_name,
                    "initiated": initiated,
                    "connected": connected,
                    "connect_rate": round(connected / initiated, 4) if initiated else 0.0,
                }
            )
        return results

    def count_by_column(
        self,
        model: Any,
        column: Any,
        *,
        tenant_id: int | None = None,
        extra_conditions: list[Any] | None = None,
    ) -> dict[str, int]:
        """通用「按枚举列分组计数」，避免为每张表各写一个方法。"""
        stmt = select(column, func.count()).select_from(model)
        conditions: list[Any] = []
        if tenant_id is not None:
            conditions.append(model.tenant_id == tenant_id)
        if hasattr(model, "is_deleted"):
            conditions.append(model.is_deleted.is_(False))
        if extra_conditions:
            conditions.extend(extra_conditions)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.group_by(column)

        counts: dict[str, int] = {}
        for value, amount in self.db.execute(stmt).all():
            key = value.value if hasattr(value, "value") else str(value)
            counts[key] = int(amount)
        return counts

    def count_active_sessions(self, *, tenant_id: int) -> int:
        """进行中的会话数（未结束 / 未超时 / 未释放）。"""
        active = (
            SessionStatus.CREATED,
            SessionStatus.ASSIGNED,
            SessionStatus.CALLING,
            SessionStatus.CONNECTED,
        )
        stmt = select(func.count()).select_from(OutboundSession).where(
            OutboundSession.tenant_id == tenant_id,
            OutboundSession.is_deleted.is_(False),
            OutboundSession.status.in_(active),
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_callbacks(self, *, tenant_id: int) -> dict[str, int]:
        """回呼任务按状态计数，并单独给出「已到期待派单」数量。"""
        counts = self.count_by_column(
            CallbackTask, CallbackTask.status, tenant_id=tenant_id
        )
        stmt = select(func.count()).select_from(CallbackTask).where(
            CallbackTask.tenant_id == tenant_id,
            CallbackTask.is_deleted.is_(False),
            CallbackTask.status == CallbackStatus.PENDING,
            or_(CallbackTask.scheduled_at.is_(None), CallbackTask.scheduled_at <= func.now()),
        )
        counts["DUE"] = int(self.db.execute(stmt).scalar_one())
        return counts

    def count_records_by_status(self, *, tenant_id: int) -> dict[str, int]:
        return self.count_by_column(
            OutboundRecord, OutboundRecord.status, tenant_id=tenant_id
        )

    def count_tasks_by_status(self, *, tenant_id: int) -> dict[str, int]:
        return self.count_by_column(
            OutboundTask, OutboundTask.status, tenant_id=tenant_id
        )


__all__ = ["SOURCE_ALL", "SOURCE_CALLBACK", "SOURCE_OUTBOUND", "CallFlowReportRepository"]
