"""优秀案例库数据访问。默认过滤软删除，tenant_id 传入才过滤。"""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.qc import QcCaseLibrary


class QcCaseLibraryRepository:
    """案例库查询与写入。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, case_id: int) -> QcCaseLibrary | None:
        stmt = select(QcCaseLibrary).where(
            QcCaseLibrary.id == case_id,
            QcCaseLibrary.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_conversation(self, conversation_id: int) -> QcCaseLibrary | None:
        """同一对话最多沉淀一个案例（软删除的部分唯一索引口径）。"""
        stmt = select(QcCaseLibrary).where(
            QcCaseLibrary.conversation_id == conversation_id,
            QcCaseLibrary.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        is_published: bool | None = None,
        tag: str | None = None,
        keyword: str | None = None,
    ) -> Select:
        stmt = stmt.where(QcCaseLibrary.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(QcCaseLibrary.tenant_id == tenant_id)
        if is_published is not None:
            stmt = stmt.where(QcCaseLibrary.is_published.is_(is_published))
        if tag:
            # JSONB 数组包含判断：tags @> '["tag"]'
            stmt = stmt.where(QcCaseLibrary.tags.contains([tag]))
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    QcCaseLibrary.title.ilike(like),
                    QcCaseLibrary.reason.ilike(like),
                )
            )
        return stmt

    def list_paged(self, *, page: int, page_size: int, **filters: object) -> list[QcCaseLibrary]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(select(QcCaseLibrary), **filters)  # type: ignore[arg-type]
        stmt = stmt.order_by(QcCaseLibrary.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, **filters: object) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(QcCaseLibrary), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> QcCaseLibrary:
        case = QcCaseLibrary(**values)
        self.db.add(case)
        self.db.flush()
        return case


__all__ = ["QcCaseLibraryRepository"]