"""外呼任务看板服务（OB-023 / §41）。

聚合「名单信息 + 呼叫号码（按任务配置顺序）+ 拨打历史 + 会话 + 服务小结 + 接口信息」，
号码顺序严格来自任务配置，不由数据库默认顺序决定（§41）。
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.models.outbound import CallHistory, ServiceSummary
from app.repositories.outbound.list_repository import OutboundListRepository
from app.repositories.outbound.record_repository import OutboundRecordRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.services.outbound.phone_resolver import OutboundPhoneResolver

logger = logging.getLogger(__name__)


class OutboundBoardService:
    """任务看板聚合查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.list_repo = OutboundListRepository(db)
        self.record_repo = OutboundRecordRepository(db)
        self.task_repo = OutboundTaskRepository(db)
        self.phone_resolver = OutboundPhoneResolver(db)

    def list_histories(self, list_id: int) -> list[CallHistory]:
        """拨打历史（OB-023-2）。"""
        if self.list_repo.get_by_id(list_id) is None:
            raise NotFound("名单不存在")
        return self.record_repo.list_histories_by_list(list_id)

    def build_board(self, list_id: int) -> dict[str, Any]:
        """任务看板聚合数据。"""
        name_list = self.list_repo.get_by_id(list_id)
        if name_list is None:
            raise NotFound("名单不存在")

        task = self.task_repo.get_by_id(name_list.task_id)
        resolved = self.phone_resolver.resolve(task, name_list)
        sessions = self.record_repo.list_sessions_by_list(list_id)
        summaries = self._list_summaries([item.id for item in sessions])

        return {
            "list_info": name_list,
            "phones": resolved.phones,
            "phone_source": resolved.phone_source,
            "histories": self.record_repo.list_histories_by_list(list_id),
            "sessions": sessions,
            "summaries": summaries,
            "external_info": {
                "provider": self.phone_resolver.phone_provider.name,
                "source_order": resolved.source_order,
                "list_phones": resolved.list_phones,
                "provider_phones": resolved.provider_phones,
                "task_id": name_list.task_id,
                "task_name": task.task_name if task else None,
            },
        }

    # ---------- 内部 ----------

    def _list_summaries(self, session_ids: list[int]) -> list[ServiceSummary]:
        if not session_ids:
            return []
        stmt = (
            select(ServiceSummary)
            .where(
                ServiceSummary.session_id.in_(session_ids),
                ServiceSummary.is_deleted.is_(False),
            )
            .order_by(ServiceSummary.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())
