"""Provider 工厂：按 .env 配置选择实现（§68）。

Service 层只依赖抽象接口，绝不直接实例化具体 Provider，也不直接发 HTTP。
"""

from app.core.config import settings
from app.core.exceptions import AppException
from app.providers.asr.aliyun import AliyunAsrProvider
from app.providers.asr.base import AsrProvider
from app.providers.asr.mock import MockAsrProvider
from app.providers.call.base import CallGatewayProvider
from app.providers.call.gateway import GatewayCallProvider
from app.providers.call.mock import MockCallProvider
from app.providers.ivr.base import IvrProvider
from app.providers.ivr.mock import MockIvrProvider
from app.providers.phone.base import PhoneProvider
from app.providers.phone.mock import MockPhoneProvider
from app.providers.phone.third_party import ThirdPartyPhoneProvider
from app.providers.tts.base import TtsProvider
from app.providers.tts.mock import MockTtsProvider


def _resolve(name: str, mapping: dict[str, type], kind: str) -> type:
    provider_cls = mapping.get(name)
    if provider_cls is None:
        raise AppException(f"未知的 {kind} Provider：{name}，可选 {sorted(mapping)}")
    return provider_cls


def get_phone_provider() -> PhoneProvider:
    provider_cls = _resolve(
        settings.PHONE_PROVIDER,
        {"mock": MockPhoneProvider, "third_party": ThirdPartyPhoneProvider},
        "PHONE",
    )
    if provider_cls is MockPhoneProvider:
        return MockPhoneProvider()
    return ThirdPartyPhoneProvider(  # type: ignore[return-value]
        base_url=settings.PHONE_PROVIDER_URL,
        api_key=settings.PHONE_PROVIDER_API_KEY,
        timeout=settings.PROVIDER_TIMEOUT_SECONDS,
        max_retries=settings.PROVIDER_MAX_RETRIES,
    )


def get_call_provider() -> CallGatewayProvider:
    provider_cls = _resolve(
        settings.CALL_GATEWAY_PROVIDER,
        {"mock": MockCallProvider, "gateway": GatewayCallProvider},
        "CALL",
    )
    if provider_cls is MockCallProvider:
        return MockCallProvider()
    return GatewayCallProvider(  # type: ignore[return-value]
        base_url=settings.CALL_GATEWAY_URL,
        api_key=settings.CALL_GATEWAY_API_KEY,
        timeout=settings.PROVIDER_TIMEOUT_SECONDS,
        max_retries=settings.PROVIDER_MAX_RETRIES,
    )


def get_ivr_provider() -> IvrProvider:
    return _resolve(settings.IVR_PROVIDER, {"mock": MockIvrProvider}, "IVR")()


def get_asr_provider() -> AsrProvider:
    return _resolve(
        settings.ASR_PROVIDER,
        {"mock": MockAsrProvider, "aliyun": AliyunAsrProvider},
        "ASR",
    )()


def get_tts_provider() -> TtsProvider:
    return _resolve(settings.TTS_PROVIDER, {"mock": MockTtsProvider}, "TTS")()
