"""外呼场景数据访问（OB-003）。"""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.outbound import OutboundScene
from app.models.outbound.enums import CommonStatus


class OutboundSceneRepository:
    """外呼场景查询。两级结构：parent_id 为空即一级场景。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, scene_id: int) -> OutboundScene | None:
        stmt = select(OutboundScene).where(
            OutboundScene.id == scene_id, OutboundScene.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_ids(self, scene_ids: list[int]) -> list[OutboundScene]:
        if not scene_ids:
            return []
        stmt = select(OutboundScene).where(
            OutboundScene.id.in_(scene_ids), OutboundScene.is_deleted.is_(False)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_children(self, parent_id: int) -> list[OutboundScene]:
        """一级场景下的全部二级场景（含已软删除的排除）。"""
        stmt = select(OutboundScene).where(
            OutboundScene.parent_id == parent_id, OutboundScene.is_deleted.is_(False)
        )
        return list(self.db.execute(stmt).scalars().all())

    def exists_same_name(
        self, *, tenant_id: int, type_id: int, parent_id: int | None, name: str
    ) -> bool:
        """同一父级下场景名不允许重复（DB 未建唯一索引，因 parent_id 可空）。"""
        stmt = select(func.count()).select_from(OutboundScene).where(
            OutboundScene.tenant_id == tenant_id,
            OutboundScene.type_id == type_id,
            OutboundScene.name == name,
            OutboundScene.is_deleted.is_(False),
        )
        stmt = (
            stmt.where(OutboundScene.parent_id.is_(None))
            if parent_id is None
            else stmt.where(OutboundScene.parent_id == parent_id)
        )
        return int(self.db.execute(stmt).scalar_one()) > 0

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        type_id: int | None = None,
        parent_id: int | None = None,
        name: str | None = None,
        level: int | None = None,
        status: CommonStatus | None = None,
    ) -> Select:
        stmt = stmt.where(OutboundScene.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(OutboundScene.tenant_id == tenant_id)
        if type_id is not None:
            stmt = stmt.where(OutboundScene.type_id == type_id)
        if parent_id is not None:
            stmt = stmt.where(OutboundScene.parent_id == parent_id)
        if name:
            stmt = stmt.where(OutboundScene.name.ilike(f"%{name}%"))
        if level is not None:
            stmt = stmt.where(OutboundScene.level == level)
        if status is not None:
            stmt = stmt.where(OutboundScene.status == status)
        return stmt

    def list_paged(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        type_id: int | None = None,
        parent_id: int | None = None,
        name: str | None = None,
        level: int | None = None,
        status: CommonStatus | None = None,
    ) -> list[OutboundScene]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(
            select(OutboundScene),
            tenant_id=tenant_id,
            type_id=type_id,
            parent_id=parent_id,
            name=name,
            level=level,
            status=status,
        )
        stmt = (
            stmt.order_by(
                OutboundScene.level.asc(),
                OutboundScene.sort_order.asc(),
                OutboundScene.id.asc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_all(
        self,
        *,
        tenant_id: int | None = None,
        type_id: int | None = None,
        status: CommonStatus | None = None,
    ) -> list[OutboundScene]:
        """不分页（用于构建两级树，规模有限）。"""
        stmt = self._apply_filters(
            select(OutboundScene), tenant_id=tenant_id, type_id=type_id, status=status
        )
        stmt = stmt.order_by(
            OutboundScene.level.asc(), OutboundScene.sort_order.asc(), OutboundScene.id.asc()
        )
        return list(self.db.execute(stmt).scalars().all())

    def count(
        self,
        *,
        tenant_id: int | None = None,
        type_id: int | None = None,
        parent_id: int | None = None,
        name: str | None = None,
        level: int | None = None,
        status: CommonStatus | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(OutboundScene),
            tenant_id=tenant_id,
            type_id=type_id,
            parent_id=parent_id,
            name=name,
            level=level,
            status=status,
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> OutboundScene:
        scene = OutboundScene(**values)
        self.db.add(scene)
        self.db.flush()
        return scene
