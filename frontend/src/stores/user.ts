import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getMeApi, loginApi, logoutApi, type LoginParams, type UserInfo } from '@/api/auth'
import { clearTokens, getAccessToken, setTokens } from '@/api/request'

export const useUserStore = defineStore('user', () => {
  const token = ref(getAccessToken())
  const userInfo = ref<UserInfo | null>(null)

  const permissions = computed(() => new Set(userInfo.value?.permissions ?? []))
  const isSuperuser = computed(() => userInfo.value?.is_superuser === true)
  const displayName = computed(() => userInfo.value?.nickname || userInfo.value?.username || '')

  /** 权限判断：超级管理员直接放行（与后端 require_permission 行为一致） */
  function hasPermission(code?: string): boolean {
    if (!code) return true
    if (isSuperuser.value) return true
    return permissions.value.has(code)
  }

  async function login(params: LoginParams): Promise<void> {
    const { data } = await loginApi(params)
    setTokens(data.access_token, data.refresh_token)
    token.value = data.access_token
  }

  async function loadUserInfo(): Promise<UserInfo> {
    const { data } = await getMeApi()
    userInfo.value = data
    return data
  }

  async function logout(): Promise<void> {
    try {
      await logoutApi()
    } catch {
      // 登出接口失败不阻断本地清理
    } finally {
      reset()
    }
  }

  function reset(): void {
    clearTokens()
    token.value = ''
    userInfo.value = null
  }

  return {
    token,
    userInfo,
    permissions,
    isSuperuser,
    displayName,
    hasPermission,
    login,
    loadUserInfo,
    logout,
    reset,
  }
})
