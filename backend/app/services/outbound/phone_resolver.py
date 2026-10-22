"""呼叫号码解析（OB-021 1.2/1.3/2.3、OB-023 1、§20）。

统一负责「名单自带号码 + 第三方电话簿 + 任务配置的来源顺序」的合并去重，
执行引擎 / 会话 / 看板三处共用，避免顺序逻辑出现多份实现。

号码顺序规则（§23）：严格按任务配置中 OrderID / UserID / 收件人号码 的顺序。
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.outbound import OutboundList, OutboundTask
from app.providers import get_phone_provider
from app.providers.phone.base import PhoneProvider
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.utils.async_bridge import run_sync
from app.utils.validators import is_valid_phone

SOURCE_ORDER_ID = "order_id"
SOURCE_USER_ID = "user_id"
SOURCE_RECIPIENT = "recipient_number"

#: 任务未配置号码来源顺序时的默认顺序（ASSUMPTION-034）
DEFAULT_SOURCE_ORDER: tuple[str, ...] = (SOURCE_ORDER_ID, SOURCE_USER_ID, SOURCE_RECIPIENT)

SOURCE_LABELS: dict[str, str] = {
    SOURCE_ORDER_ID: "OrderID",
    SOURCE_USER_ID: "UserID",
    SOURCE_RECIPIENT: "收件人号码",
}


@dataclass
class ResolvedPhones:
    """号码解析结果（含来源明细，便于看板展示「接口信息」）。"""

    phones: list[str] = field(default_factory=list)
    source_order: list[str] = field(default_factory=list)
    list_phones: list[str] = field(default_factory=list)
    provider_phones: dict[str, list[str]] = field(default_factory=dict)

    @property
    def phone_source(self) -> str:
        """可读的来源说明，例如「OrderID → UserID」。"""
        if not self.source_order:
            return ""
        return " → ".join(SOURCE_LABELS.get(item, item) for item in self.source_order)


class OutboundPhoneResolver:
    """按任务配置解析出可呼叫号码清单。"""

    def __init__(self, db: Session, *, phone_provider: PhoneProvider | None = None) -> None:
        self.task_repo = OutboundTaskRepository(db)
        self._phone_provider = phone_provider

    @property
    def phone_provider(self) -> PhoneProvider:
        if self._phone_provider is None:
            self._phone_provider = get_phone_provider()
        return self._phone_provider

    def source_order(self, task: OutboundTask) -> list[str]:
        """任务级来源顺序：取各来源在所有启用配置行中的最小顺序值。"""
        orders: dict[str, int] = {}
        for row in self.task_repo.list_task_numbers(task.id):
            if not row.enabled:
                continue
            for name, value in (
                (SOURCE_ORDER_ID, row.order_id),
                (SOURCE_USER_ID, row.user_id),
                (SOURCE_RECIPIENT, row.recipient_number),
            ):
                if value is None:
                    continue
                orders[name] = min(orders.get(name, int(value)), int(value))

        if not orders:
            return list(DEFAULT_SOURCE_ORDER)
        return [name for name, _ in sorted(orders.items(), key=lambda item: (item[1], item[0]))]

    def resolve(self, task: OutboundTask | None, name_list: OutboundList) -> ResolvedPhones:
        """解析号码：名单自带 → 配置来源顺序（含第三方电话簿）→ 去重。"""
        result = ResolvedPhones(source_order=self.source_order(task) if task else [])

        def add(value: object, *, from_provider: bool = False, source: str = "") -> None:
            if value is None:
                return
            candidate = str(value).strip()
            if not is_valid_phone(candidate):
                return
            if candidate not in result.phones:
                result.phones.append(candidate)
            if from_provider and source:
                bucket = result.provider_phones.setdefault(source, [])
                if candidate not in bucket:
                    bucket.append(candidate)

        # 1) 名单自带号码（导入的号码列）
        for item in name_list.phone_numbers or []:
            add(item)
            if item:
                candidate = str(item).strip()
                if candidate and candidate not in result.list_phones:
                    result.list_phones.append(candidate)

        # 2) 按任务配置的来源顺序取号
        for source in result.source_order:
            if source == SOURCE_ORDER_ID and name_list.order_id:
                for phone in run_sync(
                    self.phone_provider.get_user_phones(order_id=name_list.order_id)
                ):
                    add(phone, from_provider=True, source=SOURCE_ORDER_ID)
            elif source == SOURCE_USER_ID and name_list.user_id:
                for phone in run_sync(
                    self.phone_provider.get_user_phones(user_id=name_list.user_id)
                ):
                    add(phone, from_provider=True, source=SOURCE_USER_ID)
            elif source == SOURCE_RECIPIENT:
                add(name_list.recipient_phone)

        return result
