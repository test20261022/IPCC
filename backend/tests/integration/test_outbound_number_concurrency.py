"""外呼号码并发扣减测试（§13 / §73）。

本用例不使用事务回滚夹具，而是用独立连接真实提交数据并并发扣减，
验证「同一号码同时扣减不会重复扣减、不会突破次数上限」。
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.models.outbound import OutboundNumber, Tenant
from app.repositories.outbound.number_repository import OutboundNumberRepository

CONCURRENCY_ATTEMPTS = 24
CONCURRENCY_WORKERS = 8
USAGE_LIMIT = 5


@pytest.fixture
def committed_number(engine: Engine):
    """在独立事务中提交一个号码，测试结束后物理清理。"""
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with maker() as session:
        tenant = Tenant(code="CONC-TENANT", name="并发测试租户")
        session.add(tenant)
        session.flush()
        number = OutboundNumber(
            tenant_id=tenant.id,
            display_name="并发号码",
            caller_number="02199990000",
            usage_limit=USAGE_LIMIT,
        )
        session.add(number)
        session.commit()
        tenant_id, number_id = tenant.id, number.id

    yield {"tenant_id": tenant_id, "number_id": number_id}

    with maker() as session:
        session.execute(delete(OutboundNumber).where(OutboundNumber.id == number_id))
        session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        session.commit()


def _consume_in_own_connection(engine: Engine, number_id: int) -> int:
    """每次扣减使用独立连接与独立事务，模拟真实并发调用。"""
    with sessionmaker(bind=engine)() as session:
        affected = OutboundNumberRepository(session).consume_atomically(number_id)
        session.commit()
        return affected


def test_concurrent_consume_never_exceeds_limit(engine: Engine, committed_number: dict) -> None:
    """24 次并发扣减、上限 5：成功次数必须正好等于 5，且 used_count 不回退。"""
    number_id = committed_number["number_id"]

    with ThreadPoolExecutor(max_workers=CONCURRENCY_WORKERS) as pool:
        results = list(
            pool.map(
                lambda _: _consume_in_own_connection(engine, number_id),
                range(CONCURRENCY_ATTEMPTS),
            )
        )

    successes = sum(1 for affected in results if affected == 1)
    failures = sum(1 for affected in results if affected == 0)

    assert successes == USAGE_LIMIT, f"并发扣减成功次数应为 {USAGE_LIMIT}，实际 {successes}"
    assert failures == CONCURRENCY_ATTEMPTS - USAGE_LIMIT

    with sessionmaker(bind=engine)() as session:
        number = session.get(OutboundNumber, number_id)
        assert number is not None
        assert number.used_count == USAGE_LIMIT


def test_consume_after_exhaustion_returns_zero(engine: Engine, committed_number: dict) -> None:
    number_id = committed_number["number_id"]

    for _ in range(USAGE_LIMIT):
        assert _consume_in_own_connection(engine, number_id) == 1
    assert _consume_in_own_connection(engine, number_id) == 0


def test_consume_on_disabled_number_returns_zero(engine: Engine, committed_number: dict) -> None:
    from app.models.outbound.enums import CommonStatus

    number_id = committed_number["number_id"]
    with sessionmaker(bind=engine)() as session:
        number = session.get(OutboundNumber, number_id)
        number.status = CommonStatus.DISABLED
        session.commit()

    assert _consume_in_own_connection(engine, number_id) == 0


def test_consume_applies_step_atomically(engine: Engine, committed_number: dict) -> None:
    """一次扣减 step 超过剩余次数时必须整体失败，不允许部分扣减。"""
    number_id = committed_number["number_id"]

    with sessionmaker(bind=engine)() as session:
        affected = OutboundNumberRepository(session).consume_atomically(
            number_id, step=USAGE_LIMIT + 1
        )
        session.commit()
        assert affected == 0

    with sessionmaker(bind=engine)() as session:
        number = session.get(OutboundNumber, number_id)
        assert number.used_count == 0
