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
        <el-form-item label="组名">
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

    <el-card v-permission="'qc:reviewer:list'" shadow="never">
      <div class="page-toolbar">
        <span class="page-toolbar__total">共 {{ total }} 条</span>
        <div class="page-toolbar__actions">
          <el-button
            v-permission="'qc:reviewer:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增专家组
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="组名" min-width="160" show-overflow-tooltip />
        <el-table-column label="说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column prop="member_count" label="成员数" width="90" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'qc:reviewer:update'"
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-permission="'qc:reviewer:update'"
              link
              type="primary"
              @click="openMembers(row)"
            >
              成员管理
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

    <!-- 新增 / 编辑专家组 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
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
        <el-form-item label="组名" prop="name">
          <el-input v-model="form.name" placeholder="请输入专家组名称" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="初始成员">
          <el-select
            v-model="formMemberIds"
            multiple
            filterable
            placeholder="可多选，后续也可在成员管理中调整"
            class="full-width"
          >
            <el-option
              v-for="user in reviewers"
              :key="user.id"
              :label="`${user.nickname || user.username}（${user.username}）`"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 成员管理 -->
    <el-drawer v-model="membersVisible" :title="membersTitle" size="640px">
      <div v-loading="membersLoading">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="保存为全量覆盖：未出现在下方列表中的成员会被移出专家组。"
        />

        <div class="member-add">
          <el-select
            v-model="pendingUserIds"
            multiple
            filterable
            placeholder="选择要添加的质检员"
            class="full-width"
            @change="onPendingChange"
          >
            <el-option
              v-for="user in availableReviewers"
              :key="user.id"
              :label="`${user.nickname || user.username}（${user.username}）`"
              :value="user.id"
            />
          </el-select>
        </div>

        <el-table :data="memberRows" border stripe max-height="420">
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column label="昵称" min-width="120">
            <template #default="{ row }">{{ row.nickname || '-' }}</template>
          </el-table-column>
          <el-table-column label="参与派发" width="110">
            <template #default="{ row }">
              <el-switch v-model="row.is_active" />
            </template>
          </el-table-column>
          <el-table-column label="单轮质检上限" width="150">
            <template #default="{ row }">
              <el-input-number v-model="row.max_concurrent" :min="1" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeMemberRow($index)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="memberRows.length === 0" description="暂无成员" :image-size="60" />
      </div>

      <template #footer>
        <el-button @click="membersVisible = false">关闭</el-button>
        <el-button
          v-permission="'qc:reviewer:update'"
          type="primary"
          :loading="saving"
          @click="onSaveMembers"
        >
          保存
        </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { listTenantOptions, type TenantOption } from '@/api/outbound/common'
import {
  createReviewerGroup,
  getReviewerGroup,
  listAssignableReviewers,
  listReviewerGroups,
  replaceReviewerGroupMembers,
  updateReviewerGroup,
  type ReviewerGroup,
  type ReviewerGroupMember,
  type ReviewerQuery,
  type ReviewerUser,
} from '@/api/qc/reviewers'

const loading = ref(false)
const rows = ref<ReviewerGroup[]>([])
const total = ref(0)
const tenants = ref<TenantOption[]>([])
const reviewers = ref<ReviewerUser[]>([])

const query = reactive<ReviewerQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  keyword: '',
})

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listReviewerGroups(query)
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

/** 拉取可分配质检员，用于新增时选初始成员与成员管理的候选下拉 */
async function loadReviewers(tenantId?: number): Promise<void> {
  if (!tenantId) {
    reviewers.value = []
    return
  }
  const { data } = await listAssignableReviewers({ tenant_id: tenantId, page_size: 200 })
  reviewers.value = data.items
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.keyword = ''
  query.tenant_id = tenants.value[0]?.id
  onSearch()
}

/* ---------- 新增 / 编辑 ---------- */

interface GroupForm {
  tenant_id?: number
  name: string
  description: string
}

const dialogVisible = ref(false)
const submitting = ref(false)
const isEdit = ref(false)
const currentId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const formMemberIds = ref<number[]>([])

const form = reactive<GroupForm>({
  tenant_id: undefined,
  name: '',
  description: '',
})

const formRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  name: [{ required: true, message: '请输入专家组名称', trigger: 'blur' }],
}

const dialogTitle = computed(() => (isEdit.value ? '编辑专家组' : '新增专家组'))

function resetForm(): void {
  form.name = ''
  form.description = ''
  formMemberIds.value = []
}

function onFormTenantChange(): void {
  formMemberIds.value = []
  void loadReviewers(form.tenant_id)
}

async function openCreate(): Promise<void> {
  isEdit.value = false
  currentId.value = null
  resetForm()
  form.tenant_id = query.tenant_id ?? tenants.value[0]?.id
  await loadReviewers(form.tenant_id)
  dialogVisible.value = true
}

async function openEdit(row: ReviewerGroup): Promise<void> {
  isEdit.value = true
  currentId.value = row.id
  resetForm()
  form.tenant_id = row.tenant_id
  form.name = row.name
  form.description = row.description
  dialogVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isEdit.value && currentId.value !== null) {
      // 编辑仅改名称与说明，成员调整走成员管理
      await updateReviewerGroup(currentId.value, {
        name: form.name,
        description: form.description,
      })
      ElMessage.success('保存成功')
    } else {
      await createReviewerGroup({
        tenant_id: form.tenant_id as number,
        name: form.name,
        description: form.description,
        member_user_ids: formMemberIds.value,
      })
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    await loadData()
  } finally {
    submitting.value = false
  }
}

/* ---------- 成员管理 ---------- */

const membersVisible = ref(false)
const membersLoading = ref(false)
const saving = ref(false)
const currentGroupId = ref<number | null>(null)
const currentGroupName = ref('')
const memberRows = ref<ReviewerGroupMember[]>([])
const pendingUserIds = ref<number[]>([])

const membersTitle = computed(() => `成员管理 - ${currentGroupName.value}`)

/** 候选项排除已在组内的成员 */
const availableReviewers = computed<ReviewerUser[]>(() => {
  const used = new Set(memberRows.value.map((item) => item.user_id))
  return reviewers.value.filter((item) => !used.has(item.id))
})

async function openMembers(row: ReviewerGroup): Promise<void> {
  membersVisible.value = true
  membersLoading.value = true
  currentGroupId.value = row.id
  currentGroupName.value = row.name
  memberRows.value = []
  pendingUserIds.value = []
  try {
    const { data } = await getReviewerGroup(row.id)
    memberRows.value = data.members.map((item) => ({ ...item }))
    await loadReviewers(data.tenant_id)
  } finally {
    membersLoading.value = false
  }
}

/** 下拉选中即追加到表格并清空选择，避免重复选择同一批人 */
function onPendingChange(value: (string | number)[]): void {
  value.forEach((id) => {
    const userId = Number(id)
    const user = reviewers.value.find((item) => item.id === userId)
    if (!user) return
    memberRows.value.push({
      user_id: userId,
      is_active: true,
      max_concurrent: 1,
      username: user.username,
      nickname: user.nickname,
    })
  })
  pendingUserIds.value = []
}

function removeMemberRow(index: number): void {
  memberRows.value.splice(index, 1)
}

async function onSaveMembers(): Promise<void> {
  if (currentGroupId.value === null) return
  if (memberRows.value.length === 0) {
    ElMessage.warning('成员列表为空，保存会清空该专家组全部成员')
    return
  }
  saving.value = true
  try {
    // 全量覆盖：以当前表格状态为准
    const { data } = await replaceReviewerGroupMembers(currentGroupId.value, {
      members: memberRows.value.map((row) => ({
        user_id: row.user_id,
        is_active: row.is_active,
        max_concurrent: row.max_concurrent,
      })),
    })
    memberRows.value = data.members.map((item) => ({ ...item }))
    ElMessage.success('成员已保存')
    await loadData()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadTenants()
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

.page-toolbar__total {
  color: #606266;
}

.member-add {
  margin: 16px 0;
}
</style>