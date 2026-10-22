"""电话簿 / 号码查询 Provider 抽象（§29）。"""

from abc import ABC, abstractmethod


class PhoneProvider(ABC):
    """第三方号码查询：按 UserID / OrderID 获取电话号码列表。"""

    name: str = "base"

    @abstractmethod
    async def get_user_phones(
        self,
        *,
        user_id: str | None = None,
        order_id: str | None = None,
    ) -> list[str]:
        """返回该用户 / 订单关联的号码列表（可能为空）。"""
