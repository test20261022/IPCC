"""优秀案例库服务：CRUD 与发布。

同一对话最多沉淀一个案例，重复入选按唯一索引口径抛 Conflict。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound
from app.models.qc import QcCaseLibrary
from app.repositories.qc.case_repository import QcCaseLibraryRepository
from app.repositories.qc.conversation_repository import QcConversationRepository
from app.schemas.qc.case import CaseCreateIn, CaseUpdateIn

logger = logging.getLogger(__name__)


class QcCaseLibraryService:
    """优秀案例业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = QcCaseLibraryRepository(db)
        self.conversation_repo = QcConversationRepository(db)

    # ---------- 查询 ----------

    def list_cases(
        self, *, page: int, page_size: int, **filters: object
    ) -> tuple[list[QcCaseLibrary], int]:
        items = self.repo.list_paged(page=page, page_size=page_size, **filters)
        total = self.repo.count(**filters)
        return items, total

    def get_case(self, case_id: int) -> QcCaseLibrary:
        case = self.repo.get_by_id(case_id)
        if case is None:
            raise NotFound("优秀案例不存在")
        return case

    # ---------- 新增 ----------

    def create_case(
        self, payload: CaseCreateIn, *, created_by: int | None = None
    ) -> QcCaseLibrary:
        if self.conversation_repo.get_by_id(payload.conversation_id) is None:
            raise NotFound("来源对话不存在")
        if self.repo.get_by_conversation(payload.conversation_id) is not None:
            raise Conflict("该对话已入选案例库")

        try:
            case = self.repo.create(
                tenant_id=payload.tenant_id,
                conversation_id=payload.conversation_id,
                item_id=payload.item_id,
                title=payload.title,
                reason=payload.reason,
                tags=payload.tags,
                is_published=False,
                published_at=None,
                created_by=created_by,
            )
            self.db.commit()
        except IntegrityError as exc:
            # 并发写入时由数据库唯一索引兜底
            self.db.rollback()
            raise Conflict("该对话已入选案例库") from exc

        logger.info("创建优秀案例成功：id=%s conversation=%s", case.id, case.conversation_id)
        return case

    # ---------- 编辑 ----------

    def update_case(self, case_id: int, payload: CaseUpdateIn) -> QcCaseLibrary:
        case = self.get_case(case_id)
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(case, field, value)
        self.db.commit()
        logger.info("更新优秀案例成功：id=%s fields=%s", case_id, sorted(changes))
        return case

    # ---------- 删除 ----------

    def delete_case(self, case_id: int) -> None:
        case = self.get_case(case_id)
        case.mark_deleted()
        self.db.commit()
        logger.info("删除优秀案例成功：id=%s", case_id)

    # ---------- 发布 ----------

    def publish_case(self, case_id: int) -> QcCaseLibrary:
        case = self.get_case(case_id)
        if not case.is_published:
            case.is_published = True
            case.published_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.info("发布优秀案例成功：id=%s", case_id)
        return case


__all__ = ["QcCaseLibraryService"]