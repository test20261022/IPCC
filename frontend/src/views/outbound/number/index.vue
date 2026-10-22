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
        <el-form-item label="主叫号码">
          <el-input
            v-model="query.caller_number"
            placeholder="模糊匹配"
            clearable
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item label="外显名称">
          <el-input
            v-model="query.display_name"
            placeholder="模糊匹配"
            clearable
            @keyup.enter="onSearch"
          />
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
            v-permission="'outbound:number:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column prop="caller_number" label="主叫号码" width="160" />
        <el-table-column prop="display_name" label="外显名称" min-width="160" />
        <el-table-column label="号码类型" width="120">
          <template #default="{ row }">
            {{ row.number_type || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="使用次数" width="200">
          <template #default="{ row }">
            <div>{{ usageText(row) }}</div>
            <el-progress
              :percentage="usagePercent(row)"
              :status="isOverLimit(row) ? 'exception' : ''"
              :stroke-width="6"
              :show-text="false"
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.status" />
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'outbound:number:use'"
              link
              type="success"
              @click="onConsume(row)"
            >
              扣减次数
            </el-button>
            <el-button
              v-permission="'outbound:number:update'"
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-permission="'outbound:number:update'"
              link
              type="warning"
              @click="onToggleStatus(row)"
            >
              {{ row.status === 'ENABLED' ? '停用' : '启用' }}
            </el-button>
            <el-button
              v-permission="'outbound:number:delete'"
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
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="租户" prop="tenant_id">
          <el-select
            v-model="form.tenant_id"
            placeholder="请选择租户"
            :disabled="isEdit"
            class="full-width"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="外显名称" prop="display_name">
          <el-input v-model="form.display_name" placeholder="如 客服热线" maxlength="128" />
        </el-form-item>
        <el-form-item label="主叫号码" prop="caller_number">
          <el-input
            v-model="form.caller_number"
            placeholder="如 4001234567"
            maxlength="32"
            :disabled="isEdit"
          />
        </el-form-item>
        <el-form-item label="号码类型" prop="number_type">
          <el-input v-model="form.number_type" placeholder="如 固话 / 手机" maxlength="32" />
        </el-form-item>
        <el-form-item label="次数上限">
          <el-input-number
            v-model="form.usage_limit"
            :min="0"
            placeholder="留空表示不限次数"
            class="full-width"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="255" />
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
import { COMMON_STATUS_OPTIONS } from '@/api/outbound/enums'
import {
  changeOutboundNumberStatus,
  consumeOutboundNumber,
  createOutboundNumber,
  deleteOutboundNumber,
  listOutboundNumbers,
  updateOutboundNumber,
  type OutboundNumber,
  type OutboundNumberPayload,
  type OutboundNumberQuery,
} from '@/api/outbound/number'
import StatusTag from '@/components/StatusTag.vue'
import type { CommonStatus } from '@/types/api'

const loading = ref(false)
const submitting = ref(false)
const rows = ref<OutboundNumber[]>([])
const total = ref(0)
const tenants = ref<TenantOption[]>([])

const query = reactive<OutboundNumberQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  caller_number: '',
  display_name: '',
  status: undefined,
})

const dialogVisible = ref(false)
const isEdit = ref(false)
const currentId = ref<number | null>(null)
const formRef = ref<FormInstance>()

interface NumberForm {
  tenant_id?: number
  display_name: string
  caller_number: string
  number_type: string
  usage_limit: number | null
  remark: string
}

const form = reactive<NumberForm>({
  tenant_id: undefined,
  display_name: '',
  caller_number: '',
  number_type: '',
  usage_limit: null,
  remark: '',
})

const formRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  display_name: [{ required: true, message: '请输入外显名称', trigger: 'blur' }],
  caller_number: [
    { required: true, message: '请输入主叫号码', trigger: 'blur' },
    {
      pattern: /^[0-9+\-]{5,32}$/,
      message: '请输入合法的主叫号码（5-32 位数字，可含 + -）',
      trigger: 'blur',
    },
  ],
}

const dialogTitle = computed(() => (isEdit.value ? '编辑外呼号码' : '新增外呼号码'))

/** 使用次数文案：上限为空时展示「不限」 */
function usageText(row: OutboundNumber): string {
  if (row.usage_limit == null) {
    return `${row.used_count} / 不限`
  }
  return `${row.used_count} / ${row.usage_limit}`
}

/** 使用进度百分比：上限为 0 或空时按 0 处理 */
function usagePercent(row: OutboundNumber): number {
  if (!row.usage_limit) return 0
  return Math.min(100, Math.round((row.used_count / row.usage_limit) * 100))
}

/** 是否超过使用上限 */
function isOverLimit(row: OutboundNumber): boolean {
  return !!row.usage_limit && row.used_count > row.usage_limit
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listOutboundNumbers(query)
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

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.caller_number = ''
  query.display_name = ''
  query.status = undefined
  onSearch()
}

function resetForm(): void {
  form.display_name = ''
  form.caller_number = ''
  form.number_type = ''
  form.usage_limit = null
  form.remark = ''
}

function openCreate(): void {
  isEdit.value = false
  currentId.value = null
  resetForm()
  form.tenant_id = query.tenant_id ?? tenants.value[0]?.id
  dialogVisible.value = true
}

function openEdit(row: OutboundNumber): void {
  isEdit.value = true
  currentId.value = row.id
  form.tenant_id = row.tenant_id
  form.display_name = row.display_name
  form.caller_number = row.caller_number
  form.number_type = row.number_type
  form.usage_limit = row.usage_limit
  form.remark = row.remark
  dialogVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  const payload: OutboundNumberPayload = {
    display_name: form.display_name,
    number_type: form.number_type,
    usage_limit: form.usage_limit ?? null,
    remark: form.remark,
  }

  submitting.value = true
  try {
    if (isEdit.value && currentId.value !== null) {
      await updateOutboundNumber(currentId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await createOutboundNumber({
        ...payload,
        tenant_id: form.tenant_id,
        caller_number: form.caller_number,
      })
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    await loadData()
  } finally {
    submitting.value = false
  }
}

async function onConsume(row: OutboundNumber): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认扣减主叫号码「${row.caller_number}」1 次使用次数？`, '扣减确认', {
      type: 'warning',
      confirmButtonText: '确定扣减',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  const { data } = await consumeOutboundNumber(row.id, 1)
  ElMessage.success(`已扣减 1 次，当前已用 ${data.used_count} 次`)
  await loadData()
}

async function onToggleStatus(row: OutboundNumber): Promise<void> {
  const next: CommonStatus = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  await changeOutboundNumberStatus(row.id, next)
  ElMessage.success(next === 'ENABLED' ? '已启用' : '已停用')
  await loadData()
}

async function onDelete(row: OutboundNumber): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除主叫号码「${row.caller_number}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await deleteOutboundNumber(row.id)
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
