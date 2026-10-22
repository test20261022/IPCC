"""外呼场景服务（OB-003）。

规则：
- 被外呼任务引用过的场景不可编辑、不可删除（删除失败时回显引用任务清单）。
- 删除一级场景联动软删除其下全部二级场景；批量删除同样遵守引用校验。
"""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ParamError, ResourceReferenced, StateNotAllowed
from app.models.outbound import OutboundScene
from app.models.outbound.enums import CommonStatus
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.repositories.outbound.scene_repository import OutboundSceneRepository
from app.repositories.outbound.type_repository import OutboundTypeRepository
from app.schemas.outbound.config import OutboundSceneCreate, OutboundSceneUpdate
from app.services.outbound.common import apply_updates, ensure_tenant_active

logger = logging.getLogger(__name__)


class OutboundSceneService:
    """外呼场景业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = OutboundSceneRepository(db)
        self.type_repo = OutboundTypeRepository(db)
        self.ref = ReferenceRepository(db)

    # ---------- 查询 ----------

    def list_scenes(self, **filters: object) -> tuple[list[OutboundScene], int]:
        page = int(filters.pop("page"))  # type: ignore[arg-type]
        page_size = int(filters.pop("page_size"))  # type: ignore[arg-type]
        items = self.repo.list_paged(page=page, page_size=page_size, **filters)  # type: ignore[arg-type]
        total = self.repo.count(**filters)  # type: ignore[arg-type]
        return items, total

    def get_scene(self, scene_id: int) -> OutboundScene:
        scene = self.repo.get_by_id(scene_id)
        if scene is None:
            raise NotFound("外呼场景不存在")
        return scene

    def build_tree(
        self,
        *,
        tenant_id: int | None = None,
        type_id: int | None = None,
        status: CommonStatus | None = None,
    ) -> list[dict]:
        """构建两级树：一级场景携带 children（OB-003 两级结构）。"""
        scenes = self.repo.list_all(tenant_id=tenant_id, type_id=type_id, status=status)
        nodes: dict[int, dict] = {}
        for scene in scenes:
            nodes[scene.id] = {"scene": scene, "children": []}

        roots: list[dict] = []
        for scene in scenes:
            node = nodes[scene.id]
            parent = nodes.get(scene.parent_id) if scene.parent_id else None
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)
        return roots

    # ---------- 新增 ----------

    def create_scene(self, payload: OutboundSceneCreate) -> OutboundScene:
        ensure_tenant_active(self.db, payload.tenant_id)
        self._validate_parent(
            tenant_id=payload.tenant_id,
            type_id=payload.type_id,
            level=payload.level,
            parent_id=payload.parent_id,
        )
        if self.repo.exists_same_name(
            tenant_id=payload.tenant_id,
            type_id=payload.type_id,
            parent_id=payload.parent_id,
            name=payload.name,
        ):
            raise Conflict(f"同级下已存在同名场景：{payload.name}")

        scene = self.repo.create(**payload.model_dump())
        self.db.commit()
        logger.info("创建外呼场景成功：id=%s name=%s level=%s", scene.id, scene.name, scene.level)
        return scene

    # ---------- 编辑 ----------

    def update_scene(self, scene_id: int, payload: OutboundSceneUpdate) -> OutboundScene:
        scene = self.get_scene(scene_id)

        # 规则 3.1：被外呼任务引用过的场景不可编辑
        if self.ref.count_tasks_by_scene(scene_id):
            raise ResourceReferenced("外呼场景已被外呼任务引用，禁止编辑")

        changes = payload.model_dump(exclude_unset=True)
        target_type_id = int(changes.get("type_id", scene.type_id))
        if "type_id" in changes and self.type_repo.get_by_id(target_type_id) is None:
            raise NotFound("外呼类型不存在")

        if "name" in changes and changes["name"] != scene.name:
            if self.repo.exists_same_name(
                tenant_id=scene.tenant_id,
                type_id=target_type_id,
                parent_id=scene.parent_id,
                name=str(changes["name"]),
            ):
                raise Conflict(f"同级下已存在同名场景：{changes['name']}")

        if "type_id" in changes and scene.parent_id is not None:
            # 二级场景换类型时必须与父场景保持一致
            parent = self.repo.get_by_id(scene.parent_id)
            if parent is not None and parent.type_id != target_type_id:
                raise ParamError("二级场景的类型必须与父场景一致")

        apply_updates(scene, payload)
        self.db.commit()
        logger.info("更新外呼场景成功：id=%s fields=%s", scene_id, sorted(changes))
        return scene

    # ---------- 删除 ----------

    def delete_scene(self, scene_id: int) -> dict:
        """删除单个场景；一级场景联动软删除二级场景（规则 3.3）。"""
        return self.batch_delete_scenes([scene_id])

    def batch_delete_scenes(self, scene_ids: list[int]) -> dict:
        """批量删除，全量校验通过才执行（任一被引用则整体拒绝）。"""
        if not scene_ids:
            raise ParamError("请选择要删除的场景")

        targets = self._collect_delete_targets(scene_ids)

        referenced_tasks = self.ref.list_tasks_using_scenes([scene.id for scene in targets])
        if referenced_tasks:
            # 规则 3.1 / 3.2：回显引用任务清单
            names = "、".join(dict.fromkeys(referenced_tasks))
            raise ResourceReferenced(f"场景已被以下任务引用，禁止删除：{names}")

        for scene in targets:
            scene.mark_deleted()
        self.db.commit()

        logger.info("删除外呼场景成功：请求=%s 实际软删除=%s", len(scene_ids), len(targets))
        return {"requested": len(scene_ids), "deleted": len(targets)}

    # ---------- 内部 ----------

    def _collect_delete_targets(self, scene_ids: list[int]) -> list[OutboundScene]:
        """把入参展开为「自身 + 其下二级场景」，并去重。"""
        found = {scene.id: scene for scene in self.repo.get_by_ids(scene_ids)}
        missing = [scene_id for scene_id in scene_ids if scene_id not in found]
        if missing:
            raise NotFound(f"外呼场景不存在：{missing}")

        targets: dict[int, OutboundScene] = dict(found)
        for scene in list(found.values()):
            if scene.level == 1:
                for child in self.repo.list_children(scene.id):
                    targets.setdefault(child.id, child)
        return list(targets.values())

    def _validate_parent(
        self, *, tenant_id: int, type_id: int, level: int, parent_id: int | None
    ) -> None:
        outbound_type = self.type_repo.get_by_id(type_id)
        if outbound_type is None:
            raise NotFound("外呼类型不存在")
        if outbound_type.tenant_id != tenant_id:
            raise ParamError("外呼类型与场景不属于同一租户")

        if level == 1:
            if parent_id is not None:
                raise ParamError("一级场景不允许指定父场景")
            return

        if parent_id is None:
            raise ParamError("二级场景必须指定父场景")

        parent = self.repo.get_by_id(parent_id)
        if parent is None:
            raise NotFound("父场景不存在")
        if parent.level != 1:
            raise ParamError("仅支持两级场景，父场景必须是一级场景")
        if parent.type_id != type_id:
            raise ParamError("二级场景的类型必须与父场景一致")

    def set_status(self, scene_id: int, status: CommonStatus) -> OutboundScene:
        scene = self.get_scene(scene_id)
        if scene.status != status:
            scene.status = status
            self.db.commit()
            logger.info("外呼场景状态变更：id=%s -> %s", scene_id, status)
        return scene

    def ensure_scene_enabled(self, scene_id: int) -> OutboundScene:
        """供其他服务复用的场景可用性校验。"""
        scene = self.repo.get_by_id(scene_id)
        if scene is None:
            raise NotFound("外呼场景不存在")
        if scene.status != CommonStatus.ENABLED:
            raise StateNotAllowed("外呼场景已停用")
        return scene
