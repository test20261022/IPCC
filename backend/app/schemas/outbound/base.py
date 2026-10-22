"""外呼 Schema 公共基类。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OutboundSchemaBase(BaseModel):
    """外呼模块 Schema 基类：允许从 ORM 对象直接构造。"""

    model_config = ConfigDict(from_attributes=True)


class OutboundOutBase(OutboundSchemaBase):
    """出参基类：统一带上主键与时间戳。"""

    id: int = Field(description="主键")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class OutboundUpdateBase(OutboundSchemaBase):
    """入参基类：更新语义为「只更新显式传入的字段」。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class BatchDeleteResult(OutboundSchemaBase):
    """批量删除结果：requested 为请求条数，deleted 为实际软删除条数（含级联）。"""

    requested: int = Field(default=0, description="请求删除条数")
    deleted: int = Field(default=0, description="实际删除条数（一级场景会级联其二级场景）")


__all__ = [
    "BatchDeleteResult",
    "OutboundOutBase",
    "OutboundSchemaBase",
    "OutboundUpdateBase",
]
