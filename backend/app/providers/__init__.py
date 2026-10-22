"""外部系统 Provider 层（§28 / §29 / §30）。

约定：
- 所有第三方交互必须经过 Provider，Service 层禁止直接发 HTTP；
- 实现由 .env 选择（§68），未配置真实地址时真实实现会直接报错，不会静默降级；
- Mock 只覆盖外部系统，业务状态（任务 / 名单 / 号码次数 / 重试 / 超时 / 会话 / 账本）始终真实流转。
"""

from app.providers.factory import (
    get_asr_provider,
    get_call_provider,
    get_ivr_provider,
    get_phone_provider,
    get_tts_provider,
)

__all__ = [
    "get_asr_provider",
    "get_call_provider",
    "get_ivr_provider",
    "get_phone_provider",
    "get_tts_provider",
]
