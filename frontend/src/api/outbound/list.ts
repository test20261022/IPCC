import { http, default as service } from '@/api/request'
import type { PageData, PageQuery } from '@/types/api'

export type ListStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'SUCCESS'
  | 'FAILED'
  | 'EXHAUSTED'
  | 'CANCELLED'

export type ImportBatchStatus =
  | 'PENDING'
  | 'PARSING'
  | 'VALIDATING'
  | 'IMPORTING'
  | 'SUCCESS'
  | 'PARTIAL_FAILED'
  | 'FAILED'

/** 外呼名单行（OB-011 / OB-012） */
export interface OutboundList {
  id: number
  tenant_id: number
  task_id: number
  import_batch_id: number | null
  user_id: string | null
  order_id: string | null
  recipient_name: string | null
  recipient_phone: string | null
  phone_numbers: string[] | null
  dynamic_fields: Record<string, unknown> | null
  status: ListStatus
  priority: number
  attempt_count: number
  last_call_at: string | null
  remark: string
  created_at: string
  updated_at: string
}

export interface OutboundListQuery extends PageQuery {
  tenant_id?: number
  task_id?: number
  user_id?: string
  order_id?: string
  import_batch_id?: number
  status?: ListStatus
}

/** 导入失败明细单行（§25） */
export interface OutboundImportFailure {
  row: number
  field: string
  reason: string
  raw: string | null
}

/** 导入结果 */
export interface OutboundImportResult {
  batch_id: number
  total_rows: number
  success_rows: number
  failed_rows: number
  failures: OutboundImportFailure[]
}

/** 导入批次 */
export interface OutboundImportBatch {
  id: number
  tenant_id: number
  task_id: number
  file_name: string
  file_size: number
  total_rows: number
  success_rows: number
  failed_rows: number
  status: ImportBatchStatus
  error_message: string | null
  imported_by: number | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface OutboundImportBatchDetail extends OutboundImportBatch {
  failures: OutboundImportFailure[]
}

export interface OutboundImportBatchQuery extends PageQuery {
  tenant_id?: number
  task_id?: number
  status?: ImportBatchStatus
}

/** 全场景变量（OB-012） */
export interface OutboundVariableResult {
  variables: Record<string, unknown>
}

export const importOutboundList = (taskId: number, file: File) => {
  const form = new FormData()
  form.append('task_id', String(taskId))
  form.append('file', file)
  return http.post<OutboundImportResult>('/outbound/lists/import', form)
}

export const listOutboundLists = (params: OutboundListQuery) =>
  http.get<PageData<OutboundList>>('/outbound/lists', params as Record<string, unknown>)

export const getOutboundList = (id: number) =>
  http.get<OutboundList>(`/outbound/lists/${id}`)

export const getListVariables = (id: number) =>
  http.get<OutboundVariableResult>(`/outbound/lists/${id}/variables`)

export const listImportBatches = (params: OutboundImportBatchQuery) =>
  http.get<PageData<OutboundImportBatch>>(
    '/outbound/import-batches',
    params as Record<string, unknown>,
  )

export const getImportBatch = (id: number) =>
  http.get<OutboundImportBatchDetail>(`/outbound/import-batches/${id}`)

/** 下载失败明细 CSV（带 BOM，Excel 打开不乱码） */
export async function downloadImportFailures(batchId: number): Promise<Blob> {
  return (await service.get(`/outbound/import-batches/${batchId}/failures/download`, {
    responseType: 'blob',
  })) as unknown as Blob
}
