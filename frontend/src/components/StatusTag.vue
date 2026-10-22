<template>
  <el-tag :type="meta.type" disable-transitions>{{ meta.text }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type TagType = 'success' | 'info' | 'warning' | 'danger' | 'primary'

/** 状态码 → 中文与标签色（与后端枚举值一一对应） */
const STATUS_MAP: Record<string, { text: string; type: TagType }> = {
  // 通用
  ENABLED: { text: '启用', type: 'success' },
  DISABLED: { text: '停用', type: 'info' },
  // 任务
  DRAFT: { text: '草稿', type: 'info' },
  READY: { text: '就绪', type: 'primary' },
  RUNNING: { text: '运行中', type: 'success' },
  PAUSED: { text: '已暂停', type: 'warning' },
  COMPLETED: { text: '已完成', type: 'success' },
  CANCELLED: { text: '已取消', type: 'danger' },
  // 名单行
  PENDING: { text: '待处理', type: 'info' },
  PROCESSING: { text: '处理中', type: 'primary' },
  SUCCESS: { text: '成功', type: 'success' },
  FAILED: { text: '失败', type: 'danger' },
  EXHAUSTED: { text: '重试耗尽', type: 'danger' },
  // 执行记录
  ASSIGNED: { text: '已分配', type: 'primary' },
  CALLING: { text: '呼叫中', type: 'warning' },
  RETRY_WAITING: { text: '重试等待', type: 'warning' },
  TIMEOUT: { text: '已超时', type: 'danger' },
  // 导入批次
  PARSING: { text: '解析中', type: 'primary' },
  VALIDATING: { text: '校验中', type: 'primary' },
  IMPORTING: { text: '导入中', type: 'primary' },
  PARTIAL_FAILED: { text: '部分失败', type: 'warning' },
  // 会话
  CREATED: { text: '已创建', type: 'info' },
  CONNECTED: { text: '已接通', type: 'success' },
  ENDED: { text: '已结束', type: 'info' },
  RELEASED: { text: '已释放', type: 'info' },
  // 坐席
  OFFLINE: { text: '离线', type: 'info' },
  IDLE: { text: '空闲', type: 'success' },
  BUSY: { text: '忙碌', type: 'warning' },
  RESERVED: { text: '已预占', type: 'primary' },
  // 预占
  ACCEPTED: { text: '已接单', type: 'success' },
  EXPIRED: { text: '已过期', type: 'danger' },
  // 呼叫结果
  INITIATED: { text: '已发起', type: 'primary' },
  RINGING: { text: '振铃中', type: 'primary' },
  NO_ANSWER: { text: '无应答', type: 'warning' },
  REJECTED: { text: '已拒接', type: 'danger' },
  HANGUP: { text: '已挂断', type: 'info' },
}

const props = defineProps<{
  value?: string | null
  /** 按页面覆写的文案：同一状态码在不同业务下含义不同，如 PENDING 在名单是「待处理」、在回呼任务是「待回呼」 */
  labels?: Record<string, string>
}>()

const meta = computed(() => {
  const key = props.value ?? ''
  const base =
    STATUS_MAP[key] ?? { text: props.value ?? '-', type: 'info' as TagType }
  const override = props.labels?.[key]
  return override ? { ...base, text: override } : base
})
</script>
