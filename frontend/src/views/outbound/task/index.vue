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
        <el-form-item label="任务名称">
          <el-input
            v-model="query.task_name"
            placeholder="模糊匹配"
            clearable
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item label="站点">
          <el-select
            v-model="query.site_id"
            placeholder="全部"
            clearable
            class="filter-select"
            @change="onSearch"
          >
            <el-option v-for="item in siteOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="技能队列">
          <el-select
            v-model="query.skill_queue_id"
            placeholder="全部"
            clearable
            class="filter-select"
            @change="onSearch"
          >
            <el-option
              v-for="item in queueOptions"
              :key="item.id"
              :label="item.name"
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
            @change="onTypeFilterChange"
          >
            <el-option
              v-for="item in typeOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="外呼场景">
          <el-select v-model="query.scene_id" placeholder="全部" clearable class="filter-select">
            <el-option
              v-for="item in filterSceneOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" clearable class="filter-select-sm">
            <el-option
              v-for="item in TASK_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="派单模式">
          <el-select
            v-model="query.dispatch_mode"
            placeholder="全部"
            clearable
            class="filter-select-sm"
          >
            <el-option
              v-for="item in DISPATCH_MODE_OPTIONS"
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
            v-permission="'outbound:task:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column prop="task_name" label="任务名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="站点" width="120">
          <template #default="{ row }">{{ nameOfSite(row.site_id) }}</template>
        </el-table-column>
        <el-table-column label="技能队列" width="140">
          <template #default="{ row }">{{ nameOfQueue(row.skill_queue_id) }}</template>
        </el-table-column>
        <el-table-column label="外呼类型" width="130">
          <template #default="{ row }">{{ nameOfType(row.type_id) }}</template>
        </el-table-column>
        <el-table-column label="外呼场景" width="140">
          <template #default="{ row }">{{ nameOfScene(row.scene_id) }}</template>
        </el-table-column>
        <el-table-column label="派单模式" width="110">
          <template #default="{ row }">
            {{ labelOf(DISPATCH_MODE_LABELS, row.dispatch_mode) }}
          </template>
        </el-table-column>
        <el-table-column label="号码策略" width="120">
          <template #default="{ row }">
            {{ labelOf(NUMBER_STRATEGY_LABELS, row.number_select_strategy) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">{{ row.priority }}</template>
        </el-table-column>
        <el-table-column label="重试" width="110">
          <template #default="{ row }">
            {{ row.max_retry_count }} 次 / {{ row.retry_interval }}s
          </template>
        </el-table-column>
        <el-table-column label="并发" width="80">
          <template #default="{ row }">{{ row.max_concurrency }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'outbound:task:update'"
              link
              type="primary"
              :disabled="!EDITABLE_STATUSES.includes(row.status)"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-dropdown
              v-permission="'outbound:task:update'"
              trigger="click"
              @command="(command: TaskStatus) => onChangeStatus(row, command)"
            >
              <el-button link type="warning" :disabled="transitionsOf(row.status).length === 0">
                状态流转
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="item in transitionsOf(row.status)"
                    :key="item"
                    :command="item"
                  >
                    {{ labelOf(TASK_STATUS_LABELS, item) }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button v-permission="'outbound:task:copy'" link type="primary" @click="openCopy(row)">
              复制
            </el-button>
            <el-button
              v-permission="'outbound:task:list'"
              link
              type="primary"
              @click="openPrediction(row)"
            >
              预测
            </el-button>
            <el-button
              v-permission="'outbound:task:delete'"
              link
              type="danger"
              :disabled="!DELETABLE_STATUSES.includes(row.status)"
              @click="onDelete(row)"
            >
              删除
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

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="900px" top="5vh">
      <el-tabs v-model="formTab">
        <el-tab-pane label="基础信息" name="base">
          <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px">
            <el-form-item label="租户" prop="tenant_id">
              <el-select
                v-model="form.tenant_id"
                placeholder="请选择租户"
                :disabled="isEdit"
                class="full-width"
                @change="onFormTenantChange"
              >
                <el-option
                  v-for="item in tenants"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="任务名称" prop="task_name">
              <el-input v-model="form.task_name" placeholder="同租户下任务名唯一" />
            </el-form-item>
            <el-form-item label="站点">
              <el-select v-model="form.site_id" placeholder="可选" clearable class="full-width">
                <el-option
                  v-for="item in siteOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="技能队列">
              <el-select v-model="form.skill_queue_id" placeholder="可选" clearable class="full-width">
                <el-option
                  v-for="item in queueOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="外呼类型">
              <el-select
                v-model="form.type_id"
                placeholder="可选"
                clearable
                class="full-width"
                @change="onFormTypeChange"
              >
                <el-option
                  v-for="item in typeOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="外呼场景">
              <el-select v-model="form.scene_id" placeholder="可选" clearable class="full-width">
                <el-option
                  v-for="item in formSceneOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="优先级">
              <el-input-number v-model="form.priority" :min="0" :max="9999" />
              <span class="form-tip">数值越小越先派单</span>
            </el-form-item>
            <el-form-item label="任务说明">
              <el-input v-model="form.description" type="textarea" :rows="3" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="策略配置" name="strategy">
          <el-form label-width="110px">
            <el-form-item label="派单模式">
              <el-select v-model="form.dispatch_mode" class="full-width">
                <el-option
                  v-for="item in DISPATCH_MODE_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="号码选取策略">
              <el-select v-model="form.number_select_strategy" class="full-width">
                <el-option
                  v-for="item in NUMBER_STRATEGY_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="失败重试间隔">
              <el-input-number v-model="form.retry_interval" :min="0" :max="86400" />
              <span class="form-tip">秒</span>
            </el-form-item>
            <el-form-item label="最大重试次数">
              <el-input-number v-model="form.max_retry_count" :min="0" :max="10" />
              <span class="form-tip">0 表示不重试</span>
            </el-form-item>
            <el-form-item label="单次呼叫超时">
              <el-input-number v-model="form.call_timeout_seconds" :min="1" :max="3600" />
              <span class="form-tip">秒，超过即回收（§22）</span>
            </el-form-item>
            <el-form-item label="最大并发呼叫">
              <el-input-number v-model="form.max_concurrency" :min="1" :max="999" />
            </el-form-item>
            <el-form-item label="预测调整系数">
              <el-input-number
                v-model="form.adjustment_factor"
                :min="0"
                :max="99"
                :step="0.1"
                :precision="2"
              />
              <span class="form-tip">仅预测外呼生效（§36）</span>
            </el-form-item>
            <el-form-item label="IVR 流程">
              <el-select v-model="form.ivr_flow_id" placeholder="可选，不使用 IVR" clearable class="full-width">
                <el-option
                  v-for="item in ivrFlowOptions"
                  :key="item.id"
                  :label="`${item.name}（${item.code}）`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="号码配置" name="numbers">
          <div class="number-toolbar">
            <span class="form-tip">
              按 OrderID / UserID / 收件人号码的顺序选择被叫号码来源，顺序值越小越先尝试
            </span>
            <el-button type="primary" :icon="Plus" size="small" @click="addNumberRow">
              添加号码
            </el-button>
          </div>
          <el-table :data="numberRows" border size="small">
            <el-table-column label="主叫号码" min-width="200">
              <template #default="{ row }">
                <el-select v-model="row.number_id" placeholder="请选择" filterable class="full-width">
                  <el-option
                    v-for="item in numberOptions"
                    :key="item.id"
                    :label="`${item.display_name}（${item.caller_number}）`"
                    :value="item.id"
                    :disabled="isNumberUsed(item.id, row)"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="OrderID 顺序" width="130">
              <template #default="{ row }">
                <el-input-number v-model="row.order_id" :min="1" :max="99" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="UserID 顺序" width="130">
              <template #default="{ row }">
                <el-input-number v-model="row.user_id" :min="1" :max="99" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="收件号码顺序" width="140">
              <template #default="{ row }">
                <el-input-number v-model="row.recipient_number" :min="1" :max="99" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="优先级" width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.priority" :min="0" :max="999" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="启用" width="80">
              <template #default="{ row }">
                <el-switch v-model="row.enabled" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ $index }">
                <el-button link type="danger" @click="removeNumberRow($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="copyVisible" title="复制外呼任务" width="480px">
      <el-form label-width="110px">
        <el-form-item label="源任务">
          <span>{{ copySource?.task_name ?? '-' }}</span>
        </el-form-item>
        <el-form-item label="新任务名称" required>
          <el-input v-model="copyForm.task_name" placeholder="请输入新任务名称" />
        </el-form-item>
        <el-form-item label="复制号码配置">
          <el-switch v-model="copyForm.copy_numbers" />
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="复制站点 / 队列 / 类型 / 场景 / 策略 / IVR 配置，不复制名单与执行数据；副本状态为草稿。"
        />
      </el-form>
      <template #footer>
        <el-button @click="copyVisible = false">取消</el-button>
        <el-button type="primary" :loading="copying" @click="onSubmitCopy">确定复制</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="predictionVisible" title="预测外呼并发建议" width="480px">
      <el-descriptions v-if="prediction" :column="1" border>
        <el-descriptions-item label="派单模式">
          {{ labelOf(DISPATCH_MODE_LABELS, prediction.dispatch_mode) }}
        </el-descriptions-item>
        <el-descriptions-item label="空闲坐席数">{{ prediction.available_agents }}</el-descriptions-item>
        <el-descriptions-item label="接通率">
          {{ (prediction.answer_rate * 100).toFixed(2) }}%
        </el-descriptions-item>
        <el-descriptions-item label="调整系数">{{ prediction.adjustment_factor }}</el-descriptions-item>
        <el-descriptions-item label="建议并发">{{ prediction.target_concurrency }}</el-descriptions-item>
        <el-descriptions-item label="未受限建议并发">{{ prediction.uncapped_target }}</el-descriptions-item>
        <el-descriptions-item label="任务并发上限">{{ prediction.max_concurrency }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="predictionVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import {
  DISPATCH_MODE_LABELS,
  DISPATCH_MODE_OPTIONS,
  NUMBER_STRATEGY_LABELS,
  NUMBER_STRATEGY_OPTIONS,
  TASK_STATUS_LABELS,
  TASK_STATUS_OPTIONS,
  labelOf,
} from '@/api/outbound/enums'
import {
  listSiteOptions,
  listSkillQueueOptions,
  listTenantOptions,
  type SiteOption,
  type SkillQueueOption,
  type TenantOption,
} from '@/api/outbound/common'
import { listOutboundNumbers, type OutboundNumber } from '@/api/outbound/number'
import { listIvrFlowOptions, type IvrFlowOption } from '@/api/outbound/ivr'
import { getOutboundSceneTree, type OutboundSceneTree } from '@/api/outbound/scene'
import { listOutboundTypes, type OutboundType } from '@/api/outbound/type'
import {
  changeOutboundTaskStatus,
  copyOutboundTask,
  createOutboundTask,
  deleteOutboundTask,
  getOutboundTask,
  listOutboundTasks,
  replaceTaskNumbers,
  updateOutboundTask,
  type DispatchMode,
  type NumberSelectStrategy,
  type OutboundTask,
  type OutboundTaskNumberItem,
  type OutboundTaskPayload,
  type OutboundTaskQuery,
  type TaskStatus,
} from '@/api/outbound/task'
import { getTaskPrediction, type OutboundPrediction } from '@/api/outbound/agent'
import StatusTag from '@/components/StatusTag.vue'

/** 前端镜像后端任务状态机，避免提交必然失败的流转（§18） */
const TASK_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  DRAFT: ['READY', 'CANCELLED'],
  READY: ['RUNNING', 'PAUSED', 'DRAFT', 'CANCELLED'],
  RUNNING: ['PAUSED', 'COMPLETED', 'CANCELLED'],
  PAUSED: ['RUNNING', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
}

const EDITABLE_STATUSES: TaskStatus[] = ['DRAFT', 'READY', 'PAUSED']
const DELETABLE_STATUSES: TaskStatus[] = ['DRAFT', 'CANCELLED']

const loading = ref(false)
const submitting = ref(false)
const rows = ref<OutboundTask[]>([])
const total = ref(0)

const tenants = ref<TenantOption[]>([])
const siteOptions = ref<SiteOption[]>([])
const queueOptions = ref<SkillQueueOption[]>([])
const typeOptions = ref<OutboundType[]>([])
const sceneTrees = ref<OutboundSceneTree[]>([])
const numberOptions = ref<OutboundNumber[]>([])
const ivrFlowOptions = ref<IvrFlowOption[]>([])

const query = reactive<OutboundTaskQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  task_name: '',
  site_id: undefined,
  skill_queue_id: undefined,
  type_id: undefined,
  scene_id: undefined,
  status: undefined,
  dispatch_mode: undefined,
})

const dialogVisible = ref(false)
const formTab = ref('base')
const isEdit = ref(false)
const currentId = ref<number | null>(null)
const formRef = ref<FormInstance>()

interface TaskNumberRow {
  number_id: number | null
  order_id: number | null
  user_id: number | null
  recipient_number: number | null
  priority: number
  enabled: boolean
}

interface TaskForm {
  tenant_id?: number
  task_name: string
  site_id: number | null
  skill_queue_id: number | null
  type_id: number | null
  scene_id: number | null
  dispatch_mode: DispatchMode
  number_select_strategy: NumberSelectStrategy
  retry_interval: number
  max_retry_count: number
  call_timeout_seconds: number
  max_concurrency: number
  adjustment_factor: number
  ivr_flow_id: number | null
  priority: number
  description: string
}

const form = reactive<TaskForm>({
  tenant_id: undefined,
  task_name: '',
  site_id: null,
  skill_queue_id: null,
  type_id: null,
  scene_id: null,
  dispatch_mode: 'MANUAL',
  number_select_strategy: 'ORDER',
  retry_interval: 60,
  max_retry_count: 3,
  call_timeout_seconds: 60,
  max_concurrency: 10,
  adjustment_factor: 1,
  ivr_flow_id: null,
  priority: 0,
  description: '',
})

const numberRows = ref<TaskNumberRow[]>([])

const formRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  task_name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
}

const copyVisible = ref(false)
const copying = ref(false)
const copySource = ref<OutboundTask | null>(null)
const copyForm = reactive({ task_name: '', copy_numbers: true })

const predictionVisible = ref(false)
const prediction = ref<OutboundPrediction | null>(null)

const dialogTitle = computed(() => (isEdit.value ? '编辑外呼任务' : '新增外呼任务'))

/** 把场景树展平，便于下拉与名称映射 */
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

const flatScenes = computed(() => flattenScenes(sceneTrees.value))

/** 筛选区场景：跟随筛选的类型联动 */
const filterSceneOptions = computed(() =>
  query.type_id ? flatScenes.value.filter((item) => item.type_id === query.type_id) : flatScenes.value,
)

/** 表单场景：跟随表单的类型联动 */
const formSceneOptions = computed(() =>
  form.type_id ? flatScenes.value.filter((item) => item.type_id === form.type_id) : flatScenes.value,
)

function nameOfSite(id: number | null): string {
  if (!id) return '-'
  return siteOptions.value.find((item) => item.id === id)?.name ?? `#${id}`
}

function nameOfQueue(id: number | null): string {
  if (!id) return '-'
  return queueOptions.value.find((item) => item.id === id)?.name ?? `#${id}`
}

function nameOfType(id: number | null): string {
  if (!id) return '-'
  return typeOptions.value.find((item) => item.id === id)?.name ?? `#${id}`
}

function nameOfScene(id: number | null): string {
  if (!id) return '-'
  return flatScenes.value.find((item) => item.id === id)?.name ?? `#${id}`
}

function transitionsOf(status: TaskStatus): TaskStatus[] {
  return TASK_TRANSITIONS[status] ?? []
}

function isNumberUsed(numberId: number, row: TaskNumberRow): boolean {
  return numberRows.value.some((item) => item !== row && item.number_id === numberId)
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listOutboundTasks(query)
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
    siteOptions.value = []
    queueOptions.value = []
    typeOptions.value = []
    sceneTrees.value = []
    numberOptions.value = []
    ivrFlowOptions.value = []
    return
  }
  const [sites, queues, types, scenes, numbers, ivrFlows] = await Promise.all([
    listSiteOptions({ tenant_id: tenantId }),
    listSkillQueueOptions({ tenant_id: tenantId }),
    listOutboundTypes({ tenant_id: tenantId, page_size: 200 }),
    getOutboundSceneTree({ tenant_id: tenantId }),
    listOutboundNumbers({ tenant_id: tenantId, page_size: 200 }),
    listIvrFlowOptions(tenantId),
  ])
  siteOptions.value = sites.data
  queueOptions.value = queues.data
  typeOptions.value = types.data.items
  sceneTrees.value = scenes.data
  numberOptions.value = numbers.data.items
  ivrFlowOptions.value = ivrFlows.data
}

function onTenantChange(): void {
  query.site_id = undefined
  query.skill_queue_id = undefined
  query.type_id = undefined
  query.scene_id = undefined
  void loadOptions(query.tenant_id).then(() => loadData())
}

function onTypeFilterChange(): void {
  query.scene_id = undefined
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.task_name = ''
  query.site_id = undefined
  query.skill_queue_id = undefined
  query.type_id = undefined
  query.scene_id = undefined
  query.status = undefined
  query.dispatch_mode = undefined
  onSearch()
}

function resetForm(): void {
  form.task_name = ''
  form.site_id = null
  form.skill_queue_id = null
  form.type_id = null
  form.scene_id = null
  form.dispatch_mode = 'MANUAL'
  form.number_select_strategy = 'ORDER'
  form.retry_interval = 60
  form.max_retry_count = 3
  form.call_timeout_seconds = 60
  form.max_concurrency = 10
  form.adjustment_factor = 1
  form.ivr_flow_id = null
  form.priority = 0
  form.description = ''
  numberRows.value = []
}

function addNumberRow(): void {
  numberRows.value.push({
    number_id: null,
    order_id: 1,
    user_id: null,
    recipient_number: null,
    priority: 0,
    enabled: true,
  })
}

function removeNumberRow(index: number): void {
  numberRows.value.splice(index, 1)
}

function onFormTenantChange(): void {
  form.site_id = null
  form.skill_queue_id = null
  form.type_id = null
  form.scene_id = null
  form.ivr_flow_id = null
  numberRows.value = []
  void loadOptions(form.tenant_id)
}

function onFormTypeChange(): void {
  form.scene_id = null
}

function collectNumbers(): OutboundTaskNumberItem[] {
  return numberRows.value
    .filter((row): row is TaskNumberRow & { number_id: number } => row.number_id !== null)
    .map((row, index) => ({
      number_id: row.number_id,
      order_id: row.order_id,
      user_id: row.user_id,
      recipient_number: row.recipient_number,
      sort_order: index,
      priority: row.priority,
      enabled: row.enabled,
    }))
}

async function openCreate(): Promise<void> {
  isEdit.value = false
  currentId.value = null
  formTab.value = 'base'
  resetForm()
  form.tenant_id = query.tenant_id ?? tenants.value[0]?.id
  await loadOptions(form.tenant_id)
  dialogVisible.value = true
}

async function openEdit(row: OutboundTask): Promise<void> {
  isEdit.value = true
  currentId.value = row.id
  formTab.value = 'base'
  resetForm()
  await loadOptions(row.tenant_id)
  const { data } = await getOutboundTask(row.id)
  form.tenant_id = data.tenant_id
  form.task_name = data.task_name
  form.site_id = data.site_id
  form.skill_queue_id = data.skill_queue_id
  form.type_id = data.type_id
  form.scene_id = data.scene_id
  form.dispatch_mode = data.dispatch_mode
  form.number_select_strategy = data.number_select_strategy
  form.retry_interval = data.retry_interval
  form.max_retry_count = data.max_retry_count
  form.call_timeout_seconds = data.call_timeout_seconds
  form.max_concurrency = data.max_concurrency
  form.adjustment_factor = Number(data.adjustment_factor)
  form.ivr_flow_id = data.ivr_flow_id
  form.priority = data.priority
  form.description = data.description
  numberRows.value = data.task_numbers.map((item) => ({
    number_id: item.number_id,
    order_id: item.order_id,
    user_id: item.user_id,
    recipient_number: item.recipient_number,
    priority: item.priority,
    enabled: item.enabled,
  }))
  dialogVisible.value = true
}

function buildPayload(): OutboundTaskPayload {
  return {
    task_name: form.task_name,
    site_id: form.site_id,
    skill_queue_id: form.skill_queue_id,
    type_id: form.type_id,
    scene_id: form.scene_id,
    dispatch_mode: form.dispatch_mode,
    number_select_strategy: form.number_select_strategy,
    retry_interval: form.retry_interval,
    max_retry_count: form.max_retry_count,
    call_timeout_seconds: form.call_timeout_seconds,
    max_concurrency: form.max_concurrency,
    adjustment_factor: form.adjustment_factor,
    ivr_flow_id: form.ivr_flow_id,
    priority: form.priority,
    description: form.description,
  }
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  const numbers = collectNumbers()
  submitting.value = true
  try {
    if (isEdit.value && currentId.value !== null) {
      // 更新接口不接受 tenant_id 与号码配置，号码配置走独立的全量替换接口（§19）
      await updateOutboundTask(currentId.value, buildPayload())
      await replaceTaskNumbers(currentId.value, numbers)
      ElMessage.success('保存成功')
    } else {
      await createOutboundTask({ ...buildPayload(), tenant_id: form.tenant_id, numbers })
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    await loadOptions(query.tenant_id)
    await loadData()
  } finally {
    submitting.value = false
  }
}

async function onChangeStatus(row: OutboundTask, target: TaskStatus): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认把任务「${row.task_name}」流转为「${labelOf(TASK_STATUS_LABELS, target)}」？`,
      '状态流转确认',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await changeOutboundTaskStatus(row.id, target)
  ElMessage.success('状态已更新')
  await loadData()
}

function openCopy(row: OutboundTask): void {
  copySource.value = row
  copyForm.task_name = `${row.task_name}_副本`
  copyForm.copy_numbers = true
  copyVisible.value = true
}

async function onSubmitCopy(): Promise<void> {
  if (!copySource.value) return
  if (!copyForm.task_name.trim()) {
    ElMessage.warning('请输入新任务名称')
    return
  }
  copying.value = true
  try {
    const { data } = await copyOutboundTask(copySource.value.id, {
      task_name: copyForm.task_name.trim(),
      copy_numbers: copyForm.copy_numbers,
    })
    ElMessage.success(data.created ? '复制成功' : '已存在同名副本，直接返回该副本')
    copyVisible.value = false
    await loadData()
  } finally {
    copying.value = false
  }
}

async function openPrediction(row: OutboundTask): Promise<void> {
  const { data } = await getTaskPrediction(row.id)
  prediction.value = data
  predictionVisible.value = true
}

async function onDelete(row: OutboundTask): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除外呼任务「${row.task_name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  const { data } = await deleteOutboundTask(row.id)
  ElMessage.success(`删除成功，联动删除号码配置 ${data.removed_task_numbers} 条`)
  await loadData()
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

.filter-select-sm {
  width: 130px;
}

.full-width {
  width: 100%;
}

.form-tip {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.number-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.page-toolbar__total {
  color: #606266;
}
</style>
