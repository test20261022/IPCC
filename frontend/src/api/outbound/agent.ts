import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'

export type AgentStatus = 'OFFLINE' | 'IDLE' | 'BUSY' | 'RESERVED' | 'PAUSED'

export type AssignmentStatus = 'RESERVED' | 'ACCEPTED' | 'RELEASED' | 'EXPIRED'

/** 坐席（§11） */
export interface OutboundAgent {
  id: number
  user_id: number
  tenant_id: number
  site_id: number | null
  skill_queue_id: number | null
  status: AgentStatus
  extension: string | null
  last_idle_at: string | null
  last_busy_at: string | null
  created_at: string
  updated_at: string
}

export interface OutboundAgentQuery extends PageQuery {
  tenant_id?: number
  site_id?: number
  skill_queue_id?: number
  status?: AgentStatus
}

/** 坐席状态变更历史（§11 留痕） */
export interface AgentStatusLog {
  id: number
  agent_id: number
  from_status: AgentStatus | null
  to_status: AgentStatus
  reason: string
  operator_id: number | null
  created_at: string
  updated_at: string
}

/** 派单结果明细（示闲触发自动分配时返回） */
export interface AgentDispatchItem {
  agent_id: number
  task_id: number
  record_id: number
  assignment_id: number
  expires_at: string | null
}

export interface AgentStatusChangeResult {
  agent_id: number
  from_status: AgentStatus
  to_status: AgentStatus
  assignment: AgentDispatchItem | null
}

/** 坐席预占 / 派单（§35） */
export interface AgentAssignment {
  id: number
  tenant_id: number
  agent_id: number
  task_id: number | null
  record_id: number | null
  status: AssignmentStatus
  reserved_at: string | null
  expires_at: string | null
  released_at: string | null
  release_reason: string | null
  created_at: string
  updated_at: string
}

export interface AgentAssignmentQuery extends PageQuery {
  tenant_id?: number
  agent_id?: number
  task_id?: number
  status?: AssignmentStatus
}

export interface AgentDispatchResult {
  agents_scanned: number
  assigned: number
  skipped: number
}

export interface AgentReservationExpireResult {
  scanned: number
  released: number
  skipped: number
}

/** 预测外呼并发建议（§36） */
export interface OutboundPrediction {
  task_id: number
  dispatch_mode: string
  available_agents: number
  answer_rate: number
  adjustment_factor: number
  max_concurrency: number
  target_concurrency: number
  uncapped_target: number
}

export const listOutboundAgents = (params: OutboundAgentQuery) =>
  http.get<PageData<OutboundAgent>>('/outbound/agents', params as Record<string, unknown>)

export const getOutboundAgent = (id: number) =>
  http.get<OutboundAgent>(`/outbound/agents/${id}`)

/** 新增坐席（规则 8）：必须关联既有 users 账号，一个用户最多一个坐席 */
export const createOutboundAgent = (data: {
  user_id: number
  tenant_id: number
  site_id?: number | null
  skill_queue_id?: number | null
  extension?: string | null
}) => http.post<OutboundAgent>('/outbound/agents', data)

export const updateOutboundAgent = (
  id: number,
  data: {
    site_id?: number | null
    skill_queue_id?: number | null
    extension?: string | null
  },
) => http.put<OutboundAgent>(`/outbound/agents/${id}`, data)

export const deleteOutboundAgent = (id: number) =>
  http.delete<null>(`/outbound/agents/${id}`)

export const listAgentStatusLogs = (id: number, limit = 50) =>
  http.get<AgentStatusLog[]>(`/outbound/agents/${id}/status-logs?limit=${limit}`)

/** 变更坐席状态；置为 IDLE 时立即触发自动分配（§34） */
export const changeAgentStatus = (
  id: number,
  status: AgentStatus,
  options?: { reason?: string; auto_assign?: boolean },
) =>
  http.put<AgentStatusChangeResult>(
    `/outbound/agents/${id}/status?auto_assign=${options?.auto_assign ?? true}`,
    { status, reason: options?.reason ?? '' },
  )

export const listAssignments = (params: AgentAssignmentQuery) =>
  http.get<PageData<AgentAssignment>>(
    '/outbound/assignments',
    params as Record<string, unknown>,
  )

export const dispatchAssignments = (params?: { tenant_id?: number; limit?: number }) => {
  const search = new URLSearchParams()
  if (params?.tenant_id) search.set('tenant_id', String(params.tenant_id))
  if (params?.limit) search.set('limit', String(params.limit))
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return http.post<AgentDispatchResult>(`/outbound/assignments/dispatch${suffix}`)
}

export const expireAssignments = (limit = 100) =>
  http.post<AgentReservationExpireResult>(`/outbound/assignments/expire?limit=${limit}`)

export const acceptAssignment = (id: number) =>
  http.post<Record<string, unknown>>(`/outbound/assignments/${id}/accept`)

export const releaseAssignment = (id: number, reason = '') =>
  http.post<Record<string, unknown>>(`/outbound/assignments/${id}/release`, { reason })

export const getTaskPrediction = (taskId: number) =>
  http.get<OutboundPrediction>(`/outbound/tasks/${taskId}/prediction`)
