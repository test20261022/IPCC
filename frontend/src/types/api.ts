/** 后端统一响应结构（与 app/core/response.py 对应） */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页数据结构 */
export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** 分页查询参数 */
export interface PageQuery {
  page?: number
  page_size?: number
}

/** 启用 / 停用通用状态 */
export type CommonStatus = 'ENABLED' | 'DISABLED'
