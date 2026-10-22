import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'

/** 优秀案例（对话质检-案例库） */
export interface QcCase {
  id: number
  tenant_id: number
  conversation_id: number
  item_id: number | null
  title: string
  reason: string
  tags: string[] | null
  is_published: boolean
  published_at: string | null
  created_by: number | null
  created_at: string
  updated_at: string
}

export interface QcCaseQuery extends PageQuery {
  tenant_id?: number
  is_published?: boolean
  tag?: string
  keyword?: string
}

export interface QcCaseCreatePayload {
  tenant_id: number
  conversation_id: number
  item_id?: number
  title: string
  reason: string
  tags?: string[]
}

export interface QcCaseUpdatePayload {
  item_id?: number
  title?: string
  reason?: string
  tags?: string[]
}

export const listQcCases = (params: QcCaseQuery) =>
  http.get<PageData<QcCase>>('/qc/cases', params as Record<string, unknown>)

export const getQcCase = (id: number) => http.get<QcCase>(`/qc/cases/${id}`)

export const createQcCase = (payload: QcCaseCreatePayload) =>
  http.post<QcCase>('/qc/cases', payload)

export const updateQcCase = (id: number, payload: QcCaseUpdatePayload) =>
  http.put<QcCase>(`/qc/cases/${id}`, payload)

export const deleteQcCase = (id: number) => http.delete<null>(`/qc/cases/${id}`)

export const publishQcCase = (id: number) => http.post<QcCase>(`/qc/cases/${id}/publish`)