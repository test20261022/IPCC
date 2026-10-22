"""统一响应体与业务错误码（§56）。所有接口返回 {code, message, data}。"""

from enum import IntEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BizCode(IntEnum):
    """业务错误码，与 HTTP 状态码解耦。"""

    SUCCESS = 0
    PARAM_ERROR = 40001
    UNAUTHORIZED = 40101
    FORBIDDEN = 40301
    NOT_FOUND = 40401
    CONFLICT = 40901
    STATE_NOT_ALLOWED = 40902
    NUMBER_EXHAUSTED = 40903
    RESOURCE_REFERENCED = 40904
    SYSTEM_ERROR = 50000


class ApiResponse(BaseModel, Generic[T]):
    """统一响应结构。"""

    code: int = Field(default=int(BizCode.SUCCESS), description="业务码，0 表示成功")
    message: str = Field(default="success", description="提示信息")
    data: T | None = Field(default=None, description="业务数据")


class PageData(BaseModel, Generic[T]):
    """分页数据结构（§57）。"""

    items: list[T] = Field(default_factory=list, description="当前页数据")
    total: int = Field(default=0, description="总条数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页条数")


def ok(data: object | None = None, message: str = "success") -> dict:
    """成功响应。"""
    return {"code": int(BizCode.SUCCESS), "message": message, "data": data}


def fail(code: int, message: str, data: object | None = None) -> dict:
    """失败响应。"""
    return {"code": int(code), "message": message, "data": data}


def page_data(items: list, total: int, page: int, page_size: int) -> dict:
    """分页响应数据。"""
    return {"items": items, "total": total, "page": page, "page_size": page_size}
