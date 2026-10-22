"""报表服务（OB-025 话务流水报表 / OB-028 外呼实时监控报表）。

OB-025 说明：需求要求话务流水报表增加「外呼场景 / 外呼任务 / 外呼类型 / 外呼子类型」筛选，
本模块按新报表实现（原系统不存在，P0 已与需求方确认）。
- 类型筛选：选了「外呼类型」（一级）时自动纳入其全部「外呼子类型」（二级）的任务；
- 子类型筛选：精确按二级类型过滤，与类型筛选互斥（同时传时以子类型为准）。
"""

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, ParamError
from app.repositories.outbound.agent_repository import OutboundAgentRepository
from app.repositories.outbound.report_repository import (
    SOURCE_CALLBACK,
    SOURCE_OUTBOUND,
    CallFlowReportRepository,
)
from app.repositories.outbound.type_repository import OutboundTypeRepository

logger = logging.getLogger(__name__)

#: 趋势分桶固定为 1 分钟；窗口上限由接口层限制，避免返回过长的序列
TREND_BUCKET = timedelta(minutes=1)


class OutboundReportService:
    """报表业务。只读，不产生写操作。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CallFlowReportRepository(db)
        self.type_repo = OutboundTypeRepository(db)
        self.agent_repo = OutboundAgentRepository(db)

    # ---------------- OB-025 话务流水报表 ----------------

    def call_flow_report(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        type_id: int | None = None,
        sub_type_id: int | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        """话务流水：汇总 + 分页明细，两者口径完全一致。"""
        type_ids = self._resolve_type_ids(
            type_id=type_id, sub_type_id=sub_type_id, tenant_id=tenant_id
        )
        params: dict[str, Any] = {"tenant_id": tenant_id}
        params.update(filters)
        if type_ids:
            params["type_ids"] = type_ids

        rows, total = self.repo.list_flow(page=page, page_size=page_size, **params)
        summary = self.repo.summarize_flow(**params)
        summary["status_counts"] = self.repo.count_flow_by_status(**params)

        logger.info(
            "话务流水报表查询：tenant=%s 条件=%s 命中=%s",
            tenant_id,
            sorted(key for key, value in params.items() if value is not None),
            total,
        )
        return {
            "summary": summary,
            "items": [self._to_flow_record(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _resolve_type_ids(
        self,
        *,
        type_id: int | None,
        sub_type_id: int | None,
        tenant_id: int | None,
    ) -> list[int] | None:
        """把「类型 / 子类型」两个筛选维度归一成待匹配的类型 ID 集合。"""
        if sub_type_id is not None:
            child = self.type_repo.get_by_id(sub_type_id)
            if child is None:
                raise NotFound("外呼子类型不存在")
            if child.level != 2:
                raise ParamError("所选外呼子类型不是二级类型")
            self._ensure_same_tenant(child.tenant_id, tenant_id)
            return [sub_type_id]

        if type_id is not None:
            parent = self.type_repo.get_by_id(type_id)
            if parent is None:
                raise NotFound("外呼类型不存在")
            self._ensure_same_tenant(parent.tenant_id, tenant_id)
            children = self.type_repo.list_paged(page=1, page_size=200, parent_id=type_id)
            return [type_id, *[child.id for child in children]]

        return None

    @staticmethod
    def _ensure_same_tenant(type_tenant_id: int, tenant_id: int | None) -> None:
        if tenant_id is not None and type_tenant_id != tenant_id:
            raise ParamError("外呼类型与查询租户不一致")

    @staticmethod
    def _to_flow_record(row: Any) -> dict[str, Any]:
        """把连表查询行转成响应结构。"""
        return {
            "id": row.id,
            "started_at": row.started_at,
            "phone": row.phone,
            "source": SOURCE_CALLBACK if row.callback_task_id else SOURCE_OUTBOUND,
            "task_id": row.task_id,
            "task_name": row.task_name,
            "scene_id": row.scene_id,
            "scene_name": row.scene_name,
            "type_id": row.type_id,
            "type_name": row.type_name,
            "type_level": row.type_level,
            "agent_id": row.agent_id,
            "agent_extension": row.agent_extension,
            "list_id": row.list_id,
            "user_id": row.user_id,
            "order_id": row.order_id,
            "session_id": row.session_id,
            "callback_task_id": row.callback_task_id,
            "call_status": row.call_status,
            "failure_reason": row.failure_reason,
            "connected_at": row.connected_at,
            "ended_at": row.ended_at,
            "duration": int(row.duration or 0),
            "recording_path": row.recording_path,
        }

    # ---------------- OB-028 实时监控报表 ----------------

    def realtime_monitor(self, *, tenant_id: int, window_minutes: int = 30) -> dict[str, Any]:
        """实时监控快照：窗口呼叫统计 + 各域状态分布 + 趋势 + 任务排行。"""
        now = datetime.now(timezone.utc)
        started_from = now - timedelta(minutes=window_minutes)

        calls = self.repo.window_call_stats(
            tenant_id=tenant_id, started_from=started_from, started_to=now
        )
        trend = self._fill_trend(
            self.repo.call_trend(
                tenant_id=tenant_id, started_from=started_from, started_to=now
            ),
            started_from=started_from,
            now=now,
        )

        snapshot = {
            "tenant_id": tenant_id,
            "generated_at": now,
            "window_minutes": window_minutes,
            "calls": calls,
            "agent_status": self.agent_repo.count_by_status(tenant_id=tenant_id),
            "task_status": self.repo.count_tasks_by_status(tenant_id=tenant_id),
            "record_status": self.repo.count_records_by_status(tenant_id=tenant_id),
            "callback_status": self.repo.count_callbacks(tenant_id=tenant_id),
            "active_sessions": self.repo.count_active_sessions(tenant_id=tenant_id),
            "trend": trend,
            "top_tasks": self.repo.top_tasks(
                tenant_id=tenant_id, started_from=started_from, started_to=now
            ),
        }
        logger.info(
            "实时监控快照：tenant=%s 窗口=%s 分钟 发起=%s 接通=%s",
            tenant_id,
            window_minutes,
            calls["initiated"],
            calls["connected"],
        )
        return snapshot

    @staticmethod
    def _fill_trend(
        rows: Iterable[dict[str, Any]], *, started_from: datetime, now: datetime
    ) -> list[dict[str, Any]]:
        """把稀疏的分钟桶补成连续序列，便于前端直接画折线。"""
        buckets: dict[datetime, dict[str, int]] = {}
        for row in rows:
            bucket = row["bucket"]
            buckets[bucket] = {
                "initiated": row["initiated"],
                "connected": row["connected"],
            }

        filled: list[dict[str, Any]] = []
        cursor = started_from.replace(second=0, microsecond=0)
        last = now.replace(second=0, microsecond=0)
        while cursor <= last:
            item = buckets.get(cursor, {"initiated": 0, "connected": 0})
            filled.append(
                {
                    "bucket": cursor,
                    "initiated": item["initiated"],
                    "connected": item["connected"],
                }
            )
            cursor += TREND_BUCKET
        return filled


__all__ = ["TREND_BUCKET", "OutboundReportService"]
