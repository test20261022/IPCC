"""全场景变量解析（OB-012 / §27）。

把「名单字段 + 任务配置 + 场景配置 + 用户信息 + 订单信息」合并为统一变量字典，
供话术 / IVR / ASR / TTS / 短信 / 服务小结复用。

约定：
- 系统保留键先写入，名单动态字段仅在「不覆盖保留键」的前提下平铺追加，
  避免名单里的同名列把系统变量顶掉（ASSUMPTION-026）。
- 字段缺失时返回空字符串而非抛错，保证话术渲染不中断。
"""

from typing import Any

from app.models.outbound import OutboundList, OutboundTask
from app.repositories.outbound.reference_repository import ReferenceRepository
from app.repositories.outbound.scene_repository import OutboundSceneRepository
from app.repositories.outbound.type_repository import OutboundTypeRepository


class OutboundVariableResolver:
    """名单全场景变量解析器。"""

    def __init__(self, db) -> None:  # noqa: ANN001 - Session 类型由调用方确定
        self.db = db
        self.scene_repo = OutboundSceneRepository(db)
        self.type_repo = OutboundTypeRepository(db)
        self.ref = ReferenceRepository(db)

    def resolve(self, name_list: OutboundList, task: OutboundTask | None = None) -> dict[str, Any]:
        """解析变量字典。"""
        phones = list(name_list.phone_numbers or [])
        variables: dict[str, Any] = {
            # 名单维度
            "list_id": name_list.id,
            "user_id": name_list.user_id or "",
            "order_id": name_list.order_id or "",
            "recipient_name": name_list.recipient_name or "",
            "customer_name": name_list.recipient_name or "",
            "phone": name_list.recipient_phone or (phones[0] if phones else ""),
            "phone_numbers": phones,
            "tenant_id": name_list.tenant_id,
        }

        if task is not None:
            variables.update(
                {
                    "task_id": task.id,
                    "task_name": task.task_name,
                    "dispatch_mode": task.dispatch_mode.value,
                    "max_retry_count": task.max_retry_count,
                    "retry_interval": task.retry_interval,
                }
            )

            if task.type_id is not None:
                outbound_type = self.type_repo.get_by_id(task.type_id)
                variables["type_id"] = task.type_id
                variables["type_name"] = outbound_type.name if outbound_type else ""

            if task.scene_id is not None:
                scene = self.scene_repo.get_by_id(task.scene_id)
                variables["scene_id"] = task.scene_id
                variables["scene_name"] = scene.name if scene else ""

            if task.site_id is not None:
                site = self.ref.get_site_by_id(task.site_id)
                variables["site_id"] = task.site_id
                variables["site_name"] = site.name if site else ""

        # 名单动态字段平铺；不覆盖系统保留键
        for key, value in (name_list.dynamic_fields or {}).items():
            if key not in variables:
                variables[key] = value

        return variables
