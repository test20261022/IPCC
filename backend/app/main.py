"""FastAPI 应用入口。"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_client_ip, get_user_agent
from app.api.v1.router import api_router
from app.core.cache import get_redis, is_available
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import setup_logging
from app.core.openapi_examples import apply_examples
from app.core.response import BizCode, fail, ok
from app.core.security import decode_token
from app.db.session import session_scope
from app.models.log import OperationLog
from app.repositories.user_repository import UserRepository
from app.tasks.scheduler import shutdown_scheduler, start_scheduler

setup_logging()
logger = logging.getLogger(__name__)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LOGGED_SKIP_PATHS = ("/auth/login",)
_STATUS_TO_CODE = {
    400: int(BizCode.PARAM_ERROR),
    401: int(BizCode.UNAUTHORIZED),
    403: int(BizCode.FORBIDDEN),
    404: int(BizCode.NOT_FOUND),
    409: int(BizCode.CONFLICT),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_redis()  # 预热缓存连接；不可用时自动降级
    start_scheduler()  # §22 超时回收 / §21 重试派发
    logger.info("%s 启动完成，版本 %s", settings.APP_NAME, settings.APP_VERSION)
    yield
    shutdown_scheduler()
    logger.info("%s 已关闭", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="企业管理平台后端 API",
    lifespan=lifespan,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------------- 全局异常处理（统一 {code,message,data}） ----------------


@app.exception_handler(AppException)
async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "业务异常 %s %s -> %s(%s)", request.method, request.url.path, exc.code, exc.message
    )
    return JSONResponse(status_code=exc.http_status, content=fail(exc.code, exc.message))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in err.get("loc", [])), "msg": err.get("msg", "")}
        for err in exc.errors()
    ]
    logger.warning("参数校验失败 %s %s -> %s", request.method, request.url.path, details)
    return JSONResponse(
        status_code=400,
        content=fail(int(BizCode.PARAM_ERROR), "参数错误", details),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_TO_CODE.get(exc.status_code, int(BizCode.SYSTEM_ERROR))
    return JSONResponse(
        status_code=exc.status_code,
        content=fail(code, str(exc.detail), None),
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=fail(int(BizCode.SYSTEM_ERROR), "系统异常，请稍后重试"),
    )


# ---------------- 操作日志（§70 / §59：超管操作同样记录） ----------------


def _build_operation_log(
    request: Request, status_code: int, duration_ms: int
) -> OperationLog:
    user_id: int | None = None
    username: str | None = None

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        try:
            payload = decode_token(auth_header.split(" ", 1)[1])
            user_id = int(str(payload.get("sub", "")))
        except Exception:
            user_id = None

    module = request.url.path.removeprefix(settings.API_V1_PREFIX).strip("/").split("/")[0]
    return OperationLog(
        user_id=user_id,
        username=username,
        module=module or "root",
        action=request.method,
        method=request.method,
        path=request.url.path,
        ip=get_client_ip(request),
        user_agent=(get_user_agent(request) or "")[:255] or None,
        status_code=status_code,
        success=status_code < 400,
        duration_ms=duration_ms,
    )


def _write_operation_log(request: Request, status_code: int, duration_ms: int) -> None:
    log = _build_operation_log(request, status_code, duration_ms)
    with session_scope() as db:
        if log.user_id is not None:
            user = UserRepository(db).get_by_id(log.user_id)
            log.username = user.username if user else None
        db.add(log)


@app.middleware("http")
async def operation_log_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)

    path = request.url.path
    should_log = (
        request.method not in _SAFE_METHODS
        and path.startswith(settings.API_V1_PREFIX)
        and not path.endswith(_LOGGED_SKIP_PATHS)
    )
    if should_log:
        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            await run_in_threadpool(
                _write_operation_log, request, response.status_code, duration_ms
            )
        except Exception:
            logger.exception("写入操作日志失败 %s %s", request.method, path)

    return response


# ---------------- 路由 ----------------

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get(
    "/health",
    tags=["系统"],
    summary="健康检查",
    description="返回服务自身与依赖（Redis）的可用状态，供部署探活使用。",
)
async def health() -> dict[str, Any]:
    return ok(
        {
            "status": "ok",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "redis": is_available(),
        }
    )


# ---------------- OpenAPI（§58：summary / description / response_model / examples） ---------------


def custom_openapi() -> dict[str, Any]:
    """在 FastAPI 默认文档基础上统一补齐 examples（见 core/openapi_examples.py）。"""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="企业管理平台后端 API",
        routes=app.routes,
    )
    apply_examples(schema)
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]
