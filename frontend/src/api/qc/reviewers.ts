import { http } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'

/** 可分配的质检员（专家组候选成员） */
export interface ReviewerUser {
  id: number
  username: string
  nickname: string
  is_active: boolean
}

/** 专家组 */
export interface ReviewerGroup {
  id: number
  tenant_id: number
  name: string
  description: string
  member_count: number
  created_at: string
  updated_at: string
}

/** 专家组成员 */
export interface ReviewerGroupMember {
  user_id: number
  is_active: boolean
  max_concurrent: number
  username: string
  nickname: string
}

/** 专家组详情：组信息 + 成员列表 */
export interface ReviewerGroupDetail extends ReviewerGroup {
  members: ReviewerGroupMember[]
}

export interface ReviewerQuery extends PageQuery {
  tenant_id?: number
  keyword?: string
}

/** 新增专家组入参：可同时指定初始成员 */
export interface ReviewerGroupPayload {
  tenant_id: number
  name: string
  description?: string
  member_user_ids?: number[]
}

/** 编辑专家组入参：仅名称与说明 */
export interface ReviewerGroupUpdatePayload {
  name?: string
  description?: string
}

export interface ReviewerGroupMemberPayload {
  user_id: number
  is_active: boolean
  max_concurrent: number
}

/** 成员全量替换入参：未出现在列表中的成员会被移除 */
export interface ReviewerGroupMembersPayload {
  members: ReviewerGroupMemberPayload[]
}

export const listAssignableReviewers = (params: ReviewerQuery) =>
  http.get<PageData<ReviewerUser>>('/qc/reviewers', params as Record<string, unknown>)

export const listReviewerGroups = (params: ReviewerQuery) =>
  http.get<PageData<ReviewerGroup>>('/qc/reviewer-groups', params as Record<string, unknown>)

export const getReviewerGroup = (id: number) =>
  http.get<ReviewerGroupDetail>(`/qc/reviewer-groups/${id}`)

export const createReviewerGroup = (data: ReviewerGroupPayload) =>
  http.post<ReviewerGroup>('/qc/reviewer-groups', data)

export const updateReviewerGroup = (id: number, data: ReviewerGroupUpdatePayload) =>
  http.put<ReviewerGroup>(`/qc/reviewer-groups/${id}`, data)

export const replaceReviewerGroupMembers = (id: number, data: ReviewerGroupMembersPayload) =>
  http.put<ReviewerGroupDetail>(`/qc/reviewer-groups/${id}/members`, data)