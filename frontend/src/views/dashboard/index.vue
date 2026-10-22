<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <span>当前登录用户</span>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="用户名">{{ user?.username }}</el-descriptions-item>
        <el-descriptions-item label="昵称">{{ user?.nickname || '-' }}</el-descriptions-item>
        <el-descriptions-item label="账号类型">
          {{ user?.is_superuser ? '超级管理员' : '普通用户' }}
        </el-descriptions-item>
        <el-descriptions-item label="角色">
          {{ roleText }}
        </el-descriptions-item>
        <el-descriptions-item label="权限数">{{ user?.permissions.length ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="最近登录">{{ lastLoginText }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span>模块进度</span>
      </template>
      <el-table :data="modules" border stripe>
        <el-table-column prop="name" label="模块" min-width="160" />
        <el-table-column prop="requirement" label="需求编号" width="200" />
        <el-table-column label="后端" width="100">
          <template #default="{ row }">
            <el-tag :type="row.backend ? 'success' : 'info'" disable-transitions>
              {{ row.backend ? '已完成' : '未开始' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="前端" width="120">
          <template #default="{ row }">
            <el-tag :type="row.frontend === '完成' ? 'success' : row.frontend === '进行中' ? 'warning' : 'info'" disable-transitions>
              {{ row.frontend }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const user = computed(() => userStore.userInfo)

const roleText = computed(() => {
  if (userStore.isSuperuser) return '超级管理员'
  const names = user.value?.roles.map((role) => role.name) ?? []
  return names.length ? names.join('、') : '-'
})

const lastLoginText = computed(() => {
  const value = user.value?.last_login_at
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
})

interface ModuleRow {
  name: string
  requirement: string
  backend: boolean
  frontend: string
}

const modules: ModuleRow[] = [
  { name: '外呼类型管理', requirement: 'OB-004', backend: true, frontend: '完成' },
  { name: '外呼场景管理', requirement: 'OB-003', backend: true, frontend: '待开发' },
  { name: '外呼号码管理', requirement: 'OB-001 / OB-005', backend: true, frontend: '待开发' },
  { name: '外呼任务管理', requirement: 'OB-006 / OB-020', backend: true, frontend: '待开发' },
  { name: '名单导入', requirement: 'OB-011 / OB-012', backend: false, frontend: '待开发' },
  { name: '外呼执行与会话', requirement: 'OB-021 / OB-023', backend: false, frontend: '待开发' },
  { name: 'IVR 与回呼', requirement: 'OB-017 / OB-029 / OB-030', backend: false, frontend: '待开发' },
  { name: '报表与实时监控', requirement: 'OB-025 / OB-028', backend: false, frontend: '待开发' },
]
</script>
