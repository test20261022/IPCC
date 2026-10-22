<template>
  <el-menu
    :default-active="activeMenu"
    background-color="#1f2d3d"
    text-color="#bfcbd9"
    active-text-color="#409eff"
    router
  >
    <MenuItem
      v-for="item in menuStore.routes"
      :key="item.path"
      :item="item"
      :base-path="item.path"
    />
  </el-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import MenuItem from '@/layout/components/MenuItem.vue'
import { useMenuStore } from '@/stores/menu'

const route = useRoute()
const menuStore = useMenuStore()

const activeMenu = computed(() => route.path)
</script>
