import { http } from '@/api/request'
import type { CommonStatus, PageData, PageQuery } from '@/types/api'

/** 外呼类型（OB-004） */
export interface OutboundType {
  id: number
  tenant_id: number
  parent_id: number | null
  code: string
  name: string
  level: number
  sort_order: number
  status: CommonStatus
  description: string
  created_at: string
  updated_at: string
}

export interface OutboundTypeQuery extends PageQuery {
  tenant_id?: number
  name?: string
  code?: string
  parent_id?: number
  level?: number
  status?: CommonStatus
}

export interface OutboundTypePayload {
  tenant_id?: number
  parent_id?: number | null
  code?: string
  name?: string
  level?: number
  sort_order?: number
  status?: CommonStatus
  description?: string
}

export const listOutboundTypes = (params: OutboundTypeQuery) =>
  http.get<PageData<OutboundType>>('/outbound/types', params as Record<string, unknown>)

export const createOutboundType = (data: OutboundTypePayload) =>
  http.post<OutboundType>('/outbound/types', data)

export const updateOutboundType = (id: number, data: OutboundTypePayload) =>
  http.put<OutboundType>(`/outbound/types/${id}`, data)

export const changeOutboundTypeStatus = (id: number, status: CommonStatus) =>
  http.put<OutboundType>(`/outbound/types/${id}/status`, { status })

export const deleteOutboundType = (id: number) => http.delete<null>(`/outbound/types/${id}`)
