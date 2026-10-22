import { http } from '@/api/request'

export interface LoginParams {
  username: string
  password: string
}

export interface TokenResult {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface RoleBrief {
  id: number
  code: string
  name: string
}

export interface UserInfo {
  id: number
  username: string
  nickname: string
  email: string | null
  phone: string | null
  is_active: boolean
  is_superuser: boolean
  last_login_at: string | null
  roles: RoleBrief[]
  permissions: string[]
}

export const loginApi = (data: LoginParams) => http.post<TokenResult>('/auth/login', data)

export const logoutApi = () => http.post<null>('/auth/logout', {})

export const getMeApi = () => http.get<UserInfo>('/auth/me')
