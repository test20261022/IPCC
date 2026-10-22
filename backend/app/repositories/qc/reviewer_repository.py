"""专家组数据访问：组 / 组成员 / 可入组用户。

组成员用 user_id 只读引用 users 表（基线冻结，不新建专家表）。
"""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.qc.review import QcReviewerGroup, QcReviewerGroupMember
from app.models.user import User


class QcReviewerGroupRepository:
    """专家组的查询与成员维护。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------- 专家组 ----------

    def get_by_id(self, group_id: int) -> QcReviewerGroup | None:
        stmt = select(QcReviewerGroup).where(
            QcReviewerGroup.id == group_id,
            QcReviewerGroup.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_name(self, tenant_id: int, name: str) -> QcReviewerGroup | None:
        stmt = select(QcReviewerGroup).where(
            QcReviewerGroup.tenant_id == tenant_id,
            QcReviewerGroup.name == name,
            QcReviewerGroup.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def _apply_filters(
        stmt: Select, *, tenant_id: int | None = None, keyword: str | None = None
    ) -> Select:
        stmt = stmt.where(QcReviewerGroup.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(QcReviewerGroup.tenant_id == tenant_id)
        if keyword:
            stmt = stmt.where(QcReviewerGroup.name.ilike(f"%{keyword}%"))
        return stmt

    def list_paged(
        self, *, page: int, page_size: int, tenant_id: int | None = None, keyword: str | None = None
    ) -> list[QcReviewerGroup]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(
            select(QcReviewerGroup), tenant_id=tenant_id, keyword=keyword
        )
        stmt = stmt.order_by(QcReviewerGroup.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, *, tenant_id: int | None = None, keyword: str | None = None) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(QcReviewerGroup), tenant_id=tenant_id, keyword=keyword
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> QcReviewerGroup:
        group = QcReviewerGroup(**values)
        self.db.add(group)
        self.db.flush()
        return group

    # ---------- 组成员 ----------

    def list_members(self, group_id: int) -> list[QcReviewerGroupMember]:
        stmt = (
            select(QcReviewerGroupMember)
            .where(
                QcReviewerGroupMember.group_id == group_id,
                QcReviewerGroupMember.is_deleted.is_(False),
            )
            .order_by(QcReviewerGroupMember.user_id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_active_members(self, group_id: int) -> list[QcReviewerGroupMember]:
        """启用中的组成员，按 user_id 升序（派发分片顺序必须稳定）。"""
        stmt = (
            select(QcReviewerGroupMember)
            .where(
                QcReviewerGroupMember.group_id == group_id,
                QcReviewerGroupMember.is_deleted.is_(False),
                QcReviewerGroupMember.is_active.is_(True),
            )
            .order_by(QcReviewerGroupMember.user_id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_members(self, group_ids: list[int]) -> dict[int, int]:
        """批量统计组成员数（列表页 member_count）。"""
        if not group_ids:
            return {}
        stmt = (
            select(QcReviewerGroupMember.group_id, func.count())
            .where(
                QcReviewerGroupMember.group_id.in_(group_ids),
                QcReviewerGroupMember.is_deleted.is_(False),
            )
            .group_by(QcReviewerGroupMember.group_id)
        )
        return {int(group_id): int(amount) for group_id, amount in self.db.execute(stmt).all()}

    def soft_delete_members(self, group_id: int) -> int:
        """软删除组内全部成员（replace_members 全量覆盖的前置步骤）。"""
        members = self.list_members(group_id)
        for member in members:
            member.mark_deleted()
        self.db.flush()
        return len(members)

    def add_member(self, **values: object) -> QcReviewerGroupMember:
        member = QcReviewerGroupMember(**values)
        self.db.add(member)
        self.db.flush()
        return member

    # ---------- 可入组用户 ----------

    @staticmethod
    def _apply_user_filters(
        stmt: Select, *, tenant_id: int | None = None, keyword: str | None = None
    ) -> Select:
        stmt = stmt.where(User.is_active.is_(True), User.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(User.tenant_id == tenant_id)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(or_(User.username.ilike(pattern), User.nickname.ilike(pattern)))
        return stmt

    def list_assignable_users(
        self, *, page: int, page_size: int, tenant_id: int | None = None, keyword: str | None = None
    ) -> list[User]:
        offset = (page - 1) * page_size
        stmt = self._apply_user_filters(select(User), tenant_id=tenant_id, keyword=keyword)
        stmt = stmt.order_by(User.id.asc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count_assignable_users(
        self, *, tenant_id: int | None = None, keyword: str | None = None
    ) -> int:
        stmt = self._apply_user_filters(
            select(func.count()).select_from(User), tenant_id=tenant_id, keyword=keyword
        )
        return int(self.db.execute(stmt).scalar_one())

    def list_users_by_ids(self, user_ids: list[int]) -> list[User]:
        """按 id 批量取用户（校验成员合法性 / 填充 username、nickname）。"""
        if not user_ids:
            return []
        stmt = select(User).where(
            User.id.in_(user_ids), User.is_active.is_(True), User.is_deleted.is_(False)
        )
        return list(self.db.execute(stmt).scalars().all())


__all__ = ["QcReviewerGroupRepository"]