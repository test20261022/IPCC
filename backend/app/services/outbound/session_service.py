"""外呼会话服务（OB-021 会话列表与人工外呼 / §37 会话 / §40 服务小结）。

字段缺失统一返回 None，由前端显示 "-"，接口不报错（§40）。
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, ParamError
from app.models.outbound import ServiceSummary
from app.models.outbound.enums import RecordStatus
from app.repositories.outbound.list_repository import OutboundListRepository
from app.repositories.outbound.record_repository import OutboundRecordRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.schemas.outbound.execution import ServiceSummaryCreate, ServiceSummaryUpdate
from app.services.outbound.phone_resolver import OutboundPhoneResolver

logger = logging.getLogger(__name__)

#: 坐席工作台上「待呼 / 可呼」的执行记录状态（OB-021-1）
WORKLIST_STATUSES = [
    RecordStatus.ASSIGNED,
    RecordStatus.CALLING,
    RecordStatus.RETRY_WAITING,
]

#: 工作台「包含已结束」时追加的状态
FINISHED_STATUSES = [
    RecordStatus.SUCCESS,
    RecordStatus.FAILED,
    RecordStatus.EXHAUSTED,
    RecordStatus.TIMEOUT,
]


class OutboundSessionService:
    """会话、坐席工作台与服务小结。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.record_repo = OutboundRecordRepository(db)
        self.list_repo = OutboundListRepository(db)
        self.task_repo = OutboundTaskRepository(db)
        self.phone_resolver = OutboundPhoneResolver(db)

    # ---------- 坐席名下名单（OB-021-1）----------

    def list_agent_worklist(
        self, agent_id: int, *, page: int, page_size: int, include_finished: bool = False
    ) -> tuple[list[dict[str, Any]], int]:
        statuses = list(WORKLIST_STATUSES)
        if include_finished:
            statuses += FINISHED_STATUSES

        rows, total = self.record_repo.list_agent_worklist(
            agent_id=agent_id, statuses=statuses, page=page, page_size=page_size
        )

        items: list[dict[str, Any]] = []
        for record, name_list, task in rows:
            resolved = self.phone_resolver.resolve(task, name_list)
            items.append(
                {
                    "record_id": record.id,
                    "record_status": record.status,
                    "task_id": task.id,
                    "task_name": task.task_name,
                    "list_id": name_list.id,
                    "user_id": name_list.user_id,
                    "order_id": name_list.order_id,
                    "recipient_name": name_list.recipient_name,
                    "recipient_phone": name_list.recipient_phone,
                    "phone_count": len(resolved.phones),
                    "phone_source": resolved.phone_source,
                    "has_success": self.record_repo.find_success_phone(name_list.id) is not None,
                    "current_attempt": record.current_attempt,
                    "retry_count": record.retry_count,
                    "last_failure_reason": record.failure_reason,
                    "next_retry_at": record.next_retry_at,
                    "session_id": record.session_id,
                }
            )
        return items, total

    # ---------- 号码解析与呼叫校验（OB-021-1.2/1.3/1.4/2.1/2.3）----------

    def resolve_list_phones(self, list_id: int) -> dict[str, Any]:
        """解析名单呼叫号码，并给出「是否已呼叫成功」与重试信息。"""
        name_list = self.list_repo.get_by_id(list_id)
        if name_list is None:
            raise NotFound("名单不存在")

        task = self.task_repo.get_by_id(name_list.task_id)
        resolved = self.phone_resolver.resolve(task, name_list)
        record = self.record_repo.get_by_list_id(list_id)
        success_phone = self.record_repo.find_success_phone(list_id)

        return {
            "list_id": name_list.id,
            "task_id": name_list.task_id,
            "task_name": task.task_name if task else None,
            "user_id": name_list.user_id,
            "order_id": name_list.order_id,
            "recipient_name": name_list.recipient_name,
            "recipient_phone": name_list.recipient_phone,
            "phones": resolved.phones,
            "phone_source": resolved.phone_source,
            "list_phones": resolved.list_phones,
            "provider_phones": resolved.provider_phones,
            "record_id": record.id if record else None,
            "record_status": record.status if record else None,
            "has_success": success_phone is not None,
            "success_phone": success_phone,
            "current_attempt": record.current_attempt if record else 0,
            "retry_count": record.retry_count if record else 0,
            "max_retry_count": task.max_retry_count if task else None,
            "retry_interval": task.retry_interval if task else None,
            "last_failure_reason": record.failure_reason if record else None,
            "next_retry_at": record.next_retry_at if record else None,
        }

    # ---------- 会话（§37）----------

    def list_sessions(
        self, *, page: int, page_size: int, **filters: object
    ) -> tuple[list[Any], int]:
        items = self.record_repo.list_sessions_paged(
            page=page, page_size=page_size, **filters
        )
        total = self.record_repo.count_sessions(**filters)
        return items, total

    def get_session(self, session_id: int):
        session = self.record_repo.get_session(session_id)
        if session is None:
            raise NotFound("会话不存在")
        return session

    def get_session_detail(self, session_id: int) -> dict[str, Any]:
        """会话详情：会话 + 名单 + 号码 + 拨打历史 + 服务小结（§37 / §40）。"""
        session = self.get_session(session_id)

        name_list = self.list_repo.get_by_id(session.list_id) if session.list_id else None
        task = self.task_repo.get_by_id(session.task_id) if session.task_id else None

        phones: list[str] = []
        phone_source = ""
        if name_list is not None:
            resolved = self.phone_resolver.resolve(task, name_list)
            phones = resolved.phones
            phone_source = resolved.phone_source

        histories = [
            item
            for item in self.record_repo.list_histories_by_list(session.list_id or 0)
            if item.session_id == session.id
        ]

        return {
            "session": session,
            "list_info": name_list,
            "task_name": task.task_name if task else None,
            "phones": phones,
            "phone_source": phone_source,
            "histories": histories,
            "summary": self.get_summary(session_id),
        }

    # ---------- 服务小结（§40）----------

    def get_summary(self, session_id: int) -> ServiceSummary | None:
        stmt = select(ServiceSummary).where(
            ServiceSummary.session_id == session_id,
            ServiceSummary.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalars().first()

    def upsert_summary(
        self, session_id: int, payload: ServiceSummaryCreate | ServiceSummaryUpdate
    ) -> ServiceSummary:
        """提交服务小结：一会话一条，重复提交为覆盖（DB 部分唯一索引保证）。"""
        session = self.get_session(session_id)
        changes = payload.model_dump(exclude_unset=True)
        summary = self.get_summary(session_id)

        if summary is None:
            if isinstance(payload, ServiceSummaryUpdate):
                raise ParamError("该会话还没有服务小结，请先提交")
            summary = ServiceSummary(
                tenant_id=session.tenant_id,
                session_id=session_id,
                agent_id=session.agent_id,
                summary=changes.get("summary", ""),
                result=changes.get("result", ""),
                tags=changes.get("tags") or [],
            )
            self.db.add(summary)
        else:
            for field, value in changes.items():
                setattr(summary, field, value)

        self.db.commit()
        logger.info("服务小结已保存：session=%s summary_id=%s", session_id, summary.id)
        return summary
