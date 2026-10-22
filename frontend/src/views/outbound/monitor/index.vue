<template>
  <div class="page-container">
    <el-card shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="租户">
          <el-select
            v-model="tenantId"
            placeholder="请选择租户"
            class="filter-select"
            @change="onTenantChange"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="统计窗口">
          <el-select v-model="windowMinutes" class="filter-select-sm" @change="loadData">
            <el-option label="最近 5 分钟" :value="5" />
            <el-option label="最近 15 分钟" :value="15" />
            <el-option label="最近 30 分钟" :value="30" />
            <el-option label="最近 60 分钟" :value="60" />
            <el-option label="最近 2 小时" :value="120" />
            <el-option label="最近 4 小时" :value="240" />
          </el-select>
        </el-form-item>
        <el-form-item label="自动刷新">
          <el-switch v-model="autoRefresh" active-text="30 秒" @change="onAutoRefreshChange" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadData">
            刷新
          </el-button>
        </el-form-item>
        <el-form-item v-if="monitor">
          <span class="form-tip">快照时间：{{ monitor.generated_at }}</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-item__label">窗口内发起呼叫</span>
          <span class="summary-item__value">{{ monitor?.calls.initiated ?? 0 }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">接通量</span>
          <span class="summary-item__value">{{ monitor?.calls.connected ?? 0 }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">接通率</span>
          <span class="summary-item__value">{{ percent(monitor?.calls.connect_rate) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">通话总时长</span>
          <span class="summary-item__value">
            {{ formatDuration(monitor?.calls.total_duration) }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">平均通话时长</span>
          <span class="summary-item__value">
            {{ formatDuration(monitor?.calls.avg_duration) }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">进行中会话</span>
          <span class="summary-item__value">{{ monitor?.active_sessions ?? 0 }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">到期待回呼</span>
          <span class="summary-item__value warning">
            {{ monitor?.callback_status.DUE ?? 0 }}
          </span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="chart-box__title">呼叫趋势（按分钟）</div>
      <div ref="trendChartEl" class="chart-box__canvas" />
    </el-card>

    <el-row :gutter="12">
      <el-col :span="8">
        <el-card shadow="never">
          <div class="chart-box__title">坐席状态</div>
          <el-descriptions v-if="agentEntries.length" :column="1" border size="small">
            <el-descriptions-item v-for="item in agentEntries" :key="item.key" :label="item.label">
              {{ item.value }}
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="暂无坐席数据" :image-size="60" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <div class="chart-box__title">任务状态</div>
          <el-descriptions v-if="taskEntries.length" :column="1" border size="small">
            <el-descriptions-item v-for="item in taskEntries" :key="item.key" :label="item.label">
              {{ item.value }}
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="暂无任务数据" :image-size="60" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <div class="chart-box__title">执行记录状态</div>
          <el-descriptions v-if="recordEntries.length" :column="1" border size="small">
            <el-descriptions-item v-for="item in recordEntries" :key="item.key" :label="item.label">
              {{ item.value }}
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="暂无执行记录" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <div class="chart-box__title">回呼任务状态</div>
      <div v-if="callbackEntries.length" class="tag-list">
        <el-tag
          v-for="item in callbackEntries"
          :key="item.key"
          :type="item.key === 'DUE' ? 'danger' : 'info'"
          effect="plain"
        >
          {{ item.label }}：{{ item.value }}
        </el-tag>
      </div>
      <el-empty v-else description="暂无回呼任务" :image-size="60" />
    </el-card>

    <el-card shadow="never">
      <div class="chart-box__title">窗口内任务呼叫量排行</div>
      <el-table v-loading="loading" :data="monitor?.top_tasks ?? []" border stripe>
        <el-table-column label="任务" min-width="200">
          <template #default="{ row }">
            {{ row.task_name ?? `#${row.task_id}` }}
          </template>
        </el-table-column>
        <el-table-column prop="initiated" label="发起呼叫" width="120" />
        <el-table-column prop="connected" label="接通量" width="120" />
        <el-table-column label="接通率" width="120">
          <template #default="{ row }">{{ percent(row.connect_rate) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

import { listTenantOptions, type TenantOption } from '@/api/outbound/common'
import {
  AGENT_STATUS_LABELS,
  CALLBACK_STATUS_LABELS,
  RECORD_STATUS_LABELS,
  TASK_STATUS_LABELS,
} from '@/api/outbound/enums'
import { getRealtimeMonitor, type RealtimeMonitor } from '@/api/outbound/report'
import { formatDuration, useEcharts } from '@/utils/useEcharts'
import type { EChartsOption } from '@/utils/echarts'

const loading = ref(false)
const tenants = ref<TenantOption[]>([])
const tenantId = ref<number | undefined>(undefined)
const windowMinutes = ref(30)
const autoRefresh = ref(false)
const monitor = ref<RealtimeMonitor | null>(null)

const trendChartEl = ref<HTMLDivElement>()
const { render: renderChart } = useEcharts(trendChartEl)

let timer: ReturnType<typeof setInterval> | null = null

const REFRESH_INTERVAL_MS = 30_000

function percent(value: number | undefined): string {
  return `${((value ?? 0) * 100).toFixed(2)}%`
}

function toEntries(
  source: Record<string, number> | undefined,
  labels: Record<string, string>,
  extra: { key: string; label: string }[] = [],
): { key: string; label: string; value: number }[] {
  const data = source ?? {}
  const keys = [...Object.keys(labels), ...extra.map((item) => item.key)]
  return keys
    .filter((key) => data[key] !== undefined)
    .map((key) => ({
      key,
      label: labels[key] ?? extra.find((item) => item.key === key)?.label ?? key,
      value: data[key] ?? 0,
    }))
}

const agentEntries = computed(() =>
  toEntries(monitor.value?.agent_status, AGENT_STATUS_LABELS),
)
const taskEntries = computed(() => toEntries(monitor.value?.task_status, TASK_STATUS_LABELS))
const recordEntries = computed(() =>
  toEntries(monitor.value?.record_status, RECORD_STATUS_LABELS),
)
const callbackEntries = computed(() =>
  toEntries(monitor.value?.callback_status, CALLBACK_STATUS_LABELS, [
    { key: 'DUE', label: '已到期待派单' },
  ]),
)

function trendOption(data: RealtimeMonitor): EChartsOption {
  const buckets = data.trend.map((item) =>
    new Date(item.bucket).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    }),
  )
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['发起呼叫', '接通'], bottom: 0 },
    grid: { left: 48, right: 24, top: 24, bottom: 48 },
    xAxis: { type: 'category', data: buckets, boundaryGap: false },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        name: '发起呼叫',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: data.trend.map((item) => item.initiated),
      },
      {
        name: '接通',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: data.trend.map((item) => item.connected),
      },
    ],
  }
}

async function loadData(): Promise<void> {
  if (!tenantId.value) return
  loading.value = true
  try {
    const { data } = await getRealtimeMonitor({
      tenant_id: tenantId.value,
      window_minutes: windowMinutes.value,
    })
    monitor.value = data
  } finally {
    loading.value = false
  }
}

function onTenantChange(): void {
  monitor.value = null
  void loadData()
}

function onAutoRefreshChange(value: boolean | string | number): void {
  stopTimer()
  if (value === true) {
    timer = setInterval(() => void loadData(), REFRESH_INTERVAL_MS)
  }
}

function stopTimer(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

watch(monitor, (data) => {
  if (data) renderChart(trendOption(data))
})

onMounted(async () => {
  const { data } = await listTenantOptions()
  tenants.value = data
  if (data.length > 0) {
    tenantId.value = data[0].id
    await loadData()
  }
})

onBeforeUnmount(() => {
  stopTimer()
})
</script>

<style scoped>
.filter-select {
  width: 180px;
}

.filter-select-sm {
  width: 140px;
}

.form-tip {
  color: #909399;
  font-size: 12px;
}

.summary-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 28px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-item__label {
  color: #909399;
  font-size: 13px;
}

.summary-item__value {
  color: #303133;
  font-size: 22px;
  font-weight: 600;
}

.summary-item__value.warning {
  color: #e6a23c;
}

.chart-box__title {
  margin-bottom: 12px;
  font-weight: 600;
}

.chart-box__canvas {
  height: 280px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

:deep(.el-card) {
  margin-bottom: 12px;
}
</style>
