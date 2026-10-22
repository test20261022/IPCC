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
        <el-form-item label="编码">
          <el-input v-model="query.code" placeholder="模糊匹配" clearable @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="层级">
          <el-select v-model="query.level" placeholder="全部" clearable class="filter-select-sm">
            <el-option label="类型" :value="1" />
            <el-option label="子类型" :value="2" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" clearable class="filter-select-sm">
            <el-option label="启用" value="ENABLED" />
            <el-option label="停用" value="DISABLED" />
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
            v-permission="'outbound:type:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column prop="code" label="编码" width="180" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="层级" width="100">
          <template #default="{ row }">
            {{ row.level === 1 ? '类型' : '子类型' }}
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
              v-permission="'outbound:type:update'"
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-permission="'outbound:type:update'"
              link
              type="warning"
              @click="onToggleStatus(row)"
            >
              {{ row.status === 'ENABLED' ? '停用' : '启用' }}
            </el-button>
            <el-button
              v-permission="'outbound:type:delete'"
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

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px">
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
        <el-form-item label="层级" prop="level">
          <el-radio-group v-model="form.level" :disabled="isEdit" @change="onLevelChange">
            <el-radio :value="1">类型</el-radio>
            <el-radio :value="2">子类型</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.level === 2" label="父类型" prop="parent_id">
          <el-select
            v-model="form.parent_id"
            placeholder="请选择父类型"
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
        <el-form-item label="编码" prop="code">
          <el-input v-model="form.code" placeholder="如 TP-001" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如 营销外呼" />
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
import {
  changeOutboundTypeStatus,
  createOutboundType,
  deleteOutboundType,
  listOutboundTypes,
  updateOutboundType,
  type OutboundType,
  type OutboundTypePayload,
  type OutboundTypeQuery,
} from '@/api/outbound/type'
import StatusTag from '@/components/StatusTag.vue'
import type { CommonStatus } from '@/types/api'

const loading = ref(false)
const submitting = ref(false)
const rows = ref<OutboundType[]>([])
const total = ref(0)
const tenants = ref<TenantOption[]>([])
const parentOptions = ref<OutboundType[]>([])

const query = reactive<OutboundTypeQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  name: '',
  code: '',
  level: undefined,
  status: undefined,
})

const dialogVisible = ref(false)
const isEdit = ref(false)
const currentId = ref<number | null>(null)
const formRef = ref<FormInstance>()

interface TypeForm {
  tenant_id?: number
  level: number
  parent_id: number | null
  code: string
  name: string
  sort_order: number
  description: string
}

const form = reactive<TypeForm>({
  tenant_id: undefined,
  level: 1,
  parent_id: null,
  code: '',
  name: '',
  sort_order: 0,
  description: '',
})

const formRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  code: [{ required: true, message: '请输入编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  parent_id: [{ required: true, message: '请选择父类型', trigger: 'change' }],
}

const dialogTitle = computed(() => (isEdit.value ? '编辑外呼类型' : '新增外呼类型'))

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listOutboundTypes(query)
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

async function loadParentOptions(tenantId?: number): Promise<void> {
  if (!tenantId) {
    parentOptions.value = []
    return
  }
  const { data } = await listOutboundTypes({ tenant_id: tenantId, level: 1, page_size: 200 })
  parentOptions.value = data.items
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.name = ''
  query.code = ''
  query.level = undefined
  query.status = undefined
  onSearch()
}

function resetForm(): void {
  form.level = 1
  form.parent_id = null
  form.code = ''
  form.name = ''
  form.sort_order = 0
  form.description = ''
}

function onLevelChange(): void {
  if (form.level === 1) form.parent_id = null
}

function onTenantChange(): void {
  void loadParentOptions(form.tenant_id)
}

async function openCreate(): Promise<void> {
  isEdit.value = false
  currentId.value = null
  resetForm()
  form.tenant_id = query.tenant_id ?? tenants.value[0]?.id
  await loadParentOptions(form.tenant_id)
  dialogVisible.value = true
}

async function openEdit(row: OutboundType): Promise<void> {
  isEdit.value = true
  currentId.value = row.id
  form.tenant_id = row.tenant_id
  form.level = row.level
  form.parent_id = row.parent_id
  form.code = row.code
  form.name = row.name
  form.sort_order = row.sort_order
  form.description = row.description
  await loadParentOptions(row.tenant_id)
  dialogVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  const payload: OutboundTypePayload = {
    code: form.code,
    name: form.name,
    sort_order: form.sort_order,
    description: form.description,
  }
  if (form.level === 2) {
    payload.parent_id = form.parent_id
  }

  submitting.value = true
  try {
    if (isEdit.value && currentId.value !== null) {
      await updateOutboundType(currentId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await createOutboundType({ ...payload, tenant_id: form.tenant_id, level: form.level })
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    await loadData()
  } finally {
    submitting.value = false
  }
}

async function onToggleStatus(row: OutboundType): Promise<void> {
  const next: CommonStatus = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  await changeOutboundTypeStatus(row.id, next)
  ElMessage.success(next === 'ENABLED' ? '已启用' : '已停用')
  await loadData()
}

async function onDelete(row: OutboundType): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除外呼类型「${row.name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await deleteOutboundType(row.id)
  ElMessage.success('删除成功')
  await loadData()
}

onMounted(async () => {
  await loadTenants()
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
