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
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" clearable class="filter-select-sm">
            <el-option
              v-for="item in QC_TASK_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="任务名称">
          <el-input
            v-model="query.keyword"
            placeholder="模糊匹配"
            clearable
            @keyup.enter="onSearch"
          />
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
            v-permission="'qc:task:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增任务
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="task_name" label="任务名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="专家组" width="150">
          <template #default="{ row }">{{ nameOfGroup(row.group_id) }}</template>
        </el-table-column>
        <el-table-column label="对话时间区间" min-width="330">
          <template #default="{ row }">{{ row.time_from }} ~ {{ row.time_to }}</template>
        </el-table-column>
        <el-table-column label="派发方式" width="110">
          <template #default="{ row }">
            {{ labelOf(QC_DISPATCH_MODE_LABELS, row.dispatch_mode) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.status" :labels="QC_TASK_STATUS_LABELS" />
          </template>
        </el-table-column>
        <el-table-column label="总数" width="80">
          <template #default="{ row }">{{ row.total_items }}</template>
        </el-table-column>
        <el-table-column label="已完成" width="90">
          <template #default="{ row }">{{ row.completed_items }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'qc:task:dispatch'"
              link
              type="primary"
              :disabled="row.status !== 'DRAFT'"
              @click="onDispatch(row)"
            >
              派发
            </el-button>
            <el-button link type="primary" @click="openDrawer(row)">明细</el-button>
            <el-button
              v-permission="'qc:task:update'"
              link
              type="primary"
              :disabled="row.status !== 'DRAFT'"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-permission="'qc:task:cancel'"
              link
              type="warning"
              :disabled="!CANCELLABLE_STATUSES.includes(row.status)"
              @click="onCancel(row)"
            >
              取消
            </el-button>
            <el-button
              v-permission="'qc:task:delete'"
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

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px">
        <el-form-item label="租户" prop="tenant_id">
          <el-select
            v-model="form.tenant_id"
            placeholder="请选择租户"
            :disabled="isEdit"
            class="full-width"
            @change="onFormTenantChange"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务名称" prop="task_name">
          <el-input v-model="form.task_name" placeholder="同租户下任务名唯一" />
        </el-form-item>
        <el-form-item label="专家组" prop="group_id">
          <el-select
            v-model="form.group_id"
            placeholder="请选择专家组"
            filterable
            class="full-width"
          >
            <el-option v-for="item in groups" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="质检时间区间" prop="time_range">
          <el-date-picker
            v-model="form.time_range"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            class="full-width"
          />
          <div class="form-tip">按对话开始时间圈定质检范围</div>
        </el-form-item>
        <el-form-item label="派发方式">
          <el-select v-model="form.dispatch_mode" class="full-width">
            <el-option
              v-for="item in QC_DISPATCH_MODE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="900px">
      <el-descriptions v-if="report" :column="5" border size="small" class="report-bar">
        <el-descriptions-item label="总数">{{ report.total }}</el-descriptions-item>
        <el-descriptions-item label="已完成">{{ report.completed }}</el-descriptions-item>
        <el-descriptions-item label="待质检">{{ report.pending }}</el-descriptions-item>
        <el-descriptions-item label="质检中">{{ report.reviewing }}</el-descriptions-item>
        <el-descriptions-item label="完成率">{{ completionPercent }}</el-descriptions-item>
      </el-descriptions>

      <el-form :inline="true" :model="itemQuery" class="drawer-filter" @submit.prevent>
        <el-form-item label="明细状态">
          <el-select
            v-model="itemQuery.status"
            placeholder="全部"
            clearable
            class="filter-select-sm"
            @change="onItemSearch"
          >
            <el-option
              v-for="item in QC_ITEM_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="专家">
          <el-select
            v-model="itemQuery.reviewer_id"
            placeholder="全部"
            clearable
            filterable
            class="filter-select"
            @change="onItemSearch"
          >
            <el-option
              v-for="item in reviewers"
              :key="item.id"
              :label="reviewerLabel(item)"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="等级">
          <el-select
            v-model="itemQuery.grade"
            placeholder="全部"
            clearable
            class="filter-select-sm"
            @change="onItemSearch"
          >
            <el-option
              v-for="item in QC_GRADE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <el-table v-loading="itemLoading" :data="items" border stripe size="small">
        <el-table-column prop="id" label="明细 ID" width="90" />
        <el-table-column prop="conversation_id" label="对话 ID" width="90" />
        <el-table-column label="专家" width="110">
          <template #default="{ row }">{{ row.reviewer_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.status" :labels="QC_ITEM_STATUS_LABELS" />
          </template>
        </el-table-column>
        <el-table-column label="等级" width="100">
          <template #default="{ row }">
            <el-tag
              v-if="row.grade"
              :type="QC_GRADE_TAG_TYPES[row.grade]"
              disable-transitions
            >
              {{ labelOf(QC_GRADE_LABELS, row.grade) }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="领取时间" width="170">
          <template #default="{ row }">{{ row.locked_at ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ row.submitted_at ?? '-' }}</template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="itemQuery.page"
          v-model:page-size="itemQuery.page_size"
          :total="itemTotal"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadItems"
          @size-change="onItemSearch"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import { listTenantOptions, type TenantOption } from '@/api/outbound/common'
import {
  QC_DISPATCH_MODE_LABELS,
  QC_DISPATCH_MODE_OPTIONS,
  QC_GRADE_LABELS,
  QC_GRADE_OPTIONS,
  QC_GRADE_TAG_TYPES,
  QC_ITEM_STATUS_LABELS,
  QC_ITEM_STATUS_OPTIONS,
  QC_TASK_STATUS_LABELS,
  QC_TASK_STATUS_OPTIONS,
  labelOf,
} from '@/api/qc/enums'
import type { QcReportOverview } from '@/api/qc/report'
import {
  listAssignableReviewers,
  listReviewerGroups,
  type ReviewerGroup,
  type ReviewerUser,
} from '@/api/qc/reviewers'
import {
  cancelQcTask,
  createQcTask,
  deleteQcTask,
  dispatchQcTask,
  getQcTask,
  getQcTaskReport,
  listQcTaskItems,
  listQcTasks,
  updateQcTask,
  type QcDispatchMode,
  type QcTask,
  type QcTaskItem,
  type QcTaskItemQuery,
  type QcTaskPayload,
  type QcTaskQuery,
  type QcTaskStatus,
  type QcTaskUpdatePayload,
} from '@/api/qc/tasks'
import StatusTag from '@/components/StatusTag.vue'

/** 可取消的任务状态 */
const CANCELLABLE_STATUSES: QcTaskStatus[] = ['DRAFT', 'DISPATCHED', 'REVIEWING']
/** 可删除的任务状态 */
const DELETABLE_STATUSES: QcTaskStatus[] = ['DRAFT', 'CANCELLED']

const loading = ref(false)
const submitting = ref(false)
const rows = ref<QcTask[]>([])
const total = ref(0)

const tenants = ref<TenantOption[]>([])
const groups = ref<ReviewerGroup[]>([])
const reviewers = ref<ReviewerUser[]>([])

const query = reactive<QcTaskQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  status: undefined,
  keyword: '',
})

const dialogVisible = ref(false)
const isEdit = ref(false)
const currentId = ref<number | null>(null)
const formRef = ref<FormInstance>()

interface QcTaskForm {
  tenant_id?: number
  task_name: string
  group_id: number | null
  time_range: [Date, Date] | null
  dispatch_mode: QcDispatchMode
}

const form = reactive<QcTaskForm>({
  tenant_id: undefined,
  task_name: '',
  group_id: null,
  time_range: null,
  dispatch_mode: 'ROUND_ROBIN',
})

const formRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  task_name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  group_id: [{ required: true, message: '请选择专家组', trigger: 'change' }],
  time_range: [{ required: true, message: '请选择质检时间区间', trigger: 'change' }],
}

const drawerVisible = ref(false)
const drawerTask = ref<QcTask | null>(null)
const report = ref<QcReportOverview | null>(null)
const itemLoading = ref(false)
const items = ref<QcTaskItem[]>([])
const itemTotal = ref(0)

const itemQuery = reactive<QcTaskItemQuery>({
  page: 1,
  page_size: 20,
  status: undefined,
  reviewer_id: undefined,
  grade: undefined,
})

const dialogTitle = computed(() => (isEdit.value ? '编辑质检任务' : '新增质检任务'))

const drawerTitle = computed(() =>
  drawerTask.value ? `质检任务「${drawerTask.value.task_name}」明细` : '质检任务明细',
)

const completionPercent = computed(() => {
  const rate = report.value?.completion_rate ?? 0
  return `${(rate * 100).toFixed(2)}%`
})

function nameOfGroup(groupId: number | null): string {
  if (!groupId) return '-'
  return groups.value.find((item) => item.id === groupId)?.name ?? `#${groupId}`
}

function reviewerLabel(item: ReviewerUser): string {
  return item.nickname ? `${item.nickname}（${item.username}）` : item.username
}

async function loadTenants(): Promise<void> {
  const { data } = await listTenantOptions()
  tenants.value = data
  if (!query.tenant_id && data.length > 0) {
    query.tenant_id = data[0].id
  }
}

/** 专家组下拉：无 qc:reviewer:list 权限时静默降级为显示 #id */
async function loadGroups(tenantId?: number): Promise<void> {
  if (!tenantId) {
    groups.value = []
    return
  }
  try {
    const { data } = await listReviewerGroups({ tenant_id: tenantId, page_size: 200 })
    groups.value = data.items
  } catch {
    groups.value = []
  }
}

/** 专家下拉：无 qc:reviewer:list 权限时静默降级 */
async function loadReviewers(tenantId?: number): Promise<void> {
  if (!tenantId) {
    reviewers.value = []
    return
  }
  try {
    const { data } = await listAssignableReviewers({ tenant_id: tenantId, page_size: 200 })
    reviewers.value = data.items
  } catch {
    reviewers.value = []
  }
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listQcTasks(query)
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onTenantChange(): void {
  void loadGroups(query.tenant_id).then(() => loadData())
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.keyword = ''
  query.status = undefined
  onSearch()
}

function resetForm(): void {
  form.task_name = ''
  form.group_id = null
  form.dispatch_mode = 'ROUND_ROBIN'
  form.time_range = null
}

async function openCreate(): Promise<void> {
  isEdit.value = false
  currentId.value = null
  resetForm()
  form.tenant_id = query.tenant_id ?? tenants.value[0]?.id
  await loadGroups(form.tenant_id)
  dialogVisible.value = true
}

async function openEdit(row: QcTask): Promise<void> {
  isEdit.value = true
  currentId.value = row.id
  resetForm()
  form.tenant_id = row.tenant_id
  await loadGroups(row.tenant_id)
  const { data } = await getQcTask(row.id)
  form.task_name = data.task_name
  form.group_id = data.group_id
  form.dispatch_mode = data.dispatch_mode
  form.time_range = [new Date(data.time_from), new Date(data.time_to)]
  dialogVisible.value = true
}

function onFormTenantChange(): void {
  form.group_id = null
  void loadGroups(form.tenant_id)
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  const tenantId = form.tenant_id
  const groupId = form.group_id
  const range = form.time_range
  if (!tenantId || !groupId || !range) return

  const timeFrom = range[0].toISOString()
  const timeTo = range[1].toISOString()

  submitting.value = true
  try {
    if (isEdit.value && currentId.value !== null) {
      // 编辑接口不接受 tenant_id，且后端仅允许 DRAFT 状态编辑
      const payload: QcTaskUpdatePayload = {
        task_name: form.task_name,
        group_id: groupId,
        time_from: timeFrom,
        time_to: timeTo,
        dispatch_mode: form.dispatch_mode,
      }
      await updateQcTask(currentId.value, payload)
      ElMessage.success('保存成功')
    } else {
      const payload: QcTaskPayload = {
        tenant_id: tenantId,
        task_name: form.task_name,
        group_id: groupId,
        time_from: timeFrom,
        time_to: timeTo,
        dispatch_mode: form.dispatch_mode,
      }
      await createQcTask(payload)
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    await loadData()
  } finally {
    submitting.value = false
  }
}

async function onDispatch(row: QcTask): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将把时间区间内的对话按专家组启用成员派发，重复派发不会产生重复明细',
      '派发确认',
      { type: 'warning', confirmButtonText: '确定派发', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const { data } = await dispatchQcTask(row.id)
  ElMessage.success(
    `派发完成：明细 ${data.total_items} 条，参与专家 ${data.reviewer_count} 人`,
  )
  await loadData()
}

async function onCancel(row: QcTask): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认取消质检任务「${row.task_name}」？`, '取消确认', {
      type: 'warning',
      confirmButtonText: '确定取消',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await cancelQcTask(row.id)
  ElMessage.success('任务已取消')
  await loadData()
}

async function onDelete(row: QcTask): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除质检任务「${row.task_name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  const { data } = await deleteQcTask(row.id)
  ElMessage.success(`删除成功，联动删除明细 ${data.removed_items} 条`)
  await loadData()
}

async function loadReport(taskId: number): Promise<void> {
  try {
    const { data } = await getQcTaskReport(taskId)
    report.value = data
  } catch {
    report.value = null
  }
}

async function loadItems(): Promise<void> {
  const taskId = drawerTask.value?.id
  if (!taskId) return
  itemLoading.value = true
  try {
    const { data } = await listQcTaskItems(taskId, itemQuery)
    items.value = data.items
    itemTotal.value = data.total
  } finally {
    itemLoading.value = false
  }
}

function onItemSearch(): void {
  itemQuery.page = 1
  void loadItems()
}

async function openDrawer(row: QcTask): Promise<void> {
  drawerTask.value = row
  report.value = null
  items.value = []
  itemTotal.value = 0
  itemQuery.page = 1
  itemQuery.status = undefined
  itemQuery.reviewer_id = undefined
  itemQuery.grade = undefined
  drawerVisible.value = true
  await loadReviewers(row.tenant_id)
  await loadReport(row.id)
  await loadItems()
}

onMounted(async () => {
  await loadTenants()
  await loadGroups(query.tenant_id)
  await loadData()
})
</script>

<style scoped>
.filter-select {
  width: 170px;
}

.filter-select-sm {
  width: 120px;
}

.full-width {
  width: 100%;
}

.form-tip {
  color: #909399;
  font-size: 12px;
}

.page-toolbar__total {
  color: #606266;
}

.report-bar {
  margin-bottom: 12px;
}

.drawer-filter {
  margin-bottom: 8px;
}
</style>