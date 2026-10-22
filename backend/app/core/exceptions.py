"""业务异常体系：Service 层抛 AppException，由全局处理器统一转为 {code,message,data}。"""

from typing import Any

from app.core.response import BizCode


class AppException(Exception):
    """业务异常基类。子类通过覆盖 code / http_status / message 定义语义。"""

    code: int = int(BizCode.SYSTEM_ERROR)
    http_status: int = 500
    message: str = "系统异常"

    def __init__(self, message: str | None = None, *, detail: Any = None) -> None:
        if message:
            self.message = message
        self.detail = detail
        super().__init__(self.message)


class ParamError(AppException):
    """40001 参数错误。"""

    code = int(BizCode.PARAM_ERROR)
    http_status = 400
    message = "参数错误"


class Unauthorized(AppException):
    """40101 未登录 / 登录已过期。"""

    code = int(BizCode.UNAUTHORIZED)
    http_status = 401
    message = "未登录或登录已过期"


class Forbidden(AppException):
    """40301 无权限。"""

    code = int(BizCode.FORBIDDEN)
    http_status = 403
    message = "无权限访问"


class NotFound(AppException):
    """40401 数据不存在。"""

    code = int(BizCode.NOT_FOUND)
    http_status = 404
    message = "数据不存在"


class Conflict(AppException):
    """40901 数据冲突（唯一约束等）。"""

    code = int(BizCode.CONFLICT)
    http_status = 409
    message = "数据冲突"


class StateNotAllowed(AppException):
    """40902 当前状态不允许该操作。"""

    code = int(BizCode.STATE_NOT_ALLOWED)
    http_status = 409
    message = "当前状态不允许该操作"


class NumberExhausted(AppException):
    """40903 外呼号码次数耗尽（OB-005）。"""

    code = int(BizCode.NUMBER_EXHAUSTED)
    http_status = 409
    message = "外呼号码已无可用的主叫号码"


class ResourceReferenced(AppException):
    """40904 资源已被引用，禁止编辑/删除（OB-003 / OB-004）。"""

    code = int(BizCode.RESOURCE_REFERENCED)
    http_status = 409
    message = "资源已被引用"
