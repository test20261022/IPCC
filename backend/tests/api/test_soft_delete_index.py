"""软删除与部分唯一索引测试（§50）。"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository


class TestSoftDeleteUniqueIndex:
    def test_duplicate_active_username_rejected(self, db_session: Session) -> None:
        repo = UserRepository(db_session)
        repo.create_user(username="dup_user", password_hash="x")

        with pytest.raises(IntegrityError):
            repo.create_user(username="dup_user", password_hash="x")

    def test_duplicate_active_role_code_rejected(self, db_session: Session) -> None:
        repo = UserRepository(db_session)
        repo.create_role(code="dup_role", name="重复角色")

        with pytest.raises(IntegrityError):
            repo.create_role(code="dup_role", name="重复角色2")


class TestSoftDeleteVisibility:
    def test_username_reusable_after_soft_delete(self, db_session: Session) -> None:
        repo = UserRepository(db_session)

        first = repo.create_user(username="reuse_user", password_hash="x")
        first.mark_deleted()
        db_session.flush()

        second = repo.create_user(username="reuse_user", password_hash="x")
        db_session.flush()

        assert second.id != first.id

    def test_get_by_username_ignores_soft_deleted(self, db_session: Session) -> None:
        repo = UserRepository(db_session)

        old = repo.create_user(username="hidden_user", password_hash="x")
        old.mark_deleted()
        db_session.flush()

        assert repo.get_by_username("hidden_user") is None

        new = repo.create_user(username="hidden_user", password_hash="y")
        db_session.flush()

        found = repo.get_by_username("hidden_user")
        assert found is not None
        assert found.id == new.id

    def test_get_by_id_ignores_soft_deleted(self, db_session: Session) -> None:
        repo = UserRepository(db_session)
        user = repo.create_user(username="gone_user", password_hash="x")
        user.mark_deleted()
        db_session.flush()

        assert repo.get_by_id(user.id) is None

    def test_soft_delete_stamps_deleted_at(self, db_session: Session) -> None:
        repo = UserRepository(db_session)
        user = repo.create_user(username="stamped_user", password_hash="x")
        assert user.deleted_at is None

        user.mark_deleted()
        db_session.flush()

        assert user.is_deleted is True
        assert user.deleted_at is not None


class TestRolePermissionQuery:
    def test_permission_codes_follow_role_assignment(self, db_session: Session) -> None:
        repo = UserRepository(db_session)
        role = repo.create_role(code="perm_role", name="权限角色")
        role.permissions.append(repo.create_permission(code="a:b:c", name="测试权限", module="a"))

        user = repo.create_user(username="perm_user", password_hash="x")
        repo.assign_role(user, role)
        db_session.flush()

        assert repo.get_permission_codes(user.id) == ["a:b:c"]
        assert user.permission_codes() == {"a:b:c"}
        assert user.role_codes == ["perm_role"]

    def test_user_without_role_has_no_permission(self, db_session: Session) -> None:
        repo = UserRepository(db_session)
        user = repo.create_user(username="norole_user", password_hash="x")
        db_session.flush()

        assert repo.get_permission_codes(user.id) == []
