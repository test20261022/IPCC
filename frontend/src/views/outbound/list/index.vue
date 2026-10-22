<template>
  <div class="page-container">
    <el-card shadow="never">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 名单数据 -->
        <el-tab-pane label="名单数据" name="lists">
          <el-form :inline="true" :model="query" @submit.prevent>
            <el-form-item label="租户">
              <el-select
                v-model="query.tenant_id"
                placeholder="全部"
                clearable
                class="filter-select"
                @change="onListTenantChange"
              >
                <el-option
                  v-for="item in tenants"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
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
                  v-for="item in tasks"
                  :key="item.id"
                  :label="item.task_name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="UserID">
              <el-input
                v-model="query.user_id"
                placeholder="精确匹配"
                clearable
                @keyup.enter="onSearch"
              />
            </el-form-item>
            <el-form-item label="OrderID">
              <el-input
                v-model="query.order_id"
                placeholder="精确匹配"
                clearable
                @keyup.enter="onSearch"
              />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="query.status" placeholder="全部" clearable class="filter-select-sm">
                <el-option
                  v-for="item in LIST_STATUS_OPTIONS"
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

          <div class="page-toolbar">
            <span class="page-toolbar__total">共 {{ total }} 条</span>
            <div class="page-toolbar__actions">
              <el-button
                v-permission="'outbound:list:import'"
                type="primary"
                :icon="Upload"
                @click="openImport"
              >
                导入名单
              </el-button>
            </div>
          </div>

          <el-table v-loading="loading" :data="rows" border stripe>
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="user_id" label="UserID" width="140" show-overflow-tooltip />
            <el-table-column prop="order_id" label="OrderID" width="140" show-overflow-tooltip />
            <el-table-column
              prop="recipient_name"
              label="收件人"
              width="120"
              show-overflow-tooltip
            />
            <el-table-column prop="recipient_phone" label="收件电话" width="140" />
            <el-table-column label="号码数量" width="100">
              <template #default="{ row }">
                {{ row.phone_numbers?.length ?? 0 }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" />
              </template>
            </el-table-column>
            <el-table-column prop="priority" label="优先级" width="90" />
            <el-table-column prop="attempt_count" label="尝试次数" width="100" />
            <el-table-column label="最后呼叫时间" width="180">
              <template #default="{ row }">
                {{ row.last_call_at || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-permission="'outbound:list:variable'"
                  link
                  type="primary"
                  @click="openVariables(row)"
                >
                  变量
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
            <el-form-item label="外呼任务">
              <el-select
                v-model="batchQuery.task_id"
                placeholder="全部"
                clearable
                filterable
                class="filter-select"
                @change="onBatchSearch"
              >
                <el-option
                  v-for="item in tasks"
                  :key="item.id"
                  :label="item.task_name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="导入状态">
              <el-select
                v-model="batchQuery.status"
                placeholder="全部"
                clearable
                class="filter-select-sm"
              >
                <el-option
                  v-for="item in IMPORT_BATCH_STATUS_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
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
            <el-table-column label="文件大小" width="110">
              <template #default="{ row }">
                {{ formatSize(row.file_size) }}
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
                <StatusTag :value="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="开始时间" width="180">
              <template #default="{ row }">
                {{ row.started_at || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="结束时间" width="180">
              <template #default="{ row }">
                {{ row.finished_at || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openBatchDetail(row)">明细</el-button>
                <el-button link type="primary" @click="onDownloadFailures(row.id)">
                  下载失败明细
                </el-button>
              </template>
            </el-table-column>
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

    <!-- 全场景变量 -->
    <el-dialog v-model="variableVisible" :title="variableTitle" width="560px">
      <el-table
        v-loading="variableLoading"
        :data="variableRows"
        border
        stripe
        max-height="360"
      >
        <el-table-column prop="name" label="变量名" min-width="180" />
        <el-table-column prop="value" label="变量值" min-width="240" show-overflow-tooltip />
      </el-table>
      <el-empty
        v-if="!variableLoading && variableRows.length === 0"
        description="暂无变量"
        :image-size="60"
      />
      <template #footer>
        <el-button @click="variableVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 导入批次明细 -->
    <el-dialog v-model="batchDialogVisible" title="导入批次明细" width="760px">
      <div v-loading="batchLoadingDetail">
        <el-descriptions v-if="batchDetail" :column="2" border>
          <el-descriptions-item label="文件名称">{{ batchDetail.file_name }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">
            {{ formatSize(batchDetail.file_size) }}
          </el-descriptions-item>
          <el-descriptions-item label="总行数">{{ batchDetail.total_rows }}</el-descriptions-item>
          <el-descriptions-item label="成功数">{{ batchDetail.success_rows }}</el-descriptions-item>
          <el-descriptions-item label="失败数">{{ batchDetail.failed_rows }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :value="batchDetail.status" />
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ batchDetail.started_at || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="结束时间">
            {{ batchDetail.finished_at || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="batchDetail" class="dialog-section-title">失败明细</div>
        <el-table v-if="batchFailures.length > 0" :data="batchFailures" border stripe max-height="300">
          <el-table-column prop="row" label="行号" width="80" />
          <el-table-column prop="field" label="字段" width="140" />
          <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
          <el-table-column prop="raw" label="原始值" min-width="160" show-overflow-tooltip />
        </el-table>
        <el-empty v-else-if="batchDetail" description="无失败明细" :image-size="60" />
      </div>
      <template #footer>
        <el-button @click="batchDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 导入名单 -->
    <el-dialog v-model="importVisible" title="导入外呼名单" width="640px">
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="外呼任务" required>
          <el-select
            v-model="importTaskId"
            placeholder="请选择外呼任务"
            filterable
            class="full-width"
            :disabled="importing"
          >
            <el-option
              v-for="item in tasks"
              :key="item.id"
              :label="item.task_name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名单文件" required>
          <el-upload
            ref="uploadRef"
            class="full-width"
            drag
            :auto-upload="false"
            :limit="1"
            :disabled="importing"
            accept=".xlsx,.csv"
            :on-change="onImportFileChange"
            :on-remove="onImportFileRemove"
            :on-exceed="onImportFileExceed"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">将文件拖到此处，或<em>点击选择文件</em></div>
            <template #tip>
              <div class="el-upload__tip">仅支持 .xlsx / .csv 格式，每次一个文件</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>

      <template v-if="importResult">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="总行数">{{ importResult.total_rows }}</el-descriptions-item>
          <el-descriptions-item label="成功数">
            {{ importResult.success_rows }}
          </el-descriptions-item>
          <el-descriptions-item label="失败数">
            {{ importResult.failed_rows }}
          </el-descriptions-item>
        </el-descriptions>

        <el-table
          v-if="importResult.failures.length > 0"
          :data="importResult.failures"
          border
          stripe
          max-height="260"
          class="import-failures"
        >
          <el-table-column prop="row" label="行号" width="80" />
          <el-table-column prop="field" label="字段" width="140" />
          <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
          <el-table-column prop="raw" label="原始值" min-width="160" show-overflow-tooltip />
        </el-table>
        <el-empty v-else description="无失败明细" :image-size="60" />

        <div v-if="importResult.failures.length > 0" class="import-actions">
          <el-button :icon="Download" @click="onImportDownloadFailures">下载失败明细</el-button>
        </div>
      </template>

      <template #footer>
        <template v-if="importResult">
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
import { Download, Refresh, Search, Upload, UploadFilled } from '@element-plus/icons-vue'
import {
  ElMessage,
  type TabPaneName,
  type UploadFile,
  type UploadInstance,
  type UploadRawFile,
} from 'element-plus'

import { listTaskOptions, listTenantOptions, type TaskOption, type TenantOption } from '@/api/outbound/common'
import {
  IMPORT_BATCH_STATUS_OPTIONS,
  LIST_STATUS_OPTIONS,
} from '@/api/outbound/enums'
import {
  downloadImportFailures,
  getImportBatch,
  getListVariables,
  importOutboundList,
  listImportBatches,
  listOutboundLists,
  type OutboundImportBatch,
  type OutboundImportBatchDetail,
  type OutboundImportBatchQuery,
  type OutboundImportResult,
  type OutboundList,
  type OutboundListQuery,
} from '@/api/outbound/list'
import StatusTag from '@/components/StatusTag.vue'

const activeTab = ref<TabPaneName>('lists')
const tenants = ref<TenantOption[]>([])
const tasks = ref<TaskOption[]>([])

/* ---------- 名单数据 ---------- */

const loading = ref(false)
const rows = ref<OutboundList[]>([])
const total = ref(0)

const query = reactive<OutboundListQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  task_id: undefined,
  user_id: '',
  order_id: '',
  status: undefined,
})

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listOutboundLists(query)
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.task_id = undefined
  query.user_id = ''
  query.order_id = ''
  query.status = undefined
  onSearch()
}

/* ---------- 导入批次 ---------- */

const batchLoading = ref(false)
const batchRows = ref<OutboundImportBatch[]>([])
const batchTotal = ref(0)

const batchQuery = reactive<OutboundImportBatchQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  task_id: undefined,
  status: undefined,
})

async function loadBatchData(): Promise<void> {
  batchLoading.value = true
  try {
    const { data } = await listImportBatches(batchQuery)
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
  batchQuery.task_id = undefined
  batchQuery.status = undefined
  onBatchSearch()
}

/* ---------- 租户 / 任务下拉 ---------- */

async function loadTenants(): Promise<void> {
  const { data } = await listTenantOptions()
  tenants.value = data
  const defaultTenantId = data[0]?.id
  if (defaultTenantId) {
    query.tenant_id = defaultTenantId
    batchQuery.tenant_id = defaultTenantId
  }
  await loadTaskOptions()
}

async function loadTaskOptions(): Promise<void> {
  if (!query.tenant_id) {
    tasks.value = []
    return
  }
  // 走选项接口而非任务列表接口：本页不需要 outbound:task:list 权限
  const { data } = await listTaskOptions(query.tenant_id)
  tasks.value = data
}

/** 两个页签的租户筛选保持同步，避免任务下拉与数据错配 */
function onListTenantChange(): void {
  batchQuery.tenant_id = query.tenant_id
  query.task_id = undefined
  batchQuery.task_id = undefined
  void loadTaskOptions()
  onSearch()
}

function onBatchTenantChange(): void {
  query.tenant_id = batchQuery.tenant_id
  query.task_id = undefined
  batchQuery.task_id = undefined
  void loadTaskOptions()
  onBatchSearch()
}

function onTabChange(name: TabPaneName): void {
  if (name === 'batches') {
    void loadBatchData()
  } else {
    void loadData()
  }
}

/* ---------- 全场景变量 ---------- */

interface VariableRow {
  name: string
  value: string
}

const variableVisible = ref(false)
const variableLoading = ref(false)
const variableUserId = ref<string | null>(null)
const variableRows = ref<VariableRow[]>([])

const variableTitle = computed(() =>
  variableUserId.value ? `全场景变量（UserID：${variableUserId.value}）` : '全场景变量',
)

async function openVariables(row: OutboundList): Promise<void> {
  variableVisible.value = true
  variableLoading.value = true
  variableUserId.value = row.user_id
  variableRows.value = []
  try {
    const { data } = await getListVariables(row.id)
    variableRows.value = Object.entries(data.variables ?? {}).map(([name, value]) => ({
      name,
      value: typeof value === 'string' ? value : JSON.stringify(value),
    }))
  } finally {
    variableLoading.value = false
  }
}

/* ---------- 导入批次明细 ---------- */

const batchDialogVisible = ref(false)
const batchLoadingDetail = ref(false)
const batchDetail = ref<OutboundImportBatchDetail | null>(null)

const batchFailures = computed(() => batchDetail.value?.failures ?? [])

async function openBatchDetail(row: OutboundImportBatch): Promise<void> {
  batchDialogVisible.value = true
  batchLoadingDetail.value = true
  batchDetail.value = null
  try {
    const { data } = await getImportBatch(row.id)
    batchDetail.value = data
  } finally {
    batchLoadingDetail.value = false
  }
}

function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/** 下载失败明细 CSV，浏览器直接触发下载 */
async function onDownloadFailures(batchId: number): Promise<void> {
  const blob = await downloadImportFailures(batchId)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `失败明细_${batchId}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/* ---------- 导入名单 ---------- */

const importVisible = ref(false)
const importing = ref(false)
const importTaskId = ref<number | undefined>(undefined)
const importFile = ref<UploadRawFile | null>(null)
const importResult = ref<OutboundImportResult | null>(null)
const uploadRef = ref<UploadInstance>()

function openImport(): void {
  resetImport()
  importTaskId.value = query.task_id
  importVisible.value = true
}

function resetImport(): void {
  importTaskId.value = undefined
  importFile.value = null
  importResult.value = null
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
  if (!importTaskId.value) {
    ElMessage.warning('请选择外呼任务')
    return
  }
  const file = importFile.value
  if (!file) {
    ElMessage.warning('请选择需要导入的名单文件')
    return
  }

  importing.value = true
  try {
    const { data } = await importOutboundList(importTaskId.value, file)
    importResult.value = data
    ElMessage.success(
      `导入完成：共 ${data.total_rows} 行，成功 ${data.success_rows} 行，失败 ${data.failed_rows} 行`,
    )
  } finally {
    importing.value = false
  }
}

function onImportDownloadFailures(): void {
  const result = importResult.value
  if (!result) return
  void onDownloadFailures(result.batch_id)
}

async function onImportFinish(): Promise<void> {
  closeImport()
  await loadData()
  await loadBatchData()
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

.text-danger {
  color: var(--el-color-danger);
}

.dialog-section-title {
  margin: 16px 0 8px;
  font-weight: 600;
}

.import-failures {
  margin-top: 16px;
}

.import-actions {
  margin-top: 12px;
  text-align: right;
}
</style>
