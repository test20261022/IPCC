<template>
  <template v-if="!item.meta?.hidden">
    <!-- 单个子路由且未强制展开时，直接渲染为一个菜单项，避免出现只有一项的子菜单 -->
    <el-menu-item v-if="singleChild" :index="singleChildPath">
      <el-icon v-if="singleChild?.meta?.icon">
        <component :is="singleChild.meta.icon" />
      </el-icon>
      <template #title>{{ singleChild?.meta?.title }}</template>
    </el-menu-item>

    <el-sub-menu v-else-if="visibleChildren.length" :index="basePath">
      <template #title>
        <el-icon v-if="item.meta?.icon">
          <component :is="item.meta.icon" />
        </el-icon>
        <span>{{ item.meta?.title }}</span>
      </template>
      <MenuItem
        v-for="child in visibleChildren"
        :key="child.path"
        :item="child"
        :base-path="resolvePath(basePath, child.path)"
      />
    </el-sub-menu>

    <el-menu-item v-else-if="item.meta?.title" :index="basePath">
      <el-icon v-if="item.meta?.icon">
        <component :is="item.meta.icon" />
      </el-icon>
      <template #title>{{ item.meta?.title }}</template>
    </el-menu-item>
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RouteRecordRaw } from 'vue-router'

const props = defineProps<{
  item: RouteRecordRaw
  basePath: string
}>()

const visibleChildren = computed(() => (props.item.children ?? []).filter((child) => !child.meta?.hidden))

const singleChild = computed(() => {
  if (props.item.meta?.alwaysShow) return undefined
  const children = visibleChildren.value
  if (children.length !== 1) return undefined
  const child = children[0]
  // 子路由自身还有下一级时不做折叠
  return child.children?.length ? undefined : child
})

const singleChildPath = computed(() =>
  singleChild.value ? resolvePath(props.basePath, singleChild.value.path) : props.basePath,
)

function resolvePath(base: string, path: string): string {
  if (path.startsWith('/')) return path
  return `${base.replace(/\/$/, '')}/${path}`
}
</script>
