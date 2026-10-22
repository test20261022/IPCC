"""专家组服务：组维护与成员全量覆盖。"""

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import Conflict, NotFound, ParamError
from app.models.qc.review import QcReviewerGroup
from app.models.user import User
from app.repositories.qc.reviewer_repository import QcReviewerGroupRepository
from app.schemas.qc.review import (
    ReviewerGroupCreate,
    ReviewerGroupMembersUpdate,
    ReviewerGroupUpdate,
)
from app.services.outbound.common import ensure_tenant_active

logger = logging.getLogger(__name__)


class QcReviewerService:
    """专家组业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = QcReviewerGroupRepository(db)

    # ---------- 可入组用户 ----------

    def list_assignable_users(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        keyword: str | None = None,
    ) -> tuple[list[User], int]:
        items = self.repo.list_assignable_users(
            page=page, page_size=page_size, tenant_id=tenant_id, keyword=keyword
        )
        total = self.repo.count_assignable_users(tenant_id=tenant_id, keyword=keyword)
        return items, total

    # ---------- 专家组 ----------

    def list_groups(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict], int]:
        groups = self.repo.list_paged(
            page=page, page_size=page_size, tenant_id=tenant_id, keyword=keyword
        )
        counts = self.repo.count_members([group.id for group in groups])
        items = [self._group_dict(group, counts.get(group.id, 0)) for group in groups]
        total = self.repo.count(tenant_id=tenant_id, keyword=keyword)
        return items, total

    def create_group(self, payload: ReviewerGroupCreate) -> dict:
        ensure_tenant_active(self.db, payload.tenant_id)
        if self.repo.get_by_name(payload.tenant_id, payload.name) is not None:
            raise Conflict(f"专家组名称已存在：{payload.name}")

        group = self.repo.create(
            tenant_id=payload.tenant_id,
            name=payload.name,
            description=payload.description,
        )
        member_ids = self._validate_member_ids(payload.member_user_ids)
        for user_id in sorted(member_ids):
            self._add_member(group, user_id)

        self.db.commit()
        logger.info(
            "创建专家组成功：id=%s name=%s members=%s", group.id, group.name, len(member_ids)
        )
        return self._group_dict(group, len(member_ids))

    def get_group_detail(self, group_id: int) -> dict:
        group = self._get_group(group_id)
        members = self.repo.list_members(group_id)
        users = {
            user.id: user
            for user in self.repo.list_users_by_ids([member.user_id for member in members])
        }
        return {
            **self._group_dict(group, len(members)),
            "members": [self._member_dict(member, users.get(member.user_id)) for member in members],
        }

    def update_group(self, group_id: int, payload: ReviewerGroupUpdate) -> dict:
        group = self._get_group(group_id)
        # 只更新显式传入且非空字段（None 视为未提供，避免把 NOT NULL 列清空）
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            return self._group_dict(group, len(self.repo.list_members(group_id)))

        if "name" in changes and changes["name"] != group.name:
            if self.repo.get_by_name(group.tenant_id, str(changes["name"])) is not None:
                raise Conflict(f"专家组名称已存在：{changes['name']}")

        for field, value in changes.items():
            setattr(group, field, value)
        self.db.commit()
        logger.info("更新专家组成功：id=%s fields=%s", group_id, sorted(changes))
        return self._group_dict(group, len(self.repo.list_members(group_id)))

    def replace_members(self, group_id: int, payload: ReviewerGroupMembersUpdate) -> dict:
        """全量覆盖组成员：未出现在列表中的成员被软删除。"""
        group = self._get_group(group_id)
        member_ids = self._validate_member_ids([item.user_id for item in payload.members])

        self.repo.soft_delete_members(group_id)
        added: set[int] = set()
        for item in payload.members:
            if item.user_id in added:
                continue
            added.add(item.user_id)
            self._add_member(group, item.user_id, item.is_active, item.max_concurrent)

        self.db.commit()
        logger.info("覆盖专家组成员：group=%s members=%s", group_id, len(member_ids))
        return self.get_group_detail(group_id)

    # ---------- 内部 ----------

    def _get_group(self, group_id: int) -> QcReviewerGroup:
        group = self.repo.get_by_id(group_id)
        if group is None:
            raise NotFound("专家组不存在")
        return group

    def _validate_member_ids(self, user_ids: list[int]) -> set[int]:
        """去重并校验用户存在且启用。"""
        unique_ids = list(dict.fromkeys(user_ids))
        if not unique_ids:
            return set()
        found = {user.id for user in self.repo.list_users_by_ids(unique_ids)}
        missing = [user_id for user_id in unique_ids if user_id not in found]
        if missing:
            raise ParamError(f"专家账号不存在或已停用：{missing}")
        return set(unique_ids)

    def _add_member(
        self,
        group: QcReviewerGroup,
        user_id: int,
        is_active: bool = True,
        max_concurrent: int | None = None,
    ) -> None:
        self.repo.add_member(
            tenant_id=group.tenant_id,
            group_id=group.id,
            user_id=user_id,
            is_active=is_active,
            max_concurrent=max_concurrent or settings.QC_DEFAULT_QUOTA_PER_REVIEWER,
        )

    @staticmethod
    def _group_dict(group: QcReviewerGroup, member_count: int) -> dict:
        return {
            "id": group.id,
            "tenant_id": group.tenant_id,
            "name": group.name,
            "description": group.description,
            "member_count": member_count,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        }

    @staticmethod
    def _member_dict(member, user: User | None) -> dict:
        return {
            "user_id": member.user_id,
            "is_active": member.is_active,
            "max_concurrent": member.max_concurrent,
            "username": user.username if user is not None else "",
            "nickname": user.nickname if user is not None else "",
        }


__all__ = ["QcReviewerService"]