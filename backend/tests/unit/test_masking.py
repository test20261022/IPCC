"""脱敏工具单元测试（§67）。"""

from app.utils.masking import mask_id_card, mask_phone


class TestMaskPhone:
    def test_normal_mobile(self) -> None:
        assert mask_phone("13812341234") == "138****1234"

    def test_short_number(self) -> None:
        assert mask_phone("12345") == "*****"

    def test_empty_input(self) -> None:
        assert mask_phone("") == ""
        assert mask_phone(None) == ""


class TestMaskIdCard:
    def test_normal_id_card(self) -> None:
        masked = mask_id_card("110101199001011234")
        assert masked.startswith("110101")
        assert masked.endswith("1234")
        assert "1990" not in masked

    def test_short_input(self) -> None:
        assert mask_id_card("123") == "***"

    def test_empty_input(self) -> None:
        assert mask_id_card("") == ""
