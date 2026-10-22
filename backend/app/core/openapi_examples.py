"""OpenAPI 示例（§58：必须包含 summary / description / response_model / examples / security）。

示例集中在这里维护，避免 40+ 份请求体示例散落到各个接口装饰器上：

- `REQUEST_EXAMPLES`：按组件名登记的请求体示例，贴近真实业务、可直接在 Swagger UI 试调用；
- 未登记的组件（含响应组件与自动生成的 Body_* 内联组件）由 `build_example()` 按
  示例 / 默认值 / 类型 / 枚举 / 字段名生成占位示例，保证「每个接口都有 examples」；
- `apply_examples()` 在生成 OpenAPI 文档时统一注入。
"""

from typing import Any

_DATETIME = "2026-09-21T10:00:00+08:00"
_DATE = "2026-09-21"

#: 按字段名给自动生成的占位示例挑一个可读取值
_STRING_HINTS: dict[str, str] = {
    "phone": "13800000001",
    "caller_number": "13800000001",
    "recipient_phone": "13800000001",
    "code": "CODE-001",
    "name": "示例名称",
    "nickname": "示例名称",
    "display_name": "外显名称",
    "description": "示例说明",
    "remark": "示例说明",
    "reason": "示例说明",
    "summary": "示例说明",
    "content": "示例话术",
    "message": "示例提示",
    "path": "storage/example.wav",
    "url": "https://example.com/call-result/callback",
}

#: 请求体示例（按 OpenAPI 组件名登记）；响应组件走 build_example 自动生成
REQUEST_EXAMPLES: dict[str, Any] = {
    # ---- 认证 ----
    "LoginRequest": {"username": "admin", "password": "Admin@123456"},
    "RefreshRequest": {"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.refresh"},
    # ---- OB-001 主叫号码 ----
    "OutboundNumberCreate": {
        "tenant_id": 1,
        "display_name": "上海客服主叫",
        "caller_number": "02112345678",
        "number_type": "SIP",
        "usage_limit": 1000,
        "status": "ENABLED",
        "remark": "工作日 9:00-18:00 使用",
    },
    "OutboundNumberUpdate": {
        "display_name": "上海客服主叫（改）",
        "number_type": "SIP",
        "usage_limit": 2000,
        "status": "ENABLED",
        "remark": "使用次数上调",
    },
    # ---- OB-003 / OB-004 场景与类型 ----
    "OutboundSceneCreate": {
        "tenant_id": 1,
        "type_id": 1,
        "parent_id": None,
        "level": 1,
        "name": "新客回访",
        "sort_order": 1,
        "status": "ENABLED",
        "description": "新签约客户 3 日内回访",
    },
    "OutboundSceneUpdate": {
        "type_id": 1,
        "name": "新客回访（改）",
        "sort_order": 2,
        "status": "ENABLED",
        "description": "新签约客户 7 日内回访",
    },
    "OutboundTypeCreate": {
        "tenant_id": 1,
        "parent_id": None,
        "code": "TYPE-001",
        "name": "营销外呼",
        "level": 1,
        "sort_order": 1,
        "status": "ENABLED",
        "description": "营销类外呼任务",
    },
    "OutboundTypeUpdate": {
        "code": "TYPE-001",
        "parent_id": None,
        "name": "营销外呼（改）",
        "sort_order": 1,
        "status": "ENABLED",
        "description": "营销类外呼任务（含子类型）",
    },
    # ---- OB-006 / OB-020 外呼任务 ----
    "OutboundTaskCreate": {
        "tenant_id": 1,
        "task_name": "9 月新客回访",
        "site_id": 1,
        "skill_queue_id": 1,
        "type_id": 1,
        "scene_id": 1,
        "dispatch_mode": "AUTO",
        "number_select_strategy": "ORDER",
        "retry_interval": 60,
        "max_retry_count": 2,
        "call_timeout_seconds": 30,
        "max_concurrency": 5,
        "adjustment_factor": "1.00",
        "ivr_flow_id": None,
        "description": "9 月签约客户满意度回访",
        "priority": 1,
        "numbers": [
            {"number_id": 1, "order_id": 1, "user_id": 2, "recipient_number": 3}
        ],
    },
    "OutboundTaskUpdate": {
        "task_name": "9 月新客回访（改）",
        "site_id": 1,
        "skill_queue_id": 1,
        "type_id": 1,
        "scene_id": 1,
        "dispatch_mode": "AUTO",
        "number_select_strategy": "ROUND_ROBIN",
        "retry_interval": 120,
        "max_retry_count": 3,
        "call_timeout_seconds": 45,
        "max_concurrency": 10,
        "adjustment_factor": "1.20",
        "ivr_flow_id": None,
        "description": "并发与重试策略调整",
        "priority": 2,
    },
    "OutboundTaskStatusChange": {"status": "RUNNING"},
    "OutboundTaskCopyRequest": {"task_name": "9 月新客回访-副本", "copy_numbers": True},
    # ---- OB-018 坐席 ----
    "AgentCreate": {
        "user_id": 2,
        "tenant_id": 1,
        "site_id": 1,
        "skill_queue_id": 1,
        "extension": "8001",
    },
    "AgentUpdate": {"site_id": 1, "skill_queue_id": 2, "extension": "8002"},
    "AgentStatusChange": {"status": "IDLE", "reason": "坐席上班"},
    # ---- OB-017 IVR ----
    "IvrFlowCreate": {
        "tenant_id": 1,
        "code": "IVR-CALLBACK",
        "name": "回呼确认流程",
        "entry_node_key": "welcome",
        "status": "ENABLED",
        "description": "无坐席时引导客户按键回呼",
    },
    "IvrFlowUpdate": {
        "name": "回呼确认流程（改）",
        "entry_node_key": "welcome",
        "status": "ENABLED",
        "description": "入口节点调整为 welcome",
    },
    "IvrNodeCreate": {
        "tenant_id": 1,
        "node_key": "welcome",
        "name": "欢迎播报",
        "node_type": "PLAY",
        "content": "您好，欢迎致电某某公司，请按 1 转人工，按 9 申请回呼。",
        "config": {},
        "max_replay": 2,
        "no_agent_action": "CALLBACK",
        "sort_order": 1,
    },
    "IvrNodeUpdate": {
        "name": "欢迎播报（改）",
        "node_type": "PLAY",
        "content": "您好，我司客服忙，按 9 可申请回呼。",
        "config": {},
        "max_replay": 3,
        "no_agent_action": "CALLBACK",
        "sort_order": 1,
    },
    "IvrTransitionCreate": {
        "tenant_id": 1,
        "from_node_id": 1,
        "to_node_id": 2,
        "condition_type": "KEY",
        "condition_value": "9",
        "priority": 1,
    },
    "IvrTransitionUpdate": {
        "to_node_id": 3,
        "condition_type": "KEY",
        "condition_value": "1",
        "priority": 2,
    },
    "IvrSimulationRequest": {
        "inputs": [{"input_type": "KEY", "value": "9"}],
        "current_time": "10:30",
        "queue_available": False,
        "skill_queue_id": 1,
        "max_steps": 10,
    },
    # ---- OB-021 会话小结 ----
    "ServiceSummaryCreate": {
        "session_id": 10,
        "summary": "客户确认下周上门安装",
        "result": "有意向",
        "tags": ["意向客户"],
    },
    "ServiceSummaryUpdate": {
        "summary": "客户改约到下周三上午",
        "result": "已约时间",
        "tags": ["意向客户", "待回访"],
    },
    # ---- OB-029 / OB-030 回呼 ----
    "CallbackFlowCreate": {
        "tenant_id": 1,
        "code": "CB-NOAGENT",
        "name": "无坐席回呼",
        "trigger_condition": {
            "triggers": ["NO_AGENT"],
            "business_hours": ["09:00-18:00"],
            "delay_seconds": 300,
            "max_attempts": 3,
            "priority": 0,
        },
        "ivr_flow_id": 1,
        "status": "ENABLED",
        "description": "转人工无可用坐席时自动生成回呼任务",
    },
    "CallbackFlowUpdate": {
        "name": "无坐席回呼（改）",
        "trigger_condition": {
            "triggers": ["NO_AGENT", "KEY"],
            "keys": ["9"],
            "business_hours": ["09:00-18:00"],
            "delay_seconds": 600,
            "max_attempts": 2,
            "priority": 1,
        },
        "ivr_flow_id": 1,
        "status": "ENABLED",
        "description": "补充按键回呼条件",
    },
    "CommonStatusChange": {"status": "ENABLED"},
    "CallbackTaskCreate": {
        "tenant_id": 1,
        "source": "MANUAL",
        "phone": "13800000001",
        "flow_id": 1,
        "task_id": 1,
        "list_id": 1,
        "origin_session_id": None,
        "trigger_type": None,
        "scheduled_at": _DATETIME,
        "agent_id": 2,
        "remark": "客户要求下午回电",
    },
    "CallbackTriggerContextIn": {
        "tenant_id": 1,
        "phone": "13800000001",
        "origin_session_id": 10,
        "flow_id": 1,
        "task_id": 1,
        "list_id": 1,
        "keys": ["9"],
        "no_agent": True,
        "no_answer": False,
        "current_time": "19:30",
        "attempt_count": 0,
        "remark": "IVR 按键申请回呼",
    },
    # ---- OB-008 执行与网关回调 ----
    "CallResultCallbackIn": {
        "provider_call_id": "gw-20260921-0001",
        "call_status": "CONNECTED",
        "duration": 42,
        "failure_reason": None,
        "recording_path": "gw/recordings/gw-20260921-0001.wav",
    },
}


def build_example(
    schema: dict[str, Any],
    schemas: dict[str, Any],
    *,
    depth: int = 0,
    key: str = "",
) -> Any:
    """按 JSON Schema 生成占位示例；`$ref` 递归解析，最深 3 层避免自引用死循环。"""
    if depth > 3:
        return None

    ref = schema.get("$ref")
    if ref:
        target = schemas.get(ref.rsplit("/", 1)[-1])
        return build_example(target, schemas, depth=depth + 1, key=key) if target else None

    for branch_key in ("anyOf", "oneOf"):
        branches = [item for item in schema.get(branch_key, []) if item.get("type") != "null"]
        if branches:
            return build_example(branches[0], schemas, depth=depth, key=key)

    # 模型自带的示例 / 默认值优先，让占位示例贴近真实取值（如 code=0、message=success）
    if "example" in schema:
        return schema["example"]
    if schema.get("examples"):
        return schema["examples"][0]
    if schema.get("default") is not None:
        return schema["default"]

    if schema.get("enum"):
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]

    fmt = schema.get("format")
    if fmt == "date-time":
        return _DATETIME
    if fmt == "date":
        return _DATE
    if fmt == "email":
        return "user@example.com"

    schema_type = schema.get("type")
    if schema_type == "array":
        return [build_example(schema.get("items", {}), schemas, depth=depth + 1, key=key)]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema_type == "string":
        if key in _STRING_HINTS:
            return _STRING_HINTS[key]
        if key.endswith(("_at", "_time")):
            return _DATETIME
        return "string"
    if "properties" in schema or schema_type == "object":
        return {
            name: build_example(node, schemas, depth=depth + 1, key=name)
            for name, node in (schema.get("properties") or {}).items()
        }
    return None


def apply_examples(spec: dict[str, Any]) -> None:
    """把示例注入 OpenAPI 文档（§58：examples 必须存在）。"""
    schemas: dict[str, Any] = spec.get("components", {}).get("schemas", {})
    for name, schema in schemas.items():
        example = REQUEST_EXAMPLES.get(name)
        if example is None:
            example = build_example(schema, schemas)
        if example is None:
            continue
        # 同时给出 examples（§58 要求）与 example（Swagger UI 优先读取）
        schema["examples"] = [example]
        schema["example"] = example

    for path_item in spec.get("paths", {}).values():
        for operation in path_item.values():
            _apply_inline_body_example(operation, schemas)


def _apply_inline_body_example(operation: dict[str, Any], schemas: dict[str, Any]) -> None:
    """内联请求体（未抽成组件的，如 Body(embed=True) 生成的）也要有示例。"""
    schema = (
        (operation.get("requestBody") or {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    if not schema or "$ref" in schema:
        return
    example = build_example(schema, schemas)
    if example is None:
        return
    schema["examples"] = [example]
    schema["example"] = example
