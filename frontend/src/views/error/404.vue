<template>
  <el-result icon="warning" title="404" sub-title="抱歉，你访问的页面不存在">
    <template #extra>
      <el-button type="primary" @click="router.replace('/')">返回首页</el-button>
    </template>
  </el-result>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<style scoped>
.el-result {
  height: 100%;
  background-color: #ffffff;
}
</style>
