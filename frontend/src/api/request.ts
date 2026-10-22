import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiResponse } from '@/types/api'

const ACCESS_TOKEN_KEY = 'cp_access_token'
const REFRESH_TOKEN_KEY = 'cp_refresh_token'

/**
 * 接口错误。
 *
 * 响应拦截器已经统一弹了 ElMessage，页面里 `await xxx()` 未捕获时不应再产生
 * 控制台噪声，因此这里用独立类型标记，并由 main.ts 的全局处理统一吞掉（§79）。
 */
export class ApiError extends Error {
  /** 业务码（响应体里的 code），无响应体时为 null */
  readonly code: number | null
  /** HTTP 状态码 */
  readonly status: number | null

  constructor(message: string, code: number | null = null, status: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/** 判断是否为「已提示过」的接口错误 */
export function isApiError(reason: unknown): reason is ApiError {
  return reason instanceof ApiError
}

export function getAccessToken(): string {
  return localStorage.getItem(ACCESS_TOKEN_KEY) ?? ''
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

const service: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 15000,
})

service.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let redirecting = false

service.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse | undefined
    // 统一响应体：code !== 0 视为业务失败，交给调用方按需处理
    if (body && typeof body.code === 'number' && body.code !== 0) {
      const message = body.message || '请求失败'
      ElMessage.error(message)
      return Promise.reject(new ApiError(message, body.code, response.status))
    }
    return body as never
  },
  (error) => {
    const status: number | undefined = error?.response?.status
    const url: string = error?.config?.url ?? ''
    const bodyCode: unknown = error?.response?.data?.code
    const message: string =
      error?.response?.data?.message || error?.message || '网络异常，请稍后重试'

    // 登录接口自身返回 401 时属于「账号或密码错误」，不应触发跳转
    const isLoginRequest = url.includes('/auth/login')
    if (status === 401 && !isLoginRequest) {
      clearTokens()
      if (!redirecting) {
        redirecting = true
        ElMessage.error('登录已失效，请重新登录')
        const current = `${window.location.pathname}${window.location.search}`
        window.location.href = `/login?redirect=${encodeURIComponent(current)}`
      }
    } else {
      ElMessage.error(message)
    }
    return Promise.reject(
      new ApiError(message, typeof bodyCode === 'number' ? bodyCode : null, status ?? null),
    )
  },
)

async function request<T>(config: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return (await service.request(config)) as unknown as ApiResponse<T>
}

export const http = {
  get: <T>(url: string, params?: Record<string, unknown>) =>
    request<T>({ url, method: 'get', params }),
  post: <T>(url: string, data?: unknown) => request<T>({ url, method: 'post', data }),
  put: <T>(url: string, data?: unknown) => request<T>({ url, method: 'put', data }),
  delete: <T>(url: string) => request<T>({ url, method: 'delete' }),
}

export default service
