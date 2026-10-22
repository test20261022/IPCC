<template>
  <div class="page-container">
    <el-card shadow="never">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 会话列表 -->
        <el-tab-pane label="外呼会话" name="sessions">
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
                  v-for="item in taskOptions"
                  :key="item.id"
                  :label="`#${item.id} ${item.task_name}`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="坐席">
              <el-select
                v-model="query.agent_id"
                placeholder="全部"
                clearable
                filterable
                class="filter-select"
                @change="onSearch"
              >
                <el-option
                  v-for="item in agentOptions"
                  :key="item.id"
                  :label="agentLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="名单 ID">
              <el-input-number
                v-model="query.list_id"
                :min="1"
                placeholder="全部"
                controls-position="right"
                class="filter-number"
              />
            </el-form-item>
            <el-form-item label="会话状态">
              <el-select v-model="query.status" placeholder="全部" clearable class="filter-select-sm">
                <el-option
                  v-for="item in SESSION_STATUS_OPTIONS"
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
          </div>

          <el-table v-loading="loading" :data="rows" border stripe>
            <el-table-column prop="id" label="会话 ID" width="100" />
            <el-table-column label="任务" width="160">
              <template #default="{ row }">{{ nameOfTask(row.task_id) }}</template>
            </el-table-column>
            <el-table-column label="名单 ID" width="100">
              <template #default="{ row }">{{ row.list_id ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="坐席" width="110">
              <template #default="{ row }">{{ row.agent_id ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <StatusTag :value="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="当前号码" width="140">
              <template #default="{ row }">{{ row.current_phone ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="本轮尝试" width="100">
              <template #default="{ row }">{{ row.current_attempt }}</template>
            </el-table-column>
            <el-table-column label="开始时间" width="170">
              <template #default="{ row }">{{ row.started_at ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="结束时间" width="170">
              <template #default="{ row }">{{ row.finished_at ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="结束原因" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.end_reason ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-permission="'outbound:session:list'"
                  link
                  type="primary"
                  @click="openDetail(row)"
                >
                  详情
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

        <!-- 坐席工作台 -->
        <el-tab-pane label="坐席工作台" name="worklist">
          <el-form :inline="true" @submit.prevent>
            <el-form-item label="坐席">
              <el-select
                v-model="worklistAgentId"
                placeholder="请选择坐席"
                clearable
                filterable
                class="filter-select"
                @change="onWorklistSearch"
              >
                <el-option
                  v-for="item in agentOptions"
                  :key="item.id"
                  :label="agentLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="包含已结束">
              <el-switch v-model="includeFinished" @change="onWorklistSearch" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="onWorklistSearch">查询</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="worklistLoading" :data="worklistRows" border stripe>
            <el-table-column prop="record_id" label="记录 ID" width="100" />
            <el-table-column label="任务" min-width="150">
              <template #default="{ row }">{{ row.task_name }}</template>
            </el-table-column>
            <el-table-column prop="list_id" label="名单 ID" width="100" />
            <el-table-column label="UserID" width="110">
              <template #default="{ row }">{{ row.user_id ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="OrderID" width="110">
              <template #default="{ row }">{{ row.order_id ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="收件人" width="110">
              <template #default="{ row }">{{ row.recipient_name ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="号码数量" width="100">
              <template #default="{ row }">{{ row.phone_count }}</template>
            </el-table-column>
            <el-table-column label="号码来源" width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.phone_source || '-' }}</template>
            </el-table-column>
            <el-table-column label="已接通" width="100">
              <template #default="{ row }">
                <el-tag :type="row.has_success ? 'success' : 'info'" disable-transitions>
                  {{ row.has_success ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <StatusTag :value="row.record_status" />
              </template>
            </el-table-column>
            <el-table-column label="本轮尝试" width="100">
              <template #default="{ row }">{{ row.current_attempt }}</template>
            </el-table-column>
            <el-table-column label="重试轮次" width="100">
              <template #default="{ row }">{{ row.retry_count }}</template>
            </el-table-column>
            <el-table-column label="下次可重试" width="170">
              <template #default="{ row }">{{ row.next_retry_at ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="最近失败原因" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.last_failure_reason ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-permission="'outbound:session:list'"
                  link
                  type="primary"
                  @click="openPhones(row.list_id)"
                >
                  号码
                </el-button>
                <el-button
                  v-permission="'outbound:session:call'"
                  link
                  type="primary"
                  :disabled="row.record_status === 'SUCCESS'"
                  @click="onWorklistCall(row)"
                >
                  呼叫
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="worklistQuery.page"
              v-model:page-size="worklistQuery.page_size"
              :total="worklistTotal"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="loadWorklist"
              @size-change="onWorklistSearch"
            />
          </div>
        </el-tab-pane>

        <!-- 任务看板 -->
        <el-tab-pane label="任务看板" name="board">
          <el-form :inline="true" @submit.prevent>
            <el-form-item label="名单 ID">
              <el-input-number
                v-model="boardListId"
                :min="1"
                placeholder="请输入名单 ID"
                controls-position="right"
                class="filter-number"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="loadBoard">查看看板</el-button>
            </el-form-item>
          </el-form>

          <template v-if="board">
            <el-divider content-position="left">名单信息</el-divider>
            <el-descriptions :column="3" border>
              <el-descriptions-item label="名单 ID">{{ board.list_info.id }}</el-descriptions-item>
              <el-descriptions-item label="任务 ID">{{ board.list_info.task_id }}</el-descriptions-item>
              <el-descriptions-item label="状态">
                <StatusTag :value="board.list_info.status" />
              </el-descriptions-item>
              <el-descriptions-item label="UserID">
                {{ board.list_info.user_id ?? '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="OrderID">
                {{ board.list_info.order_id ?? '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="收件人">
                {{ board.list_info.recipient_name ?? '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="收件电话">
                {{ board.list_info.recipient_phone ?? '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="号码来源">
                {{ board.phone_source || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="尝试次数">
                {{ board.list_info.attempt_count }}
              </el-descriptions-item>
            </el-descriptions>

            <el-divider content-position="left">呼叫号码</el-divider>
            <div v-if="board.phones.length" class="tag-list">
              <el-tag v-for="phone in board.phones" :key="phone" type="primary" effect="plain">
                {{ phone }}
              </el-tag>
            </div>
            <el-empty v-else description="未解析出可呼叫号码" :image-size="60" />

            <el-divider content-position="left">第三方号码接口信息</el-divider>
            <el-descriptions v-if="externalEntries.length" :column="2" border>
              <el-descriptions-item
                v-for="item in externalEntries"
                :key="item.key"
                :label="item.key"
              >
                {{ item.value }}
              </el-descriptions-item>
            </el-descriptions>
            <el-empty v-else description="无第三方接口信息" :image-size="60" />

            <el-divider content-position="left">拨打历史</el-divider>
            <el-table :data="board.histories" border stripe>
              <el-table-column prop="phone" label="被叫号码" width="140" />
              <el-table-column label="呼叫结果" width="110">
                <template #default="{ row }">
                  {{ labelOf(CALL_STATUS_LABELS, row.call_status) }}
                </template>
              </el-table-column>
              <el-table-column label="通话时长" width="110">
                <template #default="{ row }">{{ row.duration }} 秒</template>
              </el-table-column>
              <el-table-column label="开始时间" width="170">
                <template #default="{ row }">{{ row.started_at ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="接通时间" width="170">
                <template #default="{ row }">{{ row.connected_at ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="结束时间" width="170">
                <template #default="{ row }">{{ row.ended_at ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="失败原因" min-width="140" show-overflow-tooltip>
                <template #default="{ row }">{{ row.failure_reason ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="录音" min-width="160" show-overflow-tooltip>
                <template #default="{ row }">{{ row.recording_path ?? '-' }}</template>
              </el-table-column>
            </el-table>

            <el-divider content-position="left">关联会话</el-divider>
            <el-table :data="board.sessions" border stripe>
              <el-table-column prop="id" label="会话 ID" width="100" />
              <el-table-column label="坐席" width="100">
                <template #default="{ row }">{{ row.agent_id ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{ row }">
                  <StatusTag :value="row.status" />
                </template>
              </el-table-column>
              <el-table-column label="当前号码" width="140">
                <template #default="{ row }">{{ row.current_phone ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="开始时间" width="170">
                <template #default="{ row }">{{ row.started_at ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="结束时间" width="170">
                <template #default="{ row }">{{ row.finished_at ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="结束原因" min-width="140" show-overflow-tooltip>
                <template #default="{ row }">{{ row.end_reason ?? '-' }}</template>
              </el-table-column>
            </el-table>

            <el-divider content-position="left">服务小结</el-divider>
            <el-table :data="board.summaries" border stripe>
              <el-table-column prop="session_id" label="会话 ID" width="100" />
              <el-table-column prop="result" label="处理结果" width="150">
                <template #default="{ row }">{{ row.result || '-' }}</template>
              </el-table-column>
              <el-table-column label="小结内容" min-width="240" show-overflow-tooltip>
                <template #default="{ row }">{{ row.summary || '-' }}</template>
              </el-table-column>
              <el-table-column label="标签" min-width="160">
                <template #default="{ row }">
                  <el-tag
                    v-for="tag in row.tags ?? []"
                    :key="tag"
                    class="tag-item"
                    type="info"
                    effect="plain"
                  >
                    {{ tag }}
                  </el-tag>
                  <span v-if="!row.tags?.length">-</span>
                </template>
              </el-table-column>
            </el-table>
          </template>
          <el-empty v-else description="请输入名单 ID 后查询看板" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 会话详情 -->
    <el-dialog v-model="detailVisible" title="外呼会话详情" width="900px" top="5vh">
      <template v-if="detail">
        <el-divider content-position="left">会话信息</el-divider>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="会话 ID">{{ detail.session.id }}</el-descriptions-item>
          <el-descriptions-item label="任务">{{ detail.task_name ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="坐席">{{ detail.session.agent_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :value="detail.session.status" />
          </el-descriptions-item>
          <el-descriptions-item label="当前号码">
            {{ detail.session.current_phone ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="本轮尝试">
            {{ detail.session.current_attempt }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ detail.session.started_at ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="结束时间">
            {{ detail.session.finished_at ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="结束原因">
            {{ detail.session.end_reason ?? '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">名单信息</el-divider>
        <el-descriptions v-if="detail.list_info" :column="3" border>
          <el-descriptions-item label="名单 ID">{{ detail.list_info.id }}</el-descriptions-item>
          <el-descriptions-item label="UserID">
            {{ detail.list_info.user_id ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="OrderID">
            {{ detail.list_info.order_id ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="收件人">
            {{ detail.list_info.recipient_name ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="收件电话">
            {{ detail.list_info.recipient_phone ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :value="detail.list_info.status" />
          </el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="无关联名单信息" :image-size="60" />

        <el-divider content-position="left">呼叫号码（{{ detail.phone_source || '无来源说明' }}）</el-divider>
        <div v-if="detail.phones.length" class="tag-list">
          <el-tag v-for="phone in detail.phones" :key="phone" type="primary" effect="plain">
            {{ phone }}
          </el-tag>
        </div>
        <el-empty v-else description="未解析出号码" :image-size="60" />

        <el-divider content-position="left">拨打历史</el-divider>
        <el-table :data="detail.histories" border stripe size="small">
          <el-table-column prop="phone" label="被叫号码" width="140" />
          <el-table-column label="呼叫结果" width="110">
            <template #default="{ row }">
              {{ labelOf(CALL_STATUS_LABELS, row.call_status) }}
            </template>
          </el-table-column>
          <el-table-column label="通话时长" width="110">
            <template #default="{ row }">{{ row.duration }} 秒</template>
          </el-table-column>
          <el-table-column label="开始时间" width="170">
            <template #default="{ row }">{{ row.started_at ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="结束时间" width="170">
            <template #default="{ row }">{{ row.ended_at ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="失败原因" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.failure_reason ?? '-' }}</template>
          </el-table-column>
        </el-table>

        <el-divider content-position="left">服务小结</el-divider>
        <el-form label-width="90px">
          <el-form-item label="处理结果">
            <el-input v-model="summaryForm.result" placeholder="如：有意向 / 无意向" maxlength="64" />
          </el-form-item>
          <el-form-item label="小结内容">
            <el-input v-model="summaryForm.summary" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="标签">
            <el-select
              v-model="summaryForm.tags"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="可自定义标签"
              class="full-width"
            />
          </el-form-item>
          <el-form-item>
            <el-button
              v-permission="'outbound:session:call'"
              type="primary"
              :loading="summarySubmitting"
              @click="onSubmitSummary"
            >
              {{ detail.summary ? '更新小结' : '提交小结' }}
            </el-button>
            <span class="form-tip">
              {{ detail.summary ? '已存在小结，提交为覆盖更新' : '该会话尚无小结' }}
            </span>
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 号码解析 -->
    <el-dialog v-model="phonesVisible" title="名单呼叫号码解析" width="620px">
      <template v-if="phones">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="名单 ID">{{ phones.list_id }}</el-descriptions-item>
          <el-descriptions-item label="任务">{{ phones.task_name ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="号码来源顺序">
            {{ phones.phone_source || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="已呼叫成功">
            {{ phones.has_success ? `是（${phones.success_phone ?? '-'}）` : '否' }}
          </el-descriptions-item>
          <el-descriptions-item label="重试情况">
            {{ phones.retry_count }} / {{ phones.max_retry_count ?? '-' }} 次，间隔
            {{ phones.retry_interval ?? '-' }} 秒
          </el-descriptions-item>
          <el-descriptions-item label="下次可重试">
            {{ phones.next_retry_at ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="最近失败原因">
            {{ phones.last_failure_reason ?? '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">按任务配置顺序解析的号码</el-divider>
        <div v-if="phones.phones.length" class="tag-list">
          <el-tag v-for="phone in phones.phones" :key="phone" type="primary" effect="plain">
            {{ phone }}
          </el-tag>
        </div>
        <el-empty v-else description="未解析出号码" :image-size="60" />

        <el-divider content-position="left">名单自带号码</el-divider>
        <div v-if="phones.list_phones.length" class="tag-list">
          <el-tag v-for="phone in phones.list_phones" :key="phone" type="info" effect="plain">
            {{ phone }}
          </el-tag>
        </div>
        <el-empty v-else description="名单无自带号码" :image-size="60" />

        <el-divider content-position="left">第三方电话簿号码</el-divider>
        <el-descriptions
          v-if="Object.keys(phones.provider_phones).length"
          :column="1"
          border
        >
          <el-descriptions-item
            v-for="(items, source) in phones.provider_phones"
            :key="source"
            :label="source"
          >
            {{ items.join('、') }}
          </el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="无第三方号码" :image-size="60" />
      </template>
      <template #footer>
        <el-button @click="phonesVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import {
  listAgentOptions,
  listTaskOptions,
  listTenantOptions,
  type AgentOption,
  type TaskOption,
  type TenantOption,
} from '@/api/outbound/common'
import { CALL_STATUS_LABELS, SESSION_STATUS_OPTIONS, labelOf } from '@/api/outbound/enums'
import { callRecord } from '@/api/outbound/record'
import {
  getAgentWorklist,
  getListBoard,
  getSessionDetail,
  listOutboundSessions,
  resolveListPhones,
  submitSessionSummary,
  updateSessionSummary,
  type OutboundAgentWorklistItem,
  type OutboundBoard,
  type OutboundListPhones,
  type OutboundSession,
  type OutboundSessionDetail,
  type OutboundSessionQuery,
} from '@/api/outbound/session'
import StatusTag from '@/components/StatusTag.vue'

const activeTab = ref('sessions')

const loading = ref(false)
const rows = ref<OutboundSession[]>([])
const total = ref(0)

const tenants = ref<TenantOption[]>([])
const taskOptions = ref<TaskOption[]>([])
const agentOptions = ref<AgentOption[]>([])

const query = reactive<OutboundSessionQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  task_id: undefined,
  agent_id: undefined,
  list_id: undefined,
  status: undefined,
})

// ---------- 会话详情 ----------
const detailVisible = ref(false)
const detail = ref<OutboundSessionDetail | null>(null)
const summarySubmitting = ref(false)
const summaryForm = reactive<{ summary: string; result: string; tags: string[] }>({
  summary: '',
  result: '',
  tags: [],
})

// ---------- 坐席工作台 ----------
const worklistLoading = ref(false)
const worklistAgentId = ref<number | undefined>(undefined)
const includeFinished = ref(false)
const worklistRows = ref<OutboundAgentWorklistItem[]>([])
const worklistTotal = ref(0)
const worklistQuery = reactive<{ page: number; page_size: number }>({ page: 1, page_size: 20 })

// ---------- 号码解析 ----------
const phonesVisible = ref(false)
const phones = ref<OutboundListPhones | null>(null)

// ---------- 任务看板 ----------
const boardListId = ref<number | undefined>(undefined)
const board = ref<OutboundBoard | null>(null)

const externalEntries = computed<{ key: string; value: string }[]>(() => {
  const info = board.value?.external_info
  if (!info) return []
  return Object.entries(info).map(([key, value]) => ({
    key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
})

function agentLabel(item: AgentOption): string {
  return `#${item.id}${item.extension ? ` 分机 ${item.extension}` : ''}`
}

function nameOfTask(taskId: number | null): string {
  if (!taskId) return '-'
  const task = taskOptions.value.find((item) => item.id === taskId)
  return task ? `#${task.id} ${task.task_name}` : `#${taskId}`
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listOutboundSessions(query)
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

async function loadOptions(tenantId?: number): Promise<void> {
  if (!tenantId) {
    taskOptions.value = []
    agentOptions.value = []
    return
  }
  const [tasks, agents] = await Promise.all([
    // 走选项接口而非任务列表接口：本页不需要 outbound:task:list 权限
    listTaskOptions(tenantId),
    listAgentOptions({ tenant_id: tenantId }),
  ])
  taskOptions.value = tasks.data
  agentOptions.value = agents.data
}

function onTenantChange(): void {
  query.task_id = undefined
  query.agent_id = undefined
  worklistAgentId.value = undefined
  worklistRows.value = []
  worklistTotal.value = 0
  void loadOptions(query.tenant_id).then(() => loadData())
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.task_id = undefined
  query.agent_id = undefined
  query.list_id = undefined
  query.status = undefined
  onSearch()
}

function onTabChange(name: string | number): void {
  if (name === 'board') return
  void loadData()
}

async function openDetail(row: OutboundSession): Promise<void> {
  const { data } = await getSessionDetail(row.id)
  detail.value = data
  summaryForm.summary = data.summary?.summary ?? ''
  summaryForm.result = data.summary?.result ?? ''
  summaryForm.tags = data.summary?.tags ?? []
  detailVisible.value = true
}

async function onSubmitSummary(): Promise<void> {
  if (!detail.value) return
  const sessionId = detail.value.session.id
  summarySubmitting.value = true
  try {
    if (detail.value.summary) {
      await updateSessionSummary(sessionId, { ...summaryForm })
    } else {
      await submitSessionSummary(sessionId, { ...summaryForm })
    }
    ElMessage.success('小结已保存')
    await openDetail(detail.value.session)
  } finally {
    summarySubmitting.value = false
  }
}

async function loadWorklist(): Promise<void> {
  if (!worklistAgentId.value) {
    worklistRows.value = []
    worklistTotal.value = 0
    return
  }
  worklistLoading.value = true
  try {
    const { data } = await getAgentWorklist(worklistAgentId.value, {
      page: worklistQuery.page,
      page_size: worklistQuery.page_size,
      include_finished: includeFinished.value,
    })
    worklistRows.value = data.items
    worklistTotal.value = data.total
  } finally {
    worklistLoading.value = false
  }
}

function onWorklistSearch(): void {
  worklistQuery.page = 1
  void loadWorklist()
}

async function openPhones(listId: number): Promise<void> {
  const { data } = await resolveListPhones(listId)
  phones.value = data
  phonesVisible.value = true
}

async function onWorklistCall(row: OutboundAgentWorklistItem): Promise<void> {
  const { data } = await callRecord(row.record_id, worklistAgentId.value ?? null)
  ElMessage.success(
    `呼叫已发起，记录状态：${data.status}；本轮尝试 ${data.current_attempt} 个号码，累计重试 ${data.retry_count} 轮`,
  )
  await loadWorklist()
}

async function loadBoard(): Promise<void> {
  if (!boardListId.value) {
    ElMessage.warning('请输入名单 ID')
    return
  }
  const { data } = await getListBoard(boardListId.value)
  board.value = data
}

onMounted(async () => {
  await loadTenants()
  await loadOptions(query.tenant_id)
  await loadData()
})
</script>

<style scoped>
.filter-select {
  width: 180px;
}

.filter-select-sm {
  width: 130px;
}

.filter-number {
  width: 150px;
}

.full-width {
  width: 100%;
}

.form-tip {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-item {
  margin-right: 4px;
}

.page-toolbar__total {
  color: #606266;
}
</style>
