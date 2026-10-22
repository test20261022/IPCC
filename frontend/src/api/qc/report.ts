import { http } from '@/api/request'

/** 质检概览报表（GET /qc/reports/overview） */
export interface QcReportOverview {
  /** 任务 ID；为空表示按租户汇总全部任务 */
  task_id: number | null
  /** 明细总数 */
  total: number
  /** 已完成数 */
  completed: number
  /** 待质检数 */
  pending: number
  /** 质检中数 */
  reviewing: number
  /** 完成率，0~1 */
  completion_rate: number
  /** 等级分布：EXCELLENT / PASS / FAIL */
  grade_counts: Record<string, number>
  /** 参与质检的专家数 */
  reviewer_count: number
}

/** 按天分桶的单日完成数据（bucket 形如 YYYY-MM-DD） */
export interface QcDailyCompletionItem {
  bucket: string
  total: number
  excellent: number
  /**
   * 及格数。后端 JSON 字段名为 `pass`（Python 保留字，无法直接作为字段名），
   * 故 TS 侧以 `pass_count` 承载；读取时需兼容 `row.pass`（页面用 passOf 收敛）。
   */
  pass_count: number
  fail: number
}

export interface QcDailyCompletion {
  /** 连续自然日序列（无数据补零） */
  items: QcDailyCompletionItem[]
  date_from: string
  date_to: string
}

export interface QcReportOverviewQuery {
  tenant_id?: number
  task_id?: number
}

export interface QcDailyCompletionQuery {
  date_from: string
  date_to: string
  tenant_id?: number
  task_id?: number
}

export const getQcReportOverview = (params?: QcReportOverviewQuery) =>
  http.get<QcReportOverview>('/qc/reports/overview', params as Record<string, unknown>)

export const getQcDailyCompletion = (params: QcDailyCompletionQuery) =>
  http.get<QcDailyCompletion>(
    '/qc/reports/daily-completion',
    params as unknown as Record<string, unknown>,
  )