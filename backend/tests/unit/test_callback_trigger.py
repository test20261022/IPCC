"""回呼触发条件匹配单元测试（§45）。纯内存，不依赖数据库。"""

import pytest

from app.models.outbound.enums import CallbackTriggerType
from app.services.outbound.callback_trigger import (
    CallbackTriggerContext,
    condition_priority,
    in_business_hours,
    match_condition,
    normalize_triggers,
)


def _ctx(**overrides) -> CallbackTriggerContext:
    payload = {"source": "IVR"}
    payload.update(overrides)
    return CallbackTriggerContext(**payload)


class TestNormalizeTriggers:
    def test_accepts_enum_values_case_insensitively(self) -> None:
        assert normalize_triggers(["no_agent", "Key"]) == [
            CallbackTriggerType.NO_AGENT,
            CallbackTriggerType.KEY,
        ]

    def test_ignores_unknown_and_deduplicates(self) -> None:
        assert normalize_triggers(["KEY", "KEY", "NOT_A_TRIGGER"]) == [
            CallbackTriggerType.KEY
        ]

    @pytest.mark.parametrize("value", [None, "", 0, [], {}])
    def test_non_list_values_yield_empty(self, value: object) -> None:
        assert normalize_triggers(value) == []

    def test_single_string_value(self) -> None:
        assert normalize_triggers("NO_ANSWER") == [CallbackTriggerType.NO_ANSWER]


class TestBusinessHours:
    @pytest.mark.parametrize(
        ("config", "now", "expected"),
        [
            (None, "12:00", True),  # 未配置即全天候
            ([], "03:00", True),
            (["09:00-18:00"], "10:00", True),
            (["09:00-18:00"], "20:00", False),
            (["09:00-12:00", "14:00-18:00"], "13:00", False),
            (["invalid"], "13:00", True),  # 配置非法视同未配置
        ],
    )
    def test_in_business_hours(self, config: object, now: str, expected: bool) -> None:
        assert in_business_hours(config, now) is expected


class TestNoTriggerConfigured:
    def test_empty_condition_never_matches(self) -> None:
        decision = match_condition({}, _ctx(no_agent=True))
        assert decision.matched is False
        assert decision.reason == "流程未配置自动触发条件"

    def test_none_condition_never_matches(self) -> None:
        assert match_condition(None, _ctx(keys=("0",))).matched is False


class TestTriggerHits:
    def test_no_agent(self) -> None:
        condition = {"triggers": ["NO_AGENT"]}
        hit = match_condition(condition, _ctx(no_agent=True))
        assert hit.matched is True
        assert hit.trigger_type == CallbackTriggerType.NO_AGENT
        assert "无可用坐席" in hit.reason

        miss = match_condition(condition, _ctx(no_agent=False))
        assert miss.matched is False
        assert miss.trigger_type is None

    def test_no_answer(self) -> None:
        hit = match_condition({"triggers": ["NO_ANSWER"]}, _ctx(no_answer=True))
        assert hit.matched is True
        assert hit.trigger_type == CallbackTriggerType.NO_ANSWER

    def test_key_with_configured_keys(self) -> None:
        condition = {"triggers": ["KEY"], "keys": ["0", "9"]}
        hit = match_condition(condition, _ctx(keys=("1", "9")))
        assert hit.matched is True
        assert hit.trigger_type == CallbackTriggerType.KEY
        assert "9" in hit.reason

        miss = match_condition(condition, _ctx(keys=("1", "2")))
        assert miss.matched is False

    def test_key_without_configured_keys_matches_any_key(self) -> None:
        hit = match_condition({"triggers": ["KEY"]}, _ctx(keys=("5",)))
        assert hit.matched is True
        assert match_condition({"triggers": ["KEY"]}, _ctx()).matched is False

    def test_out_of_hours(self) -> None:
        condition = {"triggers": ["OUT_OF_HOURS"], "business_hours": ["09:00-18:00"]}
        hit = match_condition(condition, _ctx(current_time="20:30"))
        assert hit.matched is True
        assert hit.trigger_type == CallbackTriggerType.OUT_OF_HOURS

        inside = match_condition(condition, _ctx(current_time="10:00"))
        assert inside.matched is False

    def test_out_of_hours_needs_business_hours(self) -> None:
        """未配置业务时段时无法判定「非业务时段」。"""
        decision = match_condition({"triggers": ["OUT_OF_HOURS"]}, _ctx(current_time="20:30"))
        assert decision.matched is False

    def test_business_hours_gate_blocks_other_triggers(self) -> None:
        """不在业务时段且触发条件不含 OUT_OF_HOURS 时整体不触发。"""
        condition = {"triggers": ["NO_AGENT"], "business_hours": ["09:00-18:00"]}
        decision = match_condition(condition, _ctx(no_agent=True, current_time="22:00"))
        assert decision.matched is False
        assert decision.business_hours_blocked is True
        assert "不在业务时段" in decision.reason


class TestOrSemantics:
    def test_first_configured_trigger_wins(self) -> None:
        """多个触发条件同时满足时，按固定顺序取第一个，保证结果确定。"""
        condition = {"triggers": ["NO_ANSWER", "NO_AGENT", "KEY"], "keys": ["0"]}
        decision = match_condition(
            condition, _ctx(no_agent=True, no_answer=True, keys=("0",))
        )
        assert decision.matched is True
        assert decision.trigger_type == CallbackTriggerType.NO_AGENT

    def test_key_used_when_others_miss(self) -> None:
        condition = {"triggers": ["NO_AGENT", "KEY"], "keys": ["0"]}
        decision = match_condition(condition, _ctx(keys=("0",)))
        assert decision.trigger_type == CallbackTriggerType.KEY


class TestLimitsAndExtras:
    def test_max_attempts_blocks_trigger(self) -> None:
        condition = {"triggers": ["NO_AGENT"], "max_attempts": 2}
        assert match_condition(condition, _ctx(no_agent=True, attempt_count=1)).matched
        decision = match_condition(condition, _ctx(no_agent=True, attempt_count=2))
        assert decision.matched is False
        assert "尝试次数已达上限" in decision.reason

    def test_default_max_attempts_is_three(self) -> None:
        condition = {"triggers": ["NO_AGENT"]}
        assert match_condition(condition, _ctx(no_agent=True, attempt_count=2)).matched
        assert not match_condition(condition, _ctx(no_agent=True, attempt_count=3)).matched

    def test_delay_and_priority_are_passed_through(self) -> None:
        condition = {"triggers": ["NO_AGENT"], "delay_seconds": "300", "priority": "5"}
        decision = match_condition(condition, _ctx(no_agent=True))
        assert decision.delay_seconds == 300
        assert decision.priority == 5

    def test_delay_survives_when_not_matched(self) -> None:
        condition = {"triggers": ["NO_AGENT"], "delay_seconds": 60}
        decision = match_condition(condition, _ctx())
        assert decision.matched is False
        assert decision.delay_seconds == 60

    def test_negative_delay_is_clamped(self) -> None:
        condition = {"triggers": ["NO_AGENT"], "delay_seconds": -5}
        decision = match_condition(condition, _ctx(no_agent=True))
        assert decision.delay_seconds == 0

    def test_invalid_numeric_falls_back(self) -> None:
        condition = {"triggers": ["NO_AGENT"], "delay_seconds": "abc", "max_attempts": "x"}
        decision = match_condition(condition, _ctx(no_agent=True))
        assert decision.matched is True
        assert decision.delay_seconds == 0

    def test_condition_priority(self) -> None:
        assert condition_priority({"priority": 3}) == 3
        assert condition_priority({}) == 0
        assert condition_priority(None) == 0
        assert condition_priority({"priority": "bad"}) == 0

    def test_trigger_value_helper(self) -> None:
        decision = match_condition({"triggers": ["NO_AGENT"]}, _ctx(no_agent=True))
        assert decision.trigger_value == "NO_AGENT"
