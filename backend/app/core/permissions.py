"""权限码目录（§59）。

集中定义所有权限码，供 init_db 落库、API 依赖校验、前端菜单/按钮三方共用，
避免权限码散落在各处导致拼写漂移。
"""

from dataclasses import dataclass

OUTBOUND_MODULE = "outbound"


@dataclass(frozen=True)
class PermissionDef:
    """一条权限定义。"""

    code: str
    name: str
    module: str
    description: str = ""


def _p(code: str, name: str, description: str = "", module: str = OUTBOUND_MODULE) -> PermissionDef:
    return PermissionDef(code=code, name=name, module=module, description=description)


OUTBOUND_PERMISSIONS: tuple[PermissionDef, ...] = (
    # OB-001 / OB-005 外呼号码
    _p("outbound:number:list", "外呼号码查看"),
    _p("outbound:number:create", "外呼号码新增"),
    _p("outbound:number:update", "外呼号码编辑"),
    _p("outbound:number:delete", "外呼号码删除"),
    _p("outbound:number:use", "外呼号码使用（主叫次数扣减）"),
    # OB-004 外呼类型
    _p("outbound:type:list", "外呼类型查看"),
    _p("outbound:type:create", "外呼类型新增"),
    _p("outbound:type:update", "外呼类型编辑"),
    _p("outbound:type:delete", "外呼类型删除"),
    # OB-003 外呼场景
    _p("outbound:scene:list", "外呼场景查看"),
    _p("outbound:scene:create", "外呼场景新增"),
    _p("outbound:scene:update", "外呼场景编辑"),
    _p("outbound:scene:delete", "外呼场景删除"),
    # OB-006 / OB-008 / OB-020 外呼任务
    _p("outbound:task:list", "外呼任务查看"),
    _p("outbound:task:create", "外呼任务新增"),
    _p("outbound:task:update", "外呼任务编辑"),
    _p("outbound:task:delete", "外呼任务删除"),
    _p("outbound:task:copy", "外呼任务复制"),
    _p("outbound:task:execute", "外呼任务执行"),
    # OB-011 / OB-012 名单导入与变量（§59 未单列，按功能粒度补齐）
    _p("outbound:list:list", "外呼名单查看"),
    _p("outbound:list:import", "外呼名单导入"),
    _p("outbound:list:variable", "外呼名单全场景变量查看"),
    # OB-018 坐席与自动分配（§59 未单列，按功能粒度补齐）
    _p("outbound:agent:list", "坐席查看"),
    _p("outbound:agent:create", "坐席新增"),
    _p("outbound:agent:update", "坐席编辑与状态管理"),
    _p("outbound:agent:delete", "坐席删除"),
    _p("outbound:assignment:list", "坐席预占与派单查看"),
    _p("outbound:assignment:dispatch", "坐席自动派单触发"),
    _p("outbound:assignment:release", "坐席预占释放"),
    # OB-021 外呼会话
    _p("outbound:session:list", "外呼会话查看"),
    _p("outbound:session:call", "人工外呼执行"),
    # OB-028 实时监控
    _p("outbound:monitor:view", "外呼实时监控查看"),
    # OB-025 外呼报表
    _p("outbound:report:list", "外呼报表查看"),
    # OB-017 IVR
    _p("outbound:ivr:list", "IVR 流程查看"),
    _p("outbound:ivr:create", "IVR 流程新增"),
    _p("outbound:ivr:update", "IVR 流程编辑"),
    _p("outbound:ivr:delete", "IVR 流程删除"),
    # OB-029 / OB-030 回呼
    _p("outbound:callback:list", "回呼任务查看"),
    _p("outbound:callback:create", "回呼任务创建"),
    _p("outbound:callback:execute", "回呼任务执行"),
)

# ---------------- 对话质检模块 ----------------

QC_MODULE = "qc"


def _q(code: str, name: str, description: str = "") -> PermissionDef:
    return _p(code, name, description, module=QC_MODULE)


QC_PERMISSIONS: tuple[PermissionDef, ...] = (
    # 对话数据
    _q("qc:conversation:list", "质检对话查看"),
    _q("qc:conversation:create", "质检对话新增"),
    _q("qc:conversation:update", "质检对话编辑"),
    _q("qc:conversation:delete", "质检对话删除"),
    _q("qc:conversation:import", "质检对话导入"),
    _q("qc:conversation:transcribe", "质检对话语音转写"),
    # 专家组
    _q("qc:reviewer:list", "专家组查看"),
    _q("qc:reviewer:create", "专家组新增"),
    _q("qc:reviewer:update", "专家组编辑"),
    # 质检任务
    _q("qc:task:list", "质检任务查看"),
    _q("qc:task:create", "质检任务新增"),
    _q("qc:task:update", "质检任务编辑"),
    _q("qc:task:delete", "质检任务删除"),
    _q("qc:task:dispatch", "质检任务派发"),
    _q("qc:task:cancel", "质检任务取消"),
    # 质检执行
    _q("qc:review:work", "我的质检工作台查看"),
    _q("qc:review:submit", "质检结果提交"),
    # 优秀案例库
    _q("qc:case:list", "优秀案例查看"),
    _q("qc:case:create", "优秀案例新增"),
    _q("qc:case:update", "优秀案例编辑"),
    _q("qc:case:delete", "优秀案例删除"),
    _q("qc:case:publish", "优秀案例发布"),
    # 报表
    _q("qc:report:list", "质检报表查看"),
)

# 全部权限（后续模块在此追加）
ALL_PERMISSIONS: tuple[PermissionDef, ...] = OUTBOUND_PERMISSIONS + QC_PERMISSIONS

__all__ = [
    "ALL_PERMISSIONS",
    "OUTBOUND_MODULE",
    "OUTBOUND_PERMISSIONS",
    "QC_MODULE",
    "QC_PERMISSIONS",
    "PermissionDef",
]
