import { http } from '@/api/request'
import type { CommonStatus, PageData, PageQuery } from '@/types/api'

export type IvrNodeType =
  | 'PLAY'
  | 'COLLECT_DTMF'
  | 'TRANSFER_AGENT'
  | 'HANGUP'
  | 'CALLBACK'
  | 'REPLAY'

export type IvrConditionType = 'KEY' | 'ASR_RESULT' | 'TIME_RANGE' | 'QUEUE_AVAILABLE'

export type NoAgentAction = 'QUEUE' | 'CALLBACK' | 'REPLAY' | 'HANGUP'

/** IVR 流程（OB-017） */
export interface IvrFlow {
  id: number
  tenant_id: number
  code: string
  name: string
  entry_node_key: string | null
  status: CommonStatus
  description: string
  created_at: string
  updated_at: string
}

/** IVR 节点（§31） */
export interface IvrNode {
  id: number
  flow_id: number
  tenant_id: number
  node_key: string
  name: string
  node_type: IvrNodeType
  content: string
  config: Record<string, unknown> | null
  max_replay: number
  no_agent_action: NoAgentAction | null
  sort_order: number
  created_at: string
  updated_at: string
}

/** IVR 流转条件（§31） */
export interface IvrTransition {
  id: number
  flow_id: number
  tenant_id: number
  from_node_id: number
  to_node_id: number | null
  condition_type: IvrConditionType
  condition_value: string | null
  priority: number
  created_at: string
  updated_at: string
}

/** 流程详情：一次拉全节点与流转 */
export interface IvrFlowDetail extends IvrFlow {
  nodes: IvrNode[]
  transitions: IvrTransition[]
}

export interface IvrFlowQuery extends PageQuery {
  tenant_id?: number
  code?: string
  name?: string
  status?: CommonStatus
}

export interface IvrFlowPayload {
  tenant_id?: number
  code?: string
  name?: string
  entry_node_key?: string | null
  status?: CommonStatus
  description?: string
}

export interface IvrNodePayload {
  tenant_id?: number
  node_key?: string
  name?: string
  node_type?: IvrNodeType
  content?: string
  config?: Record<string, unknown>
  max_replay?: number
  no_agent_action?: NoAgentAction | null
  sort_order?: number
}

export interface IvrTransitionPayload {
  tenant_id?: number
  from_node_id?: number
  to_node_id?: number | null
  condition_type?: IvrConditionType
  condition_value?: string | null
  priority?: number
}

export interface IvrFlowDeleteResult {
  flow_id: number
  removed_nodes: number
  removed_transitions: number
}

export interface IvrNodeDeleteResult {
  node_id: number
  removed_transitions: number
}

/** 结构校验问题 */
export interface IvrValidationIssue {
  level: 'ERROR' | 'WARNING'
  code: string
  target: string
  message: string
}

export interface IvrValidationResult {
  valid: boolean
  issues: IvrValidationIssue[]
  error_count: number
  warning_count: number
  node_count: number
  transition_count: number
}

/** 模拟输入：DTMF 按键或 ASR 识别结果 */
export interface IvrSimulationInput {
  input_type: 'KEY' | 'ASR'
  value: string
}

export interface IvrSimulationRequest {
  inputs?: IvrSimulationInput[]
  current_time?: string | null
  queue_available?: boolean | null
  skill_queue_id?: number | null
  max_steps?: number | null
}

export interface IvrSimulationStep {
  index: number
  node_key: string
  node_name: string
  node_type: string
  action: string
  detail: string
  from_node_key: string | null
  to_node_key: string | null
  condition_type: string | null
  condition_value: string | null
  replay_count: number
}

export interface IvrSimulationResult {
  flow_id: number
  flow_name: string
  entry_node_key: string | null
  final_node_key: string | null
  ended: boolean
  transferred: boolean
  no_agent_action: string | null
  collected_keys: string[]
  replay_count: number
  end_reason: string
  queue_available: boolean | null
  steps: IvrSimulationStep[]
}

/** IVR 流程下拉选项（任务表单使用） */
export interface IvrFlowOption {
  id: number
  tenant_id: number
  code: string
  name: string
  entry_node_key: string | null
}

export const listIvrFlows = (params: IvrFlowQuery) =>
  http.get<PageData<IvrFlow>>('/outbound/ivr/flows', params as Record<string, unknown>)

export const getIvrFlow = (id: number) =>
  http.get<IvrFlowDetail>(`/outbound/ivr/flows/${id}`)

export const createIvrFlow = (data: IvrFlowPayload) =>
  http.post<IvrFlow>('/outbound/ivr/flows', data)

export const updateIvrFlow = (id: number, data: IvrFlowPayload) =>
  http.put<IvrFlow>(`/outbound/ivr/flows/${id}`, data)

export const changeIvrFlowStatus = (id: number, status: CommonStatus) =>
  http.put<IvrFlow>(`/outbound/ivr/flows/${id}/status`, { status })

export const deleteIvrFlow = (id: number) =>
  http.delete<IvrFlowDeleteResult>(`/outbound/ivr/flows/${id}`)

/** 结构校验（OB-017） */
export const validateIvrFlow = (id: number) =>
  http.get<IvrValidationResult>(`/outbound/ivr/flows/${id}/validate`)

/** 模拟运行（OB-017） */
export const simulateIvrFlow = (id: number, data: IvrSimulationRequest) =>
  http.post<IvrSimulationResult>(`/outbound/ivr/flows/${id}/simulate`, data)

export const createIvrNode = (flowId: number, data: IvrNodePayload) =>
  http.post<IvrNode>(`/outbound/ivr/flows/${flowId}/nodes`, data)

export const updateIvrNode = (nodeId: number, data: IvrNodePayload) =>
  http.put<IvrNode>(`/outbound/ivr/nodes/${nodeId}`, data)

export const deleteIvrNode = (nodeId: number) =>
  http.delete<IvrNodeDeleteResult>(`/outbound/ivr/nodes/${nodeId}`)

export const createIvrTransition = (flowId: number, data: IvrTransitionPayload) =>
  http.post<IvrTransition>(`/outbound/ivr/flows/${flowId}/transitions`, data)

export const updateIvrTransition = (id: number, data: IvrTransitionPayload) =>
  http.put<IvrTransition>(`/outbound/ivr/transitions/${id}`, data)

export const deleteIvrTransition = (id: number) =>
  http.delete<null>(`/outbound/ivr/transitions/${id}`)

export const listIvrFlowOptions = (tenantId: number) =>
  http.get<IvrFlowOption[]>('/outbound/options/ivr-flows', { tenant_id: tenantId })
