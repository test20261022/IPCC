"""名单域 Schema（OB-011 / OB-012 / OB-021 / OB-023）。"""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.outbound.enums import ImportBatchStatus, ListStatus
from app.schemas.outbound.base import OutboundOutBase, OutboundSchemaBase, OutboundUpdateBase


class OutboundImportFailure(OutboundSchemaBase):
    """失败明细单行（§25：行号 / 字段 / 原因 / 原始值）。"""

    row: int = Field(ge=1, description="Excel 行号")
    field: str = Field(default="", description="出错字段")
    reason: str = Field(description="失败原因")
    raw: str | None = Field(default=None, description="原始值")


class OutboundImportBatchOut(OutboundOutBase):
    tenant_id: int
    task_id: int
    file_name: str
    file_size: int
    total_rows: int
    success_rows: int
    failed_rows: int
    status: ImportBatchStatus
    error_message: str | None
    imported_by: int | None
    started_at: datetime | None
    finished_at: datetime | None


class OutboundImportResultOut(OutboundSchemaBase):
    """导入结果（§25）：总行数 / 成功数 / 失败数 + 失败明细。"""

    batch_id: int = Field(description="导入批次 ID")
    total_rows: int = 0
    success_rows: int = 0
    failed_rows: int = 0
    failures: list[OutboundImportFailure] = Field(default_factory=list)


class OutboundImportBatchDetailOut(OutboundImportBatchOut):
    """批次详情：附带失败明细（超上限时截断，计数以 failed_rows 为准）。"""

    failures: list[OutboundImportFailure] = Field(default_factory=list)


class OutboundListCreate(OutboundSchemaBase):
    """手工新增名单行（导入之外的补充入口）。"""

    task_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    user_id: str | None = Field(default=None, max_length=64, description="业务 UserID")
    order_id: str | None = Field(default=None, max_length=64, description="业务 OrderID")
    recipient_name: str | None = Field(default=None, max_length=128)
    recipient_phone: str | None = Field(default=None, max_length=32)
    phone_numbers: list[str] = Field(default_factory=list, description="多号码清单")
    dynamic_fields: dict[str, Any] = Field(default_factory=dict, description="动态字段")
    priority: int = 0
    remark: str = Field(default="", max_length=255)


class OutboundListUpdate(OutboundUpdateBase):
    recipient_name: str | None = Field(default=None, max_length=128)
    recipient_phone: str | None = Field(default=None, max_length=32)
    phone_numbers: list[str] | None = None
    dynamic_fields: dict[str, Any] | None = None
    priority: int | None = None
    status: ListStatus | None = None
    remark: str | None = Field(default=None, max_length=255)


class OutboundListOut(OutboundOutBase):
    tenant_id: int
    task_id: int
    import_batch_id: int | None
    user_id: str | None
    order_id: str | None
    recipient_name: str | None
    recipient_phone: str | None
    phone_numbers: list[str] | None
    dynamic_fields: dict[str, Any] | None
    status: ListStatus
    priority: int
    attempt_count: int
    last_call_at: datetime | None
    remark: str


class OutboundVariableOut(OutboundSchemaBase):
    """OB-012：名单 + 任务 + 场景合并后的全场景变量。"""

    variables: dict[str, Any] = Field(
        default_factory=dict, description="可直接用于话术 / IVR 的变量"
    )


__all__ = [
    "OutboundImportBatchDetailOut",
    "OutboundImportBatchOut",
    "OutboundImportFailure",
    "OutboundImportResultOut",
    "OutboundListCreate",
    "OutboundListOut",
    "OutboundListUpdate",
    "OutboundVariableOut",
]
