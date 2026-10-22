"""外呼号码服务（OB-001 号码管理 / OB-005 主叫号码使用规则）。

核心规则：
- 外显名称必填、主叫号码格式校验（schema 层）、租户归属校验。
- 一个任务可配置多个号码（任务侧在 P3 落地），本服务负责号码自身与次数控制。
- 次数扣减必须走原子 UPDATE，禁止读改写（§13），失败原因区分：不存在 / 停用 / 次数耗尽。
"""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import (
    Conflict,
    NotFound,
    NumberExhausted,
    ResourceReferenced,
    StateNotAllowed,
)
from app.models.outbound import OutboundNumber
from app.models.outbound.enums import CommonStatus
from app.repositories.outbound.number_repository import OutboundNumberRepository
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.schemas.outbound.config import OutboundNumberCreate, OutboundNumberUpdate
from app.services.outbound.common import apply_updates, ensure_tenant_active

logger = logging.getLogger(__name__)


class OutboundNumberService:
    """外呼号码业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = OutboundNumberRepository(db)
        self.ref = ReferenceRepository(db)

    # ---------- 查询 ----------

    def list_numbers(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        caller_number: str | None = None,
        display_name: str | None = None,
        status: CommonStatus | None = None,
    ) -> tuple[list[OutboundNumber], int]:
        items = self.repo.list_paged(
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            caller_number=caller_number,
            display_name=display_name,
            status=status,
        )
        total = self.repo.count(
            tenant_id=tenant_id,
            caller_number=caller_number,
            display_name=display_name,
            status=status,
        )
        return items, total

    def get_number(self, number_id: int) -> OutboundNumber:
        number = self.repo.get_by_id(number_id)
        if number is None:
            raise NotFound("外呼号码不存在")
        return number

    # ---------- 新增 ----------

    def create_number(self, payload: OutboundNumberCreate) -> OutboundNumber:
        ensure_tenant_active(self.db, payload.tenant_id)
        self._ensure_caller_unique(payload.tenant_id, payload.caller_number)

        number = self.repo.create(**payload.model_dump())
        self.db.commit()
        logger.info(
            "创建外呼号码成功：id=%s caller=%s", number.id, number.caller_number
        )
        return number

    # ---------- 编辑 ----------

    def update_number(self, number_id: int, payload: OutboundNumberUpdate) -> OutboundNumber:
        number = self.get_number(number_id)
        changes = payload.model_dump(exclude_unset=True)
        apply_updates(number, payload)
        self.db.commit()
        logger.info("更新外呼号码成功：id=%s fields=%s", number_id, sorted(changes))
        return number

    def set_status(self, number_id: int, status: CommonStatus) -> OutboundNumber:
        number = self.get_number(number_id)
        if number.status != status:
            number.status = status
            self.db.commit()
            logger.info("外呼号码状态变更：id=%s -> %s", number_id, status)
        return number

    # ---------- 删除 ----------

    def delete_number(self, number_id: int) -> None:
        number = self.get_number(number_id)

        task_count = self.ref.count_tasks_by_number(number_id)
        if task_count:
            raise ResourceReferenced(f"外呼号码已被 {task_count} 个外呼任务配置引用，禁止删除")

        number.mark_deleted()
        self.db.commit()
        logger.info("删除外呼号码成功：id=%s", number_id)

    # ---------- 使用次数控制（OB-005 / §13）----------

    def consume(self, number_id: int, *, step: int = 1) -> OutboundNumber:
        """原子扣减主叫号码使用次数，返回扣减后的号码。

        affected_rows != 1 时按原因区分错误码：停用 40902 / 次数耗尽 40903。
        """
        number = self.get_number(number_id)

        affected = self.repo.consume_atomically(number_id, step=step)
        if affected != 1:
            if number.status != CommonStatus.ENABLED:
                raise StateNotAllowed("外呼号码已停用，无法使用")
            raise NumberExhausted(
                f"外呼号码使用次数已耗尽（上限 {number.usage_limit}）"
            )

        self.db.commit()
        refreshed = self.repo.refresh(number_id)
        if refreshed is None:  # pragma: no cover - 提交后必然存在
            raise NotFound("外呼号码不存在")
        logger.info(
            "外呼号码次数扣减成功：id=%s used=%s/%s",
            number_id,
            refreshed.used_count,
            refreshed.usage_limit,
        )
        return refreshed

    # ---------- 内部 ----------

    def _ensure_caller_unique(self, tenant_id: int, caller_number: str) -> None:
        if self.repo.get_by_caller_number(tenant_id, caller_number) is not None:
            raise Conflict(f"该租户下主叫号码已存在：{caller_number}")
