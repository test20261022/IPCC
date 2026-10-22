"""§58：OpenAPI 必须包含 summary / description / response_model / examples / security。

示例由 app/core/openapi_examples.py 在生成文档时统一注入，这里做覆盖率与内容校验，
避免后续新增接口时漏补 examples。
"""

import json
import re
from typing import Any

import pytest

from app.core.config import settings
from app.main import app

OUTBOUND_PREFIX = f"{settings.API_V1_PREFIX}/outbound/"
_METHODS = {"get", "post", "put", "delete", "patch"}
_REF_PATTERN = re.compile(r"#/components/schemas/([A-Za-z0-9_]+)")


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return app.openapi()


@pytest.fixture(scope="module")
def schemas(spec: dict[str, Any]) -> dict[str, Any]:
    return spec["components"]["schemas"]


@pytest.fixture(scope="module")
def operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method.upper(), path, operation)
        for path, item in spec["paths"].items()
        if path.startswith(OUTBOUND_PREFIX)
        for method, operation in item.items()
        if method in _METHODS
    ]


def _has_examples(schema: dict[str, Any], schemas: dict[str, Any]) -> bool:
    """自身上下文或 $ref 指向的组件上存在示例。"""
    ref = schema.get("$ref")
    if ref:
        schema = schemas.get(ref.rsplit("/", 1)[-1], {})
    return bool(schema.get("examples") or schema.get("example"))


class TestOperationDocs:
    def test_operations_exist(self, operations) -> None:
        assert len(operations) > 100

    def test_every_operation_has_summary_and_description(self, operations) -> None:
        missing = [
            f"{method} {path}"
            for method, path, operation in operations
            if not operation.get("summary") or not operation.get("description")
        ]
        assert missing == []

    def test_every_operation_declares_security(self, operations) -> None:
        """只有网关回调按签名鉴权、不需要 security。"""
        missing = [
            f"{method} {path}"
            for method, path, operation in operations
            if not operation.get("security") and not path.endswith("/call-result/callback")
        ]
        assert missing == []

    def test_health_has_description(self, spec) -> None:
        assert spec["paths"]["/health"]["get"]["description"]

    def test_every_response_has_examples(self, operations, schemas) -> None:
        missing = []
        for method, path, operation in operations:
            for status, response in operation.get("responses", {}).items():
                if status != "200":
                    continue
                # 文件下载等无 JSON schema 的响应不在示例范围内
                schema = response.get("content", {}).get("application/json", {}).get("schema")
                if not schema:
                    continue
                if not _has_examples(schema, schemas):
                    missing.append(f"{method} {path}")
        assert missing == []

    def test_every_request_body_has_examples(self, operations, schemas) -> None:
        checked = 0
        missing = []
        for method, path, operation in operations:
            body = operation.get("requestBody")
            if not body:
                continue
            schema = body.get("content", {}).get("application/json", {}).get("schema")
            if not schema:
                continue  # 文件上传（multipart）不在 JSON 示例范围内
            checked += 1
            if not _has_examples(schema, schemas):
                missing.append(f"{method} {path}")
        assert checked >= 30
        assert missing == []

    def test_all_referenced_components_have_examples(self, operations, schemas) -> None:
        referenced: set[str] = set()
        for _, _, operation in operations:
            referenced.update(_REF_PATTERN.findall(json.dumps(operation)))
        missing = sorted(name for name in referenced if not schemas.get(name, {}).get("examples"))
        assert missing == []


class TestExampleContent:
    def test_examples_are_json_serializable(self, schemas) -> None:
        for name, schema in schemas.items():
            for example in schema.get("examples", []):
                json.dumps(example, ensure_ascii=False)
            assert "ellipsis" not in json.dumps(schema.get("examples")), name

    def test_handwritten_request_examples(self, spec, schemas) -> None:
        create_task = schemas["OutboundTaskCreate"]["examples"][0]
        assert create_task["task_name"] == "9 月新客回访"
        assert create_task["retry_interval"] == 60
        assert create_task["numbers"][0]["number_id"] == 1

        callback = schemas["CallResultCallbackIn"]["examples"][0]
        assert callback["call_status"] == "CONNECTED"
        assert callback["provider_call_id"]

        flow = schemas["CallbackFlowCreate"]["examples"][0]
        assert flow["trigger_condition"]["triggers"] == ["NO_AGENT"]

    def test_generated_examples_follow_types_and_enums(self, schemas) -> None:
        # 枚举组件取首个取值
        assert schemas["TaskStatus"]["examples"][0] == "DRAFT"
        assert schemas["CallStatus"]["examples"][0] == "INITIATED"
        # 分页响应组件给出 items / total / page / page_size 结构
        page = schemas["PageData_OutboundTaskOut_"]["examples"][0]
        assert set(page) == {"items", "total", "page", "page_size"}
        assert isinstance(page["items"], list) and page["items"]
        # 统一响应体取模型默认值
        envelope = schemas["ApiResponse_OutboundTaskOut_"]["examples"][0]
        assert envelope["code"] == 0
        assert envelope["message"] == "success"
        assert envelope["data"]["task_name"]
