"""pytest 全局夹具：真实 PostgreSQL 上跑迁移，用例内事务隔离。

并发相关能力（SELECT FOR UPDATE / 部分唯一索引 / JSONB）依赖真实 PostgreSQL，
因此测试库与开发库同为 PostgreSQL，不使用 SQLite 替代（§98 禁止假测试）。
"""

import os
from collections.abc import Iterator
from pathlib import Path

# 必须在导入 app 之前注入：测试用低成本 bcrypt，避免大量登录用例拖慢整体耗时
os.environ.setdefault("BCRYPT_ROUNDS", "4")
# 测试进程内不启动 APScheduler（超时回收与重试派发在用例里手动触发，保证可复现）
os.environ.setdefault("SCHEDULER_ENABLED", "false")
# ASR 演示环境可能配为 aliyun（模拟实现，含轮询延时），测试固定用 mock 保证确定性与速度
os.environ.setdefault("ASR_PROVIDER", "mock")
# 回调签名密钥：CI 与干净环境没有 backend/.env，缺省为空会让回调用例全部 500
os.environ.setdefault("CALL_GATEWAY_CALLBACK_SECRET", "test-callback-secret")

import pytest
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import BASE_DIR, settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.repositories.user_repository import UserRepository

# ---------------- 测试库准备 ----------------


def _ensure_database_exists() -> None:
    """确保测试库存在（不存在则基于维护库创建）。"""
    url = make_url(settings.TEST_DATABASE_URL)
    # 注意：str(URL) 会把密码渲染为 ***，必须显式 render_as_string(hide_password=False)
    admin_url = url.set(database="postgres").render_as_string(hide_password=False)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """测试库引擎：会话开始时执行 alembic upgrade head。"""
    _ensure_database_exists()
    os.environ["ALEMBIC_DATABASE_URL"] = settings.TEST_DATABASE_URL

    alembic_config = AlembicConfig(str(Path(BASE_DIR) / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(Path(BASE_DIR) / "alembic"))
    command.upgrade(alembic_config, "head")

    eng = create_engine(settings.TEST_DATABASE_URL, pool_pre_ping=True, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """每个用例一个外层事务，结束时整体回滚，保证用例互不影响。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def _silence_operation_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """操作日志中间件走独立会话，测试中屏蔽以免污染开发库。"""

    def _noop(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("app.main._write_operation_log", _noop)


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """覆盖 get_db，使接口与用例共用同一事务会话。"""

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------- 数据夹具 ----------------


@pytest.fixture
def admin_user(db_session: Session):
    """超级管理员。"""
    repo = UserRepository(db_session)
    user = repo.create_user(
        username="admin_test",
        password_hash=hash_password("Admin@123456"),
        nickname="测试管理员",
        is_superuser=True,
    )
    db_session.flush()
    return user


@pytest.fixture
def normal_user(db_session: Session):
    """仅拥有 outbound:number:list 权限的普通用户。"""
    repo = UserRepository(db_session)
    role = repo.create_role(code="operator", name="运营人员")
    permission = repo.create_permission(
        code="outbound:number:list", name="号码查看", module="outbound"
    )
    role.permissions.append(permission)

    user = repo.create_user(
        username="user_test",
        password_hash=hash_password("User@123456"),
        nickname="测试用户",
    )
    repo.assign_role(user, role)
    db_session.flush()
    return user


def login(client: TestClient, username: str, password: str) -> str:
    """辅助函数：登录并返回 access_token。"""
    response = client.post(
        f"{settings.API_V1_PREFIX}/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


DEFAULT_USER_PASSWORD = "User@123456"


@pytest.fixture
def make_user(db_session: Session):
    """按需创建用户并授予指定权限码的工厂。"""
    from app.repositories.user_repository import UserRepository

    def _make(
        username: str,
        *permission_codes: str,
        is_superuser: bool = False,
        tenant_id: int | None = None,
    ) -> User:
        repo = UserRepository(db_session)
        user = repo.create_user(
            username=username,
            password_hash=hash_password(DEFAULT_USER_PASSWORD),
            nickname=username,
            is_superuser=is_superuser,
            tenant_id=tenant_id,
        )
        if permission_codes:
            role = repo.create_role(code=f"role_{username}", name=f"角色-{username}")
            for code in permission_codes:
                permission = repo.get_permission_by_code(code)
                if permission is None:
                    permission = repo.create_permission(code=code, name=code, module="test")
                role.permissions.append(permission)
            repo.assign_role(user, role)
        db_session.flush()
        return user

    return _make


@pytest.fixture
def user_token(client: TestClient, make_user):
    """创建带权限的用户并返回其 token。

    默认**不绑定租户**，此时用户视为平台账号（不受租户范围限制）；
    需要验证数据范围（规则 7）时传 tenant_id 显式绑定。
    """

    def _token(
        username: str,
        *permission_codes: str,
        is_superuser: bool = False,
        tenant_id: int | None = None,
    ) -> str:
        make_user(
            username,
            *permission_codes,
            is_superuser=is_superuser,
            tenant_id=tenant_id,
        )
        return login(client, username, DEFAULT_USER_PASSWORD)

    return _token


# ---------------- 外呼业务夹具 ----------------


@pytest.fixture
def tenant(db_session: Session):
    from app.models.outbound import Tenant

    entity = Tenant(code="TENANT-001", name="测试租户")
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.fixture
def disabled_tenant(db_session: Session):
    from app.models.outbound import Tenant
    from app.models.outbound.enums import CommonStatus

    entity = Tenant(code="TENANT-OFF", name="停用租户", status=CommonStatus.DISABLED)
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.fixture
def outbound_type(db_session: Session, tenant):
    from app.models.outbound import OutboundType

    entity = OutboundType(tenant_id=tenant.id, code="TYPE-001", name="营销外呼", level=1)
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.fixture
def outbound_scene(db_session: Session, tenant, outbound_type):
    from app.models.outbound import OutboundScene

    entity = OutboundScene(
        tenant_id=tenant.id, type_id=outbound_type.id, level=1, name="一级场景-新客"
    )
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.fixture
def outbound_number(db_session: Session, tenant):
    from app.models.outbound import OutboundNumber

    entity = OutboundNumber(
        tenant_id=tenant.id,
        display_name="客服热线",
        caller_number="02188886666",
        usage_limit=2,
    )
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.fixture
def outbound_task(db_session: Session, tenant, outbound_type, outbound_scene):
    from app.models.outbound import OutboundTask

    entity = OutboundTask(
        tenant_id=tenant.id,
        task_name="引用场景的任务",
        type_id=outbound_type.id,
        scene_id=outbound_scene.id,
    )
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.fixture
def site(db_session: Session, tenant):
    from app.models.outbound import Site

    entity = Site(tenant_id=tenant.id, code="SITE-001", name="站点一")
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.fixture
def skill_queue(db_session: Session, tenant, site):
    from app.models.outbound import SkillQueue

    entity = SkillQueue(tenant_id=tenant.id, site_id=site.id, code="QUEUE-001", name="外呼队列")
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.fixture
def ivr_flow(db_session: Session, tenant):
    from app.models.outbound import IvrFlow

    entity = IvrFlow(tenant_id=tenant.id, code="IVR-001", name="默认 IVR 流程")
    db_session.add(entity)
    db_session.flush()
    return entity


# ---------------- 质检业务夹具 ----------------

#: 质检模块全量权限码（用例按需授权，测试中不依赖内置 admin 角色）
QC_ALL_PERMISSIONS = (
    "qc:conversation:list",
    "qc:conversation:create",
    "qc:conversation:update",
    "qc:conversation:delete",
    "qc:conversation:import",
    "qc:conversation:transcribe",
    "qc:reviewer:list",
    "qc:reviewer:create",
    "qc:reviewer:update",
    "qc:task:list",
    "qc:task:create",
    "qc:task:update",
    "qc:task:delete",
    "qc:task:dispatch",
    "qc:task:cancel",
    "qc:review:work",
    "qc:review:submit",
    "qc:case:list",
    "qc:case:create",
    "qc:case:update",
    "qc:case:delete",
    "qc:case:publish",
    "qc:report:list",
)


@pytest.fixture
def make_qc_conversation(db_session: Session):
    """工厂：直接落库一条质检对话，便于专注被测逻辑（导入链路由专门用例覆盖）。"""
    from datetime import datetime, timezone

    from app.models.qc import QcConversation
    from app.models.qc.enums import (
        ConversationChannel,
        ConversationSource,
        TranscriptStatus,
    )

    def _make(
        tenant_id: int,
        *,
        agent_name: str = "客服A",
        ext_ref_no: str | None = None,
        started_at: datetime | None = None,
        **overrides,
    ) -> QcConversation:
        values: dict = {
            "tenant_id": tenant_id,
            "agent_name": agent_name,
            "ext_ref_no": ext_ref_no,
            "channel": ConversationChannel.CHAT,
            "source": ConversationSource.MANUAL,
            "started_at": started_at or datetime.now(timezone.utc),
            "transcript_status": TranscriptStatus.NOT_REQUIRED,
        }
        values.update(overrides)
        entity = QcConversation(**values)
        db_session.add(entity)
        db_session.flush()
        return entity

    return _make


@pytest.fixture
def make_qc_reviewer_group(db_session: Session):
    """工厂：直接落库专家组及其启用成员。"""
    from app.models.qc.review import QcReviewerGroup, QcReviewerGroupMember

    def _make(
        tenant_id: int,
        *,
        name: str = "质检专家组",
        user_ids: tuple[int, ...] = (),
        is_active: bool = True,
    ) -> QcReviewerGroup:
        group = QcReviewerGroup(tenant_id=tenant_id, name=name)
        db_session.add(group)
        db_session.flush()
        for user_id in user_ids:
            db_session.add(
                QcReviewerGroupMember(
                    tenant_id=tenant_id,
                    group_id=group.id,
                    user_id=user_id,
                    is_active=is_active,
                )
            )
        db_session.flush()
        return group

    return _make

