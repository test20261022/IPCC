"""Provider 单元测试（§29 / §30）。

重点验证 Mock 的**确定性规则**：号码派生与呼叫结果都由号码本身决定，
因此执行引擎的「多号码顺序」「重试阶梯」等行为可以在用例里被精确构造。
"""

import pytest

from app.models.outbound.enums import CallStatus
from app.providers import (
    get_asr_provider,
    get_call_provider,
    get_ivr_provider,
    get_phone_provider,
    get_tts_provider,
)
from app.providers.call.mock import MockCallProvider
from app.providers.phone.mock import MockPhoneProvider, digits_of
from app.utils.async_bridge import run_sync
from app.utils.validators import is_valid_phone


class TestPhoneProviderMock:
    def test_derives_phones_from_order_and_user(self) -> None:
        provider = MockPhoneProvider()
        phones = run_sync(provider.get_user_phones(user_id="U1234", order_id="O5678"))

        assert phones == ["13700005678", "13800001234"]
        assert all(is_valid_phone(phone) for phone in phones)

    def test_order_first_then_user(self) -> None:
        provider = MockPhoneProvider()
        phones = run_sync(provider.get_user_phones(user_id="U2", order_id="O1"))
        assert phones[0].startswith("137")
        assert phones[1].startswith("138")

    def test_only_user_id(self) -> None:
        provider = MockPhoneProvider()
        assert run_sync(provider.get_user_phones(user_id="U9")) == ["13800000009"]

    def test_no_identifier_returns_empty(self) -> None:
        provider = MockPhoneProvider()
        assert run_sync(provider.get_user_phones()) == []
        assert run_sync(provider.get_user_phones(user_id="", order_id="")) == []

    def test_pads_short_digits(self) -> None:
        provider = MockPhoneProvider()
        assert run_sync(provider.get_user_phones(order_id="O7")) == ["13700000007"]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("O-1234", "1234"), ("abc", ""), (None, ""), ("U99x88", "9988")],
    )
    def test_digits_of(self, raw: str | None, expected: str) -> None:
        assert digits_of(raw) == expected


class TestCallProviderMock:
    @pytest.mark.parametrize(
        ("phone", "expected_status", "expected_success"),
        [
            ("00001234567", CallStatus.FAILED, False),
            ("13800001111", CallStatus.NO_ANSWER, False),
            ("13800002222", CallStatus.BUSY, False),
            ("13800003333", CallStatus.REJECTED, False),
            ("13800001112", CallStatus.CONNECTED, True),
        ],
    )
    def test_status_rules(
        self, phone: str, expected_status: CallStatus, expected_success: bool
    ) -> None:
        provider = MockCallProvider()
        result = run_sync(provider.make_call(phone=phone))

        assert result.call_status == expected_status
        assert result.success is expected_success
        assert result.provider_call_id
        if expected_success:
            assert result.duration > 0
            assert result.recording_path
        else:
            assert result.failure_reason

    def test_provider_call_ids_are_unique(self) -> None:
        provider = MockCallProvider()
        first = run_sync(provider.make_call(phone="13800001112"))
        second = run_sync(provider.make_call(phone="13800001112"))
        assert first.provider_call_id != second.provider_call_id


class TestProviderFactory:
    def test_default_implementations_are_mock(self) -> None:
        assert get_phone_provider().name == "mock"
        assert get_call_provider().name == "mock"
        assert get_ivr_provider().name == "mock"
        assert get_asr_provider().name == "mock"
        assert get_tts_provider().name == "mock"

    def test_ivr_and_tts_are_callable(self) -> None:
        ivr_result = run_sync(get_ivr_provider().execute(flow_id=7))
        assert ivr_result.success is True
        assert ivr_result.final_node_key == "flow-7-end"

        asr = get_asr_provider()
        segments = run_sync(asr.transcribe_segments(audio_path="a.wav"))
        assert segments
        # transcribe 默认由分段结果拼接，两者必须一致
        assert run_sync(asr.transcribe(audio_path="a.wav")) == "\n".join(
            segment.text for segment in segments
        )
        assert run_sync(get_tts_provider().synthesize(text="你好")).endswith(".wav")
