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
        <el-form-item label="流程名称">
          <el-input
            v-model="query.name"
            placeholder="模糊匹配"
            clearable
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item label="流程编码">
          <el-input
            v-model="query.code"
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
            v-permission="'outbound:ivr:create'"
            type="primary"
            :icon="Plus"
            @click="openFlowCreate"
          >
            新增流程
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe>
        <el-table-column prop="code" label="流程编码" width="150" />
        <el-table-column prop="name" label="流程名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="入口节点" width="150">
          <template #default="{ row }">{{ row.entry_node_key ?? '未设置' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.status" />
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="'outbound:ivr:list'"
              link
              type="primary"
              @click="openConfig(row)"
            >
              配置
            </el-button>
            <el-button
              v-permission="'outbound:ivr:update'"
              link
              type="primary"
              @click="openFlowEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-permission="'outbound:ivr:update'"
              link
              type="warning"
              @click="onToggleFlowStatus(row)"
            >
              {{ row.status === 'ENABLED' ? '停用' : '启用' }}
            </el-button>
            <el-button
              v-permission="'outbound:ivr:delete'"
              link
              type="danger"
              @click="onDeleteFlow(row)"
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

    <!-- 流程新增 / 编辑 -->
    <el-dialog v-model="flowDialogVisible" :title="flowDialogTitle" width="520px">
      <el-form ref="flowFormRef" :model="flowForm" :rules="flowRules" label-width="90px">
        <el-form-item label="租户" prop="tenant_id">
          <el-select
            v-model="flowForm.tenant_id"
            placeholder="请选择租户"
            :disabled="isFlowEdit"
            class="full-width"
          >
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="流程编码" prop="code">
          <el-input
            v-model="flowForm.code"
            :disabled="isFlowEdit"
            placeholder="如 IVR-001（创建后不可修改）"
          />
        </el-form-item>
        <el-form-item label="流程名称" prop="name">
          <el-input v-model="flowForm.name" placeholder="如 营销外呼主流程" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="flowForm.description" type="textarea" :rows="2" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="flowDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmitFlow">保存</el-button>
      </template>
    </el-dialog>

    <!-- 流程配置：节点 + 流转 + 校验 + 模拟 -->
    <el-drawer
      v-model="configVisible"
      :title="`IVR 流程配置 - ${currentFlow?.name ?? ''}`"
      size="85%"
      @closed="onConfigClosed"
    >
      <div v-loading="configLoading" class="config-body">
        <template v-if="currentFlow">
          <el-form :inline="true" @submit.prevent>
            <el-form-item label="入口节点">
              <el-select
                v-model="entryNodeKey"
                placeholder="请选择入口节点"
                clearable
                class="filter-select"
              >
                <el-option
                  v-for="item in currentFlow.nodes"
                  :key="item.id"
                  :label="`${item.name}（${item.node_key}）`"
                  :value="item.node_key"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button
                v-permission="'outbound:ivr:update'"
                type="primary"
                :loading="savingEntry"
                @click="onSaveEntry"
              >
                保存入口
              </el-button>
              <el-button :icon="CircleCheck" @click="onValidate">结构校验</el-button>
              <el-button type="success" :icon="VideoPlay" @click="openSimulate">模拟运行</el-button>
              <el-button :icon="Refresh" @click="loadConfig">刷新</el-button>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="validation"
            class="validation-alert"
            :type="validation.valid ? 'success' : 'error'"
            :closable="false"
            show-icon
            :title="
              validation.valid
                ? `校验通过：${validation.node_count} 个节点 / ${validation.transition_count} 条流转`
                : `校验未通过：${validation.error_count} 个错误，${validation.warning_count} 个提示`
            "
          />
          <el-table
            v-if="validation && validation.issues.length"
            class="validation-table"
            :data="validation.issues"
            border
            size="small"
          >
            <el-table-column label="级别" width="90">
              <template #default="{ row }">
                <el-tag :type="row.level === 'ERROR' ? 'danger' : 'warning'" disable-transitions>
                  {{ row.level === 'ERROR' ? '错误' : '提示' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="target" label="位置" width="160" />
            <el-table-column prop="code" label="问题码" width="200" />
            <el-table-column prop="message" label="说明" min-width="240" />
          </el-table>

          <el-tabs v-model="configTab">
            <el-tab-pane :label="`节点配置（${currentFlow.nodes.length}）`" name="nodes">
              <div class="page-toolbar">
                <span class="form-tip">
                  按键采集节点消费一次输入后按流转条件跳转；转人工节点必须配置无坐席兜底动作（§32）
                </span>
                <el-button
                  v-permission="'outbound:ivr:create'"
                  type="primary"
                  size="small"
                  :icon="Plus"
                  @click="openNodeCreate"
                >
                  新增节点
                </el-button>
              </div>
              <el-table :data="currentFlow.nodes" border stripe size="small">
                <el-table-column prop="node_key" label="节点标识" width="150" />
                <el-table-column prop="name" label="节点名称" width="160" />
                <el-table-column label="类型" width="120">
                  <template #default="{ row }">
                    {{ labelOf(IVR_NODE_TYPE_LABELS, row.node_type) }}
                  </template>
                </el-table-column>
                <el-table-column label="话术 / 提示音" min-width="200" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.content || '-' }}</template>
                </el-table-column>
                <el-table-column label="最大重播" width="100">
                  <template #default="{ row }">{{ row.max_replay }}</template>
                </el-table-column>
                <el-table-column label="无坐席动作" width="130">
                  <template #default="{ row }">
                    {{ labelOf(NO_AGENT_ACTION_LABELS, row.no_agent_action) }}
                  </template>
                </el-table-column>
                <el-table-column label="排序" width="80">
                  <template #default="{ row }">{{ row.sort_order }}</template>
                </el-table-column>
                <el-table-column label="操作" width="130" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      v-permission="'outbound:ivr:update'"
                      link
                      type="primary"
                      @click="openNodeEdit(row)"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-permission="'outbound:ivr:delete'"
                      link
                      type="danger"
                      @click="onDeleteNode(row)"
                    >
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane
              :label="`流转条件（${currentFlow.transitions.length}）`"
              name="transitions"
            >
              <div class="page-toolbar">
                <span class="form-tip">
                  按优先级升序匹配；条件值留空或填 * 表示「无条件 / 任意按键」兜底流转
                </span>
                <el-button
                  v-permission="'outbound:ivr:create'"
                  type="primary"
                  size="small"
                  :icon="Plus"
                  :disabled="currentFlow.nodes.length === 0"
                  @click="openTransitionCreate"
                >
                  新增流转
                </el-button>
              </div>
              <el-table :data="currentFlow.transitions" border stripe size="small">
                <el-table-column label="源节点" width="170">
                  <template #default="{ row }">{{ nodeLabel(row.from_node_id) }}</template>
                </el-table-column>
                <el-table-column label="条件类型" width="120">
                  <template #default="{ row }">
                    {{ labelOf(IVR_CONDITION_TYPE_LABELS, row.condition_type) }}
                  </template>
                </el-table-column>
                <el-table-column label="条件值" width="180">
                  <template #default="{ row }">
                    <span v-if="row.condition_value === null || row.condition_value === ''">
                      兜底（无条件 / 任意按键）
                    </span>
                    <span v-else>{{ row.condition_value }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="目标节点" min-width="170">
                  <template #default="{ row }">
                    <span v-if="row.to_node_id === null">流程结束</span>
                    <span v-else>{{ nodeLabel(row.to_node_id) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="优先级" width="90">
                  <template #default="{ row }">{{ row.priority }}</template>
                </el-table-column>
                <el-table-column label="操作" width="130" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      v-permission="'outbound:ivr:update'"
                      link
                      type="primary"
                      @click="openTransitionEdit(row)"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-permission="'outbound:ivr:delete'"
                      link
                      type="danger"
                      @click="onDeleteTransition(row)"
                    >
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </template>
      </div>
    </el-drawer>

    <!-- 节点新增 / 编辑 -->
    <el-dialog v-model="nodeDialogVisible" :title="nodeDialogTitle" width="560px">
      <el-form ref="nodeFormRef" :model="nodeForm" :rules="nodeRules" label-width="110px">
        <el-form-item label="节点标识" prop="node_key">
          <el-input
            v-model="nodeForm.node_key"
            :disabled="isNodeEdit"
            placeholder="如 menu（流程内唯一，创建后不可修改）"
          />
        </el-form-item>
        <el-form-item label="节点名称" prop="name">
          <el-input v-model="nodeForm.name" placeholder="如 主菜单" />
        </el-form-item>
        <el-form-item label="节点类型" prop="node_type">
          <el-select v-model="nodeForm.node_type" class="full-width">
            <el-option
              v-for="item in IVR_NODE_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="话术 / 提示音">
          <el-input v-model="nodeForm.content" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item v-if="nodeForm.node_type === 'TRANSFER_AGENT'" label="无坐席动作" prop="no_agent_action">
          <el-select v-model="nodeForm.no_agent_action" class="full-width" placeholder="必选">
            <el-option
              v-for="item in NO_AGENT_ACTION_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="技能队列">
          <el-select
            v-model="nodeForm.skill_queue_id"
            placeholder="可选，转人工时优先按该队列判断可用性"
            clearable
            class="full-width"
          >
            <el-option
              v-for="item in queueOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="最大重播次数">
          <el-input-number v-model="nodeForm.max_replay" :min="0" :max="99" />
          <span class="form-tip">非法按键 / 无坐席重播超过该次数即挂断</span>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="nodeForm.sort_order" :min="0" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmitNode">保存</el-button>
      </template>
    </el-dialog>

    <!-- 流转新增 / 编辑 -->
    <el-dialog v-model="transitionDialogVisible" :title="transitionDialogTitle" width="560px">
      <el-form
        ref="transitionFormRef"
        :model="transitionForm"
        :rules="transitionRules"
        label-width="110px"
      >
        <el-form-item label="源节点" prop="from_node_id">
          <el-select
            v-model="transitionForm.from_node_id"
            :disabled="isTransitionEdit"
            class="full-width"
            placeholder="请选择源节点"
          >
            <el-option
              v-for="item in currentFlow?.nodes ?? []"
              :key="item.id"
              :label="`${item.name}（${item.node_key}）`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="条件类型" prop="condition_type">
          <el-select v-model="transitionForm.condition_type" class="full-width">
            <el-option
              v-for="item in IVR_CONDITION_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="transitionForm.condition_type === 'QUEUE_AVAILABLE'" label="条件值">
          <el-select
            v-model="transitionForm.condition_value"
            class="full-width"
            placeholder="留空表示「有可用坐席」"
          >
            <el-option label="有可用坐席（留空同义）" :value="''" />
            <el-option label="无可用坐席" value="false" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="条件值">
          <el-input
            v-model="transitionForm.condition_value"
            :placeholder="conditionPlaceholder"
          />
        </el-form-item>
        <el-form-item label="目标节点">
          <el-select
            v-model="transitionForm.to_node_id"
            class="full-width"
            placeholder="留空表示流程结束"
            clearable
          >
            <el-option
              v-for="item in currentFlow?.nodes ?? []"
              :key="item.id"
              :label="`${item.name}（${item.node_key}）`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="transitionForm.priority" :min="0" :max="9999" />
          <span class="form-tip">数值越小越先匹配</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transitionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmitTransition">保存</el-button>
      </template>
    </el-dialog>

    <!-- 模拟运行 -->
    <el-dialog v-model="simulateVisible" title="IVR 流程模拟运行" width="880px" top="6vh">
      <el-form label-width="110px">
        <el-form-item label="输入序列">
          <el-input
            v-model="simulateForm.inputText"
            type="textarea"
            :rows="4"
            placeholder="每行一次输入，格式「类型 值」，如：&#10;KEY 1&#10;KEY 0&#10;ASR 咨询"
          />
        </el-form-item>
        <el-form-item label="模拟时间">
          <el-input v-model="simulateForm.current_time" placeholder="HH:MM，用于时段条件" />
          <span class="form-tip">格式如 10:30</span>
        </el-form-item>
        <el-form-item label="队列可用性">
          <el-select v-model="simulateForm.queue_state" class="filter-select">
            <el-option label="自动判断（按真实空闲坐席）" value="auto" />
            <el-option label="强制：有可用坐席" value="true" />
            <el-option label="强制：无可用坐席" value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="技能队列">
          <el-select
            v-model="simulateForm.skill_queue_id"
            placeholder="可选，仅用于自动判断队列可用性"
            clearable
            class="filter-select"
          >
            <el-option
              v-for="item in queueOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button
            v-permission="'outbound:ivr:list'"
            type="primary"
            :icon="VideoPlay"
            :loading="simulating"
            @click="onSimulate"
          >
            开始推演
          </el-button>
        </el-form-item>
      </el-form>

      <template v-if="simResult">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="结束原因">
            {{ labelOf(IVR_END_REASON_LABELS, simResult.end_reason) }}
          </el-descriptions-item>
          <el-descriptions-item label="最终节点">
            {{ simResult.final_node_key ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="是否转接人工">
            <el-tag :type="simResult.transferred ? 'success' : 'info'" disable-transitions>
              {{ simResult.transferred ? '已转接' : '未转接' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="无坐席兜底动作">
            {{ labelOf(NO_AGENT_ACTION_LABELS, simResult.no_agent_action) }}
          </el-descriptions-item>
          <el-descriptions-item label="采集到的按键">
            {{ simResult.collected_keys.length ? simResult.collected_keys.join('、') : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="重播次数">{{ simResult.replay_count }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">推演轨迹</el-divider>
        <el-table :data="simResult.steps" border stripe size="small">
          <el-table-column prop="index" label="#" width="60" />
          <el-table-column label="节点" width="180">
            <template #default="{ row }">{{ row.node_name }}（{{ row.node_key }}）</template>
          </el-table-column>
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              {{ labelOf(IVR_NODE_TYPE_LABELS, row.node_type) }}
            </template>
          </el-table-column>
          <el-table-column label="动作" width="110">
            <template #default="{ row }">
              {{ labelOf(IVR_SIM_ACTION_LABELS, row.action) }}
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="说明" min-width="240" show-overflow-tooltip />
          <el-table-column label="命中条件" width="180">
            <template #default="{ row }">
              <span v-if="!row.condition_type">-</span>
              <span v-else>
                {{ labelOf(IVR_CONDITION_TYPE_LABELS, row.condition_type) }} =
                {{ row.condition_value === null ? '兜底' : row.condition_value }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="跳转" width="150">
            <template #default="{ row }">
              <span v-if="row.action !== 'MOVE'">-</span>
              <span v-else>{{ row.to_node_key ?? '流程结束' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
      <template #footer>
        <el-button @click="simulateVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { CircleCheck, Plus, Refresh, Search, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import {
  COMMON_STATUS_OPTIONS,
  IVR_CONDITION_TYPE_LABELS,
  IVR_CONDITION_TYPE_OPTIONS,
  IVR_END_REASON_LABELS,
  IVR_NODE_TYPE_LABELS,
  IVR_NODE_TYPE_OPTIONS,
  IVR_SIM_ACTION_LABELS,
  NO_AGENT_ACTION_LABELS,
  NO_AGENT_ACTION_OPTIONS,
  labelOf,
} from '@/api/outbound/enums'
import {
  listSkillQueueOptions,
  listTenantOptions,
  type SkillQueueOption,
  type TenantOption,
} from '@/api/outbound/common'
import {
  changeIvrFlowStatus,
  createIvrFlow,
  createIvrNode,
  createIvrTransition,
  deleteIvrFlow,
  deleteIvrNode,
  deleteIvrTransition,
  getIvrFlow,
  listIvrFlows,
  simulateIvrFlow,
  updateIvrFlow,
  updateIvrNode,
  updateIvrTransition,
  validateIvrFlow,
  type IvrConditionType,
  type IvrFlow,
  type IvrFlowDetail,
  type IvrFlowQuery,
  type IvrNode,
  type IvrNodePayload,
  type IvrNodeType,
  type IvrSimulationResult,
  type IvrTransition,
  type IvrTransitionPayload,
  type IvrValidationResult,
  type NoAgentAction,
} from '@/api/outbound/ivr'
import StatusTag from '@/components/StatusTag.vue'
import type { CommonStatus } from '@/types/api'

const loading = ref(false)
const submitting = ref(false)
const rows = ref<IvrFlow[]>([])
const total = ref(0)
const tenants = ref<TenantOption[]>([])
const queueOptions = ref<SkillQueueOption[]>([])

const query = reactive<IvrFlowQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  code: '',
  name: '',
  status: undefined,
})

// ---------- 流程表单 ----------
const flowDialogVisible = ref(false)
const isFlowEdit = ref(false)
const currentFlowId = ref<number | null>(null)
const flowFormRef = ref<FormInstance>()

const flowForm = reactive<{
  tenant_id?: number
  code: string
  name: string
  description: string
}>({
  tenant_id: undefined,
  code: '',
  name: '',
  description: '',
})

const flowRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  code: [{ required: true, message: '请输入流程编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入流程名称', trigger: 'blur' }],
}

const flowDialogTitle = computed(() => (isFlowEdit.value ? '编辑 IVR 流程' : '新增 IVR 流程'))

// ---------- 流程配置（抽屉） ----------
const configVisible = ref(false)
const configLoading = ref(false)
const configTab = ref('nodes')
const currentFlow = ref<IvrFlowDetail | null>(null)
const entryNodeKey = ref<string | undefined>(undefined)
const savingEntry = ref(false)
const validation = ref<IvrValidationResult | null>(null)

// ---------- 节点表单 ----------
const nodeDialogVisible = ref(false)
const isNodeEdit = ref(false)
const editingNodeId = ref<number | null>(null)
const nodeFormRef = ref<FormInstance>()

const nodeForm = reactive<{
  node_key: string
  name: string
  node_type: IvrNodeType
  content: string
  no_agent_action: NoAgentAction | null
  skill_queue_id: number | null
  max_replay: number
  sort_order: number
}>({
  node_key: '',
  name: '',
  node_type: 'PLAY',
  content: '',
  no_agent_action: null,
  skill_queue_id: null,
  max_replay: 3,
  sort_order: 0,
})

const nodeRules: FormRules = {
  node_key: [{ required: true, message: '请输入节点标识', trigger: 'blur' }],
  name: [{ required: true, message: '请输入节点名称', trigger: 'blur' }],
  node_type: [{ required: true, message: '请选择节点类型', trigger: 'change' }],
  no_agent_action: [{ required: true, message: '请选择无可用坐席动作', trigger: 'change' }],
}

const nodeDialogTitle = computed(() => (isNodeEdit.value ? '编辑 IVR 节点' : '新增 IVR 节点'))

// ---------- 流转表单 ----------
const transitionDialogVisible = ref(false)
const isTransitionEdit = ref(false)
const editingTransitionId = ref<number | null>(null)
const transitionFormRef = ref<FormInstance>()

const transitionForm = reactive<{
  from_node_id: number | undefined
  condition_type: IvrConditionType
  condition_value: string
  to_node_id: number | null
  priority: number
}>({
  from_node_id: undefined,
  condition_type: 'KEY',
  condition_value: '',
  to_node_id: null,
  priority: 0,
})

const transitionRules: FormRules = {
  from_node_id: [{ required: true, message: '请选择源节点', trigger: 'change' }],
  condition_type: [{ required: true, message: '请选择条件类型', trigger: 'change' }],
}

const transitionDialogTitle = computed(() =>
  isTransitionEdit.value ? '编辑 IVR 流转条件' : '新增 IVR 流转条件',
)

const conditionPlaceholder = computed(() => {
  if (transitionForm.condition_type === 'KEY') return '按键值，如 1；留空或 * 表示兜底'
  if (transitionForm.condition_type === 'ASR_RESULT') return '识别关键字，如 咨询；留空表示任意'
  return '时段，如 09:00-18:00 或 09:00-12:00,14:00-18:00'
})

// ---------- 模拟运行 ----------
const simulateVisible = ref(false)
const simulating = ref(false)
const simResult = ref<IvrSimulationResult | null>(null)

const simulateForm = reactive<{
  inputText: string
  current_time: string
  queue_state: 'auto' | 'true' | 'false'
  skill_queue_id: number | null
}>({
  inputText: '',
  current_time: '',
  queue_state: 'auto',
  skill_queue_id: null,
})

// ---------- 数据加载 ----------

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const { data } = await listIvrFlows(query)
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

async function loadQueues(tenantId?: number): Promise<void> {
  if (!tenantId) {
    queueOptions.value = []
    return
  }
  const { data } = await listSkillQueueOptions({ tenant_id: tenantId })
  queueOptions.value = data
}

function onTenantChange(): void {
  void loadQueues(query.tenant_id).then(() => loadData())
}

function onSearch(): void {
  query.page = 1
  void loadData()
}

function onReset(): void {
  query.code = ''
  query.name = ''
  query.status = undefined
  onSearch()
}

function nodeLabel(nodeId: number | null): string {
  if (!nodeId) return '-'
  const node = currentFlow.value?.nodes.find((item) => item.id === nodeId)
  return node ? `${node.name}（${node.node_key}）` : `#${nodeId}`
}

// ---------- 流程 CRUD ----------

function openFlowCreate(): void {
  isFlowEdit.value = false
  currentFlowId.value = null
  flowForm.tenant_id = query.tenant_id ?? tenants.value[0]?.id
  flowForm.code = ''
  flowForm.name = ''
  flowForm.description = ''
  flowDialogVisible.value = true
}

function openFlowEdit(row: IvrFlow): void {
  isFlowEdit.value = true
  currentFlowId.value = row.id
  flowForm.tenant_id = row.tenant_id
  flowForm.code = row.code
  flowForm.name = row.name
  flowForm.description = row.description
  flowDialogVisible.value = true
}

async function onSubmitFlow(): Promise<void> {
  if (!flowFormRef.value) return
  const valid = await flowFormRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isFlowEdit.value && currentFlowId.value !== null) {
      // 编码创建后不可修改，更新时只提交允许变更的字段
      await updateIvrFlow(currentFlowId.value, {
        name: flowForm.name,
        description: flowForm.description,
      })
      ElMessage.success('保存成功')
    } else {
      await createIvrFlow({
        tenant_id: flowForm.tenant_id,
        code: flowForm.code,
        name: flowForm.name,
        description: flowForm.description,
      })
      ElMessage.success('新增成功')
    }
    flowDialogVisible.value = false
    await loadData()
  } finally {
    submitting.value = false
  }
}

async function onToggleFlowStatus(row: IvrFlow): Promise<void> {
  const next: CommonStatus = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  await changeIvrFlowStatus(row.id, next)
  ElMessage.success(next === 'ENABLED' ? '已启用' : '已停用')
  await loadData()
}

async function onDeleteFlow(row: IvrFlow): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除 IVR 流程「${row.name}」？其节点与流转将一并删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const { data } = await deleteIvrFlow(row.id)
  ElMessage.success(
    `删除成功，联动删除节点 ${data.removed_nodes} 个、流转 ${data.removed_transitions} 条`,
  )
  await loadData()
}

// ---------- 流程配置 ----------

async function openConfig(row: IvrFlow): Promise<void> {
  configVisible.value = true
  configTab.value = 'nodes'
  validation.value = null
  currentFlow.value = null
  currentFlowId.value = row.id
  await loadQueues(row.tenant_id)
  await loadConfig()
}

async function loadConfig(): Promise<void> {
  if (currentFlowId.value === null) return
  configLoading.value = true
  try {
    const { data } = await getIvrFlow(currentFlowId.value)
    currentFlow.value = data
    entryNodeKey.value = data.entry_node_key ?? undefined
  } finally {
    configLoading.value = false
  }
}

function onConfigClosed(): void {
  currentFlow.value = null
  validation.value = null
  simResult.value = null
}

async function onSaveEntry(): Promise<void> {
  if (currentFlowId.value === null) return
  savingEntry.value = true
  try {
    await updateIvrFlow(currentFlowId.value, { entry_node_key: entryNodeKey.value ?? null })
    ElMessage.success('入口节点已保存')
    validation.value = null
    await loadConfig()
  } finally {
    savingEntry.value = false
  }
}

async function onValidate(): Promise<void> {
  if (currentFlowId.value === null) return
  const { data } = await validateIvrFlow(currentFlowId.value)
  validation.value = data
  if (data.valid) {
    ElMessage.success('结构校验通过')
  } else {
    ElMessage.warning(`校验发现 ${data.error_count} 个错误，请查看下方清单`)
  }
}

// ---------- 节点 CRUD ----------

function openNodeCreate(): void {
  isNodeEdit.value = false
  editingNodeId.value = null
  nodeForm.node_key = ''
  nodeForm.name = ''
  nodeForm.node_type = 'PLAY'
  nodeForm.content = ''
  nodeForm.no_agent_action = null
  nodeForm.skill_queue_id = null
  nodeForm.max_replay = 3
  nodeForm.sort_order = 0
  nodeDialogVisible.value = true
}

function openNodeEdit(row: IvrNode): void {
  isNodeEdit.value = true
  editingNodeId.value = row.id
  nodeForm.node_key = row.node_key
  nodeForm.name = row.name
  nodeForm.node_type = row.node_type
  nodeForm.content = row.content
  nodeForm.no_agent_action = row.no_agent_action
  const queueId = row.config?.skill_queue_id
  nodeForm.skill_queue_id = typeof queueId === 'number' ? queueId : null
  nodeForm.max_replay = row.max_replay
  nodeForm.sort_order = row.sort_order
  nodeDialogVisible.value = true
}

async function onSubmitNode(): Promise<void> {
  if (!nodeFormRef.value || currentFlow.value === null) return
  const valid = await nodeFormRef.value.validate().catch(() => false)
  if (!valid) return

  const payload: IvrNodePayload = {
    node_key: nodeForm.node_key,
    name: nodeForm.name,
    node_type: nodeForm.node_type,
    content: nodeForm.content,
    max_replay: nodeForm.max_replay,
    sort_order: nodeForm.sort_order,
  }
  if (nodeForm.node_type === 'TRANSFER_AGENT') {
    payload.no_agent_action = nodeForm.no_agent_action
  }
  payload.config = nodeForm.skill_queue_id ? { skill_queue_id: nodeForm.skill_queue_id } : {}

  submitting.value = true
  try {
    if (isNodeEdit.value && editingNodeId.value !== null) {
      const update: IvrNodePayload = { ...payload }
      delete update.node_key
      await updateIvrNode(editingNodeId.value, update)
      ElMessage.success('保存成功')
    } else {
      await createIvrNode(currentFlow.value.id, {
        ...payload,
        tenant_id: currentFlow.value.tenant_id,
      })
      ElMessage.success('新增成功')
    }
    nodeDialogVisible.value = false
    validation.value = null
    await loadConfig()
  } finally {
    submitting.value = false
  }
}

async function onDeleteNode(row: IvrNode): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除节点「${row.name}」？与之相关的流转条件将一并删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const { data } = await deleteIvrNode(row.id)
  ElMessage.success(`删除成功，联动删除流转 ${data.removed_transitions} 条`)
  validation.value = null
  await loadConfig()
}

// ---------- 流转 CRUD ----------

function openTransitionCreate(): void {
  if (!currentFlow.value?.nodes.length) return
  isTransitionEdit.value = false
  editingTransitionId.value = null
  transitionForm.from_node_id = currentFlow.value.nodes[0].id
  transitionForm.condition_type = 'KEY'
  transitionForm.condition_value = ''
  transitionForm.to_node_id = null
  transitionForm.priority = 0
  transitionDialogVisible.value = true
}

function openTransitionEdit(row: IvrTransition): void {
  isTransitionEdit.value = true
  editingTransitionId.value = row.id
  transitionForm.from_node_id = row.from_node_id
  transitionForm.condition_type = row.condition_type
  transitionForm.condition_value = row.condition_value ?? ''
  transitionForm.to_node_id = row.to_node_id
  transitionForm.priority = row.priority
  transitionDialogVisible.value = true
}

async function onSubmitTransition(): Promise<void> {
  if (!transitionFormRef.value || currentFlow.value === null) return
  const valid = await transitionFormRef.value.validate().catch(() => false)
  if (!valid) return

  const rawValue = transitionForm.condition_value.trim()
  const payload: IvrTransitionPayload = {
    condition_type: transitionForm.condition_type,
    // QUEUE_AVAILABLE 留空即「有可用坐席」；其余类型留空表示兜底
    condition_value: rawValue === '' ? null : rawValue,
    to_node_id: transitionForm.to_node_id,
    priority: transitionForm.priority,
  }

  submitting.value = true
  try {
    if (isTransitionEdit.value && editingTransitionId.value !== null) {
      await updateIvrTransition(editingTransitionId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await createIvrTransition(currentFlow.value.id, {
        ...payload,
        tenant_id: currentFlow.value.tenant_id,
        from_node_id: transitionForm.from_node_id,
      })
      ElMessage.success('新增成功')
    }
    transitionDialogVisible.value = false
    validation.value = null
    await loadConfig()
  } finally {
    submitting.value = false
  }
}

async function onDeleteTransition(row: IvrTransition): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该流转条件？', '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await deleteIvrTransition(row.id)
  ElMessage.success('删除成功')
  validation.value = null
  await loadConfig()
}

// ---------- 模拟运行 ----------

function openSimulate(): void {
  simResult.value = null
  simulateVisible.value = true
}

/** 把「类型 值」逐行文本解析成按顺序的输入序列 */
function parseInputs(text: string): { input_type: 'KEY' | 'ASR'; value: string }[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const [head, ...rest] = line.split(/\s+/)
      const isAsr = head.toUpperCase() === 'ASR'
      const value = isAsr ? rest.join(' ') : rest.length ? rest.join(' ') : head
      return { input_type: isAsr ? ('ASR' as const) : ('KEY' as const), value }
    })
    .filter((item) => item.value.length > 0)
}

async function onSimulate(): Promise<void> {
  if (currentFlowId.value === null) return
  const time = simulateForm.current_time.trim()
  if (time && !/^\d{2}:\d{2}$/.test(time)) {
    ElMessage.warning('模拟时间格式应为 HH:MM，如 10:30')
    return
  }

  simulating.value = true
  try {
    const { data } = await simulateIvrFlow(currentFlowId.value, {
      inputs: parseInputs(simulateForm.inputText),
      current_time: time || null,
      queue_available:
        simulateForm.queue_state === 'auto' ? null : simulateForm.queue_state === 'true',
      skill_queue_id: simulateForm.skill_queue_id,
    })
    simResult.value = data
  } finally {
    simulating.value = false
  }
}

onMounted(async () => {
  await loadTenants()
  await loadQueues(query.tenant_id)
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

.form-tip {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.config-body {
  min-height: 320px;
}

.validation-alert {
  margin-bottom: 12px;
}

.validation-table {
  margin-bottom: 12px;
}

.page-toolbar__total {
  color: #606266;
}
</style>
