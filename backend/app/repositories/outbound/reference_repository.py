"""跨表引用与主数据查询：租户校验、引用计数（供删除 / 编辑前校验使用）。

引用校验集中在此，避免各 Service 各写一份判断（§60 数据过滤必须集中实现）。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.outbound import (
    Agent,
    CallbackFlow,
    IvrFlow,
    OutboundList,
    OutboundRecord,
    OutboundScene,
    OutboundTask,
    OutboundTaskNumber,
    OutboundType,
    Site,
    SkillQueue,
    Tenant,
)
from app.models.outbound.enums import CommonStatus
from app.models.user import User


class ReferenceRepository:
    """主数据读取与跨表引用计数。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 租户（OB-001 租户设置与验证）----------

    def get_tenant_by_id(self, tenant_id: int) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.id == tenant_id, Tenant.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    # ---------- 其他主数据 ----------

    def get_site_by_id(self, site_id: int) -> Site | None:
        stmt = select(Site).where(Site.id == site_id, Site.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_skill_queue_by_id(self, skill_queue_id: int) -> SkillQueue | None:
        stmt = select(SkillQueue).where(
            SkillQueue.id == skill_queue_id, SkillQueue.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_ivr_flow_by_id(self, flow_id: int) -> IvrFlow | None:
        stmt = select(IvrFlow).where(IvrFlow.id == flow_id, IvrFlow.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_agent_by_id(self, agent_id: int) -> Agent | None:
        stmt = select(Agent).where(Agent.id == agent_id, Agent.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_by_id(self, user_id: int) -> User | None:
        """按主键读取用户（坐席开通时需要校验关联用户）。"""
        stmt = select(User).where(User.id == user_id, User.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def list_enabled_tenants(self, limit: int = 200) -> list[Tenant]:
        """启用中的租户选项（供前端下拉选择，避免前端硬编码租户 ID）。"""
        stmt = (
            select(Tenant)
            .where(Tenant.is_deleted.is_(False), Tenant.status == CommonStatus.ENABLED)
            .order_by(Tenant.id.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_enabled_sites(
        self, tenant_id: int | None = None, limit: int = 200
    ) -> list[Site]:
        """启用中的站点选项（外呼任务按站点筛选 / 归属）。"""
        stmt = (
            select(Site)
            .where(Site.is_deleted.is_(False), Site.status == CommonStatus.ENABLED)
            .order_by(Site.id.asc())
            .limit(limit)
        )
        if tenant_id is not None:
            stmt = stmt.where(Site.tenant_id == tenant_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_enabled_skill_queues(
        self,
        tenant_id: int | None = None,
        site_id: int | None = None,
        limit: int = 200,
    ) -> list[SkillQueue]:
        """启用中的技能队列选项。"""
        stmt = (
            select(SkillQueue)
            .where(
                SkillQueue.is_deleted.is_(False), SkillQueue.status == CommonStatus.ENABLED
            )
            .order_by(SkillQueue.id.asc())
            .limit(limit)
        )
        if tenant_id is not None:
            stmt = stmt.where(SkillQueue.tenant_id == tenant_id)
        if site_id is not None:
            stmt = stmt.where(SkillQueue.site_id == site_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_agent_options(
        self,
        tenant_id: int | None = None,
        skill_queue_id: int | None = None,
        limit: int = 200,
    ) -> list[Agent]:
        """坐席选项（含各状态，供人工外呼 / 工作台选择执行坐席）。"""
        stmt = (
            select(Agent)
            .where(Agent.is_deleted.is_(False))
            .order_by(Agent.id.asc())
            .limit(limit)
        )
        if tenant_id is not None:
            stmt = stmt.where(Agent.tenant_id == tenant_id)
        if skill_queue_id is not None:
            stmt = stmt.where(Agent.skill_queue_id == skill_queue_id)
        return list(self.db.execute(stmt).scalars().all())

    # ---------- 类型引用 ----------

    def count_scenes_by_type(self, type_id: int, *, include_deleted: bool = False) -> int:
        """引用该外呼类型的场景数量（OB-004：被场景引用禁止删除）。"""
        stmt = select(func.count()).select_from(OutboundScene).where(
            OutboundScene.type_id == type_id
        )
        if not include_deleted:
            stmt = stmt.where(OutboundScene.is_deleted.is_(False))
        return int(self.db.execute(stmt).scalar_one())

    def count_child_types(self, type_id: int) -> int:
        """子类型数量（父类型仍有子类型时禁止删除）。"""
        stmt = (
            select(func.count())
            .select_from(OutboundType)
            .where(OutboundType.parent_id == type_id, OutboundType.is_deleted.is_(False))
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_tasks_by_type(self, type_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(OutboundTask)
            .where(OutboundTask.type_id == type_id, OutboundTask.is_deleted.is_(False))
        )
        return int(self.db.execute(stmt).scalar_one())

    # ---------- 场景引用 ----------

    def list_tasks_using_scenes(self, scene_ids: list[int]) -> list[str]:
        """返回引用了这些场景的任务名称（OB-003 删除失败时需回显引用任务）。"""
        if not scene_ids:
            return []
        stmt = select(OutboundTask.task_name).where(
            OutboundTask.scene_id.in_(scene_ids), OutboundTask.is_deleted.is_(False)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_tasks_by_scene(self, scene_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(OutboundTask)
            .where(OutboundTask.scene_id == scene_id, OutboundTask.is_deleted.is_(False))
        )
        return int(self.db.execute(stmt).scalar_one())

    # ---------- 号码引用 ----------

    def count_tasks_by_number(self, number_id: int) -> int:
        """被任务号码配置引用的次数（OB-001：号码被任务引用时禁止删除）。"""
        stmt = (
            select(func.count())
            .select_from(OutboundTaskNumber)
            .where(
                OutboundTaskNumber.number_id == number_id,
                OutboundTaskNumber.is_deleted.is_(False),
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    # ---------- IVR 流程引用 ----------

    def count_tasks_by_ivr_flow(self, flow_id: int) -> int:
        """引用该 IVR 流程的任务数量（OB-017：被任务引用禁止删除 / 停用）。"""
        stmt = (
            select(func.count())
            .select_from(OutboundTask)
            .where(
                OutboundTask.ivr_flow_id == flow_id,
                OutboundTask.is_deleted.is_(False),
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_tasks_using_ivr_flows(self, flow_ids: list[int]) -> list[str]:
        """返回引用了这些 IVR 流程的任务名称（删除失败时回显引用任务）。"""
        if not flow_ids:
            return []
        stmt = select(OutboundTask.task_name).where(
            OutboundTask.ivr_flow_id.in_(flow_ids), OutboundTask.is_deleted.is_(False)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_callback_flows_by_ivr_flow(self, ivr_flow_id: int) -> int:
        """引用该 IVR 流程的回呼流程数量（OB-029：被回呼流程引用禁止删除 IVR 流程）。"""
        stmt = (
            select(func.count())
            .select_from(CallbackFlow)
            .where(
                CallbackFlow.ivr_flow_id == ivr_flow_id,
                CallbackFlow.is_deleted.is_(False),
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    # ---------- 任务执行数据（OB-020：复制不涉及、删除前用于提示）----------

    def count_task_lists(self, task_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(OutboundList)
            .where(OutboundList.task_id == task_id, OutboundList.is_deleted.is_(False))
        )
        return int(self.db.execute(stmt).scalar_one())

    def count_task_records(self, task_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(OutboundRecord)
            .where(OutboundRecord.task_id == task_id, OutboundRecord.is_deleted.is_(False))
        )
        return int(self.db.execute(stmt).scalar_one())
