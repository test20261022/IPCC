"""主叫号码选择器（§14）。

选择器独立于任务 / 执行逻辑，所有号码优先级排序集中在此，禁止散落到 Router / Task / Repository。
全部号码不可用时统一抛 40903（OUTBOUND_NUMBER_EXHAUSTED）。
"""

from app.core.exceptions import NumberExhausted
from app.models.outbound import OutboundNumber
from app.models.outbound.enums import NumberSelectStrategy
from app.repositories.outbound.number_repository import OutboundNumberRepository


class OutboundNumberSelector:
    """按策略挑选可用主叫号码。"""

    def __init__(self, db) -> None:  # noqa: ANN001 - Session 类型在调用方已确定
        self.repo = OutboundNumberRepository(db)

    def select(
        self,
        *,
        strategy: NumberSelectStrategy = NumberSelectStrategy.ORDER,
        tenant_id: int | None = None,
        task_id: int | None = None,
        number_ids: list[int] | None = None,
        exclude_ids: list[int] | None = None,
    ) -> OutboundNumber:
        """返回一个可用号码；无可选号码时抛 NumberExhausted。"""
        candidates = self.ordered_candidates(
            strategy=strategy,
            tenant_id=tenant_id,
            task_id=task_id,
            number_ids=number_ids,
            exclude_ids=exclude_ids,
        )
        if not candidates:
            raise NumberExhausted("外呼号码已全部不可用（不存在 / 停用 / 次数耗尽）")
        return candidates[0]

    def ordered_candidates(
        self,
        *,
        strategy: NumberSelectStrategy = NumberSelectStrategy.ORDER,
        tenant_id: int | None = None,
        task_id: int | None = None,
        number_ids: list[int] | None = None,
        exclude_ids: list[int] | None = None,
    ) -> list[OutboundNumber]:
        """按策略排序后的可用号码清单（供执行层「逐个尝试主叫号码」使用）。"""
        candidates = self._candidates(
            tenant_id=tenant_id, task_id=task_id, number_ids=number_ids
        )
        excluded = set(exclude_ids or [])
        candidates = [item for item in candidates if item[0].id not in excluded]
        return [item[0] for item in self._apply_strategy(candidates, strategy)]

    # ---------- 内部 ----------

    def _candidates(
        self, *, tenant_id: int | None, task_id: int | None, number_ids: list[int] | None
    ) -> list[tuple[OutboundNumber, int, int]]:
        """返回 (号码, sort_order, priority)。任务维度优先取任务绑定号码。"""
        if task_id is not None:
            bound = self.repo.list_task_bound_numbers(task_id)
            if bound:
                return bound
        numbers = self.repo.list_available(tenant_id=tenant_id, number_ids=number_ids)
        return [(number, 0, 0) for number in numbers]

    @staticmethod
    def _apply_strategy(
        candidates: list[tuple[OutboundNumber, int, int]], strategy: NumberSelectStrategy
    ) -> list[tuple[OutboundNumber, int, int]]:
        if strategy == NumberSelectStrategy.AVAILABLE_FIRST:
            # 剩余次数多者优先；不限次数视为无限，排最前
            return sorted(
                candidates,
                key=lambda item: (
                    0
                    if item[0].usage_limit is None
                    else 1,
                    -(item[0].usage_limit - item[0].used_count)
                    if item[0].usage_limit is not None
                    else 0,
                    item[0].id,
                ),
            )
        if strategy == NumberSelectStrategy.ROUND_ROBIN:
            # 已用次数最少者优先；因每次使用都会累加，天然形成轮询
            return sorted(candidates, key=lambda item: (item[0].used_count, item[0].id))
        # ORDER 与 CUSTOM 都按任务绑定的 sort_order / priority，再按 id
        # ASSUMPTION-014：需求未定义 CUSTOM 的具体规则，暂与 ORDER 一致
        return sorted(candidates, key=lambda item: (item[1], item[2], item[0].id))
