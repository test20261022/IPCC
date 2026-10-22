/**
 * 外呼枚举与中文文案。
 * 取值与后端 app/models/outbound/enums.py 一一对应，禁止在页面里硬编码字符串。
 */

export interface Option<T = string> {
  label: string
  value: T
}

/** 任务状态（TaskStatus） */
export const TASK_STATUS_LABELS: Record<string, string> = {
  DRAFT: '草稿',
  READY: '就绪',
  RUNNING: '运行中',
  PAUSED: '已暂停',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
}

export const TASK_STATUS_OPTIONS: Option[] = Object.entries(TASK_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 派单模式（DispatchMode） */
export const DISPATCH_MODE_LABELS: Record<string, string> = {
  MANUAL: '手动派单',
  AUTO: '自动分配',
  PREDICTIVE: '预测外呼',
}

export const DISPATCH_MODE_OPTIONS: Option[] = Object.entries(DISPATCH_MODE_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 主叫号码选取策略（NumberSelectStrategy） */
export const NUMBER_STRATEGY_LABELS: Record<string, string> = {
  ORDER: '按配置顺序',
  ROUND_ROBIN: '轮询',
  AVAILABLE_FIRST: '优先可用',
  CUSTOM: '自定义',
}

export const NUMBER_STRATEGY_OPTIONS: Option[] = Object.entries(NUMBER_STRATEGY_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 执行记录状态（RecordStatus） */
export const RECORD_STATUS_LABELS: Record<string, string> = {
  PENDING: '待处理',
  ASSIGNED: '已分配',
  CALLING: '呼叫中',
  RETRY_WAITING: '重试等待',
  SUCCESS: '成功',
  FAILED: '失败',
  EXHAUSTED: '重试耗尽',
  TIMEOUT: '已超时',
}

export const RECORD_STATUS_OPTIONS: Option[] = Object.entries(RECORD_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 名单行状态（ListStatus） */
export const LIST_STATUS_LABELS: Record<string, string> = {
  PENDING: '待处理',
  PROCESSING: '处理中',
  SUCCESS: '成功',
  FAILED: '失败',
  EXHAUSTED: '重试耗尽',
  CANCELLED: '已取消',
}

export const LIST_STATUS_OPTIONS: Option[] = Object.entries(LIST_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 导入批次状态（ImportBatchStatus） */
export const IMPORT_BATCH_STATUS_LABELS: Record<string, string> = {
  PENDING: '待处理',
  PARSING: '解析中',
  VALIDATING: '校验中',
  IMPORTING: '导入中',
  SUCCESS: '成功',
  PARTIAL_FAILED: '部分失败',
  FAILED: '失败',
}

export const IMPORT_BATCH_STATUS_OPTIONS: Option[] = Object.entries(
  IMPORT_BATCH_STATUS_LABELS,
).map(([value, label]) => ({ value, label }))

/** 坐席状态（AgentStatus） */
export const AGENT_STATUS_LABELS: Record<string, string> = {
  OFFLINE: '离线',
  IDLE: '空闲',
  BUSY: '忙碌',
  RESERVED: '已预占',
  PAUSED: '暂停',
}

export const AGENT_STATUS_OPTIONS: Option[] = Object.entries(AGENT_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 预占状态（AssignmentStatus） */
export const ASSIGNMENT_STATUS_LABELS: Record<string, string> = {
  RESERVED: '已预占',
  ACCEPTED: '已接单',
  RELEASED: '已释放',
  EXPIRED: '已过期',
}

export const ASSIGNMENT_STATUS_OPTIONS: Option[] = Object.entries(ASSIGNMENT_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 会话状态（SessionStatus） */
export const SESSION_STATUS_LABELS: Record<string, string> = {
  CREATED: '已创建',
  ASSIGNED: '已分配',
  CALLING: '呼叫中',
  CONNECTED: '已接通',
  ENDED: '已结束',
  TIMEOUT: '已超时',
  RELEASED: '已释放',
}

export const SESSION_STATUS_OPTIONS: Option[] = Object.entries(SESSION_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 单次呼叫结果（CallStatus） */
export const CALL_STATUS_LABELS: Record<string, string> = {
  INITIATED: '已发起',
  RINGING: '振铃中',
  CONNECTED: '已接通',
  NO_ANSWER: '无应答',
  BUSY: '忙线',
  REJECTED: '已拒接',
  FAILED: '失败',
  TIMEOUT: '超时',
  HANGUP: '已挂断',
}

export const CALL_STATUS_OPTIONS: Option[] = Object.entries(CALL_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 话务来源（报表筛选用，与后端 report_repository 的 SOURCE_* 常量一致） */
export const CALL_FLOW_SOURCE_LABELS: Record<string, string> = {
  ALL: '全部话务',
  OUTBOUND: '外呼话务',
  CALLBACK: '回呼话务',
}

export const CALL_FLOW_SOURCE_OPTIONS: Option[] = Object.entries(CALL_FLOW_SOURCE_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 通用启用 / 停用 */
export const COMMON_STATUS_OPTIONS: Option[] = [
  { label: '启用', value: 'ENABLED' },
  { label: '停用', value: 'DISABLED' },
]

/** 场景 / 类型层级 */
export const LEVEL_OPTIONS: Option<number>[] = [
  { label: '一级', value: 1 },
  { label: '二级', value: 2 },
]

/** IVR 节点类型（§31） */
export const IVR_NODE_TYPE_LABELS: Record<string, string> = {
  PLAY: '播报',
  COLLECT_DTMF: '按键采集',
  TRANSFER_AGENT: '转人工',
  HANGUP: '挂断',
  CALLBACK: '转回呼',
  REPLAY: '重播',
}

export const IVR_NODE_TYPE_OPTIONS: Option[] = Object.entries(IVR_NODE_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** IVR 流转条件类型（§31） */
export const IVR_CONDITION_TYPE_LABELS: Record<string, string> = {
  KEY: '按键',
  ASR_RESULT: '识别结果',
  TIME_RANGE: '时段',
  QUEUE_AVAILABLE: '队列可用',
}

export const IVR_CONDITION_TYPE_OPTIONS: Option[] = Object.entries(
  IVR_CONDITION_TYPE_LABELS,
).map(([value, label]) => ({ value, label }))

/** 转人工无可用坐席时的动作（§32，禁止硬编码） */
export const NO_AGENT_ACTION_LABELS: Record<string, string> = {
  QUEUE: '排队等待',
  CALLBACK: '转回呼',
  REPLAY: '重播重试',
  HANGUP: '直接挂断',
}

export const NO_AGENT_ACTION_OPTIONS: Option[] = Object.entries(NO_AGENT_ACTION_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** IVR 模拟推演的动作 */
export const IVR_SIM_ACTION_LABELS: Record<string, string> = {
  PLAY: '播报',
  REPLAY: '重播',
  MOVE: '流转',
  TRANSFER: '转接人工',
  QUEUE: '进入排队',
  CALLBACK: '转入回呼',
  HANGUP: '挂断',
  NO_INPUT: '无输入',
  END: '流程结束',
  ABORT: '中止',
}

/** IVR 模拟推演的结束原因 */
export const IVR_END_REASON_LABELS: Record<string, string> = {
  TRANSFERRED: '已转接人工坐席',
  QUEUE: '已进入技能队列排队',
  CALLBACK: '已转为回呼任务',
  HANGUP: '已挂断',
  FLOW_END: '流程正常结束',
  NO_INPUT: '无输入等待超时结束',
  MAX_STEPS: '推演步数超限终止',
  ENTRY_NOT_FOUND: '入口节点缺失',
}

/** 号码来源顺序字段：用于任务号码配置与看板展示 */
export const PHONE_SOURCE_LABELS: Record<string, string> = {
  order_id: 'OrderID',
  user_id: 'UserID',
  recipient_number: '收件人号码',
}

/** 回呼来源（OB-029 IVR 回呼 / OB-030 人工回呼） */
export const CALLBACK_SOURCE_LABELS: Record<string, string> = {
  IVR: 'IVR 回呼',
  MANUAL: '人工回呼',
}

export const CALLBACK_SOURCE_OPTIONS: Option[] = Object.entries(CALLBACK_SOURCE_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 回呼任务状态（§46） */
export const CALLBACK_STATUS_LABELS: Record<string, string> = {
  PENDING: '待回呼',
  ASSIGNED: '已分配',
  CALLING: '呼叫中',
  SUCCESS: '已成功',
  FAILED: '已失败',
  CANCELLED: '已取消',
}

export const CALLBACK_STATUS_OPTIONS: Option[] = Object.entries(CALLBACK_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 回呼自动触发条件（§45） */
export const CALLBACK_TRIGGER_TYPE_LABELS: Record<string, string> = {
  NO_AGENT: '转人工无可用坐席',
  NO_ANSWER: '未接通坐席即挂断',
  KEY: '客户按键命中',
  OUT_OF_HOURS: '非业务时段来电',
}

export const CALLBACK_TRIGGER_TYPE_OPTIONS: Option[] = Object.entries(
  CALLBACK_TRIGGER_TYPE_LABELS,
).map(([value, label]) => ({ value, label }))

export function labelOf(map: Record<string, string>, value?: string | null): string {
  if (!value) return '-'
  return map[value] ?? value
}
