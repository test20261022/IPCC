"""预测外呼（§36）。

MVP 采用简单统计模型，算法集中在本服务，禁止散落到 Router / Task / Repository：
    answer_rate        = answered / total
    target_concurrency = available_agents × answer_rate × adjustment_factor
"""

import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.outbound import OutboundTask
from app.repositories.outbound.agent_repository import OutboundAgentRepository
from app.repositories.outbound.record_repository import OutboundRecordRepository

logger = logging.getLogger(__name__)

#: 接通率统计窗口（分钟）：窗口过短样本不足，过长对实时并发不敏感
ANSWER_RATE_WINDOW_MINUTES = 60


class OutboundPredictionService:
    """预测外呼计算。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.agent_repo = OutboundAgentRepository(db)
        self.record_repo = OutboundRecordRepository(db)

    def answer_rate(
        self, *, task_id: int | None = None, tenant_id: int | None = None
    ) -> dict[str, object]:
        """接通率：answered / total（窗口内无呼叫时返回 0，避免除零）。"""
        since = datetime.now(timezone.utc) - timedelta(minutes=ANSWER_RATE_WINDOW_MINUTES)
        total, answered = self.record_repo.history_stats(
            task_id=task_id, tenant_id=tenant_id, since=since
        )
        rate = round(answered / total, 4) if total else 0.0
        return {
            "window_minutes": ANSWER_RATE_WINDOW_MINUTES,
            "total_calls": total,
            "answered_calls": answered,
            "answer_rate": rate,
        }

    def target_concurrency(self, task: OutboundTask) -> dict[str, object]:
        """目标并发：available_agents × answer_rate × adjustment_factor（向上取整）。"""
        status_count = self.agent_repo.count_by_status(
            tenant_id=task.tenant_id, skill_queue_id=task.skill_queue_id
        )
        available_agents = int(status_count.get("IDLE", 0))

        rate_info = self.answer_rate(task_id=task.id)
        answer_rate = float(rate_info["answer_rate"])  # type: ignore[arg-type]
        factor = float(task.adjustment_factor)

        target = max(0, math.ceil(available_agents * answer_rate * factor))
        # 预测并发不应超过任务自身配置的并发上限
        capped = min(target, task.max_concurrency)

        result = {
            "task_id": task.id,
            "dispatch_mode": task.dispatch_mode.value,
            "available_agents": available_agents,
            "answer_rate": answer_rate,
            "adjustment_factor": factor,
            "max_concurrency": task.max_concurrency,
            "target_concurrency": capped,
            "uncapped_target": target,
        }
        logger.debug("预测外呼计算：%s", result)
        return result
