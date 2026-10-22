"""外呼号码数据访问（OB-001 / OB-005）。

次数扣减只提供原子 UPDATE，禁止读改写（§13）。
"""

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.outbound import OutboundNumber, OutboundTaskNumber
from app.models.outbound.enums import CommonStatus


class OutboundNumberRepository:
    """外呼号码查询与原子扣减。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, number_id: int) -> OutboundNumber | None:
        stmt = select(OutboundNumber).where(
            OutboundNumber.id == number_id, OutboundNumber.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_caller_number(self, tenant_id: int, caller_number: str) -> OutboundNumber | None:
        stmt = select(OutboundNumber).where(
            OutboundNumber.tenant_id == tenant_id,
            OutboundNumber.caller_number == caller_number,
            OutboundNumber.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        caller_number: str | None = None,
        display_name: str | None = None,
        status: CommonStatus | None = None,
    ) -> Select:
        stmt = stmt.where(OutboundNumber.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(OutboundNumber.tenant_id == tenant_id)
        if caller_number:
            stmt = stmt.where(OutboundNumber.caller_number.ilike(f"%{caller_number}%"))
        if display_name:
            stmt = stmt.where(OutboundNumber.display_name.ilike(f"%{display_name}%"))
        if status is not None:
            stmt = stmt.where(OutboundNumber.status == status)
        return stmt

    def list_paged(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        caller_number: str | None = None,
        display_name: str | None = None,
        status: CommonStatus | None = None,
    ) -> list[OutboundNumber]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(
            select(OutboundNumber),
            tenant_id=tenant_id,
            caller_number=caller_number,
            display_name=display_name,
            status=status,
        )
        stmt = stmt.order_by(OutboundNumber.id.desc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(
        self,
        *,
        tenant_id: int | None = None,
        caller_number: str | None = None,
        display_name: str | None = None,
        status: CommonStatus | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(OutboundNumber),
            tenant_id=tenant_id,
            caller_number=caller_number,
            display_name=display_name,
            status=status,
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> OutboundNumber:
        number = OutboundNumber(**values)
        self.db.add(number)
        self.db.flush()
        return number

    # ---------- 候选号码（供 §14 选择器使用）----------

    def list_available(
        self,
        *,
        tenant_id: int | None = None,
        number_ids: list[int] | None = None,
    ) -> list[OutboundNumber]:
        """可用的号码：启用 + 未删除 + 未达次数上限。"""
        stmt = select(OutboundNumber).where(
            OutboundNumber.is_deleted.is_(False),
            OutboundNumber.status == CommonStatus.ENABLED,
            or_(
                OutboundNumber.usage_limit.is_(None),
                OutboundNumber.used_count < OutboundNumber.usage_limit,
            ),
        )
        if tenant_id is not None:
            stmt = stmt.where(OutboundNumber.tenant_id == tenant_id)
        if number_ids is not None:
            if not number_ids:
                return []
            stmt = stmt.where(OutboundNumber.id.in_(number_ids))
        stmt = stmt.order_by(OutboundNumber.id.asc())
        return list(self.db.execute(stmt).scalars().all())

    def list_task_bound_numbers(self, task_id: int) -> list[tuple[OutboundNumber, int, int]]:
        """任务绑定的可用号码，附带 (sort_order, priority) 供 ORDER 策略排序。"""
        stmt = (
            select(OutboundNumber, OutboundTaskNumber.sort_order, OutboundTaskNumber.priority)
            .join(OutboundTaskNumber, OutboundTaskNumber.number_id == OutboundNumber.id)
            .where(
                OutboundTaskNumber.task_id == task_id,
                OutboundTaskNumber.is_deleted.is_(False),
                OutboundTaskNumber.enabled.is_(True),
                OutboundNumber.is_deleted.is_(False),
                OutboundNumber.status == CommonStatus.ENABLED,
                or_(
                    OutboundNumber.usage_limit.is_(None),
                    OutboundNumber.used_count < OutboundNumber.usage_limit,
                ),
            )
            .order_by(
                OutboundTaskNumber.sort_order.asc(),
                OutboundTaskNumber.priority.asc(),
                OutboundNumber.id.asc(),
            )
        )
        return [
            (row[0], int(row[1]), int(row[2])) for row in self.db.execute(stmt).all()
        ]

    # ---------- 原子扣减（§13 核心规则）----------

    def consume_atomically(self, number_id: int, *, step: int = 1) -> int:
        """原子扣减使用次数，返回受影响行数。

        必须保证：号码存在、未删除、状态可用、且 used_count + step <= usage_limit。
        调用方只能以 `affected_rows == 1` 判定扣减成功（§13）。
        """
        stmt = (
            update(OutboundNumber)
            .where(
                OutboundNumber.id == number_id,
                OutboundNumber.is_deleted.is_(False),
                OutboundNumber.status == CommonStatus.ENABLED,
                or_(
                    OutboundNumber.usage_limit.is_(None),
                    OutboundNumber.used_count + step <= OutboundNumber.usage_limit,
                ),
            )
            .values(used_count=OutboundNumber.used_count + step)
        )
        result = self.db.execute(stmt)
        return int(result.rowcount or 0)

    def refresh(self, number_id: int) -> OutboundNumber | None:
        """重新读取号码当前值（扣减后用于回显）。"""
        self.db.expire_all()
        return self.get_by_id(number_id)
