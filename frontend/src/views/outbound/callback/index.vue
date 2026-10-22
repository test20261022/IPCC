<template>
  <div class="page-container">
    <el-card shadow="never">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 回呼流程（OB-029） -->
        <el-tab-pane label="回呼流程" name="flows">
          <el-form :inline="true" :model="flowQuery" @submit.prevent>
            <el-form-item label="租户">
              <el-select
                v-model="flowQuery.tenant_id"
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
            <el-form-item label="流程名称">
              <el-input
                v-model="flowQuery.name"
                placeholder="模糊匹配"
                clearable
                @keyup.enter="onFlowSearch"
              />
            </el-form-item>
            <el-form-item label="流程编码">
              <el-input
                v-model="flowQuery.code"
                placeholder="模糊匹配"
                clearable
                @keyup.enter="onFlowSearch"
              />
            </el-form-item>
            <el-form-item label="状态">
              <el-select
                v-model="flowQuery.status"
                placeholder="全部"
                clearable
                class="filter-select-sm"
              >
                <el-option
                  v-for="item in COMMON_STATUS_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="onFlowSearch">查询</el-button>
              <el-button :icon="Refresh" @click="onFlowReset">重置</el-button>
            </el-form-item>
          </el-form>

          <div class="page-toolbar">
            <span class="page-toolbar__total">共 {{ flowTotal }} 条</span>
            <div class="page-toolbar__actions">
              <el-button
                v-permission="'outbound:callback:create'"
                type="primary"
                :icon="Plus"
                @click="openFlowCreate"
              >
                新增回呼流程
              </el-button>
            </div>
          </div>

          <el-table v-loading="flowLoading" :data="flowRows" border stripe>
            <el-table-column prop="code" label="流程编码" width="140" />
            <el-table-column prop="name" label="流程名称" min-width="150" show-overflow-tooltip />
            <el-table-column label="触发条件" min-width="240">
              <template #default="{ row }">
                <template v-if="row.trigger_condition?.triggers?.length">
                  <el-tag
                    v-for="item in row.trigger_condition.triggers"
                    :key="item"
                    class="tag-item"
                    type="primary"
                    effect="plain"
                  >
                    {{ labelOf(CALLBACK_TRIGGER_TYPE_LABELS, item) }}
                  </el-tag>
                </template>
                <span v-else>未配置（不自动触发）</span>
              </template>
            </el-table-column>
            <el-table-column label="延迟回呼" width="110">
              <template #default="{ row }">
                {{ row.trigger_condition?.delay_seconds ? `${row.trigger_condition.delay_seconds} 秒` : '立即' }}
              </template>
            </el-table-column>
            <el-table-column label="业务时段" width="150">
              <template #default="{ row }">
                {{ row.trigger_condition?.business_hours?.join('、') || '全天候' }}
              </template>
            </el-table-column>
            <el-table-column label="关联 IVR" width="110">
              <template #default="{ row }">
                {{ row.ivr_flow_id ? `#${row.ivr_flow_id}` : '-' }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="190" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-permission="'outbound:callback:create'"
                  link
                  type="primary"
                  @click="openFlowEdit(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-permission="'outbound:callback:create'"
                  link
                  type="warning"
                  @click="onToggleFlowStatus(row)"
                >
                  {{ row.status === 'ENABLED' ? '停用' : '启用' }}
                </el-button>
                <el-button
                  v-permission="'outbound:callback:create'"
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
              v-model:current-page="flowQuery.page"
              v-model:page-size="flowQuery.page_size"
              :total="flowTotal"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="loadFlows"
              @size-change="onFlowSearch"
            />
          </div>
        </el-tab-pane>

        <!-- 回呼任务（OB-029 / OB-030） -->
        <el-tab-pane label="回呼任务" name="tasks">
          <el-form :inline="true" :model="taskQuery" @submit.prevent>
            <el-form-item label="租户">
              <el-select
                v-model="taskQuery.tenant_id"
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
            <el-form-item label="来源">
              <el-select
                v-model="taskQuery.source"
                placeholder="全部"
                clearable
                class="filter-select-sm"
              >
                <el-option
                  v-for="item in CALLBACK_SOURCE_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select
                v-model="taskQuery.status"
                placeholder="全部"
                clearable
                class="filter-select-sm"
              >
                <el-option
                  v-for="item in CALLBACK_STATUS_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="回呼号码">
              <el-input
                v-model="taskQuery.phone"
                placeholder="模糊匹配"
                clearable
                @keyup.enter="onTaskSearch"
              />
            </el-form-item>
            <el-form-item label="坐席">
              <el-select
                v-model="taskQuery.agent_id"
                placeholder="全部"
                clearable
                filterable
                class="filter-select"
              >
                <el-option
                  v-for="item in agentOptions"
                  :key="item.id"
                  :label="agentLabel(item)"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="回呼流程">
              <el-select
                v-model="taskQuery.flow_id"
                placeholder="全部"
                clearable
                class="filter-select"
              >
                <el-option
                  v-for="item in flowOptions"
                  :key="item.id"
                  :label="`${item.name}（${item.code}）`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="onTaskSearch">查询</el-button>
              <el-button :icon="Refresh" @click="onTaskReset">重置</el-button>
            </el-form-item>
          </el-form>

          <div class="page-toolbar">
            <span class="page-toolbar__total">共 {{ taskTotal }} 条</span>
            <div class="page-toolbar__actions">
              <el-button
                v-permission="'outbound:callback:create'"
                type="primary"
                :icon="Plus"
                @click="openTaskCreate"
              >
                新建人工回呼
              </el-button>
              <el-button
                v-permission="'outbound:callback:execute'"
                :icon="Promotion"
                @click="onDispatchDue"
              >
                批量派单到期
              </el-button>
              <el-button
                v-permission="'outbound:callback:create'"
                type="success"
                :icon="PhoneFilled"
                @click="openIvrSimulate"
              >
                IVR 回呼试算
              </el-button>
            </div>
          </div>

          <el-table v-loading="taskLoading" :data="taskRows" border stripe>
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column label="来源" width="110">
              <template #default="{ row }">
                {{ labelOf(CALLBACK_SOURCE_LABELS, row.source) }}
              </template>
            </el-table-column>
            <el-table-column prop="phone" label="回呼号码" width="140" />
            <el-table-column label="触发条件" width="150">
              <template #default="{ row }">
                {{ labelOf(CALLBACK_TRIGGER_TYPE_LABELS, row.trigger_type) }}
              </template>
            </el-table-column>
            <el-table-column label="关联任务/名单" width="140">
              <template #default="{ row }">
                <span v-if="!row.task_id && !row.list_id">-</span>
                <span v-else>
                  {{ row.task_id ? `任务#${row.task_id}` : '' }}
                  {{ row.list_id ? `名单#${row.list_id}` : '' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="计划回呼" width="170">
              <template #default="{ row }">{{ row.scheduled_at ?? '立即' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" :labels="CALLBACK_STATUS_LABELS" />
              </template>
            </el-table-column>
            <el-table-column label="坐席" width="100">
              <template #default="{ row }">{{ row.agent_id ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="尝试" width="80">
              <template #default="{ row }">{{ row.attempt_count }}</template>
            </el-table-column>
            <el-table-column label="最后呼叫" width="170">
              <template #default="{ row }">{{ row.last_call_at ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="备注" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.remark || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="280" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-permission="'outbound:callback:execute'"
                  link
                  type="primary"
                  :disabled="row.status !== 'PENDING'"
                  @click="openAssign(row)"
                >
                  派单
                </el-button>
                <el-button
                  v-permission="'outbound:callback:execute'"
                  link
                  type="success"
                  :disabled="row.status !== 'ASSIGNED'"
                  @click="onCall(row)"
                >
                  呼出
                </el-button>
                <el-button
                  v-permission="'outbound:callback:execute'"
                  link
                  type="primary"
                  :disabled="!['ASSIGNED', 'CALLING'].includes(row.status)"
                  @click="openFinish(row)"
                >
                  登记结果
                </el-button>
                <el-button
                  v-permission="'outbound:callback:execute'"
                  link
                  type="warning"
                  :disabled="row.status !== 'FAILED'"
                  @click="onRequeue(row)"
                >
                  重呼
                </el-button>
                <el-button
                  v-permission="'outbound:callback:execute'"
                  link
                  type="danger"
                  :disabled="!['PENDING', 'ASSIGNED', 'CALLING'].includes(row.status)"
                  @click="onCancel(row)"
                >
                  取消
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="taskQuery.page"
              v-model:page-size="taskQuery.page_size"
              :total="taskTotal"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="loadTasks"
              @size-change="onTaskSearch"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 回呼流程新增 / 编辑 -->
    <el-dialog v-model="flowDialogVisible" :title="flowDialogTitle" width="640px">
      <el-form ref="flowFormRef" :model="flowForm" :rules="flowRules" label-width="120px">
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
            placeholder="如 CB-001（创建后不可修改）"
          />
        </el-form-item>
        <el-form-item label="流程名称" prop="name">
          <el-input v-model="flowForm.name" placeholder="如 转人工无坐席回呼" />
        </el-form-item>
        <el-form-item label="自动触发条件">
          <el-select
            v-model="flowForm.triggers"
            multiple
            placeholder="留空表示不自动触发（仅人工创建）"
            class="full-width"
          >
            <el-option
              v-for="item in CALLBACK_TRIGGER_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="flowForm.triggers.includes('KEY')" label="命中按键">
          <el-select
            v-model="flowForm.keys"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="如 0、9；留空表示客户按任意键即触发"
            class="full-width"
          />
        </el-form-item>
        <el-form-item label="业务时段">
          <el-input
            v-model="flowForm.businessHoursText"
            placeholder="如 09:00-18:00 或 09:00-12:00,14:00-18:00；留空表示全天候"
          />
        </el-form-item>
        <el-form-item label="延迟回呼">
          <el-input-number v-model="flowForm.delay_seconds" :min="0" :max="86400" />
          <span class="form-tip">秒；0 表示立即回呼</span>
        </el-form-item>
        <el-form-item label="最大尝试次数">
          <el-input-number v-model="flowForm.max_attempts" :min="1" :max="20" />
          <span class="form-tip">达到后不再自动生成回呼</span>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="flowForm.priority" :min="0" :max="9999" />
          <span class="form-tip">多流程同时命中时，数值小者优先</span>
        </el-form-item>
        <el-form-item label="关联 IVR 流程">
          <el-select
            v-model="flowForm.ivr_flow_id"
            placeholder="可选"
            clearable
            class="full-width"
          >
            <el-option
              v-for="item in ivrFlowOptions"
              :key="item.id"
              :label="`${item.name}（${item.code}）`"
              :value="item.id"
            />
          </el-select>
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

    <!-- 新建人工回呼 -->
    <el-dialog v-model="taskDialogVisible" title="新建人工回呼（OB-030）" width="560px">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-width="110px">
        <el-form-item label="租户" prop="tenant_id">
          <el-select v-model="taskForm.tenant_id" placeholder="请选择租户" class="full-width">
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="回呼号码" prop="phone">
          <el-input v-model="taskForm.phone" placeholder="请输入客户号码" maxlength="32" />
        </el-form-item>
        <el-form-item label="回呼流程">
          <el-select v-model="taskForm.flow_id" placeholder="可选" clearable class="full-width">
            <el-option
              v-for="item in flowOptions"
              :key="item.id"
              :label="`${item.name}（${item.code}）`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关联外呼任务">
          <el-select
            v-model="taskForm.task_id"
            placeholder="可选"
            clearable
            filterable
            class="full-width"
          >
            <el-option
              v-for="item in outboundTaskOptions"
              :key="item.id"
              :label="`#${item.id} ${item.task_name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="指定坐席">
          <el-select
            v-model="taskForm.agent_id"
            placeholder="可选，留空则后续派单时自动挑选"
            clearable
            filterable
            class="full-width"
          >
            <el-option
              v-for="item in agentOptions"
              :key="item.id"
              :label="agentLabel(item)"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="计划回呼时间">
          <el-date-picker
            v-model="taskForm.scheduled_at"
            type="datetime"
            placeholder="留空表示立即回呼"
            class="full-width"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="taskForm.remark" type="textarea" :rows="2" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmitTask">保存</el-button>
      </template>
    </el-dialog>

    <!-- 派单 -->
    <el-dialog v-model="assignVisible" title="回呼任务派单" width="460px">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="回呼号码">{{ assignTarget?.phone ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="来源">
          {{ labelOf(CALLBACK_SOURCE_LABELS, assignTarget?.source) }}
        </el-descriptions-item>
      </el-descriptions>
      <el-form class="assign-form" label-width="90px">
        <el-form-item label="执行坐席">
          <el-select
            v-model="assignAgentId"
            placeholder="留空则由系统挑选空闲坐席"
            clearable
            filterable
            class="full-width"
          >
            <el-option
              v-for="item in agentOptions"
              :key="item.id"
              :label="agentLabel(item)"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onAssign">确定派单</el-button>
      </template>
    </el-dialog>

    <!-- 登记结果 -->
    <el-dialog v-model="finishVisible" title="登记回呼结果" width="480px">
      <el-form label-width="90px">
        <el-form-item label="处理结果">
          <el-radio-group v-model="finishSuccess">
            <el-radio :value="true">已成功</el-radio>
            <el-radio :value="false">已失败</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="finishRemark" type="textarea" :rows="2" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="finishVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onFinish">保存</el-button>
      </template>
    </el-dialog>

    <!-- IVR 回呼试算 -->
    <el-dialog v-model="ivrVisible" title="IVR 回呼试算（OB-029）" width="640px">
      <el-alert
        class="ivr-hint"
        type="info"
        :closable="false"
        show-icon
        title="模拟 IVR 会话结束时上报触发上下文，按 §45 匹配回呼流程并生成回呼任务；同一会话 ID 只会生成一条（§78 幂等）。"
      />
      <el-form ref="ivrFormRef" :model="ivrForm" :rules="ivrRules" label-width="130px">
        <el-form-item label="租户" prop="tenant_id">
          <el-select v-model="ivrForm.tenant_id" class="full-width">
            <el-option v-for="item in tenants" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="回呼号码" prop="phone">
          <el-input v-model="ivrForm.phone" placeholder="客户来电号码" maxlength="32" />
        </el-form-item>
        <el-form-item label="原会话 ID" prop="origin_session_id">
          <el-input-number
            v-model="ivrForm.origin_session_id"
            :min="1"
            controls-position="right"
            class="filter-number"
          />
          <span class="form-tip">幂等键，重复提交同一 ID 不会重复生成</span>
        </el-form-item>
        <el-form-item label="指定回呼流程">
          <el-select v-model="ivrForm.flow_id" placeholder="留空则按优先级自动匹配" clearable class="full-width">
            <el-option
              v-for="item in flowOptions"
              :key="item.id"
              :label="`${item.name}（${item.code}）`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="客户按键">
          <el-select
            v-model="ivrForm.keys"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="如 0、9"
            class="full-width"
          />
        </el-form-item>
        <el-form-item label="触发事实">
          <el-checkbox v-model="ivrForm.no_agent">转人工无可用坐席</el-checkbox>
          <el-checkbox v-model="ivrForm.no_answer">未接通坐席即挂断</el-checkbox>
        </el-form-item>
        <el-form-item label="来电时间">
          <el-input v-model="ivrForm.current_time" placeholder="HH:MM，用于时段判定" />
        </el-form-item>
        <el-form-item label="已回呼次数">
          <el-input-number
            v-model="ivrForm.attempt_count"
            :min="0"
            :max="20"
            controls-position="right"
            class="filter-number"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            v-permission="'outbound:callback:create'"
            type="primary"
            :loading="submitting"
            @click="onIvrSimulate"
          >
            提交并匹配
          </el-button>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="ivrResult"
        :type="ivrResult.created ? 'success' : 'warning'"
        :closable="false"
        show-icon
        :title="ivrResult.created ? '已生成回呼任务' : '未生成回呼任务'"
        :description="ivrResult.reason"
      />
      <el-descriptions v-if="ivrResult?.task" class="ivr-result" :column="2" border>
        <el-descriptions-item label="回呼任务 ID">{{ ivrResult.task.id }}</el-descriptions-item>
        <el-descriptions-item label="命中流程">
          {{ ivrResult.flow_name ?? `#${ivrResult.flow_id}` }}
        </el-descriptions-item>
        <el-descriptions-item label="触发条件">
          {{ labelOf(CALLBACK_TRIGGER_TYPE_LABELS, ivrResult.trigger_type) }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <StatusTag :value="ivrResult.task.status" :labels="CALLBACK_STATUS_LABELS" />
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="ivrVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { PhoneFilled, Plus, Promotion, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import {
  CALLBACK_SOURCE_LABELS,
  CALLBACK_SOURCE_OPTIONS,
  CALLBACK_STATUS_LABELS,
  CALLBACK_STATUS_OPTIONS,
  CALLBACK_TRIGGER_TYPE_LABELS,
  CALLBACK_TRIGGER_TYPE_OPTIONS,
  COMMON_STATUS_OPTIONS,
  labelOf,
} from '@/api/outbound/enums'
import {
  listAgentOptions,
  listTaskOptions,
  listTenantOptions,
  type AgentOption,
  type TaskOption,
  type TenantOption,
} from '@/api/outbound/common'
import {
  assignCallbackTask,
  callCallbackTask,
  cancelCallbackTask,
  changeCallbackFlowStatus,
  createCallbackFlow,
  createCallbackFromIvr,
  createCallbackTask,
  deleteCallbackFlow,
  dispatchDueCallbacks,
  finishCallbackTask,
  listCallbackFlows,
  listCallbackTasks,
  requeueCallbackTask,
  updateCallbackFlow,
  type CallbackFlow,
  type CallbackFlowQuery,
  type CallbackTask,
  type CallbackTaskQuery,
  type CallbackTriggerResult,
  type CallbackTriggerType,
} from '@/api/outbound/callback'
import { listIvrFlowOptions, type IvrFlowOption } from '@/api/outbound/ivr'
import StatusTag from '@/components/StatusTag.vue'
import type { CommonStatus } from '@/types/api'

const activeTab = ref('flows')
const submitting = ref(false)

const tenants = ref<TenantOption[]>([])
const agentOptions = ref<AgentOption[]>([])
const ivrFlowOptions = ref<IvrFlowOption[]>([])
const outboundTaskOptions = ref<TaskOption[]>([])

// ---------- 回呼流程 ----------
const flowLoading = ref(false)
const flowRows = ref<CallbackFlow[]>([])
const flowTotal = ref(0)

const flowQuery = reactive<CallbackFlowQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  code: '',
  name: '',
  status: undefined,
})

const flowDialogVisible = ref(false)
const isFlowEdit = ref(false)
const currentFlowId = ref<number | null>(null)
const flowFormRef = ref<FormInstance>()

const flowForm = reactive<{
  tenant_id?: number
  code: string
  name: string
  triggers: CallbackTriggerType[]
  keys: string[]
  businessHoursText: string
  delay_seconds: number
  max_attempts: number
  priority: number
  ivr_flow_id: number | null
  description: string
}>({
  tenant_id: undefined,
  code: '',
  name: '',
  triggers: [],
  keys: [],
  businessHoursText: '',
  delay_seconds: 0,
  max_attempts: 3,
  priority: 0,
  ivr_flow_id: null,
  description: '',
})

const flowRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  code: [{ required: true, message: '请输入流程编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入流程名称', trigger: 'blur' }],
}

const flowDialogTitle = computed(() => (isFlowEdit.value ? '编辑回呼流程' : '新增回呼流程'))

/** 回呼流程下拉选项（供任务筛选 / 表单 / 试算复用） */
const flowOptions = computed(() => flowRows.value)

// ---------- 回呼任务 ----------
const taskLoading = ref(false)
const taskRows = ref<CallbackTask[]>([])
const taskTotal = ref(0)

const taskQuery = reactive<CallbackTaskQuery>({
  page: 1,
  page_size: 20,
  tenant_id: undefined,
  source: undefined,
  status: undefined,
  phone: '',
  agent_id: undefined,
  flow_id: undefined,
})

const taskDialogVisible = ref(false)
const taskFormRef = ref<FormInstance>()
const taskForm = reactive<{
  tenant_id?: number
  phone: string
  flow_id: number | null
  task_id: number | null
  agent_id: number | null
  scheduled_at: Date | null
  remark: string
}>({
  tenant_id: undefined,
  phone: '',
  flow_id: null,
  task_id: null,
  agent_id: null,
  scheduled_at: null,
  remark: '',
})

const taskRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  phone: [{ required: true, message: '请输入回呼号码', trigger: 'blur' }],
}

// ---------- 派单 / 登记结果 ----------
const assignVisible = ref(false)
const assignTarget = ref<CallbackTask | null>(null)
const assignAgentId = ref<number | undefined>(undefined)

const finishVisible = ref(false)
const finishTarget = ref<CallbackTask | null>(null)
const finishSuccess = ref(true)
const finishRemark = ref('')

// ---------- IVR 回呼试算 ----------
const ivrVisible = ref(false)
const ivrFormRef = ref<FormInstance>()
const ivrResult = ref<CallbackTriggerResult | null>(null)

const ivrForm = reactive<{
  tenant_id?: number
  phone: string
  origin_session_id: number | undefined
  flow_id: number | null
  keys: string[]
  no_agent: boolean
  no_answer: boolean
  current_time: string
  attempt_count: number
}>({
  tenant_id: undefined,
  phone: '',
  origin_session_id: undefined,
  flow_id: null,
  keys: [],
  no_agent: false,
  no_answer: false,
  current_time: '',
  attempt_count: 0,
})

const ivrRules: FormRules = {
  tenant_id: [{ required: true, message: '请选择租户', trigger: 'change' }],
  phone: [{ required: true, message: '请输入回呼号码', trigger: 'blur' }],
  origin_session_id: [{ required: true, message: '请输入原会话 ID', trigger: 'blur' }],
}

function agentLabel(item: AgentOption): string {
  return `#${item.id}${item.extension ? ` 分机 ${item.extension}` : ''}`
}

// ---------- 加载 ----------

async function loadFlows(): Promise<void> {
  flowLoading.value = true
  try {
    const { data } = await listCallbackFlows(flowQuery)
    flowRows.value = data.items
    flowTotal.value = data.total
  } finally {
    flowLoading.value = false
  }
}

async function loadTasks(): Promise<void> {
  taskLoading.value = true
  try {
    const { data } = await listCallbackTasks(taskQuery)
    taskRows.value = data.items
    taskTotal.value = data.total
  } finally {
    taskLoading.value = false
  }
}

async function loadTenants(): Promise<void> {
  const { data } = await listTenantOptions()
  tenants.value = data
  if (!flowQuery.tenant_id && data.length > 0) {
    flowQuery.tenant_id = data[0].id
    taskQuery.tenant_id = data[0].id
  }
}

async function loadOptions(tenantId?: number): Promise<void> {
  if (!tenantId) {
    agentOptions.value = []
    ivrFlowOptions.value = []
    outboundTaskOptions.value = []
    return
  }
  const [agents, ivrFlows, tasks] = await Promise.all([
    listAgentOptions({ tenant_id: tenantId }),
    listIvrFlowOptions(tenantId),
    // 走选项接口而非任务列表接口：本页不需要 outbound:task:list 权限
    listTaskOptions(tenantId),
  ])
  agentOptions.value = agents.data
  ivrFlowOptions.value = ivrFlows.data
  outboundTaskOptions.value = tasks.data
}

function onTenantChange(): void {
  taskQuery.tenant_id = flowQuery.tenant_id
  taskQuery.agent_id = undefined
  taskQuery.flow_id = undefined
  flowQuery.page = 1
  taskQuery.page = 1
  void loadOptions(flowQuery.tenant_id).then(() => Promise.all([loadFlows(), loadTasks()]))
}

function onTabChange(): void {
  void loadFlows()
  void loadTasks()
}

function onFlowSearch(): void {
  flowQuery.page = 1
  void loadFlows()
}

function onFlowReset(): void {
  flowQuery.code = ''
  flowQuery.name = ''
  flowQuery.status = undefined
  onFlowSearch()
}

function onTaskSearch(): void {
  taskQuery.page = 1
  void loadTasks()
}

function onTaskReset(): void {
  taskQuery.source = undefined
  taskQuery.status = undefined
  taskQuery.phone = ''
  taskQuery.agent_id = undefined
  taskQuery.flow_id = undefined
  onTaskSearch()
}

// ---------- 回呼流程 CRUD ----------

function openFlowCreate(): void {
  isFlowEdit.value = false
  currentFlowId.value = null
  flowForm.tenant_id = flowQuery.tenant_id ?? tenants.value[0]?.id
  flowForm.code = ''
  flowForm.name = ''
  flowForm.triggers = []
  flowForm.keys = []
  flowForm.businessHoursText = ''
  flowForm.delay_seconds = 0
  flowForm.max_attempts = 3
  flowForm.priority = 0
  flowForm.ivr_flow_id = null
  flowForm.description = ''
  flowDialogVisible.value = true
}

function openFlowEdit(row: CallbackFlow): void {
  isFlowEdit.value = true
  currentFlowId.value = row.id
  const condition = row.trigger_condition ?? {}
  flowForm.tenant_id = row.tenant_id
  flowForm.code = row.code
  flowForm.name = row.name
  flowForm.triggers = [...(condition.triggers ?? [])]
  flowForm.keys = [...(condition.keys ?? [])]
  flowForm.businessHoursText = (condition.business_hours ?? []).join(',')
  flowForm.delay_seconds = condition.delay_seconds ?? 0
  flowForm.max_attempts = condition.max_attempts ?? 3
  flowForm.priority = condition.priority ?? 0
  flowForm.ivr_flow_id = row.ivr_flow_id
  flowForm.description = row.description
  flowDialogVisible.value = true
}

async function onSubmitFlow(): Promise<void> {
  if (!flowFormRef.value) return
  const valid = await flowFormRef.value.validate().catch(() => false)
  if (!valid) return

  const hours = flowForm.businessHoursText
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
  const triggerCondition = {
    triggers: flowForm.triggers,
    keys: flowForm.triggers.includes('KEY') ? flowForm.keys : [],
    business_hours: hours,
    delay_seconds: flowForm.delay_seconds,
    max_attempts: flowForm.max_attempts,
    priority: flowForm.priority,
  }

  submitting.value = true
  try {
    if (isFlowEdit.value && currentFlowId.value !== null) {
      await updateCallbackFlow(currentFlowId.value, {
        name: flowForm.name,
        trigger_condition: triggerCondition,
        ivr_flow_id: flowForm.ivr_flow_id,
        description: flowForm.description,
      })
      ElMessage.success('保存成功')
    } else {
      await createCallbackFlow({
        tenant_id: flowForm.tenant_id,
        code: flowForm.code,
        name: flowForm.name,
        trigger_condition: triggerCondition,
        ivr_flow_id: flowForm.ivr_flow_id,
        description: flowForm.description,
      })
      ElMessage.success('新增成功')
    }
    flowDialogVisible.value = false
    await loadFlows()
  } finally {
    submitting.value = false
  }
}

async function onToggleFlowStatus(row: CallbackFlow): Promise<void> {
  const next: CommonStatus = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  await changeCallbackFlowStatus(row.id, next)
  ElMessage.success(next === 'ENABLED' ? '已启用' : '已停用')
  await loadFlows()
}

async function onDeleteFlow(row: CallbackFlow): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除回呼流程「${row.name}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await deleteCallbackFlow(row.id)
  ElMessage.success('删除成功')
  await loadFlows()
}

// ---------- 回呼任务 ----------

function openTaskCreate(): void {
  taskForm.tenant_id = taskQuery.tenant_id ?? tenants.value[0]?.id
  taskForm.phone = ''
  taskForm.flow_id = null
  taskForm.task_id = null
  taskForm.agent_id = null
  taskForm.scheduled_at = null
  taskForm.remark = ''
  taskDialogVisible.value = true
}

async function onSubmitTask(): Promise<void> {
  if (!taskFormRef.value) return
  const valid = await taskFormRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    await createCallbackTask({
      tenant_id: taskForm.tenant_id,
      source: 'MANUAL',
      phone: taskForm.phone.trim(),
      flow_id: taskForm.flow_id,
      task_id: taskForm.task_id,
      agent_id: taskForm.agent_id,
      scheduled_at: taskForm.scheduled_at ? taskForm.scheduled_at.toISOString() : null,
      remark: taskForm.remark,
    })
    ElMessage.success('回呼任务已创建')
    taskDialogVisible.value = false
    await loadTasks()
  } finally {
    submitting.value = false
  }
}

async function onDispatchDue(): Promise<void> {
  const { data } = await dispatchDueCallbacks({ tenant_id: taskQuery.tenant_id, limit: 50 })
  ElMessage.success(
    `扫描到期待回呼 ${data.scanned} 条，成功派单 ${data.assigned} 条，跳过 ${data.skipped} 条`,
  )
  await loadTasks()
}

function openAssign(row: CallbackTask): void {
  assignTarget.value = row
  assignAgentId.value = row.agent_id ?? undefined
  assignVisible.value = true
}

async function onAssign(): Promise<void> {
  if (!assignTarget.value) return
  submitting.value = true
  try {
    const { data } = await assignCallbackTask(assignTarget.value.id, assignAgentId.value ?? null)
    ElMessage.success(
      data.auto_assigned ? `已自动派给坐席 #${data.agent_id}` : `已派给坐席 #${data.agent_id}`,
    )
    assignVisible.value = false
    await loadTasks()
  } finally {
    submitting.value = false
  }
}

async function onCall(row: CallbackTask): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认向 ${row.phone} 发起回呼？`, '回呼确认', {
      type: 'warning',
      confirmButtonText: '发起回呼',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  const { data } = await callCallbackTask(row.id)
  if (data.status === 'SUCCESS') {
    ElMessage.success(`回呼成功，主叫号码 ${data.calling_number ?? '-'}，通话接通`)
  } else {
    ElMessage.warning(`回呼未成功：${data.failure_reason ?? data.call_status ?? '未知原因'}`)
  }
  await loadTasks()
}

function openFinish(row: CallbackTask): void {
  finishTarget.value = row
  finishSuccess.value = true
  finishRemark.value = ''
  finishVisible.value = true
}

async function onFinish(): Promise<void> {
  if (!finishTarget.value) return
  submitting.value = true
  try {
    await finishCallbackTask(finishTarget.value.id, finishSuccess.value, finishRemark.value)
    ElMessage.success('结果已登记')
    finishVisible.value = false
    await loadTasks()
  } finally {
    submitting.value = false
  }
}

async function onRequeue(row: CallbackTask): Promise<void> {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt('请输入重呼原因（可留空）', '重新入队', {
      inputValue: '',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    reason = result.value ?? ''
  } catch {
    return
  }
  await requeueCallbackTask(row.id, reason)
  ElMessage.success('已退回待回呼')
  await loadTasks()
}

async function onCancel(row: CallbackTask): Promise<void> {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt('请输入取消原因（可留空）', '取消回呼任务', {
      inputValue: '',
      confirmButtonText: '确定取消',
      cancelButtonText: '返回',
    })
    reason = result.value ?? ''
  } catch {
    return
  }
  await cancelCallbackTask(row.id, reason)
  ElMessage.success('已取消')
  await loadTasks()
}

// ---------- IVR 回呼试算 ----------

function openIvrSimulate(): void {
  ivrResult.value = null
  ivrForm.tenant_id = taskQuery.tenant_id ?? tenants.value[0]?.id
  ivrForm.phone = ''
  ivrForm.origin_session_id = undefined
  ivrForm.flow_id = null
  ivrForm.keys = []
  ivrForm.no_agent = false
  ivrForm.no_answer = false
  ivrForm.current_time = ''
  ivrForm.attempt_count = 0
  ivrVisible.value = true
}

async function onIvrSimulate(): Promise<void> {
  if (!ivrFormRef.value) return
  const valid = await ivrFormRef.value.validate().catch(() => false)
  if (!valid) return
  const time = ivrForm.current_time.trim()
  if (time && !/^\d{2}:\d{2}$/.test(time)) {
    ElMessage.warning('来电时间格式应为 HH:MM，如 20:30')
    return
  }

  submitting.value = true
  try {
    const { data } = await createCallbackFromIvr({
      tenant_id: ivrForm.tenant_id as number,
      phone: ivrForm.phone.trim(),
      origin_session_id: ivrForm.origin_session_id as number,
      flow_id: ivrForm.flow_id,
      keys: ivrForm.keys,
      no_agent: ivrForm.no_agent,
      no_answer: ivrForm.no_answer,
      current_time: time || null,
      attempt_count: ivrForm.attempt_count,
    })
    ivrResult.value = data
    await loadTasks()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await loadTenants()
  await loadOptions(flowQuery.tenant_id)
  await loadFlows()
})
</script>

<style scoped>
.filter-select {
  width: 180px;
}

.filter-select-sm {
  width: 120px;
}

.filter-number {
  width: 140px;
}

.full-width {
  width: 100%;
}

.form-tip {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.tag-item {
  margin-right: 4px;
}

.assign-form {
  margin-top: 16px;
}

.ivr-hint {
  margin-bottom: 12px;
}

.ivr-result {
  margin-top: 12px;
}

.page-toolbar__total {
  color: #606266;
}
</style>
