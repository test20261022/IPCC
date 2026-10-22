import { http } from '@/api/request'
import type { CommonStatus, PageData, PageQuery } from '@/types/api'

/** 外呼场景（OB-003） */
export interface OutboundScene {
  id: number
  tenant_id: number
  type_id: number
  parent_id: number | null
  level: number
  name: string
  sort_order: number
  status: CommonStatus
  description: string
  created_at: string
  updated_at: string
}

/** 两级场景树节点 */
export interface OutboundSceneTree extends OutboundScene {
  children: OutboundSceneTree[]
}

export interface OutboundSceneQuery extends PageQuery {
  tenant_id?: number
  type_id?: number
  parent_id?: number
  name?: string
  level?: number
  status?: CommonStatus
}

export interface OutboundScenePayload {
  tenant_id?: number
  type_id?: number
  parent_id?: number | null
  level?: number
  name?: string
  sort_order?: number
  status?: CommonStatus
  description?: string
}

/** 批量删除结果 */
export interface BatchDeleteResult {
  requested: number
  deleted: number
}

export const listOutboundScenes = (params: OutboundSceneQuery) =>
  http.get<PageData<OutboundScene>>('/outbound/scenes', params as Record<string, unknown>)

export const getOutboundSceneTree = (params?: {
  tenant_id?: number
  type_id?: number
  status?: CommonStatus
}) => http.get<OutboundSceneTree[]>('/outbound/scenes/tree', params as Record<string, unknown>)

export const createOutboundScene = (data: OutboundScenePayload) =>
  http.post<OutboundScene>('/outbound/scenes', data)

export const updateOutboundScene = (id: number, data: OutboundScenePayload) =>
  http.put<OutboundScene>(`/outbound/scenes/${id}`, data)

export const changeOutboundSceneStatus = (id: number, status: CommonStatus) =>
  http.put<OutboundScene>(`/outbound/scenes/${id}/status`, { status })

export const deleteOutboundScene = (id: number) =>
  http.delete<BatchDeleteResult>(`/outbound/scenes/${id}`)

export const batchDeleteOutboundScenes = (sceneIds: number[]) =>
  http.post<BatchDeleteResult>('/outbound/scenes/batch-delete', { scene_ids: sceneIds })
