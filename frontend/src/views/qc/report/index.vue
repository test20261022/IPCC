<template>
  <div class="page-container">
    <el-card shadow="never">
      <el-form :inline="true" :model="query" @submit.prevent>
        <el-form-item label="租户">
          <el-select
            v-model="query.tenant_id"
            placeholder="全部"
            clearable
            class="filter-select"
            @change="onTenantChange"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="质检任务">
          <el-select
            v-model="query.task_id"
            placeholder="全部"
            clearable
            filterable
            class="filter-select"
          >
            <el-option
              v-for="item in taskOptions"
              :key="item.id"
              :label="item.task_name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="完成时间">
          <el-date-picker
            v-model="timeRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            class="filter-range"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button :icon="Refresh" @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <div v-loading="loading" class="summary-grid">
        <div class="summary-item">
          <span class="summary-item__label">明细总量</span>
          <span class="summary-item__value">{{ overview.total }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">已完成</span>
          <span class="summary-item__value">{{ overview.completed }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">待质检</span>
          <span class="summary-item__value">{{ overview.pending }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">质检中</span>
          <span class="summary-item__value">{{ overview.reviewing }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">完成率</span>
          <span class="summary-item__value">{{ percent(overview.completion_rate) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">参与专家数</span>
          <span class="summary-item__value">{{ overview.reviewer_count }}</span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <div v-loading="loading" class="chart-row">
        <div class="chart-box">
          <div class="chart-box__title">完成率</div>
          <div ref="completionChartEl" class="chart-box__canvas" />
        </div>
        <div class="chart-box">
          <div class="chart-box__title">等级分布</div>
          <div ref="gradeChartEl" class="chart-box__canvas" />
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <div v-loading="loading" class="chart-box">
        <div class="chart-box__title">每日完成量</div>
        <div ref="dailyChartEl" class="chart-box__canvas" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'

import { listTenantOptions, type TenantOption } from '@/api/outbound/common'
import { QC_GRADE_LABELS, labelOf } from '@/api/qc/enums'
import {
  getQcDailyCompletion,
  getQcReportOverview,
  type QcDailyCompletion,
  type QcDailyCompletionItem,
  type QcReportOverview,
  type QcReportOverviewQuery,
} from '@/api/qc/report'
import { listQcTasks, type QcTask } from '@/api/qc/tasks'
import { useEcharts } from '@/utils/useEcharts'
import type { EChartsOption } from '@/utils/echarts'

const loading = ref(false)
const tenants = ref<TenantOption[]>([])
const taskOptions = ref<QcTask[]>([])

const query = reactive<QcReportOverviewQuery>({
  tenant_id: undefined,
  task_id: undefined,
})

/** 默认统计最近 14 天 */
const timeRange = ref<[Date, Date] | null>(defaultRange())

const overview = ref<QcReportOverview>({
  task_id: null,
  total: 0,
  completed: 0,
  pending: 0,
  reviewing: 0,
  completion_rate: 0,
  grade_counts: {},
  reviewer_count: 0,
})

const daily = ref<QcDailyCompletion>({ items: [], date_from: '', date_to: '' })

const completionChartEl = ref<HTMLDivElement>()
const gradeChartEl = ref<HTMLDivElement>()
const dailyChartEl = ref<HTMLDivElement>()
const { render: renderCompletion } = useEcharts(completionChartEl)
const { render: renderGrade } = useEcharts(gradeChartEl)
const { render: renderDaily } = useEcharts(dailyChartEl)

function defaultRange(): [Date, Date] {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - 13)
  return [start, end]
}

/** Date → YYYY-MM-DD */
function formatDate(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

/**
 * 及格数读取收敛：后端 JSON 字段名为 `pass`，TS 类型以 `pass_count` 承载。
 * 这里统一兼容两种字段，避免在图表逻辑里散落断言。
 */
function passOf(row: QcDailyCompletionItem): number {
  return row.pass_count ?? (row as { pass?: number }).pass ?? 0
}

function dateParams(): { date_from: string; date_to: string } {
  const range = timeRange.value ?? defaultRange()
  return { date_from: formatDate(range[0]), date_to: formatDate(range[1]) }
}

async function loadReport(): Promise<void> {
  loading.value = true
  try {
    const [overviewRes, dailyRes] = await Promise.all([
      getQcReportOverview({ tenant_id: query.tenant_id, task_id: query.task_id }),
      getQcDailyCompletion({
        ...dateParams(),
        tenant_id: query.tenant_id,
        task_id: query.task_id,
      }),
    ])
    overview.value = overviewRes.data
    daily.value = dailyRes.data
  } finally {
    loading.value = false
  }
}

async function loadTenants(): Promise<void> {
  const { data } = await listTenantOptions()
  tenants.value = data
  if (!query.tenant_id && data.length > 0) {
    query.tenant_id = data[0].id
  }
}

/** 任务下拉依赖 qc:task:list 权限；无权限时静默降级为空，报表仍可按租户汇总 */
async function loadTasks(): Promise<void> {
  if (!query.tenant_id) {
    taskOptions.value = []
    return
  }
  try {
    const { data } = await listQcTasks({ tenant_id: query.tenant_id, page_size: 200 })
    taskOptions.value = data.items
  } catch {
    taskOptions.value = []
  }
}

function onTenantChange(): void {
  query.task_id = undefined
  void loadTasks().then(() => loadReport())
}

function onSearch(): void {
  void loadReport()
}

function onReset(): void {
  timeRange.value = defaultRange()
  query.task_id = undefined
  void loadReport()
}

/** 完成率饼图：已完成 / 未完成 */
function completionChartOption(data: QcReportOverview): EChartsOption {
  const items = [
    { name: '已完成', value: data.completed },
    { name: '未完成', value: Math.max(0, data.total - data.completed) },
  ]
  const seriesData = items.some((item) => item.value > 0)
    ? items
    : [{ name: '暂无数据', value: 0 }]
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['40%', '68%'],
        avoidLabelOverlap: true,
        label: { formatter: '{b}: {c}' },
        data: seriesData,
      },
    ],
  }
}

/** 等级分布饼图：EXCELLENT / PASS / FAIL */
function gradeChartOption(counts: Record<string, number>): EChartsOption {
  const data = (['EXCELLENT', 'PASS', 'FAIL'] as const).map((grade) => ({
    name: labelOf(QC_GRADE_LABELS, grade),
    value: counts[grade] ?? 0,
  }))
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['40%', '68%'],
        avoidLabelOverlap: true,
        label: { formatter: '{b}: {c}' },
        data,
      },
    ],
  }
}

/** 每日完成量柱状图：后端已补齐无数据日（补零），逐日画出柱子 */
function dailyChartOption(items: QcDailyCompletionItem[]): EChartsOption {
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 40, right: 20, top: 40, bottom: 60 },
    xAxis: { type: 'category', data: items.map((item) => item.bucket) },
    yAxis: { type: 'value' },
    series: [
      { name: '总量', type: 'bar', data: items.map((item) => item.total) },
      { name: '优秀', type: 'bar', data: items.map((item) => item.excellent) },
      { name: '及格', type: 'bar', data: items.map((item) => passOf(item)) },
      { name: '不及格', type: 'bar', data: items.map((item) => item.fail) },
    ],
  }
}

watch(overview, (value) => {
  renderCompletion(completionChartOption(value))
  renderGrade(gradeChartOption(value.grade_counts ?? {}))
})

watch(daily, (value) => {
  renderDaily(dailyChartOption(value.items))
})

onMounted(async () => {
  await loadTenants()
  await loadTasks()
  await loadReport()
  renderCompletion(completionChartOption(overview.value))
  renderGrade(gradeChartOption(overview.value.grade_counts ?? {}))
  renderDaily(dailyChartOption(daily.value.items))
})
</script>

<style scoped>
.filter-select {
  width: 170px;
}

.filter-range {
  width: 380px;
}

.summary-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 32px;
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

.chart-row {
  display: flex;
  gap: 16px;
}

.chart-box {
  flex: 1;
  min-width: 320px;
}

.chart-box__title {
  margin-bottom: 8px;
  font-weight: 600;
}

.chart-box__canvas {
  height: 260px;
}
</style>