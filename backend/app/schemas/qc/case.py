"""优秀案例库 Schema：案例的出入参。"""

from datetime import datetime

from pydantic import Field

from app.schemas.qc.conversation import QcOutBase, QcSchemaBase, QcUpdateBase


class CaseCreateIn(QcSchemaBase):
    """把一条对话沉淀为优秀案例。"""

    tenant_id: int = Field(gt=0, description="租户")
    conversation_id: int = Field(gt=0, description="来源对话")
    item_id: int | None = Field(default=None, gt=0, description="来源质检明细（可选）")
    title: str = Field(min_length=1, max_length=128, description="案例标题")
    reason: str = Field(default="", description="入选理由 / 亮点")
    tags: list[str] | None = Field(default=None, description="标签，供筛选")


class CaseUpdateIn(QcUpdateBase):
    """编辑案例（只更新显式传入的字段）。"""

    item_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=128)
    reason: str | None = None
    tags: list[str] | None = None


class CaseOut(QcOutBase):
    """优秀案例出参。"""

    tenant_id: int
    conversation_id: int
    item_id: int | None = None
    title: str
    reason: str
    tags: list[str] | None = None
    is_published: bool
    published_at: datetime | None = None
    created_by: int | None = None


__all__ = ["CaseCreateIn", "CaseOut", "CaseUpdateIn"]