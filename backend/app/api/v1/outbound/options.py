"""外呼下拉选项接口：表单需要的只读主数据。

登录即可访问（不含敏感信息），避免前端硬编码租户 ID 等主键。
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, tenant_scope_optional, tenant_scope_required
from app.core.response import ApiResponse, ok
from app.db.session import get_db
from app.models.outbound.enums import CommonStatus
from app.models.user import User
from app.repositories.outbound.ivr_repository import IvrFlowRepository
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.outbound.config import (
    AgentOptionOut,
    SiteOptionOut,
    SkillQueueOptionOut,
    TaskOptionOut,
    TenantOptionOut,
    UserOptionOut,
)
from app.schemas.outbound.ivr import IvrFlowOptionOut

router = APIRouter(prefix="/outbound/options", tags=["外呼-选项"])


@router.get(
    "/tenants",
    response_model=ApiResponse[list[TenantOptionOut]],
    summary="租户下拉选项",
    description=(
        "返回启用中的租户列表，供业务表单选择归属租户；"
        "绑定租户的普通用户只会看到自己所属租户。"
    ),
)
def list_tenant_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    tenants = ReferenceRepository(db).list_enabled_tenants()
    # 数据范围：绑定租户的普通用户只返回自己的租户，避免下拉里出现越权选项
    if not current_user.is_superuser and current_user.tenant_id is not None:
        tenants = [tenant for tenant in tenants if tenant.id == current_user.tenant_id]
    return ok(
        [
            TenantOptionOut(id=tenant.id, code=tenant.code, name=tenant.name)
            for tenant in tenants
        ]
    )


@router.get(
    "/sites",
    response_model=ApiResponse[list[SiteOptionOut]],
    summary="站点下拉选项",
    description="返回启用中的站点，支持按租户过滤（OB-006 按站点查询任务）。",
)
def list_site_options(
    tenant_id: int | None = Depends(tenant_scope_optional),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    sites = ReferenceRepository(db).list_enabled_sites(tenant_id=tenant_id)
    return ok(
        [
            SiteOptionOut(id=site.id, tenant_id=site.tenant_id, code=site.code, name=site.name)
            for site in sites
        ]
    )


@router.get(
    "/skill-queues",
    response_model=ApiResponse[list[SkillQueueOptionOut]],
    summary="技能队列下拉选项",
    description="返回启用中的技能队列，支持按租户 / 站点过滤（OB-006 按技能队列查询任务）。",
)
def list_skill_queue_options(
    tenant_id: int | None = Depends(tenant_scope_optional),
    site_id: int | None = Query(default=None, gt=0, description="站点"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    queues = ReferenceRepository(db).list_enabled_skill_queues(
        tenant_id=tenant_id, site_id=site_id
    )
    return ok(
        [
            SkillQueueOptionOut(
                id=queue.id,
                tenant_id=queue.tenant_id,
                site_id=queue.site_id,
                code=queue.code,
                name=queue.name,
            )
            for queue in queues
        ]
    )


@router.get(
    "/agents",
    response_model=ApiResponse[list[AgentOptionOut]],
    summary="坐席下拉选项",
    description="返回坐席最小字段集合，供人工外呼选择执行坐席、工作台选择坐席使用。",
)
def list_agent_options(
    tenant_id: int | None = Depends(tenant_scope_optional),
    skill_queue_id: int | None = Query(default=None, gt=0, description="技能队列"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    agents = ReferenceRepository(db).list_agent_options(
        tenant_id=tenant_id, skill_queue_id=skill_queue_id
    )
    return ok(
        [
            AgentOptionOut(
                id=agent.id,
                user_id=agent.user_id,
                tenant_id=agent.tenant_id,
                site_id=agent.site_id,
                skill_queue_id=agent.skill_queue_id,
                extension=agent.extension,
                status=agent.status,
            )
            for agent in agents
        ]
    )


@router.get(
    "/ivr-flows",
    response_model=ApiResponse[list[IvrFlowOptionOut]],
    summary="IVR 流程下拉选项",
    description="返回启用中的 IVR 流程，供外呼任务表单选择（OB-017）。",
)
def list_ivr_flow_options(
    tenant_id: int = Depends(tenant_scope_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    flows = IvrFlowRepository(db).list_paged(
        page=1, page_size=200, tenant_id=tenant_id, status=CommonStatus.ENABLED
    )
    return ok(
        [
            IvrFlowOptionOut(
                id=flow.id,
                tenant_id=flow.tenant_id,
                code=flow.code,
                name=flow.name,
                entry_node_key=flow.entry_node_key,
            )
            for flow in flows
        ]
    )


@router.get(
    "/tasks",
    response_model=ApiResponse[list[TaskOptionOut]],
    summary="外呼任务下拉选项",
    description=(
        "返回外呼任务的最小字段集合，供报表 / 坐席 / 回呼等页面的「任务」筛选使用。"
        "这些页面本身不需要 outbound:task:list 权限，故不走任务列表接口，避免越权耦合。"
    ),
)
def list_task_options(
    tenant_id: int = Depends(tenant_scope_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    tasks = OutboundTaskRepository(db).list_paged(
        page=1, page_size=200, tenant_id=tenant_id
    )
    return ok(
        [
            TaskOptionOut(id=task.id, tenant_id=task.tenant_id, task_name=task.task_name)
            for task in tasks
        ]
    )


@router.get(
    "/users",
    response_model=ApiResponse[list[UserOptionOut]],
    summary="用户下拉选项",
    description="返回启用中的用户账号，供开通坐席时选择关联用户（§3.1 坐席必须关联 users）。",
)
def list_user_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    users = UserRepository(db).list_active_options()
    return ok(
        [
            UserOptionOut(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                tenant_id=user.tenant_id,
            )
            for user in users
        ]
    )
