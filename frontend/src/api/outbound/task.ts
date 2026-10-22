import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'

/** 任务号码配置项（提交时使用；task_id 由路径决定） */
export interface OutboundTaskNumberItem {
  number_id: number
  order_id?: number | null
  user_id?: number | null
  recipient_number?: number | null
  sort_order?: number
  priority?: number
  enabled?: boolean
}

/** 任务内的号码配置明细 */
export interface OutboundTaskNumber {
  id: number
  task_id: number
  number_id: number
  order_id: number | null
  user_id: number | null
  recipient_number: number | null
  sort_order: number
  priority: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export type TaskStatus =
  | 'DRAFT'
  | 'READY'
  | 'RUNNING'
  | 'PAUSED'
  | 'COMPLETED'
  | 'CANCELLED'

export type DispatchMode = 'MANUAL' | 'AUTO' | 'PREDICTIVE'

export type NumberSelectStrategy = 'ORDER' | 'ROUND_ROBIN' | 'AVAILABLE_FIRST' | 'CUSTOM'

/** 外呼任务（OB-006 / OB-008） */
export interface OutboundTask {
  id: number
  tenant_id: number
  task_name: string
  site_id: number | null
  skill_queue_id: number | null
  type_id: number | null
  scene_id: number | null
  status: TaskStatus
  dispatch_mode: DispatchMode
  number_select_strategy: NumberSelectStrategy
  retry_interval: number
  max_retry_count: number
  call_timeout_seconds: number
  max_concurrency: number
  adjustment_factor: string
  ivr_flow_id: number | null
  copied_from_id: number | null
  priority: number
  description: string
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface OutboundTaskDetail extends OutboundTask {
  task_numbers: OutboundTaskNumber[]
}

export interface OutboundTaskQuery extends PageQuery {
  tenant_id?: number
  task_name?: string
  site_id?: number
  skill_queue_id?: number
  type_id?: number
  scene_id?: number
  status?: TaskStatus
  dispatch_mode?: DispatchMode
}

export interface OutboundTaskPayload {
  tenant_id?: number
  task_name?: string
  site_id?: number | null
  skill_queue_id?: number | null
  type_id?: number | null
  scene_id?: number | null
  dispatch_mode?: DispatchMode
  number_select_strategy?: NumberSelectStrategy
  retry_interval?: number
  max_retry_count?: number
  call_timeout_seconds?: number
  max_concurrency?: number
  adjustment_factor?: number | string
  ivr_flow_id?: number | null
  description?: string
  priority?: number
  numbers?: OutboundTaskNumberItem[]
}

/** OB-020 复制结果：created=false 表示命中幂等，返回已存在的副本 */
export interface OutboundTaskCopyResult {
  task: OutboundTask
  created: boolean
}

export interface OutboundTaskDeleteResult {
  task_id: number
  removed_task_numbers: number
}

export const listOutboundTasks = (params: OutboundTaskQuery) =>
  http.get<PageData<OutboundTask>>('/outbound/tasks', params as Record<string, unknown>)

export const getOutboundTask = (id: number) =>
  http.get<OutboundTaskDetail>(`/outbound/tasks/${id}`)

export const createOutboundTask = (data: OutboundTaskPayload) =>
  http.post<OutboundTask>('/outbound/tasks', data)

export const updateOutboundTask = (id: number, data: OutboundTaskPayload) =>
  http.put<OutboundTask>(`/outbound/tasks/${id}`, data)

/** 全量替换任务号码配置（§19 多号码配置） */
export const replaceTaskNumbers = (id: number, numbers: OutboundTaskNumberItem[]) =>
  http.put<OutboundTaskNumber[]>(`/outbound/tasks/${id}/numbers`, { numbers })

export const changeOutboundTaskStatus = (id: number, status: TaskStatus) =>
  http.put<OutboundTask>(`/outbound/tasks/${id}/status`, { status })

export const copyOutboundTask = (
  id: number,
  data: { task_name: string; copy_numbers?: boolean },
) => http.post<OutboundTaskCopyResult>(`/outbound/tasks/${id}/copy`, data)

export const deleteOutboundTask = (id: number) =>
  http.delete<OutboundTaskDeleteResult>(`/outbound/tasks/${id}`)
