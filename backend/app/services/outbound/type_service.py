"""外呼类型服务（OB-004）。

规则：
- 被场景引用的类型禁止删除；被业务（场景 / 任务）使用的类型禁止破坏性修改（code / 层级 / 父级）。
- 仍有子类型时禁止删除。
"""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ParamError, ResourceReferenced, StateNotAllowed
from app.models.outbound import OutboundType
from app.models.outbound.enums import CommonStatus
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.repositories.outbound.type_repository import OutboundTypeRepository
from app.schemas.outbound.config import OutboundTypeCreate, OutboundTypeUpdate
from app.services.outbound.common import apply_updates, ensure_tenant_active

logger = logging.getLogger(__name__)

# 被业务引用后不允许改动的字段（破坏性修改）
_BREAKING_FIELDS = ("code", "parent_id", "level")


class OutboundTypeService:
    """外呼类型业务。事务在本层提交（§55）。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = OutboundTypeRepository(db)
        self.ref = ReferenceRepository(db)

    # ---------- 查询 ----------

    def list_types(
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
    ) -> tuple[list[OutboundType], int]:
        items = self.repo.list_paged(
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            name=name,
            code=code,
            parent_id=parent_id,
            level=level,
            status=status,
        )
        total = self.repo.count(
            tenant_id=tenant_id,
            name=name,
            code=code,
            parent_id=parent_id,
            level=level,
            status=status,
        )
        return items, total

    def get_type(self, type_id: int) -> OutboundType:
        outbound_type = self.repo.get_by_id(type_id)
        if outbound_type is None:
            raise NotFound("外呼类型不存在")
        return outbound_type

    # ---------- 新增 ----------

    def create_type(self, payload: OutboundTypeCreate) -> OutboundType:
        ensure_tenant_active(self.db, payload.tenant_id)

        if self.repo.get_by_code(payload.tenant_id, payload.code) is not None:
            raise Conflict(f"外呼类型编码已存在：{payload.code}")

        self._validate_parent(
            tenant_id=payload.tenant_id,
            level=payload.level,
            parent_id=payload.parent_id,
        )

        outbound_type = self.repo.create(**payload.model_dump())
        self.db.commit()
        logger.info("创建外呼类型成功：id=%s code=%s", outbound_type.id, outbound_type.code)
        return outbound_type

    # ---------- 编辑 ----------

    def update_type(self, type_id: int, payload: OutboundTypeUpdate) -> OutboundType:
        outbound_type = self.get_type(type_id)
        changes = payload.model_dump(exclude_unset=True)

        referenced = self._is_referenced(type_id)
        # 只有「值确实发生变化」才算破坏性修改；原样回传不应被拒绝
        breaking = [
            field
            for field in _BREAKING_FIELDS
            if field in changes and getattr(outbound_type, field) != changes[field]
        ]
        if referenced and breaking:
            raise ResourceReferenced(
                f"外呼类型已被外呼场景或任务引用，禁止修改：{'、'.join(breaking)}"
            )

        if "code" in changes and changes["code"] != outbound_type.code:
            existing = self.repo.get_by_code(outbound_type.tenant_id, str(changes["code"]))
            if existing is not None:
                raise Conflict(f"外呼类型编码已存在：{changes['code']}")

        if "parent_id" in changes or "level" in changes:
            target_level = int(changes.get("level", outbound_type.level))
            target_parent = changes.get("parent_id", outbound_type.parent_id)
            self._validate_parent(
                tenant_id=outbound_type.tenant_id,
                level=target_level,
                parent_id=target_parent,
                exclude_id=type_id,
            )

        apply_updates(outbound_type, payload)
        self.db.commit()
        logger.info("更新外呼类型成功：id=%s fields=%s", type_id, sorted(changes))
        return outbound_type

    # ---------- 删除 ----------

    def delete_type(self, type_id: int) -> None:
        outbound_type = self.get_type(type_id)

        child_count = self.ref.count_child_types(type_id)
        if child_count:
            raise ResourceReferenced(f"外呼类型下仍有 {child_count} 个子类型，请先删除子类型")

        scene_count = self.ref.count_scenes_by_type(type_id)
        if scene_count:
            raise ResourceReferenced(f"外呼类型已被 {scene_count} 个外呼场景引用，禁止删除")

        task_count = self.ref.count_tasks_by_type(type_id)
        if task_count:
            raise ResourceReferenced(f"外呼类型已被 {task_count} 个外呼任务引用，禁止删除")

        outbound_type.mark_deleted()
        self.db.commit()
        logger.info("删除外呼类型成功：id=%s", type_id)

    # ---------- 内部 ----------

    def _is_referenced(self, type_id: int) -> bool:
        return bool(
            self.ref.count_scenes_by_type(type_id)
            or self.ref.count_child_types(type_id)
            or self.ref.count_tasks_by_type(type_id)
        )

    def _validate_parent(
        self, *, tenant_id: int, level: int, parent_id: int | None, exclude_id: int | None = None
    ) -> None:
        if level == 1:
            if parent_id is not None:
                raise ParamError("一级类型不允许指定父类型")
            return

        if parent_id is None:
            raise ParamError("二级子类型必须指定父类型")
        if parent_id == exclude_id:
            raise ParamError("父类型不能是自己")

        parent = self.repo.get_by_id(parent_id)
        if parent is None:
            raise NotFound("父类型不存在")
        if parent.tenant_id != tenant_id:
            raise ParamError("父类型与子类型不属于同一租户")
        if parent.level != 1:
            raise ParamError("仅支持两级类型，父类型必须是一级类型")

    def set_status(self, type_id: int, status: CommonStatus) -> OutboundType:
        """启用 / 停用（OB-004）。"""
        outbound_type = self.get_type(type_id)
        if outbound_type.status != status:
            outbound_type.status = status
            self.db.commit()
            logger.info("外呼类型状态变更：id=%s -> %s", type_id, status)
        return outbound_type


def ensure_type_enabled(db: Session, type_id: int) -> OutboundType:
    """供其他服务复用的类型可用性校验。"""
    outbound_type = OutboundTypeRepository(db).get_by_id(type_id)
    if outbound_type is None:
        raise NotFound("外呼类型不存在")
    if outbound_type.status != CommonStatus.ENABLED:
        raise StateNotAllowed("外呼类型已停用")
    return outbound_type
