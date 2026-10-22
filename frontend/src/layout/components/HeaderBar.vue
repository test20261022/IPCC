<template>
  <div class="header">
    <el-breadcrumb separator="/">
      <el-breadcrumb-item v-for="(item, index) in breadcrumbs" :key="index">
        {{ item }}
      </el-breadcrumb-item>
    </el-breadcrumb>

    <el-dropdown @command="onCommand">
      <span class="header__user">
        <el-icon><UserFilled /></el-icon>
        <span>{{ userStore.displayName }}</span>
        <el-icon><ArrowDown /></el-icon>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item disabled>
            角色：{{ roleText }}
          </el-dropdown-item>
          <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, UserFilled } from '@element-plus/icons-vue'

import { resetDynamicRoutes } from '@/router'
import { useMenuStore } from '@/stores/menu'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const menuStore = useMenuStore()

const breadcrumbs = computed(() =>
  route.matched
    .filter((item) => item.meta?.title)
    .map((item) => String(item.meta.title)),
)

const roleText = computed(() => {
  if (userStore.isSuperuser) return '超级管理员'
  const codes = userStore.userInfo?.roles.map((role) => role.name) ?? []
  return codes.length ? codes.join('、') : '普通用户'
})

async function onCommand(command: string): Promise<void> {
  if (command !== 'logout') return
  await userStore.logout()
  resetDynamicRoutes()
  menuStore.reset()
  await router.replace('/login')
}
</script>

<style scoped>
.header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header__user {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #303133;
  outline: none;
}
</style>
