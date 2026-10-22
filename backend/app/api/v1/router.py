"""v1 路由聚合：后续模块（outbound / qc 等）在此挂载。"""

from fastapi import APIRouter

from app.api.v1 import auth
from app.api.v1.outbound import (
    agents,
    callbacks,
    ivr,
    lists,
    numbers,
    options,
    records,
    reports,
    scenes,
    sessions,
    tasks,
    types,
)
from app.api.v1.qc import (
    cases as qc_cases,
)
from app.api.v1.qc import (
    conversations as qc_conversations,
)
from app.api.v1.qc import (
    reports as qc_reports,
)
from app.api.v1.qc import (
    review as qc_review,
)
from app.api.v1.qc import (
    reviewers as qc_reviewers,
)
from app.api.v1.qc import (
    tasks as qc_tasks,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(options.router)
api_router.include_router(types.router)
api_router.include_router(scenes.router)
api_router.include_router(numbers.router)
api_router.include_router(tasks.router)
api_router.include_router(lists.router)
api_router.include_router(records.router)
api_router.include_router(agents.router)
api_router.include_router(sessions.router)
api_router.include_router(ivr.router)
api_router.include_router(callbacks.router)
api_router.include_router(reports.router)

# 对话质检模块：先挂载静态路径（专家组 / 任务 / 报表 / 案例库），再挂载带 {id} 的执行域，
# 避免 `/qc/items/{item_id}` 一类动态段吞掉同层静态路径。
api_router.include_router(qc_conversations.router)
api_router.include_router(qc_reviewers.router)
api_router.include_router(qc_tasks.router)
api_router.include_router(qc_reports.router)
api_router.include_router(qc_cases.router)
api_router.include_router(qc_review.router)
