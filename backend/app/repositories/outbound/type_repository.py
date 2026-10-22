"""外呼类型数据访问（OB-004）。"""

from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.outbound import OutboundType
from app.models.outbound.enums import CommonStatus


class OutboundTypeRepository:
    """外呼类型查询。默认过滤软删除数据。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, type_id: int) -> OutboundType | None:
        stmt = select(OutboundType).where(
            OutboundType.id == type_id, OutboundType.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, tenant_id: int, code: str) -> OutboundType | None:
        stmt = select(OutboundType).where(
            OutboundType.tenant_id == tenant_id,
            OutboundType.code == code,
            OutboundType.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        name: str | None = None,
        code: str | None = None,
        parent_id: int | None = None,
        level: int | None = None,
        status: CommonStatus | None = None,
    ) -> Select:
        stmt = stmt.where(OutboundType.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(OutboundType.tenant_id == tenant_id)
        if name:
            stmt = stmt.where(OutboundType.name.ilike(f"%{name}%"))
        if code:
            stmt = stmt.where(OutboundType.code.ilike(f"%{code}%"))
        if parent_id is not None:
            stmt = stmt.where(OutboundType.parent_id == parent_id)
        if level is not None:
            stmt = stmt.where(OutboundType.level == level)
        if status is not None:
            stmt = stmt.where(OutboundType.status == status)
        return stmt

    def list_paged(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        name: str | None = None,
        code: str | None = None,
        parent_id: int | None = None,
        level: int | None = None,
        status: CommonStatus | None = None,
        include_children_of: Sequence[int] | None = None,
    ) -> list[OutboundType]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(
            select(OutboundType),
            tenant_id=tenant_id,
            name=name,
            code=code,
            parent_id=parent_id,
            level=level,
            status=status,
        )
        if include_children_of:
            stmt = stmt.where(OutboundType.parent_id.in_(list(include_children_of)))
        stmt = (
            stmt.order_by(
                OutboundType.level.asc(),
                OutboundType.sort_order.asc(),
                OutboundType.id.asc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count(
        self,
        *,
        tenant_id: int | None = None,
        name: str | None = None,
        code: str | None = None,
        parent_id: int | None = None,
        level: int | None = None,
        status: CommonStatus | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(OutboundType),
            tenant_id=tenant_id,
            name=name,
            code=code,
            parent_id=parent_id,
            level=level,
            status=status,
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> OutboundType:
        outbound_type = OutboundType(**values)
        self.db.add(outbound_type)
        self.db.flush()
        return outbound_type
