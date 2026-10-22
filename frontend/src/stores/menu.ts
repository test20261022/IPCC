import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { RouteRecordRaw } from 'vue-router'

/** 当前登录用户可见的菜单路由（由权限过滤后写入，供侧边栏渲染） */
export const useMenuStore = defineStore('menu', () => {
  const routes = ref<RouteRecordRaw[]>([])
  const ready = ref(false)

  function setRoutes(value: RouteRecordRaw[]): void {
    routes.value = value
    ready.value = true
  }

  function reset(): void {
    routes.value = []
    ready.value = false
  }

  return { routes, ready, setRoutes, reset }
})
