import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'

/** 对话渠道 */
export type ConversationChannel = 'CHAT' | 'VOICE' | 'OTHER'

/** 对话来源 */
export type ConversationSource = 'MANUAL' | 'IMPORT'

/** 语音转写状态 */
export type TranscriptStatus = 'NOT_REQUIRED' | 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED'

/** 消息说话人 */
export type MessageRole = 'AGENT' | 'CUSTOMER' | 'SYSTEM'

/** 消息来源：原始文本 / 语音转写 */
export type MessageSource = 'TEXT' | 'ASR'

/** 导入文件格式 */
export type QcImportFormat = 'TXT' | 'JSON' | 'XLSX'

/** 导入批次状态 */
export type QcImportStatus =
  | 'PENDING'
  | 'PARSING'
  | 'IMPORTING'
  | 'SUCCESS'
  | 'PARTIAL_FAILED'
  | 'FAILED'

/** 对话消息（按 seq 升序即为对话顺序） */
export interface QcMessage {
  id: number
  conversation_id: number
  seq: number
  role: MessageRole
  content: string
  start_ms: number | null
  end_ms: number | null
  source: MessageSource
  created_at: string
  updated_at: string
}

/** 对话主表 */
export interface QcConversation {
  id: number
  tenant_id: number
  ext_ref_no: string | null
  agent_name: string | null
  agent_ext: string | null
  customer_id: string | null
  channel: ConversationChannel
  source: ConversationSource
  started_at: string
  ended_at: string | null
  duration: number | null
  msg_count: number
  recording_path: string | null
  transcript_status: TranscriptStatus
  transcript_engine: string | null
  created_at: string
  updated_at: string
}

/** 对话详情：主表 + 全部消息 */
export interface QcConversationDetail extends QcConversation {
  messages: QcMessage[]
}

/** 新增对话时的消息入参 */
export interface QcMessagePayload {
  role: MessageRole
  content: string
  start_ms?: number | null
  end_ms?: number | null
}

/** 新增对话入参（tenant_id 与 started_at 必填） */
export interface QcConversationPayload {
  tenant_id: number
  ext_ref_no?: string | null
  agent_name?: string | null
  agent_ext?: string | null
  customer_id?: string | null
  channel?: ConversationChannel
  started_at: string
  ended_at?: string | null
  duration?: number | null
  recording_path?: string | null
  messages?: QcMessagePayload[]
}

/** 更新对话入参：字段全部可选，且不接受 tenant_id 与 messages */
export interface QcConversationUpdatePayload {
  ext_ref_no?: string | null
  agent_name?: string | null
  agent_ext?: string | null
  customer_id?: string | null
  channel?: ConversationChannel
  started_at?: string
  ended_at?: string | null
  duration?: number | null
  recording_path?: string | null
}

export interface QcConversationQuery extends PageQuery {
  tenant_id?: number
  agent_name?: string
  channel?: ConversationChannel
  source?: ConversationSource
  transcript_status?: TranscriptStatus
  started_from?: string
  started_to?: string
  keyword?: string
}

/** 导入批次 */
export interface QcImportBatch {
  id: number
  tenant_id: number
  file_name: string
  file_path: string | null
  format: QcImportFormat
  total_rows: number
  success_rows: number
  failed_rows: number
  status: QcImportStatus
  error_detail: Array<Record<string, unknown>> | null
  created_at: string
  updated_at: string
}

export interface QcImportBatchQuery extends PageQuery {
  tenant_id?: number
}

/** 语音转写结果 */
export interface QcTranscribeResult {
  conversation_id: number
  transcript_status: TranscriptStatus
  transcript_engine: string | null
  message_count: number
}

export const listQcConversations = (params: QcConversationQuery) =>
  http.get<PageData<QcConversation>>('/qc/conversations', params as Record<string, unknown>)

export const getQcConversation = (id: number) =>
  http.get<QcConversationDetail>(`/qc/conversations/${id}`)

export const createQcConversation = (data: QcConversationPayload) =>
  http.post<QcConversation>('/qc/conversations', data)

export const updateQcConversation = (id: number, data: QcConversationUpdatePayload) =>
  http.put<QcConversation>(`/qc/conversations/${id}`, data)

export const deleteQcConversation = (id: number) =>
  http.delete<null>(`/qc/conversations/${id}`)

export const listQcConversationMessages = (id: number) =>
  http.get<QcMessage[]>(`/qc/conversations/${id}/messages`)

/** 上传对话文件导入（multipart 表单） */
export const importQcConversations = (tenantId: number, file: File) => {
  const form = new FormData()
  form.append('tenant_id', String(tenantId))
  form.append('file', file)
  return http.post<QcImportBatch>('/qc/conversations/import', form)
}

export const listQcImportBatches = (params: QcImportBatchQuery) =>
  http.get<PageData<QcImportBatch>>(
    '/qc/conversations/import-batches',
    params as Record<string, unknown>,
  )

/** 发起语音转写（仅语音对话可用） */
export const transcribeQcConversation = (id: number) =>
  http.post<QcTranscribeResult>(`/qc/conversations/${id}/transcribe`)