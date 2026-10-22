import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'

export type RecordStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'CALLING'
  | 'RETRY_WAITING'
  | 'SUCCESS'
  | 'FAILED'
  | 'EXHAUSTED'
  | 'TIMEOUT'

export type CallStatus =
  | 'INITIATED'
  | 'RINGING'
  | 'CONNECTED'
  | 'NO_ANSWER'
  | 'BUSY'
  | 'REJECTED'
  | 'FAILED'
  | 'TIMEOUT'
  | 'HANGUP'

/** 外呼执行记录（§20 / §21 / §22） */
export interface OutboundRecord {
  id: number
  tenant_id: number
  task_id: number
  list_id: number
  agent_id: number | null
  session_id: number | null
  status: RecordStatus
  current_phone: string | null
  current_attempt: number
  retry_count: number
  assigned_at: string | null
  timeout_at: string | null
  last_call_at: string | null
  finished_at: string | null
  failure_reason: string | null
  created_at: string
  updated_at: string
}

export interface OutboundRecordQuery extends PageQuery {
  tenant_id?: number
  task_id?: number
  list_id?: number
  agent_id?: number
  status?: RecordStatus
}

/** 生成待执行记录结果（幂等） */
export interface OutboundBuildRecordsResult {
  task_id: number
  created: number
  skipped: number
}

/** 一次批量执行的统计结果 */
export interface OutboundExecuteSummary {
  task_id: number
  processed: number
  success: number
  retry_waiting: number
  exhausted: number
  failed: number
}

/** 单条记录的即时呼叫结果 */
export interface OutboundRecordCallResult {
  record_id: number
  status: RecordStatus
  session_id: number | null
  current_attempt: number
  retry_count: number
  failure_reason: string | null
}

/** 超时回收结果 */
export interface OutboundRecycleResult {
  scanned: number
  recycled: number
  skipped: number
}

export const listOutboundRecords = (params: OutboundRecordQuery) =>
  http.get<PageData<OutboundRecord>>('/outbound/records', params as Record<string, unknown>)

export const buildTaskRecords = (taskId: number, limit?: number) =>
  http.post<OutboundBuildRecordsResult>(
    `/outbound/tasks/${taskId}/records/build${limit ? `?limit=${limit}` : ''}`,
  )

export const executeTask = (taskId: number, limit?: number) =>
  http.post<OutboundExecuteSummary>(
    `/outbound/tasks/${taskId}/execute${limit ? `?limit=${limit}` : ''}`,
  )

/** 单条即时呼叫（§38 人工外呼） */
export const callRecord = (recordId: number, agentId?: number | null) =>
  http.post<OutboundRecordCallResult>(`/outbound/records/${recordId}/call`, {
    agent_id: agentId ?? null,
  })

/** 触发超时回收（§22，定时任务默认每 30 秒自动执行） */
export const recycleTimeout = (limit = 100) =>
  http.post<OutboundRecycleResult>(`/outbound/timeout/recycle?limit=${limit}`)
