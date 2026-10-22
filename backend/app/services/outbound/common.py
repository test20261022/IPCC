"""外呼服务公共工具：租户校验、部分更新、分页装配。"""

from typing import Any, Protocol, TypeVar

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, StateNotAllowed
from app.core.response import page_data
from app.models.outbound import Tenant
from app.models.outbound.enums import CommonStatus
from app.repositories.outbound.reference_repository import ReferenceRepository

T = TypeVar("T")


class PartialUpdatePayload(Protocol):
    """只要具备 model_dump 的 Pydantic 入参即可用于部分更新。"""

    def model_dump(self, *, exclude_unset: bool = ...) -> dict[str, Any]: ...


def ensure_tenant_active(db: Session, tenant_id: int) -> Tenant:
    """校验租户存在且启用（OB-001 外呼号码租户设置和验证）。"""
    tenant = ReferenceRepository(db).get_tenant_by_id(tenant_id)
    if tenant is None:
        raise NotFound("租户不存在")
    if tenant.status != CommonStatus.ENABLED:
        raise StateNotAllowed("租户已停用，禁止操作")
    return tenant


def apply_updates(instance: Any, payload: PartialUpdatePayload) -> dict[str, Any]:
    """按「只更新显式传入字段」的语义写回对象，返回被更新的字段。"""
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(instance, field, value)
    return changes


def build_page(items: list[T], total: int, page: int, page_size: int) -> dict[str, Any]:
    """统一分页响应结构（§57）。"""
    return page_data(items, total, page, page_size)
