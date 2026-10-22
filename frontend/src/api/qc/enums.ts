/**
 * 质检枚举与中文文案。
 * 取值与后端 app/models/qc/enums.py 一一对应，禁止在页面里硬编码字符串。
 *
 * Option / labelOf 复用外呼域的实现，避免两套下拉文案工具各写一遍。
 */

import { labelOf, type Option } from '@/api/outbound/enums'

export { labelOf }
export type { Option }

/** 对话渠道（ConversationChannel） */
export const CONVERSATION_CHANNEL_LABELS: Record<string, string> = {
  CHAT: '文字对话',
  VOICE: '语音对话',
  OTHER: '其他',
}

export const CONVERSATION_CHANNEL_OPTIONS: Option[] = Object.entries(
  CONVERSATION_CHANNEL_LABELS,
).map(([value, label]) => ({ value, label }))

/** 对话来源（ConversationSource） */
export const CONVERSATION_SOURCE_LABELS: Record<string, string> = {
  MANUAL: '人工录入',
  IMPORT: '批量导入',
}

export const CONVERSATION_SOURCE_OPTIONS: Option[] = Object.entries(
  CONVERSATION_SOURCE_LABELS,
).map(([value, label]) => ({ value, label }))

/** 语音转写状态（TranscriptStatus） */
export const TRANSCRIPT_STATUS_LABELS: Record<string, string> = {
  NOT_REQUIRED: '无需转写',
  PENDING: '待转写',
  RUNNING: '转写中',
  SUCCESS: '转写成功',
  FAILED: '转写失败',
}

export const TRANSCRIPT_STATUS_OPTIONS: Option[] = Object.entries(
  TRANSCRIPT_STATUS_LABELS,
).map(([value, label]) => ({ value, label }))

/** 消息说话人（MessageRole） */
export const MESSAGE_ROLE_LABELS: Record<string, string> = {
  AGENT: '客服',
  CUSTOMER: '客户',
  SYSTEM: '系统',
}

/** 消息来源（MessageSource） */
export const MESSAGE_SOURCE_LABELS: Record<string, string> = {
  TEXT: '原始文本',
  ASR: '语音转写',
}

/** 导入文件格式（QcImportFormat） */
export const QC_IMPORT_FORMAT_LABELS: Record<string, string> = {
  TXT: 'TXT',
  JSON: 'JSON',
  XLSX: 'XLSX',
}

/** 导入批次状态（QcImportStatus） */
export const QC_IMPORT_STATUS_LABELS: Record<string, string> = {
  PENDING: '待处理',
  PARSING: '解析中',
  IMPORTING: '导入中',
  SUCCESS: '成功',
  PARTIAL_FAILED: '部分失败',
  FAILED: '失败',
}

export const QC_IMPORT_STATUS_OPTIONS: Option[] = Object.entries(
  QC_IMPORT_STATUS_LABELS,
).map(([value, label]) => ({ value, label }))

/** 质检任务状态（QcTaskStatus） */
export const QC_TASK_STATUS_LABELS: Record<string, string> = {
  DRAFT: '草稿',
  DISPATCHED: '已派发',
  REVIEWING: '质检中',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
}

export const QC_TASK_STATUS_OPTIONS: Option[] = Object.entries(QC_TASK_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 派发分片方式（QcDispatchMode） */
export const QC_DISPATCH_MODE_LABELS: Record<string, string> = {
  ROUND_ROBIN: '轮询交替',
  AVERAGE: '连续均分',
}

export const QC_DISPATCH_MODE_OPTIONS: Option[] = Object.entries(QC_DISPATCH_MODE_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 质检明细状态（QcItemStatus） */
export const QC_ITEM_STATUS_LABELS: Record<string, string> = {
  PENDING: '待质检',
  REVIEWING: '质检中',
  COMPLETED: '已完成',
  TIMEOUT: '已超时',
}

export const QC_ITEM_STATUS_OPTIONS: Option[] = Object.entries(QC_ITEM_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 质检等级（QcGrade） */
export const QC_GRADE_LABELS: Record<string, string> = {
  EXCELLENT: '优秀',
  PASS: '及格',
  FAIL: '不及格',
}

export const QC_GRADE_OPTIONS: Option[] = Object.entries(QC_GRADE_LABELS).map(
  ([value, label]) => ({ value, label }),
)

/** 等级标签配色（与 StatusTag 的 type 取值一致） */
export const QC_GRADE_TAG_TYPES: Record<string, 'success' | 'warning' | 'danger'> = {
  EXCELLENT: 'success',
  PASS: 'warning',
  FAIL: 'danger',
}

/**
 * 得分 → 等级的前端预览。
 * 仅用于表单即时提示，最终等级一律以后端判定为准（后端依据配置阈值回写）。
 */
export function previewGrade(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(score)) return ''
  if (score >= 90) return 'EXCELLENT'
  if (score >= 60) return 'PASS'
  return 'FAIL'
}