import { http } from '@/api/request'
import type { PageQuery } from '@/types/api'

/** 话务流水一行（OB-025） */
export interface CallFlowRecord {
  id: number
  started_at: string | null
  phone: string
  source: 'OUTBOUND' | 'CALLBACK'
  task_id: number | null
  task_name: string | null
  scene_id: number | null
  scene_name: string | null
  type_id: number | null
  type_name: string | null
  type_level: number | null
  agent_id: number | null
  agent_extension: string | null
  list_id: number | null
  user_id: string | null
  order_id: string | null
  session_id: number | null
  callback_task_id: number | null
  call_status: string
  failure_reason: string | null
  connected_at: string | null
  ended_at: string | null
  duration: number
  recording_path: string | null
}

export interface CallFlowSummary {
  total: number
  connected: number
  connect_rate: number
  total_duration: number
  avg_duration: number
  status_counts: Record<string, number>
}

export interface CallFlowReport {
  summary: CallFlowSummary
  items: CallFlowRecord[]
  total: number
  page: number
  page_size: number
}

export interface CallFlowQuery extends PageQuery {
  tenant_id?: number
  started_from?: string
  started_to?: string
  scene_id?: number
  task_id?: number
  type_id?: number
  sub_type_id?: number
  site_id?: number
  skill_queue_id?: number
  agent_id?: number
  call_status?: string
  source?: 'ALL' | 'OUTBOUND' | 'CALLBACK'
  phone?: string
}

/** 实时监控（OB-028） */
export interface MonitorCallStats {
  initiated: number
  connected: number
  connect_rate: number
  total_duration: number
  avg_duration: number
}

export interface MonitorTrendPoint {
  bucket: string
  initiated: number
  connected: number
}

export interface MonitorTopTask {
  task_id: number
  task_name: string | null
  initiated: number
  connected: number
  connect_rate: number
}

export interface RealtimeMonitor {
  tenant_id: number
  generated_at: string
  window_minutes: number
  calls: MonitorCallStats
  agent_status: Record<string, number>
  task_status: Record<string, number>
  record_status: Record<string, number>
  callback_status: Record<string, number>
  active_sessions: number
  trend: MonitorTrendPoint[]
  top_tasks: MonitorTopTask[]
}

export const getCallFlowReport = (params: CallFlowQuery) =>
  http.get<CallFlowReport>('/outbound/reports/call-flow', params as Record<string, unknown>)

export const getRealtimeMonitor = (params: { tenant_id: number; window_minutes?: number }) =>
  http.get<RealtimeMonitor>('/outbound/reports/monitor', params as Record<string, unknown>)
