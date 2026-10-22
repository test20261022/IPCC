"""质检执行服务：我的工作台、领取 / 释放 / 提交。

并发安全依赖带状态条件的原子 UPDATE（见 QcTaskItemRepository），
提交成功后原子累加任务完成数，并按条件 UPDATE 推进任务为已完成。
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import Forbidden, NotFound, StateNotAllowed
from app.models.qc.enums import QcItemStatus
from app.models.qc.review import QcTaskItem
from app.models.user import User
from app.repositories.qc.item_repository import QcTaskItemRepository
from app.repositories.qc.task_repository import QcTaskRepository
from app.schemas.qc.review import QcItemSubmitRequest
from app.services.qc import item_state
from app.services.qc.grading import judge_grade

logger = logging.getLogger(__name__)

#: 单次超时回收扫描的明细条数上限（避免一次锁太多行）
DEFAULT_RECYCLE_BATCH = 100


class QcReviewService:
    """质检执行域业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = QcTaskItemRepository(db)
        self.task_repo = QcTaskRepository(db)

    # ---------- 我的工作台 ----------

    def list_my_items(
        self,
        *,
        current_user: User,
        page: int,
        page_size: int,
        status: QcItemStatus | None = None,
    ) -> tuple[list[QcTaskItem], int]:
        items = self.repo.list_my_items(
            page=page,
            page_size=page_size,
            reviewer_id=current_user.id,
            tenant_id=current_user.tenant_id,
            status=status,
        )
        total = self.repo.count_my_items(
            reviewer_id=current_user.id,
            tenant_id=current_user.tenant_id,
            status=status,
        )
        return items, total

    def get_item_detail(self, item_id: int, current_user: User) -> dict:
        item = self._get_visible_item(item_id, current_user)
        return {
            "item": item,
            "conversation": self.repo.get_conversation(item.conversation_id),
            "messages": self.repo.list_messages(item.conversation_id),
        }

    # ---------- 领取 / 释放 / 提交 ----------

    def claim(self, item_id: int, current_user: User) -> QcTaskItem:
        item = self._get_visible_item(item_id, current_user)
        now = datetime.now(timezone.utc)
        timeout_at = now + timedelta(seconds=settings.QC_ITEM_LOCK_TIMEOUT_SECONDS)
        claimed = self.repo.claim(
            item.id, reviewer_id=current_user.id, now=now, timeout_at=timeout_at
        )
        if not claimed:
            raise StateNotAllowed("任务已被领取或状态已变更")
        self.db.commit()
        logger.info("领取质检明细：item=%s reviewer=%s", item_id, current_user.id)
        return self._reload(item.id, current_user)

    def release(self, item_id: int, current_user: User) -> QcTaskItem:
        released = self.repo.release(
            item_id, reviewer_id=current_user.id, now=datetime.now(timezone.utc)
        )
        if not released:
            raise StateNotAllowed("仅本人持有的质检中明细可以释放")
        self.db.commit()
        logger.info("释放质检明细：item=%s reviewer=%s", item_id, current_user.id)
        return self._reload(item_id, current_user)

    def submit(
        self, item_id: int, current_user: User, payload: QcItemSubmitRequest
    ) -> dict:
        item = self._get_visible_item(item_id, current_user)
        item_state.ensure_item_transition(item.status, QcItemStatus.COMPLETED)
        grade = judge_grade(payload.score)
        now = datetime.now(timezone.utc)

        created = self.repo.insert_result(
            tenant_id=item.tenant_id,
            item_id=item.id,
            conversation_id=item.conversation_id,
            reviewer_id=current_user.id,
            score=payload.score,
            grade=grade,
            comment=payload.comment,
            score_detail=payload.score_detail,
            reviewed_at=now,
        )
        if not created:
            raise StateNotAllowed("该明细已提交过质检结果，请勿重复提交")

        submitted = self.repo.submit_item(
            item.id, reviewer_id=current_user.id, grade=grade, now=now
        )
        if not submitted:
            raise StateNotAllowed("任务已被领取或状态已变更")

        task_id = item.task_id
        self.task_repo.increment_completed(task_id, now=now)
        task_completed = self.task_repo.complete_if_done(task_id, now=now)
        self.db.commit()
        logger.info(
            "提交质检结果：item=%s reviewer=%s score=%s grade=%s",
            item_id,
            current_user.id,
            payload.score,
            grade.value,
        )
        self.db.expire_all()
        fresh = self.repo.get_by_id(item.id)
        return {
            "item_id": item.id,
            "grade": grade,
            "status": fresh.status if fresh is not None else QcItemStatus.COMPLETED,
            "submitted_at": now,
            "task_completed": task_completed,
        }

    # ---------- 超时回收 ----------

    def recycle_timeout_items(self, *, limit: int = DEFAULT_RECYCLE_BATCH) -> dict[str, object]:
        """把超时未提交的明细退回 PENDING（定时任务调用）。

        幂等：仓储层用行锁 + 锁内复核，重复扫描不会产生副作用；
        每条一个事务，避免长事务持锁。
        """
        now = datetime.now(timezone.utc)
        candidates = self.repo.list_timeout_items(now=now, limit=limit)
        result: dict[str, object] = {"scanned": len(candidates), "recycled": 0, "skipped": 0}
        for item_id in candidates:
            if self.repo.recycle(item_id, now=now):
                result["recycled"] = int(result["recycled"]) + 1  # type: ignore[arg-type]
            else:
                result["skipped"] = int(result["skipped"]) + 1  # type: ignore[arg-type]
            self.db.commit()

        if result["recycled"]:
            logger.warning("质检超时回收完成：%s", result)
        return result

    # ---------- 内部 ----------

    def _get_visible_item(self, item_id: int, current_user: User) -> QcTaskItem:
        """按租户可见范围取明细；非超管只能操作分配给自己的明细。"""
        item = self.repo.get_by_id(item_id, tenant_id=current_user.tenant_id)
        if item is None:
            raise NotFound("质检明细不存在")
        if not current_user.is_superuser and item.reviewer_id not in (None, current_user.id):
            raise Forbidden("该明细已分配给其他专家")
        return item

    def _reload(self, item_id: int, current_user: User) -> QcTaskItem:
        self.db.expire_all()
        item = self.repo.get_by_id(item_id, tenant_id=current_user.tenant_id)
        if item is None:  # pragma: no cover - 刚操作过，理论上必然存在
            raise NotFound("质检明细不存在")
        return item


__all__ = ["DEFAULT_RECYCLE_BATCH", "QcReviewService"]