<template>
  <div class="page-container">
    <el-card shadow="never">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 对话列表 -->
        <el-tab-pane label="对话列表" name="list">
          <el-form :inline="true" :model="query" @submit.prevent>
            <el-form-item label="租户">
              <el-select
                v-model="query.tenant_id"
                placeholder="全部"
                clearable
                class="filter-select"
                @change="onTenantChange"
              >
                <el-option
                  v-for="item in tenants"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="客服名称">
              <el-input
                v-model="query.agent_name"
                placeholder="模糊匹配"
                clearable
                @keyup.enter="onSearch"
              />
            </el-form-item>
            <el-form-item label="渠道">
              <el-select v-model="query.channel" placeholder="全部" clearable class="filter-select-sm">
                <el-option
                  v-for="item in CONVERSATION_CHANNEL_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="来源">
              <el-select v-model="query.source" placeholder="全部" clearable class="filter-select-sm">
                <el-option
                  v-for="item in CONVERSATION_SOURCE_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="转写状态">
              <el-select
                v-model="query.transcript_status"
                placeholder="全部"
                clearable
                class="filter-select-sm"
              >
                <el-option
                  v-for="item in TRANSCRIPT_STATUS_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="开始时间">
              <el-date-picker
                v-model="dateRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                class="filter-range"
              />
            </el-form-item>
            <el-form-item label="关键词">
              <el-input
                v-model="query.keyword"
                placeholder="消息内容模糊匹配"
                clearable
                @keyup.enter="onSearch"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
              <el-button :icon="Refresh" @click="onReset">重置</el-button>
            </el-form-item>
          </el-form>

          <div class="page-toolbar">
            <span class="page-toolbar__total">共 {{ total }} 条</span>
            <div class="page-toolbar__actions">
              <el-button
                v-permission="'qc:conversation:import'"
                type="primary"
                :icon="Upload"
                @click="openImport"
              >
                导入对话
              </el-button>
            </div>
          </div>

          <el-table v-loading="loading" :data="rows" border stripe>
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column label="客服" width="160" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.agent_name || '-' }}
                <span v-if="row.agent_ext" class="muted">（{{ row.agent_ext }}）</span>
              </template>
            </el-table-column>
            <el-table-column prop="customer_id" label="客户标识" width="140" show-overflow-tooltip />
            <el-table-column label="渠道" width="110">
              <template #default="{ row }">
                {{ labelOf(CONVERSATION_CHANNEL_LABELS, row.channel) }}
              </template>
            </el-table-column>
            <el-table-column label="来源" width="110">
              <template #default="{ row }">
                {{ labelOf(CONVERSATION_SOURCE_LABELS, row.source) }}
              </template>
            </el-table-column>
            <el-table-column prop="started_at" label="开始时间" width="180" />
            <el-table-column label="时长" width="100">
              <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
            </el-table-column>
            <el-table-column prop="msg_count" label="消息数" width="90" />
            <el-table-column label="转写状态" width="110">
              <template #default="{ row }">
                <StatusTag
                  :value="row.transcript_status"
                  :labels="TRANSCRIPT_STATUS_LABELS"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openDetail(row)">详情</el-button>
                <el-button
                  v-permission="'qc:conversation:transcribe'"
                  link
                  type="primary"
                  :disabled="row.channel !== 'VOICE'"
                  @click="onTranscribe(row)"
                >
                  转写
                </el-button>
                <el-button
                  v-permission="'qc:conversation:delete'"
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
        </el-tab-pane>

        <!-- 导入批次 -->
        <el-tab-pane label="导入批次" name="batches">
          <el-form :inline="true" :model="batchQuery" @submit.prevent>
            <el-form-item label="租户">
              <el-select
                v-model="batchQuery.tenant_id"
                placeholder="全部"
                clearable
                class="filter-select"
                @change="onBatchTenantChange"
              >
                <el-option
                  v-for="item in tenants"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="onBatchSearch">查询</el-button>
              <el-button :icon="Refresh" @click="onBatchReset">重置</el-button>
            </el-form-item>
          </el-form>

          <div class="page-toolbar">
            <span class="page-toolbar__total">共 {{ batchTotal }} 条</span>
          </div>

          <el-table v-loading="batchLoading" :data="batchRows" border stripe>
            <el-table-column prop="file_name" label="文件名称" min-width="200" show-overflow-tooltip />
            <el-table-column label="格式" width="90">
              <template #default="{ row }">
                {{ labelOf(QC_IMPORT_FORMAT_LABELS, row.format) }}
              </template>
            </el-table-column>
            <el-table-column prop="total_rows" label="总行数" width="90" />
            <el-table-column prop="success_rows" label="成功数" width="90" />
            <el-table-column label="失败数" width="90">
              <template #default="{ row }">
                <span :class="{ 'text-danger': row.failed_rows > 0 }">{{ row.failed_rows }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <StatusTag :value="row.status" :labels="QC_IMPORT_STATUS_LABELS" />
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180" />
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="batchQuery.page"
              v-model:page-size="batchQuery.page_size"
              :total="batchTotal"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="loadBatchData"
              @size-change="onBatchSearch"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 对话详情 -->
    <el-drawer v-model="detailVisible" title="对话详情" size="620px">
      <div v-loading="detailLoading">
        <el-descriptions v-if="detail" :column="2" border>
          <el-descriptions-item label="对话ID">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="外部单号">{{ detail.ext_ref_no || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客服">{{ detail.agent_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="分机号">{{ detail.agent_ext || '-' }}</el-descriptions-item>
          <el-descriptions-item label="客户标识">{{ detail.customer_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="渠道">
            {{ labelOf(CONVERSATION_CHANNEL_LABELS, detail.channel) }}
          </el-descriptions-item>
          <el-descriptions-item label="来源">
            {{ labelOf(CONVERSATION_SOURCE_LABELS, detail.source) }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ detail.started_at }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ detail.ended_at || '-' }}</el-descriptions-item>
          <el-descriptions-item label="时长">{{ formatDuration(detail.duration) }}</el-descriptions-item>
          <el-descriptions-item label="消息数">{{ detail.msg_count }}</el-descriptions-item>
          <el-descriptions-item label="转写状态">
            <StatusTag :value="detail.transcript_status" :labels="TRANSCRIPT_STATUS_LABELS" />
          </el-descriptions-item>
          <el-descriptions-item label="转写引擎">
            {{ detail.transcript_engine || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="录音路径">
            {{ detail.recording_path || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="dialog-section-title">对话内容</div>
        <div v-if="sortedMessages.length" class="bubble-list">
          <div
            v-for="msg in sortedMessages"
            :key="msg.seq"
            class="bubble-row"
            :class="`bubble-row--${roleClass(msg.role)}`"
          >
            <div class="bubble" :class="`bubble--${roleClass(msg.role)}`">
              <div class="bubble__meta">
                {{ labelOf(MESSAGE_ROLE_LABELS, msg.role) }}
                <span v-if="msg.start_ms !== null"> · {{ formatSeconds(msg.start_ms) }}</span>
              </div>
              <div class="bubble__content">{{ msg.content }}</div>
            </div>
          </div>
        </div>
        <el-empty v-else-if="detail" description="暂无消息" :image-size="60" />
      </div>
    </el-drawer>

    <!-- 导入对话 -->
    <el-dialog v-model="importVisible" title="导入对话" width="640px">
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="租户" required>
          <el-select
            v-model="importTenantId"
            placeholder="请选择租户"
            class="full-width"
            :disabled="importing"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="对话文件" required>
          <el-upload
            ref="uploadRef"
            class="full-width"
            drag
            :auto-upload="false"
            :limit="1"
            :disabled="importing"
            accept=".txt,.json,.xlsx"
            :on-change="onImportFileChange"
            :on-remove="onImportFileRemove"
            :on-exceed="onImportFileExceed"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">将文件拖到此处，或<em>点击选择文件</em></div>
            <template #tip>
              <div class="el-upload__tip">仅支持 .txt / .json / .xlsx 格式，每次一个文件</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>

      <template v-if="importBatch">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="总行数">{{ importBatch.total_rows }}</el-descriptions-item>
          <el-descriptions-item label="成功数">{{ importBatch.success_rows }}</el-descriptions-item>
          <el-descriptions-item label="失败数">{{ importBatch.failed_rows }}</el-descriptions-item>
        </el-descriptions>

        <el-table
          v-if="importErrorRows.length > 0"
          :data="importErrorRows"
          border
          stripe
          max-height="260"
          class="import-failures"
        >
          <el-table-column label="行号" width="80">
            <template #default="{ row }">{{ row.row ?? row.line ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="原因" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">{{ row.reason ?? row.message ?? '-' }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="无失败明细" :image-size="60" />
      </template>

      <template #footer>
        <template v-if="importBatch">
          <el-button @click="closeImport">关闭</el-button>
          <el-button type="primary" @click="onImportFinish">完成</el-button>
        </template>
        <template v-else>
          <el-button :disabled="importing" @click="closeImport">取消</el-button>
          <el-button type="primary" :loading="importing" @click="onImportSubmit">
            开始导入
          </el-button>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Refresh, Search, Upload, UploadFilled } from '@element-plus/icons-vue'
import {
  ElMessage,
  ElMessageBox,
  type TabPaneName,
  type UploadFile,
  type UploadInstance,
  type UploadRawFile,
} from 'element-plus'

import { listTenantOptions, type TenantOption } from '@/api/outbound/common'
import {
  CONVERSATION_CHANNEL_LABELS,
  CONVERSATION_CHANNEL_OPTIONS,
  CONVERSATION_SOURCE_LABELS,
  CONVERSATION_SOURCE_OPTIONS,
  MESSAGE_ROLE_LABELS,
  QC_IMPORT_FORMAT_LABELS,
  QC_IMPORT_STATUS_LABELS,
  TRANSCRIPT_STATUS_LABELS,
  TRANSCRIPT_STATUS_OPTIONS,
  labelOf,
} from '@/api/qc/enums'
import {
  deleteQcConversation,
  getQcConversation,
  importQcConversations,
  listQcConversations,
  listQcImportBatches,
  transcribeQcConversation,
  type QcConversation,
  type QcConversationDetail,
  type QcConversationQuery,
  type QcImportBatch,
  type QcImportBatchQuery,
  type QcMessage,
} from '@/api/qc/conversations'
import StatusTag from '@/components/StatusTag.vue'
import { formatDuration } from '@/utils/useEcharts'

const activeTab = ref<TabPaneName>('list')
const tenants = ref<TenantOption[]>([])

/* ---------- 对话列表 ---------- */

const loading = ref(false)
const rows = ref<QcConversation[]>([])
const total = ref(0)
const dateRange = ref<[Date, Date] | null>(null)

const query = reactive<QcConversationQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  agent_name: '',
  channel: undefined,
  source: undefined,
  transcript_status: undefined,
  started_from: undefined,
  started_to: undefined,
  keyword: '',
})

/** 把时间选择器的值同步为接口需要的 ISO 字符串 */
function applyDateRange(): void {
  const range = dateRange.value
  query.started_from = range?.[0] ? range[0].toISOString() : undefined
  query.started_to = range?.[1] ? range[1].toISOString() : undefined
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listQcConversations(query)
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onSearch(): void {
  applyDateRange()
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.agent_name = ''
  query.channel = undefined
  query.source = undefined
  query.transcript_status = undefined
  query.started_from = undefined
  query.started_to = undefined
  query.keyword = ''
  dateRange.value = null
  onSearch()
}

/* ---------- 导入批次 ---------- */

const batchLoading = ref(false)
const batchRows = ref<QcImportBatch[]>([])
const batchTotal = ref(0)

const batchQuery = reactive<QcImportBatchQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
})

async function loadBatchData(): Promise<void> {
  batchLoading.value = true
  try {
    const { data } = await listQcImportBatches(batchQuery)
    batchRows.value = data.items
    batchTotal.value = data.total
  } finally {
    batchLoading.value = false
  }
}

function onBatchSearch(): void {
  batchQuery.page = 1
  void loadBatchData()
}

function onBatchReset(): void {
  batchQuery.tenant_id = query.tenant_id
  onBatchSearch()
}

/* ---------- 租户与页签 ---------- */

async function loadTenants(): Promise<void> {
  const { data } = await listTenantOptions()
  tenants.value = data
  const defaultTenantId = data[0]?.id
  if (defaultTenantId) {
    query.tenant_id = defaultTenantId
    batchQuery.tenant_id = defaultTenantId
  }
}

/** 两个页签的租户筛选保持同步，避免筛选与数据错配 */
function onTenantChange(): void {
  batchQuery.tenant_id = query.tenant_id
  onSearch()
}

function onBatchTenantChange(): void {
  query.tenant_id = batchQuery.tenant_id
  onBatchSearch()
}

function onTabChange(name: TabPaneName): void {
  if (name === 'batches') {
    void loadBatchData()
  } else {
    void loadData()
  }
}

/* ---------- 详情 ---------- */

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<QcConversationDetail | null>(null)

/** 消息按 seq 升序即对话顺序 */
const sortedMessages = computed<QcMessage[]>(() =>
  [...(detail.value?.messages ?? [])].sort((a, b) => a.seq - b.seq),
)

async function openDetail(row: QcConversation): Promise<void> {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const { data } = await getQcConversation(row.id)
    detail.value = data
  } finally {
    detailLoading.value = false
  }
}

/* ---------- 转写 / 删除 ---------- */

async function onTranscribe(row: QcConversation): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认对「${row.agent_name || `#${row.id}`}」发起语音转写？`,
      '转写确认',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const { data } = await transcribeQcConversation(row.id)
  ElMessage.success(`转写完成：共生成 ${data.message_count} 条消息`)
  await loadData()
}

async function onDelete(row: QcConversation): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除对话 #${row.id}？对话消息会一并删除。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await deleteQcConversation(row.id)
  ElMessage.success('删除成功')
  await loadData()
}

/* ---------- 导入对话 ---------- */

const importVisible = ref(false)
const importing = ref(false)
const importTenantId = ref<number | undefined>(undefined)
const importFile = ref<UploadRawFile | null>(null)
const importBatch = ref<QcImportBatch | null>(null)
const uploadRef = ref<UploadInstance>()

/** 失败明细行：后端字段为行号 / 原因，兼容未知结构时降级展示 */
const importErrorRows = computed<Array<Record<string, unknown>>>(() => importBatch.value?.error_detail ?? [])

function openImport(): void {
  resetImport()
  importTenantId.value = query.tenant_id ?? tenants.value[0]?.id
  importVisible.value = true
}

function resetImport(): void {
  importTenantId.value = undefined
  importFile.value = null
  importBatch.value = null
  uploadRef.value?.clearFiles()
}

function closeImport(): void {
  importVisible.value = false
  resetImport()
}

function onImportFileChange(file: UploadFile): void {
  importFile.value = file.raw ?? null
}

function onImportFileRemove(): void {
  importFile.value = null
}

/** 已选文件时再次选择：替换旧文件 */
function onImportFileExceed(files: File[]): void {
  const raw = files[0]
  if (!raw) return
  uploadRef.value?.clearFiles()
  uploadRef.value?.handleStart(raw as UploadRawFile)
}

async function onImportSubmit(): Promise<void> {
  if (importing.value) return
  if (!importTenantId.value) {
    ElMessage.warning('请选择租户')
    return
  }
  const file = importFile.value
  if (!file) {
    ElMessage.warning('请选择需要导入的对话文件')
    return
  }

  importing.value = true
  try {
    const { data } = await importQcConversations(importTenantId.value, file)
    importBatch.value = data
    ElMessage.success(
      `导入完成：共 ${data.total_rows} 行，成功 ${data.success_rows} 行，失败 ${data.failed_rows} 行`,
    )
  } finally {
    importing.value = false
  }
}

async function onImportFinish(): Promise<void> {
  closeImport()
  await loadData()
  await loadBatchData()
}

/* ---------- 展示格式化 ---------- */

/** 说话人 → 气泡样式后缀（agent / customer / system） */
function roleClass(role: string): string {
  return (role || 'SYSTEM').toLowerCase()
}

/** 消息起始时间（毫秒）→ 秒 */
function formatSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} 秒`
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

.filter-range {
  width: 380px;
}

.full-width {
  width: 100%;
}

.page-toolbar__total {
  color: #606266;
}

.text-danger {
  color: var(--el-color-danger);
}

.muted {
  color: #909399;
}

.dialog-section-title {
  margin: 16px 0 8px;
  font-weight: 600;
}

.import-failures {
  margin-top: 16px;
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
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>