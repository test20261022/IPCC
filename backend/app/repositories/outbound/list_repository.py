"""名单与导入批次数据访问（OB-011）。"""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.outbound import OutboundImportBatch, OutboundList
from app.models.outbound.enums import ImportBatchStatus, ListStatus


class OutboundListRepository:
    """名单行查询与批量写入。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 名单行 ----------

    def get_by_id(self, list_id: int) -> OutboundList | None:
        stmt = select(OutboundList).where(
            OutboundList.id == list_id, OutboundList.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        task_id: int | None = None,
        user_id: str | None = None,
        order_id: str | None = None,
        import_batch_id: int | None = None,
        status: ListStatus | None = None,
    ) -> Select:
        stmt = stmt.where(OutboundList.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(OutboundList.tenant_id == tenant_id)
        if task_id is not None:
            stmt = stmt.where(OutboundList.task_id == task_id)
        if user_id:
            stmt = stmt.where(OutboundList.user_id == user_id)
        if order_id:
            stmt = stmt.where(OutboundList.order_id == order_id)
        if import_batch_id is not None:
            stmt = stmt.where(OutboundList.import_batch_id == import_batch_id)
        if status is not None:
            stmt = stmt.where(OutboundList.status == status)
        return stmt

    def list_paged(self, *, page: int, page_size: int, **filters: object) -> list[OutboundList]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(select(OutboundList), **filters)  # type: ignore[arg-type]
        stmt = stmt.order_by(OutboundList.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, **filters: object) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(OutboundList), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_existing_keys(self, task_id: int) -> set[tuple[str | None, str | None]]:
        """任务下已有的 (user_id, order_id) 组合，用于导入查重（§78 幂等）。"""
        stmt = select(OutboundList.user_id, OutboundList.order_id).where(
            OutboundList.task_id == task_id, OutboundList.is_deleted.is_(False)
        )
        return {(row[0], row[1]) for row in self.db.execute(stmt).all()}

    def bulk_insert(self, values: list[dict[str, object]]) -> int:
        """批量写入名单行（避免逐行 INSERT 造成的性能问题）。"""
        if not values:
            return 0
        self.db.execute(OutboundList.__table__.insert(), values)
        self.db.flush()
        return len(values)

    # ---------- 导入批次 ----------

    def create_batch(self, **values: object) -> OutboundImportBatch:
        batch = OutboundImportBatch(**values)
        self.db.add(batch)
        self.db.flush()
        return batch

    def get_batch(self, batch_id: int) -> OutboundImportBatch | None:
        stmt = select(OutboundImportBatch).where(
            OutboundImportBatch.id == batch_id, OutboundImportBatch.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_batch_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        task_id: int | None = None,
        status: ImportBatchStatus | None = None,
    ) -> Select:
        stmt = stmt.where(OutboundImportBatch.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(OutboundImportBatch.tenant_id == tenant_id)
        if task_id is not None:
            stmt = stmt.where(OutboundImportBatch.task_id == task_id)
        if status is not None:
            stmt = stmt.where(OutboundImportBatch.status == status)
        return stmt

    def list_batches_paged(
        self, *, page: int, page_size: int, **filters: object
    ) -> list[OutboundImportBatch]:
        offset = (page - 1) * page_size
        stmt = self._apply_batch_filters(
            select(OutboundImportBatch), **filters  # type: ignore[arg-type]
        )
        stmt = stmt.order_by(OutboundImportBatch.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count_batches(self, **filters: object) -> int:
        stmt = self._apply_batch_filters(
            select(func.count()).select_from(OutboundImportBatch), **filters  # type: ignore[arg-type]
        )
        return int(self.db.execute(stmt).scalar_one())
