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
        <el-form-item label="呼叫时间">
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            class="filter-range"
          />
        </el-form-item>
        <el-form-item label="话务来源">
          <el-select v-model="query.source" class="filter-select-sm">
            <el-option
              v-for="item in CALL_FLOW_SOURCE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="外呼场景">
          <el-select v-model="query.scene_id" placeholder="全部" clearable class="filter-select">
            <el-option
              v-for="item in sceneOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="外呼任务">
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
              :label="`#${item.id} ${item.task_name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="外呼类型">
          <el-select
            v-model="query.type_id"
            placeholder="全部"
            clearable
            class="filter-select"
            @change="onTypeChange"
          >
            <el-option
              v-for="item in typeOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="外呼子类型">
          <el-select
            v-model="query.sub_type_id"
            placeholder="全部"
            clearable
            :disabled="!query.type_id"
            class="filter-select"
          >
            <el-option
              v-for="item in subTypeOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="呼叫结果">
          <el-select v-model="query.call_status" placeholder="全部" clearable class="filter-select-sm">
            <el-option
              v-for="item in CALL_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="被叫号码">
          <el-input
            v-model="query.phone"
            placeholder="模糊匹配"
            clearable
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item label="坐席">
          <el-select
            v-model="query.agent_id"
            placeholder="全部"
            clearable
            filterable
            class="filter-select"
          >
            <el-option
              v-for="item in agentOptions"
              :key="item.id"
              :label="`#${item.id}${item.extension ? ` 分机 ${item.extension}` : ''}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button :icon="Refresh" @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-item__label">话务总量</span>
          <span class="summary-item__value">{{ summary.total }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">接通量</span>
          <span class="summary-item__value">{{ summary.connected }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">接通率</span>
          <span class="summary-item__value">{{ percent(summary.connect_rate) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">通话总时长</span>
          <span class="summary-item__value">{{ formatDuration(summary.total_duration) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__label">平均通话时长</span>
          <span class="summary-item__value">{{ formatDuration(summary.avg_duration) }}</span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="chart-row">
        <div class="chart-box">
          <div class="chart-box__title">呼叫结果分布</div>
          <div ref="statusChartEl" class="chart-box__canvas" />
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="page-toolbar">
        <span class="page-toolbar__total">共 {{ total }} 条</span>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column label="呼叫时间" width="170">
          <template #default="{ row }">{{ row.started_at ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">
            {{ labelOf(CALL_FLOW_SOURCE_LABELS, row.source) }}
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="被叫号码" width="140" />
        <el-table-column label="外呼任务" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.task_name ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="外呼场景" width="140">
          <template #default="{ row }">{{ row.scene_name ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="外呼类型" width="140">
          <template #default="{ row }">
            <span v-if="!row.type_name">-</span>
            <span v-else>
              {{ row.type_name }}
              <el-tag v-if="row.type_level === 2" size="small" type="info" effect="plain">
                子类型
              </el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="坐席" width="110">
          <template #default="{ row }">
            {{ row.agent_id ? `#${row.agent_id}` : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="UserID" width="110">
          <template #default="{ row }">{{ row.user_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="OrderID" width="110">
          <template #default="{ row }">{{ row.order_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="呼叫结果" width="110">
          <template #default="{ row }">
            <el-tag
              :type="row.call_status === 'CONNECTED' ? 'success' : 'warning'"
              disable-transitions
            >
              {{ labelOf(CALL_STATUS_LABELS, row.call_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="通话时长" width="110">
          <template #default="{ row }">
            {{ row.call_status === 'CONNECTED' ? formatDuration(row.duration) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.failure_reason ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="录音" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.recording_path ?? '-' }}</template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadData"
          @size-change="onSearch"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'

import {
  listAgentOptions,
  listTaskOptions,
  listTenantOptions,
  type AgentOption,
  type TaskOption,
  type TenantOption,
} from '@/api/outbound/common'
import {
  CALL_FLOW_SOURCE_LABELS,
  CALL_FLOW_SOURCE_OPTIONS,
  CALL_STATUS_LABELS,
  CALL_STATUS_OPTIONS,
  labelOf,
} from '@/api/outbound/enums'
import { getCallFlowReport, type CallFlowQuery, type CallFlowRecord, type CallFlowSummary } from '@/api/outbound/report'
import { getOutboundSceneTree, type OutboundSceneTree } from '@/api/outbound/scene'
import { listOutboundTypes, type OutboundType } from '@/api/outbound/type'
import { formatDuration, useEcharts } from '@/utils/useEcharts'
import type { EChartsOption } from '@/utils/echarts'

const loading = ref(false)
const rows = ref<CallFlowRecord[]>([])
const total = ref(0)
const summary = ref<CallFlowSummary>({
  total: 0,
  connected: 0,
  connect_rate: 0,
  total_duration: 0,
  avg_duration: 0,
  status_counts: {},
})

const tenants = ref<TenantOption[]>([])
const sceneOptions = ref<OutboundSceneTree[]>([])
const taskOptions = ref<TaskOption[]>([])
/** 全量外呼类型（含二级），「类型」与「子类型」两个下拉都从这里派生 */
const allTypes = ref<OutboundType[]>([])
const agentOptions = ref<AgentOption[]>([])

const timeRange = ref<[Date, Date] | null>(null)

const query = reactive<CallFlowQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  source: 'ALL',
  scene_id: undefined,
  task_id: undefined,
  type_id: undefined,
  sub_type_id: undefined,
  call_status: undefined,
  phone: '',
  agent_id: undefined,
})

const statusChartEl = ref<HTMLDivElement>()
const { render: renderChart } = useEcharts(statusChartEl)

/** 「外呼类型」下拉只放一级类型（二级类型走「外呼子类型」） */
const typeOptions = computed(() => allTypes.value.filter((item) => item.level === 1))

/** 子类型仅属于所选一级类型（两级结构） */
const subTypeOptions = computed(() =>
  query.type_id ? allTypes.value.filter((item) => item.parent_id === query.type_id) : [],
)

function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function flattenScenes(nodes: OutboundSceneTree[]): OutboundSceneTree[] {
  const result: OutboundSceneTree[] = []
  const walk = (items: OutboundSceneTree[]) => {
    items.forEach((item) => {
      result.push(item)
      if (item.children?.length) walk(item.children)
    })
  }
  walk(nodes)
  return result
}

function buildParams(): CallFlowQuery {
  const params: CallFlowQuery = { ...query }
  if (timeRange.value && timeRange.value.length === 2) {
    params.started_from = timeRange.value[0].toISOString()
    params.started_to = timeRange.value[1].toISOString()
  }
  return params
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await getCallFlowReport(buildParams())
    rows.value = data.items
    total.value = data.total
    summary.value = data.summary
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

async function loadOptions(tenantId?: number): Promise<void> {
  if (!tenantId) {
    sceneOptions.value = []
    taskOptions.value = []
    allTypes.value = []
    agentOptions.value = []
    return
  }
  const [scenes, tasks, types, agents] = await Promise.all([
    getOutboundSceneTree({ tenant_id: tenantId }),
    // 走选项接口而非任务列表接口：本页不需要 outbound:task:list 权限
    listTaskOptions(tenantId),
    listOutboundTypes({ tenant_id: tenantId, page_size: 200 }),
    listAgentOptions({ tenant_id: tenantId }),
  ])
  sceneOptions.value = flattenScenes(scenes.data)
  taskOptions.value = tasks.data
  allTypes.value = types.data.items
  agentOptions.value = agents.data
}

function onTenantChange(): void {
  query.scene_id = undefined
  query.task_id = undefined
  query.type_id = undefined
  query.sub_type_id = undefined
  query.agent_id = undefined
  void loadOptions(query.tenant_id).then(() => loadData())
}

/** 切换一级类型后清空子类型，避免出现「父类型 + 不属于它的子类型」的组合 */
function onTypeChange(): void {
  query.sub_type_id = undefined
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  timeRange.value = null
  query.source = 'ALL'
  query.scene_id = undefined
  query.task_id = undefined
  query.type_id = undefined
  query.sub_type_id = undefined
  query.call_status = undefined
  query.phone = ''
  query.agent_id = undefined
  onSearch()
}

function statusChartOption(counts: Record<string, number>): EChartsOption {
  const data = Object.entries(counts).map(([status, value]) => ({
    name: labelOf(CALL_STATUS_LABELS, status),
    value,
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
        data: data.length ? data : [{ name: '暂无数据', value: 0 }],
      },
    ],
  }
}

watch(
  () => summary.value.status_counts,
  (counts) => renderChart(statusChartOption(counts ?? {})),
)

onMounted(async () => {
  await loadTenants()
  await loadOptions(query.tenant_id)
  await loadData()
  renderChart(statusChartOption(summary.value.status_counts))
})
</script>

<style scoped>
.filter-select {
  width: 170px;
}

.filter-select-sm {
  width: 130px;
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

.page-toolbar__total {
  color: #606266;
}
</style>
