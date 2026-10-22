import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'
import type { QcReportOverview } from '@/api/qc/report'

/** 质检任务状态（QcTaskStatus） */
export type QcTaskStatus = 'DRAFT' | 'DISPATCHED' | 'REVIEWING' | 'COMPLETED' | 'CANCELLED'

/** 派发分片方式（QcDispatchMode） */
export type QcDispatchMode = 'ROUND_ROBIN' | 'AVERAGE'

/** 质检明细状态（QcItemStatus） */
export type QcItemStatus = 'PENDING' | 'REVIEWING' | 'COMPLETED' | 'TIMEOUT'

/** 质检等级（QcGrade） */
export type QcGrade = 'EXCELLENT' | 'PASS' | 'FAIL'

/** 质检任务 */
export interface QcTask {
  id: number
  tenant_id: number
  task_name: string
  group_id: number | null
  time_from: string
  time_to: string
  status: QcTaskStatus
  dispatch_mode: QcDispatchMode
  total_items: number
  completed_items: number
  dispatched_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

/** 质检任务详情：附带完成率 */
export interface QcTaskDetail extends QcTask {
  completion_rate: number
}

/** 质检明细 */
export interface QcTaskItem {
  id: number
  tenant_id: number
  task_id: number
  conversation_id: number
  reviewer_id: number | null
  status: QcItemStatus
  grade: QcGrade | null
  locked_at: string | null
  timeout_at: string | null
  submitted_at: string | null
  created_at: string
  updated_at: string
}

export interface QcTaskQuery extends PageQuery {
  tenant_id?: number
  status?: QcTaskStatus
  keyword?: string
}

/** 新增质检任务入参 */
export interface QcTaskPayload {
  tenant_id: number
  task_name: string
  group_id: number
  time_from: string
  time_to: string
  dispatch_mode: QcDispatchMode
}

/** 编辑质检任务入参：只更新显式传入的字段 */
export interface QcTaskUpdatePayload {
  task_name?: string
  group_id?: number
  time_from?: string
  time_to?: string
  dispatch_mode?: QcDispatchMode
}

export interface QcTaskDeleteResult {
  task_id: number
  removed_items: number
}

export interface QcTaskDispatchResult {
  task_id: number
  total_items: number
  dispatched_at: string | null
  reviewer_count: number
}

export interface QcTaskItemQuery extends PageQuery {
  status?: QcItemStatus
  reviewer_id?: number
  grade?: QcGrade
}

export const listQcTasks = (params: QcTaskQuery) =>
  http.get<PageData<QcTask>>('/qc/tasks', params as Record<string, unknown>)

export const getQcTask = (id: number) => http.get<QcTaskDetail>(`/qc/tasks/${id}`)

export const createQcTask = (data: QcTaskPayload) => http.post<QcTask>('/qc/tasks', data)

export const updateQcTask = (id: number, data: QcTaskUpdatePayload) =>
  http.put<QcTask>(`/qc/tasks/${id}`, data)

export const deleteQcTask = (id: number) =>
  http.delete<QcTaskDeleteResult>(`/qc/tasks/${id}`)

export const dispatchQcTask = (id: number) =>
  http.post<QcTaskDispatchResult>(`/qc/tasks/${id}/dispatch`)

export const cancelQcTask = (id: number) => http.post<QcTask>(`/qc/tasks/${id}/cancel`)

export const listQcTaskItems = (id: number, params: QcTaskItemQuery) =>
  http.get<PageData<QcTaskItem>>(`/qc/tasks/${id}/items`, params as Record<string, unknown>)

export const getQcTaskReport = (id: number) =>
  http.get<QcReportOverview>(`/qc/tasks/${id}/report`)