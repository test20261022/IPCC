import type { Directive, DirectiveBinding } from 'vue'

import { useUserStore } from '@/stores/user'

/**
 * 按钮级权限指令：`v-permission="'outbound:type:create'"` 或 `v-permission="['a', 'b']"`（任一满足即可）。
 * 注意：前端权限只用于隐藏入口，真正的鉴权始终以后端为准（§63）。
 */
function checkAndRemove(el: HTMLElement, binding: DirectiveBinding<string | string[]>): void {
  const userStore = useUserStore()
  const value = binding.value
  if (!value) return

  const codes = Array.isArray(value) ? value : [value]
  const allowed = codes.some((code) => userStore.hasPermission(code))
  if (!allowed) {
    el.parentNode?.removeChild(el)
  }
}

export const permission: Directive<HTMLElement, string | string[]> = {
  mounted: checkAndRemove,
}
