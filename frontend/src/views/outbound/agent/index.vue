<template>
  <div class="page-container">
    <el-card shadow="never">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="坐席管理" name="agents">
          <el-form :inline="true" :model="agentQuery" @submit.prevent>
            <el-form-item label="租户">
              <el-select
                v-model="agentQuery.tenant_id"
                placeholder="全部"
                clearable
                class="filter-select"
                @change="onAgentTenantChange"
              >
                <el-option
                  v-for="item in tenants"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="站点">
              <el-select
                v-model="agentQuery.site_id"
                placeholder="全部"
                clearable
                class="filter-select"
              >
                <el-option
                  v-for="item in sites"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="技能队列">
              <el-select
                v-model="agentQuery.skill_queue_id"
                placeholder="全部"
                clearable
                class="filter-select"
              >
                <el-option
                  v-for="item in skillQueues"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="坐席状态">
              <el-select
                v-model="agentQuery.status"
                placeholder="全部"
                clearable
                class="filter-select-sm"
              >
                <el-option
                  v-for="item in AGENT_STATUS_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="onSearchAgents">查询</el-button>
              <el-button :icon="Refresh" @click="onResetAgents">重置</el-button>
            </el-form-item>
          </el-form>

          <div class="page-toolbar">
            <span class="page-toolbar__total">共 {{ agentTotal }} 条</span>
            <div class="page-toolbar__actions">
              <el-button
                v-permission="'outbound:agent:create'"
                type="primary"
                :icon="Plus"
                @click="openAgentCreate"
              >
                新增坐席
              </el-button>
              <el-button
                v-permission="'outbound:assignment:dispatch'"
                :icon="Promotion"
                @click="onDispatch"
              >
                触发自动派单
              </el-button>
            </div>
          </div>

          <el-table v-loading="agentLoading" :data="agents" border stripe>
            <el-table-column prop="id" label="坐席ID" width="90" />
            <el-table-column prop="user_id" label="用户ID" width="100" />
            <el-table-column label="分机号" width="120">
              <template #default="{ row }">{{ row.extension || '-' }}</template>
            </el-table-column>
            <el-table-column label="技能队列" min-width="140">
              <template #default="{ row }">
                {{ nameOf(queueNameMap, row.skill_queue_id) }}
              </template>
            </el-table-column>
            <el-table-column label="站点" min-width="140">
              <template #default="{ row }">{{ nameOf(siteNameMap, row.site_id) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="最后示闲时间" width="180">
              <template #default="{ row }">{{ row.last_idle_at || '-' }}</template>
            </el-table-column>
            <el-table-column label="最后置忙时间" width="180">
              <template #default="{ row }">{{ row.last_busy_at || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="250" fixed="right">
              <template #default="{ row }">
                <el-dropdown
                  v-permission="'outbound:agent:update'"
                  trigger="click"
                  @command="(status: string) => onChangeStatus(row, status)"
                >
                  <el-button link type="primary">
                    变更状态
                    <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="item in statusOptionsFor(row)"
                        :key="item.value"
                        :command="item.value"
                      >
                        {{ item.label }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <el-button
                  v-permission="'outbound:agent:update'"
                  link
                  type="primary"
                  @click="openAgentEdit(row)"
                >
                  编辑
                </el-button>
                <el-button link type="primary" @click="onShowLogs(row)">状态历史</el-button>
                <el-button
                  v-permission="'outbound:agent:delete'"
                  link
                  type="danger"
                  @click="onDeleteAgent(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="agentQuery.page"
              v-model:page-size="agentQuery.page_size"
              :total="agentTotal"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="loadAgents"
              @size-change="onSearchAgents"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="预占与派单" name="assignments">
          <el-form :inline="true" :model="assignmentQuery" @submit.prevent>
            <el-form-item label="租户">
              <el-select
                v-model="assignmentQuery.tenant_id"
                placeholder="全部"
                clearable
                class="filter-select"
                @change="onAssignmentTenantChange"
              >
                <el-option
                  v-for="item in tenants"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="坐席">
              <el-select
                v-model="assignmentQuery.agent_id"
                placeholder="全部"
                clearable
                class="filter-select"
              >
                <el-option
                  v-for="item in agentOptions"
                  :key="item.id"
                  :label="agentLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="外呼任务">
              <el-select
                v-model="assignmentQuery.task_id"
                placeholder="全部"
                clearable
                class="filter-select"
              >
                <el-option
                  v-for="item in tasks"
                  :key="item.id"
                  :label="taskLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="预占状态">
              <el-select
                v-model="assignmentQuery.status"
                placeholder="全部"
                clearable
                class="filter-select-sm"
              >
                <el-option
                  v-for="item in ASSIGNMENT_STATUS_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="onSearchAssignments">查询</el-button>
              <el-button :icon="Refresh" @click="onResetAssignments">重置</el-button>
            </el-form-item>
          </el-form>

          <div class="page-toolbar">
            <span class="page-toolbar__total">共 {{ assignmentTotal }} 条</span>
            <div class="page-toolbar__actions">
              <el-button
                v-permission="'outbound:assignment:dispatch'"
                type="primary"
                :icon="Refresh"
                @click="onExpire"
              >
                释放超时预占
              </el-button>
            </div>
          </div>

          <el-table v-loading="assignmentLoading" :data="assignments" border stripe>
            <el-table-column prop="id" label="ID" width="90" />
            <el-table-column prop="agent_id" label="坐席ID" width="100" />
            <el-table-column label="任务ID" width="100">
              <template #default="{ row }">{{ row.task_id ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="记录ID" width="100">
              <template #default="{ row }">{{ row.record_id ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="预占时间" width="180">
              <template #default="{ row }">{{ row.reserved_at || '-' }}</template>
            </el-table-column>
            <el-table-column label="过期时间" width="180">
              <template #default="{ row }">{{ row.expires_at || '-' }}</template>
            </el-table-column>
            <el-table-column label="释放时间" width="180">
              <template #default="{ row }">{{ row.released_at || '-' }}</template>
            </el-table-column>
            <el-table-column label="释放原因" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.release_reason || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-permission="'outbound:agent:update'"
                  link
                  type="primary"
                  :disabled="row.status !== 'RESERVED'"
                  @click="onAccept(row)"
                >
                  接单
                </el-button>
                <el-button
                  v-permission="'outbound:assignment:release'"
                  link
                  type="warning"
                  :disabled="row.status !== 'RESERVED' && row.status !== 'ACCEPTED'"
                  @click="onRelease(row)"
                >
                  释放
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="assignmentQuery.page"
              v-model:page-size="assignmentQuery.page_size"
              :total="assignmentTotal"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="loadAssignments"
              @size-change="onSearchAssignments"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="logDialogVisible" title="坐席状态历史" width="760px">
      <el-table v-loading="logLoading" :data="logRows" border stripe>
        <el-table-column prop="created_at" label="变更时间" width="180" />
        <el-table-column label="原状态" width="100">
          <template #default="{ row }">
            {{ labelOf(AGENT_STATUS_LABELS, row.from_status) }}
          </template>
        </el-table-column>
        <el-table-column label="新状态" width="100">
          <template #default="{ row }">{{ labelOf(AGENT_STATUS_LABELS, row.to_status) }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作人" width="100">
          <template #default="{ row }">{{ row.operator_id ?? '-' }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="logDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 坐席新增 / 编辑（规则 8） -->
    <el-dialog v-model="agentDialogVisible" :title="agentDialogTitle" width="520px">
      <el-form ref="agentFormRef" :model="agentForm" :rules="agentRules" label-width="100px">
        <el-form-item label="租户" prop="tenant_id">
          <el-select
            v-model="agentForm.tenant_id"
            placeholder="请选择租户"
            :disabled="isAgentEdit"
            class="full-width"
            @change="onAgentFormTenantChange"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联用户" prop="user_id">
          <el-select
            v-model="agentForm.user_id"
            placeholder="请选择要开通坐席的用户"
            filterable
            :disabled="isAgentEdit"
            class="full-width"
          >
            <el-option
              v-for="item in userOptions"
              :key="item.id"
              :label="`${item.nickname || item.username}（${item.username}）`"
              :value="item.id"
            />
          </el-select>
          <span v-if="isAgentEdit" class="form-tip">关联用户创建后不可修改</span>
        </el-form-item>
        <el-form-item label="站点">
          <el-select
            v-model="agentForm.site_id"
            placeholder="可选"
            clearable
            class="full-width"
            @change="onAgentSiteChange"
          >
            <el-option
              v-for="item in sites"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="技能队列">
          <el-select
            v-model="agentForm.skill_queue_id"
            placeholder="可选；派单时优先匹配该队列"
            clearable
            class="full-width"
          >
            <el-option
              v-for="item in skillQueues"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="分机号">
          <el-input v-model="agentForm.extension" placeholder="可选" maxlength="32" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="agentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="agentSubmitting" @click="onSubmitAgent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ArrowDown, Plus, Promotion, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import {
  listAgentOptions,
  listSkillQueueOptions,
  listSiteOptions,
  listTaskOptions,
  listTenantOptions,
  listUserOptions,
  type AgentOption,
  type SiteOption,
  type SkillQueueOption,
  type TaskOption,
  type TenantOption,
  type UserOption,
} from '@/api/outbound/common'
import {
  AGENT_STATUS_LABELS,
  AGENT_STATUS_OPTIONS,
  ASSIGNMENT_STATUS_OPTIONS,
  labelOf,
  type Option,
} from '@/api/outbound/enums'
import {
  acceptAssignment,
  changeAgentStatus,
  createOutboundAgent,
  deleteOutboundAgent,
  dispatchAssignments,
  expireAssignments,
  listAgentStatusLogs,
  listAssignments,
  listOutboundAgents,
  releaseAssignment,
  updateOutboundAgent,
  type AgentAssignment,
  type AgentAssignmentQuery,
  type AgentStatus,
  type AgentStatusLog,
  type OutboundAgent,
  type OutboundAgentQuery,
} from '@/api/outbound/agent'
import StatusTag from '@/components/StatusTag.vue'

type TabName = 'agents' | 'assignments'

const activeTab = ref<TabName>('agents')

/** 下拉选项与名称映射 */
const tenants = ref<TenantOption[]>([])
const sites = ref<SiteOption[]>([])
const skillQueues = ref<SkillQueueOption[]>([])
const agentOptions = ref<AgentOption[]>([])
const tasks = ref<TaskOption[]>([])
const userOptions = ref<UserOption[]>([])

/** 坐席新增 / 编辑弹窗（规则 8） */
const agentDialogVisible = ref(false)
const isAgentEdit = ref(false)
const editingAgentId = ref<number | null>(null)
const agentSubmitting = ref(false)
const agentFormRef = ref<FormInstance>()
const agentForm = reactive<{
  tenant_id?: number
  user_id?: number
  site_id: number | null
  skill_queue_id: number | null
  extension: string
}>({
  tenant_id: undefined,
  user_id: undefined,
  site_id: null,
  skill_queue_id: null,
  extension: '',
})

const agentRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  user_id: [{ required: true, message: '请选择关联用户', trigger: 'change' }],
}

const agentDialogTitle = computed(() => (isAgentEdit.value ? '编辑坐席' : '新增坐席'))

/** 坐席列表 */
const agentLoading = ref(false)
const agents = ref<OutboundAgent[]>([])
const agentTotal = ref(0)
const agentQuery = reactive<OutboundAgentQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  site_id: undefined,
  skill_queue_id: undefined,
  status: undefined,
})

/** 预占列表 */
const assignmentLoading = ref(false)
const assignments = ref<AgentAssignment[]>([])
const assignmentTotal = ref(0)
const assignmentQuery = reactive<AgentAssignmentQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  agent_id: undefined,
  task_id: undefined,
  status: undefined,
})

/** 坐席状态历史弹窗 */
const logDialogVisible = ref(false)
const logLoading = ref(false)
const logRows = ref<AgentStatusLog[]>([])

const siteNameMap = computed(() => {
  const map = new Map<number, string>()
  sites.value.forEach((item) => map.set(item.id, item.name))
  return map
})

const queueNameMap = computed(() => {
  const map = new Map<number, string>()
  skillQueues.value.forEach((item) => map.set(item.id, item.name))
  return map
})

function nameOf(map: Map<number, string>, id: number | null): string {
  if (!id) return '-'
  return map.get(id) ?? '-'
}

function agentLabel(option: AgentOption): string {
  return option.extension ? `#${option.id} ${option.extension}` : `#${option.id}`
}

function taskLabel(task: TaskOption): string {
  return `#${task.id} ${task.task_name}`
}

function statusOptionsFor(row: OutboundAgent): Option[] {
  return AGENT_STATUS_OPTIONS.filter((item) => item.value !== row.status)
}

async function loadTenants(): Promise<void> {
  const { data } = await listTenantOptions()
  tenants.value = data
  if (data.length > 0) {
    if (!agentQuery.tenant_id) agentQuery.tenant_id = data[0].id
    if (!assignmentQuery.tenant_id) assignmentQuery.tenant_id = data[0].id
  }
}

async function loadAgentRefs(): Promise<void> {
  const userRes = await listUserOptions()
  userOptions.value = userRes.data
  if (!agentQuery.tenant_id) {
    sites.value = []
    skillQueues.value = []
    return
  }
  const [siteRes, queueRes] = await Promise.all([
    listSiteOptions({ tenant_id: agentQuery.tenant_id }),
    listSkillQueueOptions({ tenant_id: agentQuery.tenant_id }),
  ])
  sites.value = siteRes.data
  skillQueues.value = queueRes.data
}

// ---------- 坐席 CRUD（规则 8） ----------

function openAgentCreate(): void {
  isAgentEdit.value = false
  editingAgentId.value = null
  agentForm.tenant_id = agentQuery.tenant_id ?? tenants.value[0]?.id
  agentForm.user_id = undefined
  agentForm.site_id = null
  agentForm.skill_queue_id = null
  agentForm.extension = ''
  agentDialogVisible.value = true
}

function openAgentEdit(row: OutboundAgent): void {
  isAgentEdit.value = true
  editingAgentId.value = row.id
  agentForm.tenant_id = row.tenant_id
  agentForm.user_id = row.user_id
  agentForm.site_id = row.site_id
  agentForm.skill_queue_id = row.skill_queue_id
  agentForm.extension = row.extension ?? ''
  agentDialogVisible.value = true
}

/** 表单内切换租户：站点/队列需属于同一租户，先清空再重选 */
function onAgentFormTenantChange(): void {
  agentForm.site_id = null
  agentForm.skill_queue_id = null
}

/** 站点变化时清掉不属于该站点的技能队列，避免提交被后端拒绝 */
function onAgentSiteChange(): void {
  const current = agentForm.skill_queue_id
  if (!current) return
  const queue = skillQueues.value.find((item) => item.id === current)
  if (agentForm.site_id && queue && queue.site_id !== agentForm.site_id) {
    agentForm.skill_queue_id = null
  }
}

async function onSubmitAgent(): Promise<void> {
  if (!agentFormRef.value) return
  const valid = await agentFormRef.value.validate().catch(() => false)
  if (!valid) return

  agentSubmitting.value = true
  try {
    if (isAgentEdit.value && editingAgentId.value !== null) {
      // 关联用户与归属租户创建后不可修改，只提交可调整字段
      await updateOutboundAgent(editingAgentId.value, {
        site_id: agentForm.site_id,
        skill_queue_id: agentForm.skill_queue_id,
        extension: agentForm.extension || null,
      })
      ElMessage.success('保存成功')
    } else {
      await createOutboundAgent({
        tenant_id: agentForm.tenant_id as number,
        user_id: agentForm.user_id as number,
        site_id: agentForm.site_id,
        skill_queue_id: agentForm.skill_queue_id,
        extension: agentForm.extension || null,
      })
      ElMessage.success('新增成功')
    }
    agentDialogVisible.value = false
    await loadAgents()
  } finally {
    agentSubmitting.value = false
  }
}

async function onDeleteAgent(row: OutboundAgent): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除坐席 #${row.id}（用户 ${row.user_id}）？删除后该账号不再接单。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await deleteOutboundAgent(row.id)
  ElMessage.success('删除成功')
  await loadAgents()
}

async function loadAssignmentRefs(): Promise<void> {
  if (!assignmentQuery.tenant_id) {
    agentOptions.value = []
    tasks.value = []
    return
  }
  const [agentRes, taskRes] = await Promise.all([
    listAgentOptions({ tenant_id: assignmentQuery.tenant_id }),
    // 走选项接口而非任务列表接口：本页不需要 outbound:task:list 权限
    listTaskOptions(assignmentQuery.tenant_id),
  ])
  agentOptions.value = agentRes.data
  tasks.value = taskRes.data.map((item) => ({
    id: item.id,
    tenant_id: item.tenant_id,
    task_name: item.task_name,
  }))
}

async function loadAgents(): Promise<void> {
  agentLoading.value = true
  try {
    const { data } = await listOutboundAgents(agentQuery)
    agents.value = data.items
    agentTotal.value = data.total
  } finally {
    agentLoading.value = false
  }
}

async function loadAssignments(): Promise<void> {
  assignmentLoading.value = true
  try {
    const { data } = await listAssignments(assignmentQuery)
    assignments.value = data.items
    assignmentTotal.value = data.total
  } finally {
    assignmentLoading.value = false
  }
}

function onTabChange(): void {
  if (activeTab.value === 'agents') {
    void loadAgents()
  } else {
    void loadAssignments()
  }
}

function onSearchAgents(): void {
  agentQuery.page = 1
  void loadAgents()
}

function onResetAgents(): void {
  agentQuery.site_id = undefined
  agentQuery.skill_queue_id = undefined
  agentQuery.status = undefined
  onSearchAgents()
}

async function onAgentTenantChange(): Promise<void> {
  agentQuery.site_id = undefined
  agentQuery.skill_queue_id = undefined
  await loadAgentRefs()
  onSearchAgents()
}

function onSearchAssignments(): void {
  assignmentQuery.page = 1
  void loadAssignments()
}

function onResetAssignments(): void {
  assignmentQuery.agent_id = undefined
  assignmentQuery.task_id = undefined
  assignmentQuery.status = undefined
  onSearchAssignments()
}

async function onAssignmentTenantChange(): Promise<void> {
  assignmentQuery.agent_id = undefined
  assignmentQuery.task_id = undefined
  await loadAssignmentRefs()
  onSearchAssignments()
}

/** 触发自动派单：扫描空闲坐席并为其分配待处理记录 */
async function onDispatch(): Promise<void> {
  const { data } = await dispatchAssignments({ tenant_id: agentQuery.tenant_id, limit: 50 })
  ElMessage.success(
    `扫描空闲坐席 ${data.agents_scanned} 个，成功派单 ${data.assigned} 单，跳过 ${data.skipped} 个`,
  )
  await loadAgents()
  await loadAssignments()
}

/** 释放超时预占 */
async function onExpire(): Promise<void> {
  const { data } = await expireAssignments(100)
  ElMessage.success(`扫描 ${data.scanned} 条，释放 ${data.released} 条，跳过 ${data.skipped} 条`)
  await loadAssignments()
}

/** 变更坐席状态（置为 IDLE 时后端会立即触发自动分配） */
async function onChangeStatus(row: OutboundAgent, status: string): Promise<void> {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入状态变更原因（可留空）', '变更坐席状态', {
      inputValue: '',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    reason = value ?? ''
  } catch {
    return
  }
  const { data } = await changeAgentStatus(row.id, status as AgentStatus, {
    reason,
    auto_assign: true,
  })
  let message = `状态已变更为${labelOf(AGENT_STATUS_LABELS, data.to_status)}`
  if (data.assignment) {
    message += `；已自动派单：任务 #${data.assignment.task_id} / 记录 #${data.assignment.record_id}`
  }
  ElMessage.success(message)
  await loadAgents()
  await loadAssignments()
}

async function onShowLogs(row: OutboundAgent): Promise<void> {
  logDialogVisible.value = true
  logLoading.value = true
  try {
    const { data } = await listAgentStatusLogs(row.id, 50)
    logRows.value = data
  } finally {
    logLoading.value = false
  }
}

/** 接单 */
async function onAccept(row: AgentAssignment): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认接单预占记录 #${row.id}？`, '接单确认', {
      type: 'warning',
      confirmButtonText: '确定接单',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await acceptAssignment(row.id)
  ElMessage.success('接单成功')
  await loadAssignments()
}

/** 释放预占 */
async function onRelease(row: AgentAssignment): Promise<void> {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入释放原因', '释放预占', {
      inputValue: '',
      confirmButtonText: '确定释放',
      cancelButtonText: '取消',
    })
    reason = value ?? ''
  } catch {
    return
  }
  await releaseAssignment(row.id, reason)
  ElMessage.success('释放成功')
  await loadAssignments()
}

onMounted(async () => {
  await loadTenants()
  await loadAgentRefs()
  await loadAssignmentRefs()
  await loadAgents()
})
</script>

<style scoped>
.filter-select {
  width: 180px;
}

.filter-select-sm {
  width: 120px;
}

.page-toolbar__total {
  color: #606266;
}
</style>
