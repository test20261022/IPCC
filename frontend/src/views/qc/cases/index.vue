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
        <el-form-item label="发布状态">
          <el-select v-model="query.is_published" class="filter-select-sm">
            <el-option
              v-for="item in PUBLISH_STATUS_OPTIONS"
              :key="String(item.value)"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="query.tag"
            placeholder="精确匹配标签"
            clearable
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="query.keyword"
            placeholder="标题 / 理由模糊匹配"
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
            v-permission="'qc:case:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增案例
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="标签" min-width="160">
          <template #default="{ row }">
            <template v-if="row.tags && row.tags.length">
              <el-tag v-for="tag in row.tags" :key="tag" size="small" class="tag-item">
                {{ tag }}
              </el-tag>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="入选理由" min-width="200" show-overflow-tooltip />
        <el-table-column label="来源对话" width="120">
          <template #default="{ row }">
            <el-button link type="primary" @click="openPreview(row.conversation_id)">
              #{{ row.conversation_id }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="发布状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.is_published ? 'success' : 'info'" disable-transitions>
              {{ row.is_published ? '已发布' : '未发布' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ row.created_at || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openPreview(row.conversation_id)">预览</el-button>
            <el-button
              v-permission="'qc:case:update'"
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="!row.is_published"
              v-permission="'qc:case:publish'"
              link
              type="primary"
              @click="onPublish(row)"
            >
              发布
            </el-button>
            <el-button
              v-permission="'qc:case:delete'"
              link
              type="primary"
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

    <!-- 新增 / 编辑案例 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="130px">
        <el-form-item v-if="isCreate" label="租户" prop="tenant_id">
          <el-select v-model="form.tenant_id" placeholder="请选择租户" class="full-width">
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isCreate" label="来源对话 ID" prop="conversation_id">
          <el-input-number v-model="form.conversation_id" :min="1" class="full-width" />
        </el-form-item>
        <el-form-item label="来源质检明细 ID" prop="item_id">
          <el-input-number v-model="form.item_id" :min="1" class="full-width" />
          <span class="form-tip">可选，填写后关联对应质检明细</span>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="请输入案例标题" maxlength="128" />
        </el-form-item>
        <el-form-item label="入选理由" prop="reason">
          <el-input
            v-model="form.reason"
            type="textarea"
            :rows="4"
            placeholder="请输入入选理由 / 亮点"
          />
        </el-form-item>
        <el-form-item label="标签" prop="tags">
          <el-select
            v-model="form.tags"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入后回车创建标签"
            class="full-width"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 对话预览 -->
    <el-drawer v-model="previewVisible" title="对话预览" size="620px">
      <div v-loading="previewLoading">
        <el-descriptions v-if="conversation" :column="2" border>
          <el-descriptions-item label="客服">
            {{ conversation.agent_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="渠道">
            {{ labelOf(CONVERSATION_CHANNEL_LABELS, conversation.channel) }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ conversation.started_at || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="时长">
            {{ formatDuration(conversation.duration) }}
          </el-descriptions-item>
          <el-descriptions-item label="消息数">{{ conversation.msg_count }}</el-descriptions-item>
          <el-descriptions-item label="转写状态">
            {{ labelOf(TRANSCRIPT_STATUS_LABELS, conversation.transcript_status) }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="conversation" class="dialog-section-title">对话消息</div>
        <div v-if="sortedMessages.length" class="bubble-list">
          <div
            v-for="msg in sortedMessages"
            :key="msg.seq"
            class="bubble-row"
            :class="`bubble-row--${roleClass(msg.role)}`"
          >
            <div class="bubble" :class="`bubble--${roleClass(msg.role)}`">
              <div class="bubble__meta">{{ labelOf(MESSAGE_ROLE_LABELS, msg.role) }}</div>
              <div class="bubble__content">{{ msg.content }}</div>
            </div>
          </div>
        </div>
        <el-empty
          v-else-if="conversation"
          description="暂无消息"
          :image-size="60"
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
  createQcCase,
  deleteQcCase,
  listQcCases,
  publishQcCase,
  updateQcCase,
  type QcCase,
  type QcCaseQuery,
} from '@/api/qc/cases'
import {
  getQcConversation,
  type QcConversationDetail,
  type QcMessage,
} from '@/api/qc/conversations'
import {
  CONVERSATION_CHANNEL_LABELS,
  MESSAGE_ROLE_LABELS,
  TRANSCRIPT_STATUS_LABELS,
  labelOf,
} from '@/api/qc/enums'
import { formatDuration } from '@/utils/useEcharts'

/** 发布状态筛选项：全部 / 已发布 / 未发布 */
const PUBLISH_STATUS_OPTIONS: Array<{ label: string; value: boolean | undefined }> = [
  { label: '全部', value: undefined },
  { label: '已发布', value: true },
  { label: '未发布', value: false },
]

const loading = ref(false)
const rows = ref<QcCase[]>([])
const total = ref(0)
const tenants = ref<TenantOption[]>([])

const query = reactive<QcCaseQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  is_published: undefined,
  tag: '',
  keyword: '',
})

/* ---------- 列表 ---------- */

function buildParams(): QcCaseQuery {
  const params: QcCaseQuery = { ...query }
  params.tag = params.tag || undefined
  params.keyword = params.keyword || undefined
  return params
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listQcCases(buildParams())
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

function onTenantChange(): void {
  onSearch()
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.is_published = undefined
  query.tag = ''
  query.keyword = ''
  onSearch()
}

/* ---------- 新增 / 编辑 ---------- */

interface CaseForm {
  tenant_id?: number
  conversation_id?: number
  item_id?: number
  title: string
  reason: string
  tags: string[]
}

const dialogVisible = ref(false)
const submitting = ref(false)
const isCreate = ref(true)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const form = reactive<CaseForm>({
  tenant_id: undefined,
  conversation_id: undefined,
  item_id: undefined,
  title: '',
  reason: '',
  tags: [],
})

const dialogTitle = computed(() => (isCreate.value ? '新增案例' : '编辑案例'))

const formRules = computed<FormRules>(() => ({
  tenant_id: isCreate.value
    ? [{ required: true, message: '请选择租户', trigger: 'change' }]
    : [],
  conversation_id: isCreate.value
    ? [{ required: true, message: '请填写来源对话 ID', trigger: 'change' }]
    : [],
  title: [{ required: true, message: '请输入案例标题', trigger: 'blur' }],
}))

function openCreate(): void {
  isCreate.value = true
  editingId.value = null
  form.tenant_id = query.tenant_id ?? tenants.value[0]?.id
  form.conversation_id = undefined
  form.item_id = undefined
  form.title = ''
  form.reason = ''
  form.tags = []
  dialogVisible.value = true
}

function openEdit(row: QcCase): void {
  isCreate.value = false
  editingId.value = row.id
  form.tenant_id = row.tenant_id
  form.conversation_id = row.conversation_id
  form.item_id = row.item_id ?? undefined
  form.title = row.title
  form.reason = row.reason
  form.tags = row.tags ? [...row.tags] : []
  dialogVisible.value = true
}

async function onSubmit(): Promise<void> {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isCreate.value) {
      await createQcCase({
        tenant_id: form.tenant_id as number,
        conversation_id: form.conversation_id as number,
        item_id: form.item_id,
        title: form.title,
        reason: form.reason,
        tags: form.tags,
      })
      ElMessage.success('新增成功')
    } else if (editingId.value !== null) {
      // 来源对话与归属租户创建后不可修改，只提交可调整字段
      await updateQcCase(editingId.value, {
        item_id: form.item_id,
        title: form.title,
        reason: form.reason,
        tags: form.tags,
      })
      ElMessage.success('保存成功')
    }
    dialogVisible.value = false
    await loadData()
  } finally {
    submitting.value = false
  }
}

/* ---------- 发布 / 删除 ---------- */

async function onPublish(row: QcCase): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认发布案例「${row.title}」？`, '发布确认', {
      type: 'warning',
      confirmButtonText: '确定发布',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await publishQcCase(row.id)
  ElMessage.success('发布成功')
  await loadData()
}

async function onDelete(row: QcCase): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除案例「${row.title}」？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await deleteQcCase(row.id)
  ElMessage.success('删除成功')
  await loadData()
}

/* ---------- 对话预览 ---------- */

const previewVisible = ref(false)
const previewLoading = ref(false)
const conversation = ref<QcConversationDetail | null>(null)

const sortedMessages = computed<QcMessage[]>(() =>
  [...(conversation.value?.messages ?? [])].sort((a, b) => a.seq - b.seq),
)

/** 说话人 → 气泡样式后缀（AGENT 靠右 / CUSTOMER 靠左 / SYSTEM 居中） */
function roleClass(role: string): string {
  return (role || 'SYSTEM').toLowerCase()
}

async function openPreview(conversationId: number): Promise<void> {
  previewVisible.value = true
  previewLoading.value = true
  conversation.value = null
  try {
    const { data } = await getQcConversation(conversationId)
    conversation.value = data
  } finally {
    previewLoading.value = false
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
  width: 130px;
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

.tag-item + .tag-item {
  margin-left: 4px;
}

.dialog-section-title {
  margin: 16px 0 8px;
  font-weight: 600;
}

.bubble-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.bubble-row {
  display: flex;
}

.bubble-row--agent {
  justify-content: flex-end;
}

.bubble-row--customer {
  justify-content: flex-start;
}

.bubble-row--system {
  justify-content: center;
}

.bubble {
  max-width: 78%;
  padding: 8px 12px;
  border-radius: 8px;
  background: #f5f7fa;
}

.bubble--agent {
  background: #ecf5ff;
}

.bubble--system {
  background: transparent;
  color: #909399;
}

.bubble__meta {
  margin-bottom: 4px;
  font-size: 12px;
  color: #909399;
}

.bubble__content {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>