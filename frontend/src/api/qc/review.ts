import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'
import type { QcGrade, QcItemStatus, QcTaskItem } from '@/api/qc/tasks'

/** 对话渠道（与后端 QcConversationOut.channel 一致） */
export type QcConversationChannel = 'CHAT' | 'VOICE' | 'OTHER'

/** 对话来源（与后端 QcConversationOut.source 一致） */
export type QcConversationSource = 'MANUAL' | 'IMPORT'

/** 消息说话人（MessageRole） */
export type QcMessageRole = 'AGENT' | 'CUSTOMER' | 'SYSTEM'

/** 消息来源（MessageSource） */
export type QcMessageSource = 'TEXT' | 'ASR'

/** 工作台对话信息 */
export interface QcWorkConversation {
  id: number
  ext_ref_no: string | null
  agent_name: string | null
  customer_id: string | null
  channel: QcConversationChannel
  source: QcConversationSource
  started_at: string
  ended_at: string | null
  duration: number
  msg_count: number
}

/** 工作台对话消息（按 seq 升序） */
export interface QcWorkMessage {
  seq: number
  role: QcMessageRole
  content: string
  start_ms: number | null
  end_ms: number | null
  source: QcMessageSource
}

/** 质检工作台详情：明细 + 对话 + 对话消息 */
export interface QcItemDetail {
  item: QcTaskItem
  conversation: QcWorkConversation | null
  messages: QcWorkMessage[]
}

/** 提交质检结果入参：等级由后端按分数阈值判定，不接受直传 */
export interface QcItemSubmitPayload {
  score: number
  comment: string
  score_detail?: Record<string, unknown> | null
}

export interface QcItemSubmitResult {
  item_id: number
  grade: QcGrade
  status: QcItemStatus
  submitted_at: string | null
  task_completed: boolean
}

export interface MyQcItemQuery extends PageQuery {
  status?: QcItemStatus
}

export const listMyQcItems = (params: MyQcItemQuery) =>
  http.get<PageData<QcTaskItem>>('/qc/my/items', params as Record<string, unknown>)

export const getQcItemDetail = (id: number) => http.get<QcItemDetail>(`/qc/items/${id}`)

export const claimQcItem = (id: number) => http.post<QcTaskItem>(`/qc/items/${id}/claim`)

export const releaseQcItem = (id: number) => http.post<QcTaskItem>(`/qc/items/${id}/release`)

export const submitQcItem = (id: number, data: QcItemSubmitPayload) =>
  http.post<QcItemSubmitResult>(`/qc/items/${id}/submit`, data)