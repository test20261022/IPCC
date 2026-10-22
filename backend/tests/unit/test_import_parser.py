"""名单文件解析单元测试（OB-011 / §24）。纯内存，不依赖数据库。"""

import io

import pytest
from openpyxl import Workbook

from app.core.exceptions import ParamError
from app.services.outbound.import_parser import (
    detect_format,
    normalize_header,
    parse_header,
    parse_rows,
    read_rows,
)


def make_xlsx(headers: list[str], rows: list[list[str]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestDetectFormat:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [("a.xlsx", "xlsx"), ("A.XLSX", "xlsx"), ("b.csv", "csv"), ("c.CSV", "csv")],
    )
    def test_supported(self, filename: str, expected: str) -> None:
        assert detect_format(filename) == expected

    @pytest.mark.parametrize("filename", ["a.xls", "a.txt", "a", "a.pdf"])
    def test_unsupported(self, filename: str) -> None:
        with pytest.raises(ParamError):
            detect_format(filename)


class TestReadRows:
    def test_read_xlsx(self) -> None:
        content = make_xlsx(["UserID", "电话号"], [["U1", "13800001111"]])
        rows = read_rows(content, "xlsx")
        assert rows[0] == ["UserID", "电话号"]
        assert rows[1] == ["U1", "13800001111"]

    def test_read_csv_utf8_bom(self) -> None:
        content = "\ufeffUserID,电话号\nU1,13800001111\n".encode("utf-8")
        rows = read_rows(content, "csv")
        assert rows[0][0] == "UserID"
        assert rows[1] == ["U1", "13800001111"]

    def test_read_csv_gbk(self) -> None:
        content = "UserID,电话号\nU1,13800001111\n".encode("gbk")
        rows = read_rows(content, "csv")
        assert rows[0][1] == "电话号"

    def test_broken_xlsx_raises(self) -> None:
        with pytest.raises(ParamError):
            read_rows(b"not an excel file", "xlsx")


class TestNormalizeHeader:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("User ID", "userid"),
            ("user_id", "userid"),
            (" 电话号 ", "电话号"),
            ("订单-号", "订单号"),
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        assert normalize_header(raw) == expected


class TestParseHeader:
    def test_recognizes_core_columns_and_dynamic_fields(self) -> None:
        rows = [
            ["UserID", "OrderID", "收件人姓名", "电话号", "业务备注", "VIP等级"],
            ["U1", "O1", "张三", "13800001111", "备注", "金卡"],
        ]
        mapping = parse_header(rows)

        assert mapping.fields == {"user_id": 0, "order_id": 1, "recipient_name": 2}
        assert mapping.phone_indexes == [3]
        assert mapping.dynamic_indexes == {4: "业务备注", 5: "VIP等级"}

    def test_multiple_phone_columns(self) -> None:
        rows = [["UserID", "电话号", "备用手机号", "收件人号码"], []]
        mapping = parse_header(rows)

        assert mapping.phone_indexes == [1, 2, 3]
        assert mapping.recipient_phone_index == 3

    def test_header_only_rejected(self) -> None:
        with pytest.raises(ParamError) as exc_info:
            parse_header([["UserID", "电话号"]])
        assert "数据行" in str(exc_info.value)

    def test_empty_file_rejected(self) -> None:
        with pytest.raises(ParamError):
            parse_header([])

    def test_unrecognized_header_rejected(self) -> None:
        with pytest.raises(ParamError) as exc_info:
            parse_header([["列A", "列B"], ["1", "2"]])
        assert "未能识别" in str(exc_info.value)


class TestParseRows:
    def test_valid_rows_with_dynamic_fields(self) -> None:
        rows = [
            ["UserID", "OrderID", "收件人姓名", "电话号", "订单金额"],
            ["U1", "O1", "张三", "13800001111", "99.5"],
            ["U2", "O2", "李四", "13800002222", "10"],
        ]
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        assert failures == []
        assert len(parsed) == 2
        assert parsed[0].user_id == "U1"
        assert parsed[0].order_id == "O1"
        assert parsed[0].recipient_name == "张三"
        assert parsed[0].phone_numbers == ["13800001111"]
        assert parsed[0].recipient_phone == "13800001111"
        assert parsed[0].dynamic_fields == {"订单金额": "99.5"}
        assert parsed[0].row_no == 2

    def test_multiple_phone_columns_collected_in_order(self) -> None:
        rows = [
            ["UserID", "电话号", "备用号码", "收件人号码"],
            ["U1", "13800001111", "13800002222", "13800003333"],
        ]
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        assert failures == []
        assert parsed[0].phone_numbers == ["13800001111", "13800002222", "13800003333"]
        assert parsed[0].recipient_phone == "13800003333"

    def test_only_user_id_without_phone_is_allowed(self) -> None:
        """OB-023：号码可由第三方接口按 UserID 获取，因此不强制要求号码列有值。"""
        rows = [["UserID", "OrderID", "电话号"], ["U1", "O1", ""]]
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        assert failures == []
        assert parsed[0].phone_numbers == []
        assert parsed[0].recipient_phone is None

    def test_invalid_phone_reported_with_row_and_raw(self) -> None:
        rows = [["UserID", "电话号"], ["U1", "abc-123"]]
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        assert parsed == []
        assert len(failures) == 1
        assert failures[0].row == 2
        assert failures[0].field == "电话号"
        assert failures[0].reason == "号码格式不正确"
        assert failures[0].raw == "abc-123"

    def test_row_without_any_key_reported(self) -> None:
        rows = [["UserID", "OrderID", "电话号", "备注"], ["", "", "", "只有备注"]]
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        assert parsed == []
        assert len(failures) == 1
        assert "缺少 UserID" in failures[0].reason

    def test_blank_rows_skipped_silently(self) -> None:
        rows = [
            ["UserID", "电话号"],
            ["U1", "13800001111"],
            ["", ""],
            ["   ", "  "],
            ["U2", "13800002222"],
        ]
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        assert failures == []
        assert [row.user_id for row in parsed] == ["U1", "U2"]

    def test_partial_row_failure_does_not_block_others(self) -> None:
        rows = [
            ["UserID", "电话号"],
            ["U1", "13800001111"],
            ["U2", "bad-phone"],
            ["U3", "13800003333"],
        ]
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        assert [row.user_id for row in parsed] == ["U1", "U3"]
        assert [item.row for item in failures] == [3]

    def test_missing_optional_columns(self) -> None:
        rows = [["电话号"], ["13800001111"]]
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        assert failures == []
        assert parsed[0].user_id is None
        assert parsed[0].order_id is None
        assert parsed[0].recipient_name is None
