<template>
  <div class="page-container">
    <div class="workspace">
      <el-card shadow="never" class="workspace__left">
        <div class="page-toolbar">
          <el-select
            v-model="query.status"
            placeholder="全部"
            clearable
            class="filter-select-sm"
            @change="onStatusChange"
          >
            <el-option
              v-for="item in QC_ITEM_STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <div class="page-toolbar__actions">
            <el-button :icon="Refresh" @click="loadList">刷新</el-button>
          </div>
        </div>

        <div class="page-toolbar__total">共 {{ total }} 条</div>

        <div v-loading="loading" class="item-list">
          <el-empty v-if="!rows.length" description="暂无质检明细" :image-size="60" />
          <div
            v-for="row in rows"
            :key="row.id"
            :class="['item-list__entry', { 'is-active': row.id === currentId }]"
            @click="selectItem(row.id)"
          >
            <div class="item-list__head">
              <span>对话 #{{ row.conversation_id }}</span>
              <StatusTag :value="row.status" :labels="QC_ITEM_STATUS_LABELS" />
            </div>
            <div class="item-list__meta">
              <span>任务 #{{ row.task_id }}</span>
              <el-tag
                v-if="row.grade"
                :type="QC_GRADE_TAG_TYPES[row.grade]"
                size="small"
                disable-transitions
              >
                {{ labelOf(QC_GRADE_LABELS, row.grade) }}
              </el-tag>
            </div>
          </div>
        </div>

        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="query.page"
            v-model:page-size="query.page_size"
            :total="total"
            layout="prev, pager, next"
            small
            @current-change="loadList"
          />
        </div>
      </el-card>

      <el-card shadow="never" class="workspace__right">
        <el-empty v-if="!detail" description="请从左侧选择一条待质检对话" />
        <template v-else>
          <el-descriptions :column="3" border>
            <el-descriptions-item label="对话 ID">
              {{ detail.item.conversation_id }}
            </el-descriptions-item>
            <el-descriptions-item label="客服">
              {{ detail.conversation?.agent_name ?? '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="渠道">
              {{ labelOf(CONVERSATION_CHANNEL_LABELS, detail.conversation?.channel) }}
            </el-descriptions-item>
            <el-descriptions-item label="开始时间">
              {{ detail.conversation?.started_at ?? '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="时长">
              {{ detail.conversation ? `${detail.conversation.duration} 秒` : '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="消息数">
              {{ detail.conversation?.msg_count ?? 0 }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="workspace__actions">
            <el-button
              v-if="detail.item.status === 'PENDING'"
              v-permission="'qc:review:work'"
              type="primary"
              :loading="claiming"
              @click="onClaim"
            >
              领取
            </el-button>
            <el-button
              v-else-if="detail.item.status === 'REVIEWING'"
              v-permission="'qc:review:work'"
              type="warning"
              @click="onRelease"
            >
              释放
            </el-button>
            <span class="form-tip">{{ statusTip }}</span>
          </div>

          <div class="bubbles">
            <el-empty v-if="!sortedMessages.length" description="暂无对话消息" :image-size="60" />
            <div
              v-for="message in sortedMessages"
              :key="message.seq"
              :class="['bubble-row', bubbleClass(message.role)]"
            >
              <div class="bubble">
                <div class="bubble__role">
                  {{ labelOf(MESSAGE_ROLE_LABELS, message.role) }}
                  <span v-if="message.start_ms !== null">{{ secondLabel(message.start_ms) }}</span>
                </div>
                <div class="bubble__content">{{ message.content }}</div>
              </div>
            </div>
          </div>

          <el-form :model="form" label-width="90px" class="review-form">
            <el-form-item label="得分">
              <el-input-number v-model="form.score" :min="0" :max="100" :disabled="!editable" />
              <span class="form-tip">0~100 分，必填</span>
            </el-form-item>
            <el-form-item label="等级预览">
              <el-tag :type="gradeTagType" disable-transitions>{{ gradePreview }}</el-tag>
              <div class="form-tip">等级由后端按分数阈值最终判定</div>
            </el-form-item>
            <el-form-item label="评语">
              <el-input v-model="form.comment" type="textarea" :rows="3" :disabled="!editable" />
            </el-form-item>
            <el-form-item label="分项得分">
              <div class="score-detail">
                <div
                  v-for="(entry, index) in form.scoreDetail"
                  :key="index"
                  class="score-detail__row"
                >
                  <el-input v-model="entry.key" placeholder="分项名称" :disabled="!editable" />
                  <el-input-number
                    v-model="entry.value"
                    :min="0"
                    :max="100"
                    :disabled="!editable"
                  />
                  <el-button link type="danger" :disabled="!editable" @click="removeScoreDetail(index)">
                    删除
                  </el-button>
                </div>
                <el-button
                  link
                  type="primary"
                  :icon="Plus"
                  :disabled="!editable"
                  @click="addScoreDetail"
                >
                  添加分项
                </el-button>
              </div>
            </el-form-item>
            <el-form-item>
              <el-button
                v-permission="'qc:review:submit'"
                type="primary"
                :disabled="!editable"
                :loading="submitting"
                @click="onSubmit"
              >
                提交质检
              </el-button>
              <span v-if="detail.item.status === 'COMPLETED'" class="form-tip">该明细已提交</span>
            </el-form-item>
          </el-form>
        </template>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  CONVERSATION_CHANNEL_LABELS,
  MESSAGE_ROLE_LABELS,
  QC_GRADE_LABELS,
  QC_GRADE_TAG_TYPES,
  QC_ITEM_STATUS_LABELS,
  QC_ITEM_STATUS_OPTIONS,
  labelOf,
  previewGrade,
} from '@/api/qc/enums'
import {
  claimQcItem,
  getQcItemDetail,
  listMyQcItems,
  releaseQcItem,
  submitQcItem,
  type MyQcItemQuery,
  type QcItemDetail,
  type QcMessageRole,
} from '@/api/qc/review'
import type { QcTaskItem } from '@/api/qc/tasks'
import StatusTag from '@/components/StatusTag.vue'

const loading = ref(false)
const claiming = ref(false)
const submitting = ref(false)
const rows = ref<QcTaskItem[]>([])
const total = ref(0)
const currentId = ref<number | null>(null)

const detail = ref<QcItemDetail | null>(null)

const query = reactive<MyQcItemQuery>({
  page: 1,
  page_size: 20,
  status: 'PENDING',
})

interface ScoreDetailEntry {
  key: string
  value: number
}

const form = reactive<{ score: number; comment: string; scoreDetail: ScoreDetailEntry[] }>({
  score: 0,
  comment: '',
  scoreDetail: [],
})

const editable = computed(() => detail.value?.item.status === 'REVIEWING')

const sortedMessages = computed(() => {
  const list = detail.value?.messages ?? []
  return [...list].sort((a, b) => a.seq - b.seq)
})

const gradePreview = computed(() => labelOf(QC_GRADE_LABELS, previewGrade(form.score)))

const gradeTagType = computed(() => QC_GRADE_TAG_TYPES[previewGrade(form.score)] ?? 'info')

const statusTip = computed(() => {
  const status = detail.value?.item.status
  if (status === 'PENDING') return '该明细待领取，领取后可评分'
  if (status === 'REVIEWING') return '已领取，请评分后提交'
  if (status === 'COMPLETED') return '该明细已提交'
  if (status === 'TIMEOUT') return '该明细已超时'
  return ''
})

function bubbleClass(role: QcMessageRole): string {
  if (role === 'AGENT') return 'is-agent'
  if (role === 'CUSTOMER') return 'is-customer'
  return 'is-system'
}

function secondLabel(startMs: number): string {
  return `（第 ${Math.floor(startMs / 1000)} 秒）`
}

function resetReviewForm(): void {
  form.score = 0
  form.comment = ''
  form.scoreDetail = []
}

async function loadList(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listMyQcItems(query)
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function loadDetail(itemId: number): Promise<void> {
  const { data } = await getQcItemDetail(itemId)
  detail.value = data
  resetReviewForm()
}

async function selectItem(itemId: number): Promise<void> {
  currentId.value = itemId
  await loadDetail(itemId)
}

function onStatusChange(): void {
  query.page = 1
  currentId.value = null
  detail.value = null
  void loadList()
}

function addScoreDetail(): void {
  form.scoreDetail.push({ key: '', value: 0 })
}

function removeScoreDetail(index: number): void {
  form.scoreDetail.splice(index, 1)
}

async function onClaim(): Promise<void> {
  const itemId = detail.value?.item.id
  if (!itemId) return
  claiming.value = true
  try {
    await claimQcItem(itemId)
    ElMessage.success('领取成功')
    await loadDetail(itemId)
    await loadList()
  } finally {
    claiming.value = false
  }
}

async function onRelease(): Promise<void> {
  const itemId = detail.value?.item.id
  if (!itemId) return
  try {
    await ElMessageBox.confirm('确认释放该质检明细？释放后将回到待质检。', '释放确认', {
      type: 'warning',
      confirmButtonText: '确定释放',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await releaseQcItem(itemId)
  ElMessage.success('已释放')
  await loadDetail(itemId)
  await loadList()
}

async function selectNextPending(): Promise<void> {
  const next = rows.value.find((row) => row.status === 'PENDING')
  if (next) {
    await selectItem(next.id)
    return
  }
  currentId.value = null
  detail.value = null
  ElMessage.info('当前没有更多待质检对话')
}

async function onSubmit(): Promise<void> {
  const itemId = detail.value?.item.id
  if (!itemId) return
  const scoreDetail: Record<string, unknown> = {}
  form.scoreDetail.forEach((entry) => {
    const key = entry.key.trim()
    if (key) scoreDetail[key] = entry.value
  })
  submitting.value = true
  try {
    const { data } = await submitQcItem(itemId, {
      score: form.score,
      comment: form.comment,
      score_detail: Object.keys(scoreDetail).length > 0 ? scoreDetail : null,
    })
    ElMessage.success(`提交成功，判定等级：${labelOf(QC_GRADE_LABELS, data.grade)}`)
    await loadList()
    await selectNextPending()
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  void loadList()
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

.form-tip {
  color: #909399;
  font-size: 12px;
}

.workspace {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.workspace__left {
  width: 360px;
  flex: none;
}

.workspace__right {
  flex: 1;
  min-width: 0;
}

.item-list {
  min-height: 120px;
}

.item-list__entry {
  padding: 8px 10px;
  margin-bottom: 8px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
}

.item-list__entry:hover {
  border-color: #c6e2ff;
}

.item-list__entry.is-active {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.item-list__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.item-list__meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #909399;
  font-size: 12px;
}

.workspace__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
}

.bubbles {
  max-height: 380px;
  overflow: auto;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 6px;
}

.bubble-row {
  display: flex;
  margin-bottom: 10px;
}

.bubble-row.is-agent {
  justify-content: flex-end;
}

.bubble-row.is-customer {
  justify-content: flex-start;
}

.bubble-row.is-system {
  justify-content: center;
}

.bubble {
  max-width: 70%;
  padding: 8px 10px;
  background: #ffffff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.bubble-row.is-agent .bubble {
  background: #ecf5ff;
  border-color: #d9ecff;
}

.bubble-row.is-system .bubble {
  color: #909399;
  background: transparent;
  border-color: transparent;
}

.bubble__role {
  margin-bottom: 4px;
  color: #909399;
  font-size: 12px;
}

.bubble__content {
  white-space: pre-wrap;
  word-break: break-word;
}

.review-form {
  margin-top: 16px;
}

.score-detail {
  width: 100%;
}

.score-detail__row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>