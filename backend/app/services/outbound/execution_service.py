"""外呼执行引擎（OB-008 / §20 多号码顺序 / §21 重试阶梯 / §38 人工外呼）。

职责边界：
- 本服务负责「执行」：取号 → 选主叫 → 扣次数 → 呼叫 → 记录结果 → 决定重试。
- 坐席自动分配 / 预占与派单属于 OB-018（P6），本服务只接受可选的 agent_id。
- 超时回收在 timeout_service（§22），与本服务共用失败收尾逻辑。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFound, StateNotAllowed
from app.models.outbound import (
    OutboundList,
    OutboundNumber,
    OutboundRecord,
    OutboundSession,
    OutboundTask,
)
from app.models.outbound.enums import (
    AgentStatus,
    CallStatus,
    ListStatus,
    RecordStatus,
    SessionStatus,
    TaskStatus,
)
from app.providers import get_call_provider, get_phone_provider
from app.providers.call.base import CallGatewayProvider
from app.providers.phone.base import PhoneProvider
from app.repositories.outbound.list_repository import OutboundListRepository
from app.repositories.outbound.number_repository import OutboundNumberRepository
from app.repositories.outbound.record_repository import OutboundRecordRepository
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.services.outbound.number_selector import OutboundNumberSelector
from app.services.outbound.phone_resolver import OutboundPhoneResolver
from app.services.outbound.retry_policy import apply_failure_ladder, sync_name_list_status
from app.services.outbound.task_progress import maybe_complete_task
from app.utils.async_bridge import run_sync

logger = logging.getLogger(__name__)

SOURCE_ORDER_ID = "order_id"
SOURCE_USER_ID = "user_id"
SOURCE_RECIPIENT = "recipient_number"

#: 已完成（成功）的记录不允许重复呼叫
_SUCCESS_STATUS = RecordStatus.SUCCESS


class OutboundExecutionService:
    """外呼执行。每条记录一个事务，避免单条失败回滚整批。"""

    def __init__(
        self,
        db: Session,
        *,
        phone_provider: PhoneProvider | None = None,
        call_provider: CallGatewayProvider | None = None,
    ) -> None:
        self.db = db
        self.task_repo = OutboundTaskRepository(db)
        self.list_repo = OutboundListRepository(db)
        self.record_repo = OutboundRecordRepository(db)
        self.number_repo = OutboundNumberRepository(db)
        self.ref = ReferenceRepository(db)
        self.selector = OutboundNumberSelector(db)
        self.phone_resolver = OutboundPhoneResolver(db, phone_provider=phone_provider)
        # 允许注入 Provider，便于测试替换
        self._phone_provider = phone_provider
        self._call_provider = call_provider
        self._assignment_service = None

    @property
    def phone_provider(self) -> PhoneProvider:
        if self._phone_provider is None:
            self._phone_provider = get_phone_provider()
        return self._phone_provider

    @property
    def call_provider(self) -> CallGatewayProvider:
        if self._call_provider is None:
            self._call_provider = get_call_provider()
        return self._call_provider

    @property
    def assignment_service(self):  # noqa: ANN201 - 延迟导入避免循环依赖
        if self._assignment_service is None:
            from app.services.outbound.assignment_service import OutboundAssignmentService

            self._assignment_service = OutboundAssignmentService(self.db)
        return self._assignment_service

    # ---------- 查询 ----------

    def list_records(
        self, *, page: int, page_size: int, **filters: object
    ) -> tuple[list[OutboundRecord], int]:
        items = self.record_repo.list_paged(page=page, page_size=page_size, **filters)
        total = self.record_repo.count(**filters)
        return items, total

    # ---------- 生成待执行记录 ----------

    def build_records(self, task_id: int, *, limit: int | None = None) -> dict[str, int]:
        """把任务下待执行的名单行转成执行记录（幂等：已存在记录的行跳过）。"""
        task = self._get_task(task_id)
        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            raise StateNotAllowed("已完成或已取消的任务不能再生成执行数据")

        batch = limit or settings.EXECUTE_BATCH_SIZE
        existing = self.record_repo.list_existing_list_ids(task_id)
        candidates = self.list_repo.list_paged(
            page=1,
            page_size=batch,
            task_id=task_id,
            status=ListStatus.PENDING,
        )
        rows = [
            {
                "tenant_id": task.tenant_id,
                "task_id": task.id,
                "list_id": name_list.id,
                "status": RecordStatus.PENDING,
                "current_attempt": 0,
                "retry_count": 0,
                "is_deleted": False,
            }
            for name_list in candidates
            if name_list.id not in existing
        ]
        created = self.record_repo.bulk_insert(rows)
        self.db.commit()
        skipped = len(candidates) - created
        logger.info("生成执行记录：task=%s created=%s skipped=%s", task_id, created, skipped)
        return {"task_id": task_id, "created": created, "skipped": skipped}

    # ---------- 批量执行（任务级）----------

    def execute_task(self, task_id: int, *, limit: int | None = None) -> dict[str, object]:
        """执行一批待执行记录（§20：按任务配置的号码顺序逐个尝试）。"""
        task = self._get_task(task_id)
        if task.status != TaskStatus.RUNNING:
            raise StateNotAllowed("仅「运行中（RUNNING）」的任务可以执行，请先流转任务状态")

        batch = limit or settings.EXECUTE_BATCH_SIZE
        records = self.record_repo.list_executable(task_id, limit=batch, now=self._now())

        summary: dict[str, object] = {
            "task_id": task_id,
            "processed": 0,
            "success": 0,
            "retry_waiting": 0,
            "exhausted": 0,
            "failed": 0,
        }
        counter_key = {
            RecordStatus.SUCCESS: "success",
            RecordStatus.RETRY_WAITING: "retry_waiting",
            RecordStatus.EXHAUSTED: "exhausted",
            RecordStatus.FAILED: "failed",
        }

        for record in records:
            status = self._execute_record(record, task)
            summary["processed"] = int(summary["processed"]) + 1  # type: ignore[arg-type]
            key = counter_key.get(status)
            if key:
                summary[key] = int(summary[key]) + 1  # type: ignore[arg-type]
            self.db.commit()

        # 规则 2：本批处理完后若已无未完成记录，任务自动置为已完成
        if maybe_complete_task(self.db, task):
            self.db.commit()
            summary["task_completed"] = True
            logger.info("任务已全部执行完毕，自动完成：task=%s", task_id)

        logger.info("任务执行完成：%s", summary)
        return summary

    def execute_due_retries(
        self, *, task_limit: int = 20, record_limit: int = 20
    ) -> dict[str, object]:
        """扫描运行中任务，执行已到重试时间的记录（供定时任务调用）。"""
        totals = {"tasks": 0, "processed": 0, "success": 0}
        for task_id in self.task_repo.list_running_ids(limit=task_limit):
            result = self.execute_task(task_id, limit=record_limit)
            totals["tasks"] += 1
            totals["processed"] += int(result["processed"])  # type: ignore[arg-type]
            totals["success"] += int(result["success"])  # type: ignore[arg-type]
        return totals

    # ---------- 单条执行（人工外呼 / 即时呼叫）----------

    def execute_record(
        self, record_id: int, *, agent_id: int | None = None
    ) -> dict[str, object]:
        record = self.record_repo.get_by_id(record_id)
        if record is None:
            raise NotFound("执行记录不存在")
        if record.status == _SUCCESS_STATUS:
            raise StateNotAllowed("该记录已呼叫成功，无需重复呼叫")

        task = self._get_task(record.task_id)
        if task.status != TaskStatus.RUNNING:
            raise StateNotAllowed("仅「运行中（RUNNING）」的任务可以执行呼叫")

        if agent_id is not None:
            self._validate_agent(agent_id, task.tenant_id)
            self.assignment_service.accept_for_call(agent_id, record.id)

        status = self._execute_record(record, task, agent_id=agent_id)

        # §34：呼叫结束后释放坐席并回到空闲，并尝试领取下一单
        if agent_id is not None or record.agent_id is not None:
            self.assignment_service.release_for_record(record.id)

        # 规则 2：单条即时呼叫后同样检查任务是否可以自动完成
        maybe_complete_task(self.db, task)

        self.db.commit()
        return {
            "record_id": record_id,
            "status": status.value,
            "session_id": record.session_id,
            "current_attempt": record.current_attempt,
            "retry_count": record.retry_count,
            "failure_reason": record.failure_reason,
        }

    # ---------- 网关结果回调（§78：回调必须幂等）----------

    def handle_call_result(
        self,
        *,
        provider_call_id: str,
        call_status: CallStatus,
        duration: int = 0,
        failure_reason: str | None = None,
        recording_path: str | None = None,
    ) -> dict[str, object]:
        """异步网关结果回写。已有最终结果的呼叫记录直接忽略重复回调。"""
        history = self.record_repo.get_history_by_provider_call_id(provider_call_id)
        if history is None:
            raise NotFound("呼叫记录不存在")
        if history.ended_at is not None:
            return {"updated": False, "reason": "该呼叫已有最终结果，忽略重复回调"}

        now = self._now()
        history.call_status = call_status
        history.duration = duration
        history.failure_reason = failure_reason
        if recording_path:
            history.recording_path = recording_path
        history.ended_at = now

        success = call_status == CallStatus.CONNECTED
        if success:
            history.connected_at = now

        record = (
            self.record_repo.get_by_id(history.record_id)
            if history.record_id is not None
            else None
        )
        session = (
            self.record_repo.get_session(history.session_id)
            if history.session_id is not None
            else None
        )
        name_list = (
            self.list_repo.get_by_id(history.list_id) if history.list_id is not None else None
        )
        task = self.task_repo.get_by_id(record.task_id) if record is not None else None

        if record is not None:
            if success:
                record.status = RecordStatus.SUCCESS
                record.finished_at = now
                record.timeout_at = None
                record.next_retry_at = None
                record.failure_reason = None
                sync_name_list_status(name_list, RecordStatus.SUCCESS)
            elif task is not None:
                record.retry_count += 1
                record.timeout_at = None
                record.failure_reason = (
                    failure_reason or f"呼叫失败（{call_status.value}）"
                )[:255]
                apply_failure_ladder(record, task, now=now)
                sync_name_list_status(name_list, record.status)

        if session is not None:
            session.status = SessionStatus.ENDED
            session.finished_at = now
            session.timeout_at = None

        self.db.commit()
        logger.info(
            "网关结果回调：provider_call_id=%s status=%s record=%s",
            provider_call_id,
            call_status.value,
            record.status.value if record is not None else None,
        )
        return {
            "updated": True,
            "record_status": record.status.value if record is not None else None,
        }

    # ---------- 核心：单条记录的多号码顺序执行 ----------

    def _execute_record(
        self, record: OutboundRecord, task: OutboundTask, *, agent_id: int | None = None
    ) -> RecordStatus:
        name_list = self.list_repo.get_by_id(record.list_id)
        if name_list is None:
            return self._finalize(record, None, task, None, "名单不存在", permanent=True)

        session = self._ensure_session(record, task, agent_id)
        phones = self._resolve_phones(task, name_list)
        if not phones:
            return self._finalize(
                record,
                session,
                task,
                name_list,
                "无可呼叫号码（名单未提供号码，第三方也未返回）",
                permanent=True,
            )

        last_reason = "呼叫失败"
        # §20：每轮都从第一个号码重新按配置顺序尝试
        for index, phone in enumerate(phones):
            now = self._now()
            record.current_attempt = index + 1
            record.current_phone = phone
            record.last_call_at = now
            record.status = RecordStatus.CALLING
            session.current_phone = phone
            session.current_attempt = index + 1
            session.status = SessionStatus.CALLING
            record.timeout_at = now + timedelta(seconds=task.call_timeout_seconds)
            session.timeout_at = record.timeout_at

            calling_number = self._pick_calling_number(task)
            if calling_number is None:
                # 无可用主叫号码属于资源/配置问题，重试同一批数据不会自愈 → 永久失败
                return self._finalize(
                    record,
                    session,
                    task,
                    name_list,
                    "外呼号码已全部不可用（不存在 / 停用 / 次数耗尽）",
                    permanent=True,
                )

            history = self.record_repo.create_history(
                tenant_id=task.tenant_id,
                session_id=session.id,
                record_id=record.id,
                task_id=task.id,
                list_id=name_list.id,
                agent_id=agent_id or record.agent_id,
                phone=phone,
                call_status=CallStatus.INITIATED,
                started_at=now,
                provider=self.call_provider.name,
            )

            result = run_sync(
                self.call_provider.make_call(
                    phone=phone, agent_id=agent_id, session_id=session.id
                )
            )
            ended = self._now()
            history.call_status = result.call_status
            history.failure_reason = result.failure_reason
            history.provider_call_id = result.provider_call_id
            history.duration = result.duration
            history.recording_path = result.recording_path
            history.ended_at = ended
            if result.success:
                history.connected_at = ended

            if result.success:
                return self._finalize_success(record, session, name_list, ended, calling_number)

            last_reason = result.failure_reason or f"呼叫失败（{result.call_status.value}）"
            logger.info(
                "外呼未接通：record=%s phone=%s reason=%s", record.id, phone, last_reason
            )

        return self._finalize(record, session, task, name_list, last_reason)

    def _finalize_success(
        self,
        record: OutboundRecord,
        session: OutboundSession,
        name_list: OutboundList,
        ended: datetime,
        calling_number: OutboundNumber,
    ) -> RecordStatus:
        record.status = RecordStatus.SUCCESS
        record.finished_at = ended
        record.timeout_at = None
        record.next_retry_at = None
        record.failure_reason = None

        session.status = SessionStatus.ENDED
        session.finished_at = ended
        session.timeout_at = None

        name_list.status = ListStatus.SUCCESS
        name_list.attempt_count = (name_list.attempt_count or 0) + 1
        name_list.last_call_at = ended
        logger.info(
            "外呼成功：record=%s 主叫=%s used=%s/%s",
            record.id,
            calling_number.caller_number,
            calling_number.used_count,
            calling_number.usage_limit,
        )
        return RecordStatus.SUCCESS

    def _finalize(
        self,
        record: OutboundRecord,
        session: OutboundSession | None,
        task: OutboundTask,
        name_list: OutboundList | None,
        reason: str,
        *,
        permanent: bool = False,
    ) -> RecordStatus:
        """失败收尾：按 §21 重试阶梯决定 RETRY_WAITING / EXHAUSTED / FAILED。"""
        now = self._now()
        record.retry_count += 1
        record.timeout_at = None
        record.finished_at = None
        record.failure_reason = reason[:255]

        if session is not None:
            session.status = SessionStatus.ENDED
            session.finished_at = now
            session.timeout_at = None

        if name_list is not None:
            name_list.attempt_count = (name_list.attempt_count or 0) + 1
            name_list.last_call_at = now

        apply_failure_ladder(record, task, now=now, permanent=permanent)
        sync_name_list_status(name_list, record.status)

        logger.info(
            "外呼失败收尾：record=%s status=%s retry=%s/%s reason=%s",
            record.id,
            record.status.value,
            record.retry_count,
            task.max_retry_count,
            reason,
        )
        return record.status

    # ---------- 内部工具 ----------

    def _get_task(self, task_id: int) -> OutboundTask:
        task = self.task_repo.get_by_id(task_id)
        if task is None:
            raise NotFound("外呼任务不存在")
        return task

    def _validate_agent(self, agent_id: int, tenant_id: int) -> None:
        """§38：人工外呼前校验坐席（状态校验与预占在 P6 完善）。"""
        agent = self.ref.get_agent_by_id(agent_id)
        if agent is None:
            raise NotFound("坐席不存在")
        if agent.tenant_id != tenant_id:
            raise StateNotAllowed("坐席与任务不属于同一租户")
        if agent.status == AgentStatus.OFFLINE:
            raise StateNotAllowed("坐席当前离线，无法执行人工外呼")

    def _ensure_session(
        self, record: OutboundRecord, task: OutboundTask, agent_id: int | None
    ) -> OutboundSession:
        if record.session_id is not None:
            existing = self.record_repo.get_session(record.session_id)
            if existing is not None:
                return existing

        session = self.record_repo.create_session(
            tenant_id=task.tenant_id,
            task_id=task.id,
            list_id=record.list_id,
            agent_id=agent_id or record.agent_id,
            status=SessionStatus.CREATED,
            current_attempt=0,
            started_at=self._now(),
        )
        record.session_id = session.id
        if agent_id is not None:
            record.agent_id = agent_id
        return session

    def _resolve_phones(self, task: OutboundTask, name_list: OutboundList) -> list[str]:
        """按任务配置顺序解析出可呼叫号码（复用公共解析器，与看板/会话保持一致）。"""
        return self.phone_resolver.resolve(task, name_list).phones

    def _pick_calling_number(self, task: OutboundTask) -> OutboundNumber | None:
        """按策略逐个尝试主叫号码并原子扣减次数（§13 / §14）。"""
        candidates = self.selector.ordered_candidates(
            strategy=task.number_select_strategy,
            tenant_id=task.tenant_id,
            task_id=task.id,
        )
        for candidate in candidates:
            if self.number_repo.consume_atomically(candidate.id) == 1:
                self.db.refresh(candidate)
                return candidate
        return None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
