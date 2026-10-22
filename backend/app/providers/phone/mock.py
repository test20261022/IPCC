"""Mock 电话簿（§30）。

确定性派生号码，便于回归测试与联调：
- OrderID 数字部分 → `137` + 后 8 位（不足补 0）
- UserID 数字部分  → `138` + 后 8 位（不足补 0）

因此测试可以通过构造 user_id / order_id 控制返回号码，
再结合呼叫网关 Mock 的号码规则断言「多号码顺序尝试」等行为。
"""

import re

from app.providers.phone.base import PhoneProvider


def digits_of(text: str | None) -> str:
    return re.sub(r"\D", "", text or "")


class MockPhoneProvider(PhoneProvider):
    name = "mock"

    async def get_user_phones(
        self,
        *,
        user_id: str | None = None,
        order_id: str | None = None,
    ) -> list[str]:
        phones: list[str] = []

        order_digits = digits_of(order_id)
        if order_digits:
            phones.append(f"137{order_digits[-8:].zfill(8)}")

        user_digits = digits_of(user_id)
        if user_digits:
            phone = f"138{user_digits[-8:].zfill(8)}"
            if phone not in phones:
                phones.append(phone)

        return phones
