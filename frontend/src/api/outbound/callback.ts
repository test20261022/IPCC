import { http } from '@/api/request'
import type { CommonStatus, PageData, PageQuery } from '@/types/api'

export type CallbackSource = 'IVR' | 'MANUAL'

export type CallbackStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'CALLING'
  | 'SUCCESS'
  | 'FAILED'
  | 'CANCELLED'

export type CallbackTriggerType = 'NO_AGENT' | 'NO_ANSWER' | 'KEY' | 'OUT_OF_HOURS'

/** 回呼流程触发条件（§45，存 trigger_condition JSONB） */
export interface CallbackTriggerCondition {
  triggers?: CallbackTriggerType[]
  keys?: string[]
  business_hours?: string[]
  delay_seconds?: number
  max_attempts?: number
  priority?: number
}

/** 回呼流程（OB-029） */
export interface CallbackFlow {
  id: number
  tenant_id: number
  code: string
  name: string
  trigger_condition: CallbackTriggerCondition | null
  ivr_flow_id: number | null
  status: CommonStatus
  description: string
  created_at: string
  updated_at: string
}

export interface CallbackFlowQuery extends PageQuery {
  tenant_id?: number
  code?: string
  name?: string
  status?: CommonStatus
  ivr_flow_id?: number
}

export interface CallbackFlowPayload {
  tenant_id?: number
  code?: string
  name?: string
  trigger_condition?: CallbackTriggerCondition
  ivr_flow_id?: number | null
  status?: CommonStatus
  description?: string
}

/** 回呼任务（§46） */
export interface CallbackTask {
  id: number
  tenant_id: number
  flow_id: number | null
  source: CallbackSource
  task_id: number | null
  list_id: number | null
  origin_session_id: number | null
  agent_id: number | null
  phone: string
  status: CallbackStatus
  trigger_type: CallbackTriggerType | null
  scheduled_at: string | null
  attempt_count: number
  assigned_at: string | null
  last_call_at: string | null
  finished_at: string | null
  remark: string
  created_at: string
  updated_at: string
}

export interface CallbackTaskQuery extends PageQuery {
  tenant_id?: number
  source?: CallbackSource
  status?: CallbackStatus
  flow_id?: number
  task_id?: number
  list_id?: number
  agent_id?: number
  phone?: string
}

export interface CallbackTaskPayload {
  tenant_id?: number
  source?: CallbackSource
  phone?: string
  flow_id?: number | null
  task_id?: number | null
  list_id?: number | null
  origin_session_id?: number | null
  trigger_type?: CallbackTriggerType | null
  scheduled_at?: string | null
  agent_id?: number | null
  remark?: string
}

/** IVR 触发上下文（OB-029 试算 / 上报） */
export interface CallbackTriggerContextPayload {
  tenant_id: number
  phone: string
  origin_session_id: number
  flow_id?: number | null
  task_id?: number | null
  list_id?: number | null
  keys?: string[]
  no_agent?: boolean
  no_answer?: boolean
  current_time?: string | null
  attempt_count?: number
  remark?: string
}

export interface CallbackTriggerResult {
  created: boolean
  reason: string
  flow_id: number | null
  flow_name: string | null
  trigger_type: CallbackTriggerType | null
  task: CallbackTask | null
}

export interface CallbackAssignResult {
  task_id: number
  agent_id: number
  assigned_at: string | null
  auto_assigned: boolean
}

export interface CallbackDispatchResult {
  scanned: number
  assigned: number
  skipped: number
}

export interface CallbackCallResult {
  task_id: number
  status: CallbackStatus
  attempt_count: number
  call_status: string | null
  failure_reason: string | null
  calling_number: string | null
  history_id: number | null
}

export const listCallbackFlows = (params: CallbackFlowQuery) =>
  http.get<PageData<CallbackFlow>>('/outbound/callback/flows', params as Record<string, unknown>)

export const createCallbackFlow = (data: CallbackFlowPayload) =>
  http.post<CallbackFlow>('/outbound/callback/flows', data)

export const updateCallbackFlow = (id: number, data: CallbackFlowPayload) =>
  http.put<CallbackFlow>(`/outbound/callback/flows/${id}`, data)

export const changeCallbackFlowStatus = (id: number, status: CommonStatus) =>
  http.put<CallbackFlow>(`/outbound/callback/flows/${id}/status`, { status })

export const deleteCallbackFlow = (id: number) =>
  http.delete<{ flow_id: number }>(`/outbound/callback/flows/${id}`)

export const listCallbackTasks = (params: CallbackTaskQuery) =>
  http.get<PageData<CallbackTask>>('/outbound/callback/tasks', params as Record<string, unknown>)

export const createCallbackTask = (data: CallbackTaskPayload) =>
  http.post<CallbackTask>('/outbound/callback/tasks', data)

/** 上报 IVR 会话触发上下文，按 §45 匹配流程并生成回呼任务（§78 幂等） */
export const createCallbackFromIvr = (data: CallbackTriggerContextPayload) =>
  http.post<CallbackTriggerResult>('/outbound/callback/tasks/from-ivr', data)

export const dispatchDueCallbacks = (params?: { tenant_id?: number; limit?: number }) => {
  const search = new URLSearchParams()
  if (params?.tenant_id) search.set('tenant_id', String(params.tenant_id))
  if (params?.limit) search.set('limit', String(params.limit))
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return http.post<CallbackDispatchResult>(`/outbound/callback/tasks/dispatch${suffix}`)
}

export const assignCallbackTask = (taskId: number, agentId?: number | null) =>
  http.post<CallbackAssignResult>(`/outbound/callback/tasks/${taskId}/assign`, {
    agent_id: agentId ?? null,
  })

export const callCallbackTask = (taskId: number) =>
  http.post<CallbackCallResult>(`/outbound/callback/tasks/${taskId}/call`)

export const finishCallbackTask = (taskId: number, success: boolean, remark?: string | null) =>
  http.post<CallbackTask>(`/outbound/callback/tasks/${taskId}/finish`, {
    success,
    remark: remark ?? null,
  })

export const cancelCallbackTask = (taskId: number, reason?: string) =>
  http.post<CallbackTask>(`/outbound/callback/tasks/${taskId}/cancel`, { reason: reason ?? '' })

export const requeueCallbackTask = (taskId: number, reason?: string) =>
  http.post<CallbackTask>(`/outbound/callback/tasks/${taskId}/requeue`, { reason: reason ?? '' })
