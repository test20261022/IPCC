import { http } from '@/api/request'
import type { CommonStatus, PageData, PageQuery } from '@/types/api'

/** 外呼号码（OB-001 / OB-005） */
export interface OutboundNumber {
  id: number
  tenant_id: number
  display_name: string
  caller_number: string
  number_type: string
  usage_limit: number | null
  used_count: number
  status: CommonStatus
  remark: string
  created_at: string
  updated_at: string
}

export interface OutboundNumberQuery extends PageQuery {
  tenant_id?: number
  caller_number?: string
  display_name?: string
  status?: CommonStatus
}

export interface OutboundNumberPayload {
  tenant_id?: number
  display_name?: string
  caller_number?: string
  number_type?: string
  usage_limit?: number | null
  status?: CommonStatus
  remark?: string
}

export const listOutboundNumbers = (params: OutboundNumberQuery) =>
  http.get<PageData<OutboundNumber>>('/outbound/numbers', params as Record<string, unknown>)

export const createOutboundNumber = (data: OutboundNumberPayload) =>
  http.post<OutboundNumber>('/outbound/numbers', data)

export const updateOutboundNumber = (id: number, data: OutboundNumberPayload) =>
  http.put<OutboundNumber>(`/outbound/numbers/${id}`, data)

export const changeOutboundNumberStatus = (id: number, status: CommonStatus) =>
  http.put<OutboundNumber>(`/outbound/numbers/${id}/status`, { status })

export const deleteOutboundNumber = (id: number) =>
  http.delete<null>(`/outbound/numbers/${id}`)

/** 扣减主叫号码使用次数（§13 原子扣减） */
export const consumeOutboundNumber = (id: number, step = 1) =>
  http.post<OutboundNumber>(`/outbound/numbers/${id}/consume?step=${step}`)
