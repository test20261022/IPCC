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
        <el-form-item label="外呼任务">
          <el-select
            v-model="query.task_id"
            placeholder="全部"
            clearable
            filterable
            class="filter-select"
            @change="onSearch"
          >
            <el-option
              v-for="item in taskOptions"
              :key="item.id"
              :label="`#${item.id} ${item.task_name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名单 ID">
          <el-input-number
            v-model="query.list_id"
            :min="1"
            placeholder="全部"
            controls-position="right"
            class="filter-number"
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
        <el-form-item label="执行状态">
          <el-select v-model="query.status" placeholder="全部" clearable class="filter-select">
            <el-option
              v-for="item in RECORD_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
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
      <div class="page-toolbar">
        <span class="page-toolbar__total">共 {{ total }} 条</span>
        <div class="page-toolbar__actions">
          <el-button
            v-permission="'outbound:task:execute'"
            type="primary"
            :icon="DocumentAdd"
            :disabled="!query.task_id"
            @click="onBuildRecords"
          >
            生成待执行记录
          </el-button>
          <el-button
            v-permission="'outbound:task:execute'"
            type="success"
            :icon="VideoPlay"
            :disabled="!query.task_id"
            @click="onExecute"
          >
            执行一批外呼
          </el-button>
          <el-button
            v-permission="'outbound:task:execute'"
            type="warning"
            :icon="RefreshLeft"
            @click="onRecycleTimeout"
          >
            触发超时回收
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="!query.task_id"
        class="task-hint"
        type="info"
        :closable="false"
        show-icon
        title="生成待执行记录与执行外呼需要先在上方筛选「外呼任务」。"
      />

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column prop="id" label="记录 ID" width="100" />
        <el-table-column label="任务" width="150">
          <template #default="{ row }">{{ nameOfTask(row.task_id) }}</template>
        </el-table-column>
        <el-table-column prop="list_id" label="名单 ID" width="100" />
        <el-table-column label="坐席" width="100">
          <template #default="{ row }">{{ row.agent_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="会话" width="100">
          <template #default="{ row }">{{ row.session_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <StatusTag :value="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="当前号码" width="140">
          <template #default="{ row }">{{ row.current_phone ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="本轮尝试" width="100">
          <template #default="{ row }">{{ row.current_attempt }}</template>
        </el-table-column>
        <el-table-column label="重试轮次" width="100">
          <template #default="{ row }">
            {{ row.retry_count }}
            <el-tag v-if="row.retry_count > 0" size="small" type="warning" effect="plain">
              已重试
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="超时时间" width="170">
          <template #default="{ row }">{{ row.timeout_at ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="最后呼叫" width="170">
          <template #default="{ row }">{{ row.last_call_at ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="170">
          <template #default="{ row }">{{ row.finished_at ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.failure_reason ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'outbound:session:call'"
              link
              type="primary"
              :disabled="row.status === 'SUCCESS'"
              @click="openCall(row)"
            >
              呼叫
            </el-button>
          </template>
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

    <el-dialog v-model="callVisible" title="单条即时呼叫（人工外呼）" width="520px">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="记录 ID">{{ callTarget?.id ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="任务">
          {{ callTarget ? nameOfTask(callTarget.task_id) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="当前号码">
          {{ callTarget?.current_phone ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="记录状态">
          <StatusTag :value="callTarget?.status" />
        </el-descriptions-item>
      </el-descriptions>
      <el-form class="call-form" label-width="90px">
        <el-form-item label="执行坐席">
          <el-select
            v-model="callAgentId"
            placeholder="可选，留空表示系统发起"
            clearable
            filterable
            class="full-width"
          >
            <el-option
              v-for="item in agentOptions"
              :key="item.id"
              :label="`#${item.id}${item.extension ? ` 分机 ${item.extension}` : ''}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="callVisible = false">取消</el-button>
        <el-button type="primary" :loading="calling" @click="onCall">发起呼叫</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resultVisible" title="执行结果" width="480px">
      <el-descriptions v-if="executeResult" :column="1" border>
        <el-descriptions-item label="任务">{{ executeResult.task_id }}</el-descriptions-item>
        <el-descriptions-item label="本次处理">{{ executeResult.processed }}</el-descriptions-item>
        <el-descriptions-item label="呼叫成功">{{ executeResult.success }}</el-descriptions-item>
        <el-descriptions-item label="进入重试等待">
          {{ executeResult.retry_waiting }}
        </el-descriptions-item>
        <el-descriptions-item label="重试已耗尽">{{ executeResult.exhausted }}</el-descriptions-item>
        <el-descriptions-item label="失败">{{ executeResult.failed }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="resultVisible = false">知道了</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { DocumentAdd, Refresh, RefreshLeft, Search, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  listAgentOptions,
  listTaskOptions,
  listTenantOptions,
  type AgentOption,
  type TaskOption,
  type TenantOption,
} from '@/api/outbound/common'
import { RECORD_STATUS_OPTIONS } from '@/api/outbound/enums'
import {
  buildTaskRecords,
  callRecord,
  executeTask,
  listOutboundRecords,
  recycleTimeout,
  type OutboundExecuteSummary,
  type OutboundRecord,
  type OutboundRecordQuery,
} from '@/api/outbound/record'
import StatusTag from '@/components/StatusTag.vue'

const loading = ref(false)
const rows = ref<OutboundRecord[]>([])
const total = ref(0)

const tenants = ref<TenantOption[]>([])
const taskOptions = ref<TaskOption[]>([])
const agentOptions = ref<AgentOption[]>([])

const query = reactive<OutboundRecordQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  task_id: undefined,
  list_id: undefined,
  agent_id: undefined,
  status: undefined,
})

const callVisible = ref(false)
const calling = ref(false)
const callTarget = ref<OutboundRecord | null>(null)
const callAgentId = ref<number | undefined>(undefined)

const resultVisible = ref(false)
const executeResult = ref<OutboundExecuteSummary | null>(null)

function nameOfTask(taskId: number | null): string {
  if (!taskId) return '-'
  const task = taskOptions.value.find((item) => item.id === taskId)
  return task ? `#${task.id} ${task.task_name}` : `#${taskId}`
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listOutboundRecords(query)
    rows.value = data.items
    total.value = data.total
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
    taskOptions.value = []
    agentOptions.value = []
    return
  }
  const [tasks, agents] = await Promise.all([
    // 走选项接口而非任务列表接口：本页不需要 outbound:task:list 权限
    listTaskOptions(tenantId),
    listAgentOptions({ tenant_id: tenantId }),
  ])
  taskOptions.value = tasks.data
  agentOptions.value = agents.data
}

function onTenantChange(): void {
  query.task_id = undefined
  query.agent_id = undefined
  void loadOptions(query.tenant_id).then(() => loadData())
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.task_id = undefined
  query.list_id = undefined
  query.agent_id = undefined
  query.status = undefined
  onSearch()
}

async function onBuildRecords(): Promise<void> {
  if (!query.task_id) return
  const { data } = await buildTaskRecords(query.task_id)
  ElMessage.success(`本次新建记录 ${data.created} 条，已存在跳过 ${data.skipped} 条`)
  await loadData()
}

async function onExecute(): Promise<void> {
  if (!query.task_id) return
  try {
    await ElMessageBox.confirm(
      '确认对当前任务执行一批外呼？仅「运行中」的任务会真正发起呼叫。',
      '执行确认',
      { type: 'warning', confirmButtonText: '开始执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const { data } = await executeTask(query.task_id)
  executeResult.value = data
  resultVisible.value = true
  await loadData()
}

async function onRecycleTimeout(): Promise<void> {
  const { data } = await recycleTimeout(100)
  ElMessage.success(`扫描 ${data.scanned} 条，回收 ${data.recycled} 条，跳过 ${data.skipped} 条`)
  await loadData()
}

function openCall(row: OutboundRecord): void {
  callTarget.value = row
  callAgentId.value = row.agent_id ?? undefined
  callVisible.value = true
}

async function onCall(): Promise<void> {
  if (!callTarget.value) return
  calling.value = true
  try {
    const { data } = await callRecord(callTarget.value.id, callAgentId.value ?? null)
    ElMessage.success(
      `呼叫已发起，记录状态：${data.status}；本轮尝试 ${data.current_attempt} 个号码，累计重试 ${data.retry_count} 轮`,
    )
    callVisible.value = false
    await loadData()
  } finally {
    calling.value = false
  }
}

onMounted(async () => {
  await loadTenants()
  await loadOptions(query.tenant_id)
  await loadData()
})
</script>

<style scoped>
.filter-select {
  width: 180px;
}

.filter-number {
  width: 140px;
}

.full-width {
  width: 100%;
}

.task-hint {
  margin-bottom: 12px;
}

.call-form {
  margin-top: 16px;
}

.page-toolbar__total {
  color: #606266;
}
</style>
