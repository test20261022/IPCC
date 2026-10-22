"""外呼任务服务（OB-006 查询增强 / OB-020 任务复制 / §17 配置 / §18 状态机）。

复制语义（§23）：只复制基础配置，绝不复制执行数据（名单 / 记录 / 会话 / 历史 / 小结 / 统计）。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import (
    Conflict,
    NotFound,
    ParamError,
    ResourceReferenced,
    StateNotAllowed,
)
from app.models.outbound import OutboundTask, OutboundTaskNumber
from app.models.outbound.enums import DispatchMode, TaskStatus
from app.repositories.outbound.number_repository import OutboundNumberRepository
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.repositories.outbound.scene_repository import OutboundSceneRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.repositories.outbound.type_repository import OutboundTypeRepository
from app.schemas.outbound.task import (
    OutboundTaskCopyRequest,
    OutboundTaskCreate,
    OutboundTaskNumberItem,
    OutboundTaskUpdate,
)
from app.services.outbound import task_state
from app.services.outbound.common import apply_updates, ensure_tenant_active

logger = logging.getLogger(__name__)

# 复制时携带的配置字段（§23）；执行数据（名单 / 记录 / 会话 / 历史 / 小结 / 统计）一律不复制
_COPY_FIELDS = (
    "site_id",
    "skill_queue_id",
    "type_id",
    "scene_id",
    "dispatch_mode",
    "number_select_strategy",
    "retry_interval",
    "max_retry_count",
    "call_timeout_seconds",
    "max_concurrency",
    "adjustment_factor",
    "ivr_flow_id",
    "description",
)


class OutboundTaskService:
    """外呼任务业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = OutboundTaskRepository(db)
        self.ref = ReferenceRepository(db)
        self.type_repo = OutboundTypeRepository(db)
        self.scene_repo = OutboundSceneRepository(db)
        self.number_repo = OutboundNumberRepository(db)

    # ---------- 查询（OB-006）----------

    def list_tasks(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        task_name: str | None = None,
        site_id: int | None = None,
        skill_queue_id: int | None = None,
        type_id: int | None = None,
        scene_id: int | None = None,
        status: TaskStatus | None = None,
        dispatch_mode: DispatchMode | None = None,
    ) -> tuple[list[OutboundTask], int]:
        filters = {
            "tenant_id": tenant_id,
            "task_name": task_name,
            "site_id": site_id,
            "skill_queue_id": skill_queue_id,
            "type_id": type_id,
            "scene_id": scene_id,
            "status": status,
            "dispatch_mode": dispatch_mode,
        }
        items = self.repo.list_paged(page=page, page_size=page_size, **filters)
        total = self.repo.count(**filters)
        return items, total

    def get_task(self, task_id: int) -> OutboundTask:
        task = self.repo.get_by_id(task_id)
        if task is None:
            raise NotFound("外呼任务不存在")
        return task

    def get_task_detail(self, task_id: int) -> tuple[OutboundTask, list[OutboundTaskNumber]]:
        task = self.get_task(task_id)
        return task, self.repo.list_task_numbers(task_id)

    # ---------- 新增 ----------

    def create_task(self, payload: OutboundTaskCreate) -> OutboundTask:
        ensure_tenant_active(self.db, payload.tenant_id)

        if self.repo.get_by_name(payload.tenant_id, payload.task_name) is not None:
            raise Conflict(f"任务名称已存在：{payload.task_name}")

        values = payload.model_dump(exclude={"numbers"})
        self._validate_references(payload.tenant_id, values)
        number_values = self._validate_numbers(payload.tenant_id, payload.numbers)

        task = self.repo.create(**values, status=TaskStatus.DRAFT)
        for item in number_values:
            self.repo.add_task_number(tenant_id=payload.tenant_id, task_id=task.id, **item)

        self.db.commit()
        logger.info(
            "创建外呼任务成功：id=%s name=%s numbers=%s",
            task.id,
            task.task_name,
            len(number_values),
        )
        return task

    # ---------- 编辑 ----------

    def update_task(self, task_id: int, payload: OutboundTaskUpdate) -> OutboundTask:
        task = self.get_task(task_id)
        task_state.ensure_editable(task.status)

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return task

        if "task_name" in changes and changes["task_name"] != task.task_name:
            if self.repo.get_by_name(task.tenant_id, str(changes["task_name"])) is not None:
                raise Conflict(f"任务名称已存在：{changes['task_name']}")

        self._validate_references(task.tenant_id, changes, current=task)

        apply_updates(task, payload)
        self.db.commit()
        logger.info("更新外呼任务成功：id=%s fields=%s", task_id, sorted(changes))
        return task

    def replace_numbers(
        self, task_id: int, items: list[OutboundTaskNumberItem]
    ) -> list[OutboundTaskNumber]:
        """全量替换任务号码配置（§19 多号码配置）。"""
        task = self.get_task(task_id)
        task_state.ensure_editable(task.status)

        number_values = self._validate_numbers(task.tenant_id, items)
        self.repo.soft_delete_task_numbers(task_id)
        for item in number_values:
            self.repo.add_task_number(
                tenant_id=task.tenant_id, task_id=task.id, **item
            )

        self.db.commit()
        logger.info("替换任务号码配置成功：task=%s count=%s", task_id, len(number_values))
        return self.repo.list_task_numbers(task_id)

    # ---------- 状态流转（§18 / §77）----------

    def change_status(self, task_id: int, target: TaskStatus) -> OutboundTask:
        task = self.get_task(task_id)
        task_state.ensure_transition(task.status, target)

        if target == TaskStatus.READY and self.repo.count_enabled_numbers(task_id) == 0:
            raise StateNotAllowed("请先为该任务配置至少一个启用的外呼号码")

        now = datetime.now(timezone.utc)
        if target == TaskStatus.RUNNING and task.started_at is None:
            task.started_at = now
        if target in task_state.FINISHED_STATUSES:
            task.finished_at = now

        task.status = target
        self.db.commit()
        logger.info("外呼任务状态流转：id=%s -> %s", task_id, target.value)
        return task

    # ---------- 复制（OB-020）----------

    def copy_task(
        self, task_id: int, payload: OutboundTaskCopyRequest
    ) -> tuple[OutboundTask, bool]:
        """复制任务，返回 (任务, 是否本次新建)。

        §78 幂等：同租户下若已存在「来源=本任务且同名」的副本，直接返回该副本。
        """
        source = self.get_task(task_id)

        existing = self.repo.get_copied_task(source.tenant_id, payload.task_name, source.id)
        if existing is not None:
            logger.info("任务复制命中幂等：source=%s target=%s", task_id, existing.id)
            return existing, False

        if self.repo.get_by_name(source.tenant_id, payload.task_name) is not None:
            raise Conflict(f"任务名称已存在：{payload.task_name}")

        values = {field: getattr(source, field) for field in _COPY_FIELDS}
        new_task = self.repo.create(
            tenant_id=source.tenant_id,
            task_name=payload.task_name,
            status=TaskStatus.DRAFT,
            copied_from_id=source.id,
            **values,
        )

        if payload.copy_numbers:
            for row in self.repo.list_task_numbers(source.id):
                self.repo.add_task_number(
                    tenant_id=source.tenant_id,
                    task_id=new_task.id,
                    number_id=row.number_id,
                    order_id=row.order_id,
                    user_id=row.user_id,
                    recipient_number=row.recipient_number,
                    sort_order=row.sort_order,
                    priority=row.priority,
                    enabled=row.enabled,
                )

        self.db.commit()
        logger.info(
            "复制外呼任务成功：source=%s target=%s copy_numbers=%s",
            task_id,
            new_task.id,
            payload.copy_numbers,
        )
        return new_task, True

    # ---------- 删除 ----------

    def delete_task(self, task_id: int) -> dict:
        task = self.get_task(task_id)
        task_state.ensure_deletable(task.status)

        # ASSUMPTION-019：已有执行记录时禁止删除，避免报表与超时回收出现孤儿数据
        record_count = self.ref.count_task_records(task_id)
        if record_count:
            raise ResourceReferenced(
                f"任务已产生 {record_count} 条执行记录，禁止删除；如需终止请改为「取消」"
            )

        removed_numbers = self.repo.soft_delete_task_numbers(task_id)
        task.mark_deleted()
        self.db.commit()
        logger.info("删除外呼任务成功：id=%s 联动软删号码配置=%s", task_id, removed_numbers)
        return {"task_id": task_id, "removed_task_numbers": removed_numbers}

    # ---------- 内部校验 ----------

    def _validate_references(
        self, tenant_id: int, values: dict, current: OutboundTask | None = None
    ) -> None:
        """校验站点 / 技能队列 / 类型 / 场景 / IVR 流程的存在性、租户归属与一致性。"""

        def _current(field: str) -> object:
            return getattr(current, field) if current is not None else None

        site_id = values.get("site_id", _current("site_id"))
        if site_id is not None:
            site = self.ref.get_site_by_id(int(site_id))
            if site is None:
                raise NotFound("站点不存在")
            if site.tenant_id != tenant_id:
                raise ParamError("站点与任务不属于同一租户")

        skill_queue_id = values.get("skill_queue_id", _current("skill_queue_id"))
        if skill_queue_id is not None:
            queue = self.ref.get_skill_queue_by_id(int(skill_queue_id))
            if queue is None:
                raise NotFound("技能队列不存在")
            if queue.tenant_id != tenant_id:
                raise ParamError("技能队列与任务不属于同一租户")
            if site_id is not None and queue.site_id != int(site_id):
                raise ParamError("技能队列不属于所选站点")

        type_id = values.get("type_id", _current("type_id"))
        if type_id is not None:
            outbound_type = self.type_repo.get_by_id(int(type_id))
            if outbound_type is None:
                raise NotFound("外呼类型不存在")
            if outbound_type.tenant_id != tenant_id:
                raise ParamError("外呼类型与任务不属于同一租户")

        scene_id = values.get("scene_id", _current("scene_id"))
        if scene_id is not None:
            scene = self.scene_repo.get_by_id(int(scene_id))
            if scene is None:
                raise NotFound("外呼场景不存在")
            if scene.tenant_id != tenant_id:
                raise ParamError("外呼场景与任务不属于同一租户")
            if type_id is not None and scene.type_id != int(type_id):
                raise ParamError("外呼场景与所选外呼类型不一致")

        ivr_flow_id = values.get("ivr_flow_id", _current("ivr_flow_id"))
        if ivr_flow_id is not None:
            flow = self.ref.get_ivr_flow_by_id(int(ivr_flow_id))
            if flow is None:
                raise NotFound("IVR 流程不存在")
            if flow.tenant_id != tenant_id:
                raise ParamError("IVR 流程与任务不属于同一租户")

    def _validate_numbers(
        self, tenant_id: int, items: list[OutboundTaskNumberItem]
    ) -> list[dict]:
        values: list[dict] = []
        seen: set[int] = set()
        for item in items:
            if item.number_id in seen:
                raise ParamError(f"号码重复配置：{item.number_id}")
            seen.add(item.number_id)

            number = self.number_repo.get_by_id(item.number_id)
            if number is None:
                raise NotFound(f"外呼号码不存在：{item.number_id}")
            if number.tenant_id != tenant_id:
                raise ParamError("外呼号码与任务不属于同一租户")
            values.append(item.model_dump())
        return values
