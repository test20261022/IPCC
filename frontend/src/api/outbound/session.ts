import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'
import type { CallStatus, RecordStatus } from '@/api/outbound/record'
import type { OutboundList } from '@/api/outbound/list'

export type SessionStatus =
  | 'CREATED'
  | 'ASSIGNED'
  | 'CALLING'
  | 'CONNECTED'
  | 'ENDED'
  | 'TIMEOUT'
  | 'RELEASED'

/** 外呼会话（§37） */
export interface OutboundSession {
  id: number
  tenant_id: number
  task_id: number | null
  list_id: number | null
  agent_id: number | null
  status: SessionStatus
  current_phone: string | null
  current_attempt: number
  started_at: string | null
  finished_at: string | null
  timeout_at: string | null
  end_reason: string | null
  created_at: string
  updated_at: string
}

export interface OutboundSessionQuery extends PageQuery {
  tenant_id?: number
  task_id?: number
  agent_id?: number
  list_id?: number
  status?: SessionStatus
}

/** 拨打历史（§39） */
export interface CallHistory {
  id: number
  tenant_id: number
  session_id: number | null
  record_id: number | null
  task_id: number | null
  list_id: number | null
  agent_id: number | null
  phone: string
  call_status: CallStatus
  failure_reason: string | null
  started_at: string | null
  connected_at: string | null
  ended_at: string | null
  duration: number
  recording_path: string | null
  provider: string | null
  provider_call_id: string | null
  created_at: string
  updated_at: string
}

/** 服务小结（§40） */
export interface ServiceSummary {
  id: number
  tenant_id: number
  session_id: number
  agent_id: number | null
  summary: string
  result: string
  tags: string[] | null
  created_at: string
  updated_at: string
}

export interface ServiceSummaryPayload {
  summary?: string
  result?: string
  tags?: string[]
}

/** 会话详情：会话 + 名单 + 号码 + 拨打历史 + 服务小结 */
export interface OutboundSessionDetail {
  session: OutboundSession
  list_info: OutboundList | null
  task_name: string | null
  phones: string[]
  phone_source: string
  histories: CallHistory[]
  summary: ServiceSummary | null
}

/** 坐席名下待呼名单（OB-021-1） */
export interface OutboundAgentWorklistItem {
  record_id: number
  record_status: RecordStatus
  task_id: number
  task_name: string
  list_id: number
  user_id: string | null
  order_id: string | null
  recipient_name: string | null
  recipient_phone: string | null
  phone_count: number
  phone_source: string
  has_success: boolean
  current_attempt: number
  retry_count: number
  last_failure_reason: string | null
  next_retry_at: string | null
  session_id: number | null
}

/** 名单号码解析与呼叫校验（OB-021） */
export interface OutboundListPhones {
  list_id: number
  task_id: number
  task_name: string | null
  user_id: string | null
  order_id: string | null
  recipient_name: string | null
  recipient_phone: string | null
  phones: string[]
  phone_source: string
  list_phones: string[]
  provider_phones: Record<string, string[]>
  record_id: number | null
  record_status: RecordStatus | null
  has_success: boolean
  success_phone: string | null
  current_attempt: number
  retry_count: number
  max_retry_count: number | null
  retry_interval: number | null
  last_failure_reason: string | null
  next_retry_at: string | null
}

/** OB-023 外呼任务看板 */
export interface OutboundBoard {
  list_info: OutboundList
  phones: string[]
  phone_source: string
  histories: CallHistory[]
  sessions: OutboundSession[]
  summaries: ServiceSummary[]
  external_info: Record<string, unknown>
}

export const listOutboundSessions = (params: OutboundSessionQuery) =>
  http.get<PageData<OutboundSession>>('/outbound/sessions', params as Record<string, unknown>)

export const getSessionDetail = (id: number) =>
  http.get<OutboundSessionDetail>(`/outbound/sessions/${id}`)

export const getSessionSummary = (id: number) =>
  http.get<ServiceSummary | null>(`/outbound/sessions/${id}/summary`)

export const submitSessionSummary = (id: number, data: ServiceSummaryPayload) =>
  http.post<ServiceSummary>(`/outbound/sessions/${id}/summary`, data)

export const updateSessionSummary = (id: number, data: ServiceSummaryPayload) =>
  http.put<ServiceSummary>(`/outbound/sessions/${id}/summary`, data)

export const getAgentWorklist = (
  agentId: number,
  params?: { page?: number; page_size?: number; include_finished?: boolean },
) =>
  http.get<PageData<OutboundAgentWorklistItem>>(
    `/outbound/agents/${agentId}/worklist`,
    params as Record<string, unknown>,
  )

export const resolveListPhones = (listId: number) =>
  http.get<OutboundListPhones>(`/outbound/lists/${listId}/phones`)

export const listListHistories = (listId: number) =>
  http.get<CallHistory[]>(`/outbound/lists/${listId}/histories`)

export const getListBoard = (listId: number) =>
  http.get<OutboundBoard>(`/outbound/lists/${listId}/board`)
