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
            @change="onSearch"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="query.name" placeholder="模糊匹配" clearable @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="外呼类型">
          <el-select
            v-model="query.type_id"
            placeholder="全部"
            clearable
            class="filter-select"
            @change="onSearch"
          >
            <el-option
              v-for="item in typeOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="层级">
          <el-select v-model="query.level" placeholder="全部" clearable class="filter-select-sm">
            <el-option
              v-for="item in LEVEL_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" clearable class="filter-select-sm">
            <el-option
              v-for="item in COMMON_STATUS_OPTIONS"
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
            v-permission="'outbound:scene:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增
          </el-button>
          <el-button
            v-permission="'outbound:scene:delete'"
            type="danger"
            :disabled="selectedIds.length === 0"
            @click="onBatchDelete"
          >
            批量删除
          </el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="rows"
        border
        stripe
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="外呼类型" min-width="140">
          <template #default="{ row }">{{ typeNameMap[row.type_id] ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="层级" width="100">
          <template #default="{ row }">
            {{ row.level === 1 ? '一级场景' : '二级场景' }}
          </template>
        </el-table-column>
        <el-table-column label="父场景" min-width="140">
          <template #default="{ row }">
            {{ row.parent_id ? (sceneNameMap[row.parent_id] ?? '-') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.status" />
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="80" />
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'outbound:scene:update'"
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-permission="'outbound:scene:update'"
              link
              type="warning"
              @click="onToggleStatus(row)"
            >
              {{ row.status === 'ENABLED' ? '停用' : '启用' }}
            </el-button>
            <el-button
              v-permission="'outbound:scene:delete'"
              link
              type="danger"
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

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="租户" prop="tenant_id">
          <el-select
            v-model="form.tenant_id"
            placeholder="请选择租户"
            :disabled="isEdit"
            class="full-width"
            @change="onTenantChange"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="外呼类型" prop="type_id">
          <el-select
            v-model="form.type_id"
            placeholder="请选择外呼类型"
            :disabled="isEdit"
            class="full-width"
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
        <el-form-item label="层级" prop="level">
          <el-radio-group v-model="form.level" :disabled="isEdit" @change="onLevelChange">
            <el-radio :value="1">一级场景</el-radio>
            <el-radio :value="2">二级场景</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.level === 2" label="父场景" prop="parent_id">
          <el-select
            v-model="form.parent_id"
            placeholder="请选择父场景"
            :disabled="isEdit"
            class="full-width"
          >
            <el-option
              v-for="item in parentOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如 意向确认" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import { listTenantOptions, type TenantOption } from '@/api/outbound/common'
import { COMMON_STATUS_OPTIONS, LEVEL_OPTIONS } from '@/api/outbound/enums'
import {
  batchDeleteOutboundScenes,
  changeOutboundSceneStatus,
  createOutboundScene,
  deleteOutboundScene,
  getOutboundSceneTree,
  listOutboundScenes,
  updateOutboundScene,
  type OutboundScene,
  type OutboundScenePayload,
  type OutboundSceneQuery,
  type OutboundSceneTree,
} from '@/api/outbound/scene'
import { listOutboundTypes, type OutboundType } from '@/api/outbound/type'
import StatusTag from '@/components/StatusTag.vue'
import type { CommonStatus } from '@/types/api'

const loading = ref(false)
const submitting = ref(false)
const rows = ref<OutboundScene[]>([])
const total = ref(0)
const tenants = ref<TenantOption[]>([])
const typeOptions = ref<OutboundType[]>([])
const parentOptions = ref<OutboundSceneTree[]>([])
const sceneNameMap = ref<Record<number, string>>({})
const selectedIds = ref<number[]>([])

const query = reactive<OutboundSceneQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  name: '',
  type_id: undefined,
  level: undefined,
  status: undefined,
})

const dialogVisible = ref(false)
const isEdit = ref(false)
const currentId = ref<number | null>(null)
const formRef = ref<FormInstance>()

interface SceneForm {
  tenant_id?: number
  type_id?: number
  level: number
  parent_id: number | null
  name: string
  sort_order: number
  description: string
}

const form = reactive<SceneForm>({
  tenant_id: undefined,
  type_id: undefined,
  level: 1,
  parent_id: null,
  name: '',
  sort_order: 0,
  description: '',
})

const formRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  type_id: [{ required: true, message: '请选择外呼类型', trigger: 'change' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  parent_id: [{ required: true, message: '请选择父场景', trigger: 'change' }],
}

const dialogTitle = computed(() => (isEdit.value ? '编辑外呼场景' : '新增外呼场景'))

/** type_id → 外呼类型名称 */
const typeNameMap = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {}
  for (const item of typeOptions.value) {
    map[item.id] = item.name
  }
  return map
})

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listOutboundScenes(query)
    rows.value = data.items
    total.value = data.total
    await loadSceneNames()
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

async function loadTypeOptions(): Promise<void> {
  const { data } = await listOutboundTypes({ level: 1, page_size: 200 })
  typeOptions.value = data.items
}

/** 拉取场景树，构建 场景 id → 名称 映射，用于展示父场景名称 */
async function loadSceneNames(): Promise<void> {
  if (!query.tenant_id) {
    sceneNameMap.value = {}
    return
  }
  const { data } = await getOutboundSceneTree({
    tenant_id: query.tenant_id,
    type_id: query.type_id,
  })
  const map: Record<number, string> = {}
  const walk = (nodes: OutboundSceneTree[]): void => {
    for (const node of nodes) {
      map[node.id] = node.name
      walk(node.children)
    }
  }
  walk(data)
  sceneNameMap.value = map
}

/** 父场景选项仅取一级场景 */
async function loadParentOptions(tenantId?: number, typeId?: number): Promise<void> {
  if (!tenantId || !typeId) {
    parentOptions.value = []
    return
  }
  const { data } = await getOutboundSceneTree({ tenant_id: tenantId, type_id: typeId })
  parentOptions.value = data.filter((item) => item.level === 1)
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.name = ''
  query.type_id = undefined
  query.level = undefined
  query.status = undefined
  onSearch()
}

function onSelectionChange(selection: OutboundScene[]): void {
  selectedIds.value = selection.map((item) => item.id)
}

function resetForm(): void {
  form.type_id = undefined
  form.level = 1
  form.parent_id = null
  form.name = ''
  form.sort_order = 0
  form.description = ''
}

function onLevelChange(): void {
  if (form.level === 1) form.parent_id = null
}

function onTenantChange(): void {
  form.parent_id = null
  void loadParentOptions(form.tenant_id, form.type_id)
}

function onTypeChange(): void {
  form.parent_id = null
  void loadParentOptions(form.tenant_id, form.type_id)
}

async function openCreate(): Promise<void> {
  isEdit.value = false
  currentId.value = null
  resetForm()
  form.tenant_id = query.tenant_id ?? tenants.value[0]?.id
  await loadParentOptions(form.tenant_id, form.type_id)
  dialogVisible.value = true
}

async function openEdit(row: OutboundScene): Promise<void> {
  isEdit.value = true
  currentId.value = row.id
  form.tenant_id = row.tenant_id
  form.type_id = row.type_id
  form.level = row.level
  form.parent_id = row.parent_id
  form.name = row.name
  form.sort_order = row.sort_order
  form.description = row.description
  await loadParentOptions(row.tenant_id, row.type_id)
  dialogVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isEdit.value && currentId.value !== null) {
      // 编辑时不提交 tenant_id / type_id / level / parent_id（后端不接受变更）
      const payload: OutboundScenePayload = {
        name: form.name,
        sort_order: form.sort_order,
        description: form.description,
      }
      await updateOutboundScene(currentId.value, payload)
      ElMessage.success('保存成功')
    } else {
      const payload: OutboundScenePayload = {
        tenant_id: form.tenant_id,
        type_id: form.type_id,
        level: form.level,
        parent_id: form.level === 2 ? form.parent_id : null,
        name: form.name,
        sort_order: form.sort_order,
        description: form.description,
      }
      await createOutboundScene(payload)
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    await loadData()
  } finally {
    submitting.value = false
  }
}

async function onToggleStatus(row: OutboundScene): Promise<void> {
  const next: CommonStatus = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  await changeOutboundSceneStatus(row.id, next)
  ElMessage.success(next === 'ENABLED' ? '已启用' : '已停用')
  await loadData()
}

async function onDelete(row: OutboundScene): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除外呼场景「${row.name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  const { data } = await deleteOutboundScene(row.id)
  ElMessage.success(`已删除 ${data.deleted} 条场景（一级场景会级联其二级场景）`)
  await loadData()
}

async function onBatchDelete(): Promise<void> {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${selectedIds.value.length} 条场景？`,
      '批量删除确认',
      {
        type: 'warning',
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }
  const { data } = await batchDeleteOutboundScenes(selectedIds.value)
  ElMessage.success(`已删除 ${data.deleted} 条场景（一级场景会级联其二级场景）`)
  selectedIds.value = []
  await loadData()
}

onMounted(async () => {
  await loadTenants()
  await loadTypeOptions()
  await loadData()
})
</script>

<style scoped>
.filter-select {
  width: 180px;
}

.filter-select-sm {
  width: 120px;
}

.full-width {
  width: 100%;
}

.page-toolbar__total {
  color: #606266;
}
</style>
