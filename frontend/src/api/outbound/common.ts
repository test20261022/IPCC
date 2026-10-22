import { http } from '@/api/request'

/** 通用下拉选项 */

export interface TenantOption {
  id: number
  code: string
  name: string
}

export interface SiteOption {
  id: number
  tenant_id: number
  code: string
  name: string
}

export interface SkillQueueOption {
  id: number
  tenant_id: number
  site_id: number
  code: string
  name: string
}

export interface AgentOption {
  id: number
  user_id: number
  tenant_id: number
  site_id: number | null
  skill_queue_id: number | null
  extension: string | null
  status: string
}

export interface UserOption {
  id: number
  username: string
  nickname: string
  tenant_id: number | null
}

/** 任务下拉选项：报表 / 坐席 / 回呼等页面只需任务名，无需 outbound:task:list 权限 */
export interface TaskOption {
  id: number
  tenant_id: number
  task_name: string
}

export const listTenantOptions = () => http.get<TenantOption[]>('/outbound/options/tenants')

export const listSiteOptions = (params?: { tenant_id?: number }) =>
  http.get<SiteOption[]>('/outbound/options/sites', params as Record<string, unknown>)

export const listSkillQueueOptions = (params?: { tenant_id?: number; site_id?: number }) =>
  http.get<SkillQueueOption[]>('/outbound/options/skill-queues', params as Record<string, unknown>)

export const listAgentOptions = (params?: { tenant_id?: number; skill_queue_id?: number }) =>
  http.get<AgentOption[]>('/outbound/options/agents', params as Record<string, unknown>)

export const listUserOptions = () => http.get<UserOption[]>('/outbound/options/users')

export const listTaskOptions = (tenantId: number) =>
  http.get<TaskOption[]>('/outbound/options/tasks', { tenant_id: tenantId })
