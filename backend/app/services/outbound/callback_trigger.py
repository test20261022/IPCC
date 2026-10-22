"""回呼触发条件匹配（OB-029 IVR 回呼 / OB-030 人工回呼，§45）。

设计要点：
1. 触发类型用 CallbackTriggerType 枚举收敛（§77 禁止魔法字符串散落），
   避免把「什么情况下该回呼」硬编码在服务层。
2. 参数放在 CallbackFlow.trigger_condition（JSONB），本模块是唯一的解释入口。
3. 纯逻辑：不访问数据库、不依赖系统时钟（时间由调用方传入），便于单测覆盖。

trigger_condition 结构（全部可选，缺省即不限制）::

    {
      "triggers": ["NO_AGENT", "KEY"],        # 自动触发条件，任一命中即触发；空表示不自动触发
      "keys": ["0", "9"],                     # KEY 触发命中的按键，空表示「用户按了任意键」
      "business_hours": ["09:00-18:00"],      # 业务时段，用于门禁与 OUT_OF_HOURS 判定
      "delay_seconds": 300,                   # 生成回呼任务后延迟多久回呼
      "max_attempts": 3,                      # 达到该尝试次数后不再自动触发
      "priority": 0                           # 多流程同时命中时，数值小者优先
    }
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.models.outbound.enums import CallbackTriggerType
from app.services.outbound.ivr_strategy import is_valid_time_range, time_in_range

logger = logging.getLogger(__name__)

#: 触发类型判定顺序（与 CallbackTriggerType 成员顺序一致，保证多命中时结果确定）
TRIGGER_ORDER: tuple[CallbackTriggerType, ...] = (
    CallbackTriggerType.NO_AGENT,
    CallbackTriggerType.NO_ANSWER,
    CallbackTriggerType.KEY,
    CallbackTriggerType.OUT_OF_HOURS,
)

DEFAULT_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class CallbackTriggerContext:
    """触发判定所需的事实，全部由调用方提供，便于复现与测试。"""

    source: str
    keys: tuple[str, ...] = ()
    no_agent: bool = False
    no_answer: bool = False
    current_time: str | None = None
    attempt_count: int = 0


@dataclass(frozen=True)
class CallbackTriggerDecision:
    """触发判定结果。"""

    matched: bool
    reason: str
    trigger_type: CallbackTriggerType | None = None
    delay_seconds: int = 0
    priority: int = 0
    business_hours_blocked: bool = False
    details: tuple[str, ...] = field(default=())

    @property
    def trigger_value(self) -> str | None:
        """命中的触发类型字符串值（写入 CallbackTask.trigger_type）。"""
        return self.trigger_type.value if self.trigger_type else None


def _as_str_list(value: Any) -> list[str]:
    """把 JSONB 里的取值统一成字符串列表（容忍单值、数字、None）。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, list | tuple):
        return [str(item) for item in value if item is not None]
    return []


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_triggers(value: Any) -> list[CallbackTriggerType]:
    """把配置里的 triggers 归一成枚举列表，未知取值忽略并记日志。"""
    result: list[CallbackTriggerType] = []
    for raw in _as_str_list(value):
        try:
            item = CallbackTriggerType(raw.strip().upper())
        except ValueError:
            logger.warning("回呼流程配置了未知触发条件，已忽略：%s", raw)
            continue
        if item not in result:
            result.append(item)
    return result


def in_business_hours(business_hours: Any, current_time: str | None) -> bool:
    """当前时间是否在业务时段内；未配置业务时段视为「全天候」。"""
    ranges = [item for item in _as_str_list(business_hours) if is_valid_time_range(item)]
    if not ranges:
        return True
    return any(time_in_range(item, current_time) for item in ranges)


def _trigger_hit(
    trigger: CallbackTriggerType,
    *,
    condition: dict[str, Any],
    context: CallbackTriggerContext,
    all_day: bool,
) -> str | None:
    """单个触发条件是否命中；命中返回中文说明，未命中返回 None。"""
    if trigger == CallbackTriggerType.NO_AGENT:
        if context.no_agent:
            return "转人工时技能队列无可用坐席"
        return None

    if trigger == CallbackTriggerType.NO_ANSWER:
        if context.no_answer:
            return "客户未接通坐席即挂断"
        return None

    if trigger == CallbackTriggerType.KEY:
        configured = _as_str_list(condition.get("keys"))
        if not configured:
            # 未配置具体按键：只要客户在流程中按过键即命中
            return f"客户按键：{'、'.join(context.keys)}" if context.keys else None
        hit = [key for key in context.keys if key in configured]
        return f"客户按键命中：{'、'.join(hit)}" if hit else None

    if trigger == CallbackTriggerType.OUT_OF_HOURS:
        # 非业务时段来电：仅在存在业务时段定义、且当前不在其中时命中
        if all_day or context.current_time is None:
            return None
        return f"非业务时段来电（{context.current_time}）"

    return None


def match_condition(
    condition: dict[str, Any] | None, context: CallbackTriggerContext
) -> CallbackTriggerDecision:
    """判定「这份回呼流程配置」在给定上下文下是否应生成回呼任务（§45）。

    判定顺序：
    1. 尝试次数已达上限 → 不触发；
    2. 未配置 triggers → 不自动触发（人工回呼走显式创建接口）；
    3. 配置了业务时段但当前不在其中，且触发条件里没有 OUT_OF_HOURS → 不触发（时段门禁）；
    4. 按 TRIGGER_ORDER 取第一个命中的触发条件。
    """
    data: dict[str, Any] = dict(condition or {})
    delay = max(0, _as_int(data.get("delay_seconds"), 0))
    priority = _as_int(data.get("priority"), 0)

    max_attempts = max(1, _as_int(data.get("max_attempts"), DEFAULT_MAX_ATTEMPTS))
    if context.attempt_count >= max_attempts:
        return CallbackTriggerDecision(
            matched=False,
            reason=f"尝试次数已达上限（{context.attempt_count}/{max_attempts}）",
            delay_seconds=delay,
            priority=priority,
        )

    triggers = normalize_triggers(data.get("triggers"))
    if not triggers:
        return CallbackTriggerDecision(
            matched=False,
            reason="流程未配置自动触发条件",
            delay_seconds=delay,
            priority=priority,
        )

    all_day = in_business_hours(data.get("business_hours"), context.current_time)
    if (
        not all_day
        and context.current_time is not None
        and CallbackTriggerType.OUT_OF_HOURS not in triggers
    ):
        return CallbackTriggerDecision(
            matched=False,
            reason=f"当前不在业务时段内（{context.current_time}）",
            delay_seconds=delay,
            priority=priority,
            business_hours_blocked=True,
        )

    details: list[str] = []
    for trigger in TRIGGER_ORDER:
        if trigger not in triggers:
            continue
        detail = _trigger_hit(
            trigger, condition=data, context=context, all_day=all_day
        )
        if detail is not None:
            details.append(detail)
            return CallbackTriggerDecision(
                matched=True,
                reason=detail,
                trigger_type=trigger,
                delay_seconds=delay,
                priority=priority,
                details=tuple(details),
            )

    return CallbackTriggerDecision(
        matched=False,
        reason="触发条件均未命中",
        delay_seconds=delay,
        priority=priority,
        details=tuple(details),
    )


def condition_priority(condition: dict[str, Any] | None) -> int:
    """流程优先级（数值小者优先），供多流程命中时排序使用。"""
    return _as_int((condition or {}).get("priority"), 0)


__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "TRIGGER_ORDER",
    "CallbackTriggerContext",
    "CallbackTriggerDecision",
    "condition_priority",
    "in_business_hours",
    "match_condition",
    "normalize_triggers",
]
