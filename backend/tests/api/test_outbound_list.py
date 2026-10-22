"""名单导入接口测试（OB-011 / OB-012）。"""

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core.config import settings
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/outbound"

ALL_LIST_PERMS = (
    "outbound:list:list",
    "outbound:list:import",
    "outbound:list:variable",
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


def make_csv(headers: list[str], rows: list[list[str]]) -> bytes:
    lines = [",".join(headers), *[",".join(row) for row in rows]]
    return ("\ufeff" + "\n".join(lines)).encode("utf-8")


def _upload(client: TestClient, token: str, task_id: int, filename: str, content: bytes):
    return client.post(
        f"{PREFIX}/lists/import",
        headers=auth_headers(token),
        data={"task_id": str(task_id)},
        files={"file": (filename, content, "application/octet-stream")},
    )


class TestListPermissions:
    def test_import_requires_permission(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        token = user_token("list_only_view", "outbound:list:list")
        response = _upload(
            client, token, outbound_task.id, "a.csv", make_csv(["UserID"], [["U1"]])
        )
        assert response.status_code == 403
        assert response.json()["code"] == 40301

    def test_list_requires_permission(self, client: TestClient, user_token) -> None:
        token = user_token("list_no_perm", "outbound:task:list")
        assert client.get(f"{PREFIX}/lists", headers=auth_headers(token)).status_code == 403

    def test_variables_requires_permission(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        token = user_token("list_importer", "outbound:list:import", "outbound:list:list")
        _upload(
            client,
            token,
            outbound_task.id,
            "perm.csv",
            make_csv(["UserID", "电话号"], [["U-P1", "13800001111"]]),
        )
        listing = client.get(
            f"{PREFIX}/lists", headers=auth_headers(token), params={"task_id": outbound_task.id}
        ).json()["data"]
        list_id = listing["items"][0]["id"]

        # 该用户没有 outbound:list:variable 权限
        response = client.get(f"{PREFIX}/lists/{list_id}/variables", headers=auth_headers(token))
        assert response.status_code == 403
        assert response.json()["code"] == 40301


class TestImportXlsx:
    def test_import_success(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("xlsx_user", *ALL_LIST_PERMS)
        content = make_xlsx(
            ["UserID", "OrderID", "收件人姓名", "电话号"],
            [["U1001", "O2001", "张三", "13800001111"], ["U1002", "O2002", "李四", "13800002222"]],
        )
        response = _upload(client, token, outbound_task.id, "名单.xlsx", content)

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["total_rows"] == 2
        assert data["success_rows"] == 2
        assert data["failed_rows"] == 0
        assert data["failures"] == []

        listing = client.get(
            f"{PREFIX}/lists",
            headers=auth_headers(token),
            params={"task_id": outbound_task.id},
        ).json()["data"]
        assert listing["total"] == 2
        first = listing["items"][0]
        assert first["user_id"] in {"U1001", "U1002"}
        assert first["status"] == "PENDING"

    def test_batch_recorded_as_success(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("xlsx_batch", *ALL_LIST_PERMS)
        content = make_xlsx(["UserID", "电话号"], [["U1", "13800001111"]])
        batch_id = _upload(client, token, outbound_task.id, "b.xlsx", content).json()["data"][
            "batch_id"
        ]

        response = client.get(f"{PREFIX}/import-batches/{batch_id}", headers=auth_headers(token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "SUCCESS"
        assert data["file_name"] == "b.xlsx"
        assert data["file_size"] > 0
        assert data["started_at"] is not None
        assert data["finished_at"] is not None


class TestImportCsvDynamicHeaders:
    def test_dynamic_fields_and_multi_phone(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        token = user_token("csv_dynamic", *ALL_LIST_PERMS)
        content = make_csv(
            ["UserID", "OrderID", "收件人姓名", "电话号", "备用号码", "订单金额", "VIP等级"],
            [["U2001", "O3001", "王五", "13800001111", "13800002222", "199.00", "铂金"]],
        )
        response = _upload(client, token, outbound_task.id, "动态表头.csv", content)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["success_rows"] == 1

        listing = client.get(
            f"{PREFIX}/lists",
            headers=auth_headers(token),
            params={"task_id": outbound_task.id},
        ).json()["data"]
        item = listing["items"][0]
        assert item["phone_numbers"] == ["13800001111", "13800002222"]
        assert item["dynamic_fields"] == {"订单金额": "199.00", "VIP等级": "铂金"}


class TestImportFailures:
    def test_partial_failure_details(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("partial_user", *ALL_LIST_PERMS)
        content = make_xlsx(
            ["UserID", "电话号"],
            [
                ["U1", "13800001111"],
                ["U2", "bad-phone"],
                ["", ""],
            ],
        )
        response = _upload(client, token, outbound_task.id, "部分失败.xlsx", content)
        data = response.json()["data"]

        assert data["total_rows"] == 2
        assert data["success_rows"] == 1
        assert data["failed_rows"] == 1
        assert data["failures"] == [
            {"row": 3, "field": "电话号", "reason": "号码格式不正确", "raw": "bad-phone"}
        ]

    def test_all_rows_failed_marks_batch_failed(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        token = user_token("all_failed", *ALL_LIST_PERMS)
        content = make_xlsx(["UserID", "电话号"], [["U1", "bad"], ["U2", "also-bad"]])
        response = _upload(client, token, outbound_task.id, "全失败.xlsx", content)
        batch_id = response.json()["data"]["batch_id"]
        assert response.json()["data"]["success_rows"] == 0

        detail = client.get(
            f"{PREFIX}/import-batches/{batch_id}", headers=auth_headers(token)
        ).json()["data"]
        assert detail["status"] == "FAILED"
        assert len(detail["failures"]) == 2

    def test_batch_failures_download_csv(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        token = user_token("download_user", *ALL_LIST_PERMS)
        content = make_xlsx(["UserID", "电话号"], [["U1", "bad-phone"]])
        batch_id = _upload(client, token, outbound_task.id, "下载.xlsx", content).json()["data"][
            "batch_id"
        ]

        response = client.get(
            f"{PREFIX}/import-batches/{batch_id}/failures/download", headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        text = response.content.decode("utf-8-sig")
        lines = text.strip().splitlines()
        assert lines[0] == "行号,字段,失败原因,原始值"
        assert "bad-phone" in lines[1]


class TestImportDuplicates:
    def test_reimport_is_idempotent(self, client: TestClient, user_token, outbound_task) -> None:
        """§78：重复导入同一份名单不产生重复数据。"""
        token = user_token("dup_import", *ALL_LIST_PERMS)
        content = make_xlsx(
            ["UserID", "OrderID", "电话号"],
            [["U-D1", "O-D1", "13800001111"], ["U-D2", "O-D2", "13800002222"]],
        )

        first = _upload(client, token, outbound_task.id, "dup.xlsx", content).json()["data"]
        assert first["success_rows"] == 2

        second = _upload(client, token, outbound_task.id, "dup.xlsx", content).json()["data"]
        assert second["success_rows"] == 0
        assert second["failed_rows"] == 2
        assert all("重复导入" in item["reason"] for item in second["failures"])

        listing = client.get(
            f"{PREFIX}/lists",
            headers=auth_headers(token),
            params={"task_id": outbound_task.id},
        ).json()["data"]
        assert listing["total"] == 2

    def test_duplicate_inside_same_file(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        token = user_token("dup_in_file", *ALL_LIST_PERMS)
        content = make_xlsx(
            ["UserID", "OrderID", "电话号"],
            [["U-S1", "O-S1", "13800001111"], ["U-S1", "O-S1", "13800001111"]],
        )
        data = _upload(client, token, outbound_task.id, "内部重复.xlsx", content).json()["data"]
        assert data["success_rows"] == 1
        assert data["failed_rows"] == 1


class TestImportValidation:
    def test_unsupported_extension(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("bad_ext", *ALL_LIST_PERMS)
        response = _upload(client, token, outbound_task.id, "名单.xls", b"anything")
        assert response.status_code == 400
        assert ".xlsx" in response.json()["message"]

    def test_empty_file(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("empty_file", *ALL_LIST_PERMS)
        response = _upload(client, token, outbound_task.id, "空.csv", b"")
        assert response.status_code == 400

    def test_unknown_task(self, client: TestClient, user_token) -> None:
        token = user_token("bad_task", *ALL_LIST_PERMS)
        response = _upload(client, token, 999999, "a.csv", make_csv(["UserID"], [["U1"]]))
        assert response.status_code == 404

    def test_header_only_file(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("header_only", *ALL_LIST_PERMS)
        response = _upload(
            client, token, outbound_task.id, "只有表头.csv", make_csv(["UserID"], [])
        )
        assert response.status_code == 400

    def test_broken_xlsx(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("broken_xlsx", *ALL_LIST_PERMS)
        response = _upload(client, token, outbound_task.id, "坏文件.xlsx", b"not-excel")
        assert response.status_code == 400


class TestListQuery:
    def test_filters(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("list_filter", *ALL_LIST_PERMS)
        content = make_xlsx(
            ["UserID", "OrderID", "电话号"],
            [["U-F1", "O-F1", "13800001111"], ["U-F2", "O-F2", "13800002222"]],
        )
        _upload(client, token, outbound_task.id, "f.xlsx", content)

        by_user = client.get(
            f"{PREFIX}/lists", headers=auth_headers(token), params={"user_id": "U-F1"}
        ).json()["data"]
        assert by_user["total"] == 1
        assert by_user["items"][0]["order_id"] == "O-F1"

        by_order = client.get(
            f"{PREFIX}/lists", headers=auth_headers(token), params={"order_id": "O-F2"}
        ).json()["data"]
        assert by_order["total"] == 1

        by_task = client.get(
            f"{PREFIX}/lists", headers=auth_headers(token), params={"task_id": outbound_task.id}
        ).json()["data"]
        assert by_task["total"] == 2

        by_none = client.get(
            f"{PREFIX}/lists", headers=auth_headers(token), params={"user_id": "NOT-EXIST"}
        ).json()["data"]
        assert by_none["total"] == 0

    def test_detail_not_found(self, client: TestClient, user_token) -> None:
        token = user_token("list_detail_404", "outbound:list:list")
        assert client.get(f"{PREFIX}/lists/999999", headers=auth_headers(token)).status_code == 404

    def test_batch_list_and_not_found(self, client: TestClient, user_token, outbound_task) -> None:
        token = user_token("batch_list", *ALL_LIST_PERMS)
        _upload(
            client,
            token,
            outbound_task.id,
            "batches.xlsx",
            make_xlsx(["UserID"], [["U-B1"]]),
        )

        listing = client.get(
            f"{PREFIX}/import-batches",
            headers=auth_headers(token),
            params={"task_id": outbound_task.id},
        ).json()["data"]
        assert listing["total"] == 1
        assert listing["items"][0]["status"] == "SUCCESS"

        response = client.get(f"{PREFIX}/import-batches/999999", headers=auth_headers(token))
        assert response.status_code == 404


class TestVariables:
    """OB-012 全场景变量获取。"""

    def test_variables_merge_task_and_dynamic_fields(
        self, client: TestClient, user_token, outbound_task, outbound_scene
    ) -> None:
        token = user_token("variable_user", *ALL_LIST_PERMS)
        content = make_xlsx(
            ["UserID", "OrderID", "收件人姓名", "电话号", "订单金额"],
            [["U-V1", "O-V1", "赵六", "13800001111", "288.00"]],
        )
        _upload(client, token, outbound_task.id, "vars.xlsx", content)

        list_item = client.get(
            f"{PREFIX}/lists",
            headers=auth_headers(token),
            params={"task_id": outbound_task.id},
        ).json()["data"]["items"][0]

        response = client.get(
            f"{PREFIX}/lists/{list_item['id']}/variables", headers=auth_headers(token)
        )
        assert response.status_code == 200
        variables = response.json()["data"]["variables"]

        # 名单维度
        assert variables["user_id"] == "U-V1"
        assert variables["order_id"] == "O-V1"
        assert variables["recipient_name"] == "赵六"
        assert variables["customer_name"] == "赵六"
        assert variables["phone"] == "13800001111"
        assert variables["phone_numbers"] == ["13800001111"]
        # 任务与场景维度
        assert variables["task_id"] == outbound_task.id
        assert variables["task_name"] == outbound_task.task_name
        assert variables["scene_id"] == outbound_scene.id
        assert variables["scene_name"] == outbound_scene.name
        # 动态字段平铺
        assert variables["订单金额"] == "288.00"

    def test_dynamic_field_does_not_override_reserved_key(
        self, client: TestClient, user_token, outbound_task
    ) -> None:
        """名单里同名列不得覆盖系统保留键（ASSUMPTION-026）。"""
        token = user_token("variable_reserved", *ALL_LIST_PERMS)
        content = make_xlsx(
            ["UserID", "电话号", "task_name"],
            [["U-R1", "13800001111", "恶意覆盖"]],
        )
        _upload(client, token, outbound_task.id, "reserved.xlsx", content)

        list_item = client.get(
            f"{PREFIX}/lists",
            headers=auth_headers(token),
            params={"task_id": outbound_task.id},
        ).json()["data"]["items"][0]

        variables = client.get(
            f"{PREFIX}/lists/{list_item['id']}/variables", headers=auth_headers(token)
        ).json()["data"]["variables"]
        assert variables["task_name"] == outbound_task.task_name

    def test_variables_unknown_list(self, client: TestClient, user_token) -> None:
        token = user_token("variable_404", *ALL_LIST_PERMS)
        assert (
            client.get(f"{PREFIX}/lists/999999/variables", headers=auth_headers(token)).status_code
            == 404
        )
