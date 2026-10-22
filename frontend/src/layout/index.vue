<template>
  <el-container class="layout">
    <el-aside class="layout__aside" width="220px">
      <div class="layout__logo">{{ appTitle }}</div>
      <SidebarMenu />
    </el-aside>

    <el-container>
      <el-header class="layout__header">
        <HeaderBar />
      </el-header>
      <el-main class="layout__main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import HeaderBar from '@/layout/components/HeaderBar.vue'
import SidebarMenu from '@/layout/components/SidebarMenu.vue'

const appTitle = import.meta.env.VITE_APP_TITLE || '企业管理平台'
</script>

<style scoped>
.layout {
  height: 100%;
}

.layout__aside {
  background-color: #1f2d3d;
  overflow-x: hidden;
}

.layout__logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
  background-color: #17222e;
}

.layout__header {
  height: 56px;
  padding: 0 20px;
  background-color: #ffffff;
  border-bottom: 1px solid #e4e7ed;
}

.layout__main {
  padding: 0;
  background-color: #f5f7fa;
  overflow-y: auto;
}
</style>
