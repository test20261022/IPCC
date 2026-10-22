import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useMenuStore } from '@/stores/menu'
import { useUserStore } from '@/stores/user'
import { asyncRoutes, constantRoutes } from './routes'

/** 免登录可访问的路径 */
const WHITE_LIST = ['/login', '/404']

export const router = createRouter({
  history: createWebHistory(),
  routes: constantRoutes,
  scrollBehavior: () => ({ top: 0 }),
})

/** 记录动态添加的路由名，登出时用于清理 */
const addedRouteNames: string[] = []

/**
 * 按权限递归过滤路由。
 * 分组路由（有 children）若子路由全部被过滤，则整组剔除，避免出现空菜单。
 */
export function filterRoutesByPermission(
  routes: RouteRecordRaw[],
  hasPermission: (code?: string) => boolean,
): RouteRecordRaw[] {
  const result: RouteRecordRaw[] = []
  for (const route of routes) {
    if (!hasPermission(route.meta?.permission)) continue

    if (!route.children || route.children.length === 0) {
      result.push(route)
      continue
    }

    const children = filterRoutesByPermission(route.children, hasPermission)
    if (children.length === 0) continue
    result.push({ ...route, children })
  }
  return result
}

function addDynamicRoutes(hasPermission: (code?: string) => boolean): RouteRecordRaw[] {
  const accessible = filterRoutesByPermission(asyncRoutes, hasPermission)
  accessible.forEach((route) => {
    router.addRoute(route)
    if (route.name) addedRouteNames.push(String(route.name))
  })
  return accessible
}

/** 登出或切换账号时清理动态路由 */
export function resetDynamicRoutes(): void {
  addedRouteNames.forEach((name) => {
    if (router.hasRoute(name)) router.removeRoute(name)
  })
  addedRouteNames.length = 0
}

router.beforeEach(async (to) => {
  const userStore = useUserStore()
  const menuStore = useMenuStore()

  if (!userStore.token) {
    if (WHITE_LIST.includes(to.path)) return true
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  if (to.path === '/login') return { path: '/' }

  if (!userStore.userInfo) {
    try {
      await userStore.loadUserInfo()
    } catch {
      userStore.reset()
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  if (!menuStore.ready) {
    menuStore.setRoutes(addDynamicRoutes((code) => userStore.hasPermission(code)))
    // 路由刚添加，需按 path 重新匹配一次当前地址。
    // 注意：不能返回 { ...to }，因为首次导航命中的是兜底路由，展开后会带上 name，
    // 而 vue-router 优先按 name 解析，会再次落到兜底路由（表现为页面 404）。
    return { path: to.path, query: to.query, hash: to.hash, replace: true }
  }

  return true
})

export default router
