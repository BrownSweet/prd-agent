<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import JobBanner from '../components/JobBanner.vue'
import RequirementPanel from '../components/RequirementPanel.vue'
import StageProgress from '../components/StageProgress.vue'
import { stageLabel, stageTagType } from '../stages'
import type { LogicIssue, Stage } from '../types'

const route = useRoute()
const queryClient = useQueryClient()
const projectId = computed(() => String(route.params.projectId))
const answers = reactive<Record<string, string>>({})
const feedback = ref('')
const waiver = reactive({ issueId: '', reason: '' })
const waiverVisible = ref(false)
const configVisible = ref(false)
const rollbackVisible = ref(false)
const overrideVisible = ref(false)
const selectedConfigId = ref('')
const rollbackTargetStage = ref<Stage | ''>('')
const rollbackFeedback = ref('')
const overrideReason = ref('')

const project = useQuery({
  queryKey: ['project', projectId],
  queryFn: () => api.getProject(projectId.value),
  refetchInterval: (query) => {
    const data = query.state.data
    return data?.activeJob ? 2000 : false
  },
})
const configs = useQuery({
  queryKey: ['llm-configs'],
  queryFn: () => api.listLlmConfigs(),
})

watch(
  () => project.data.value?.activeJob?.jobId,
  (current, previous) => {
    if (previous && !current) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    }
  },
)

const openQuestions = computed(
  () => project.data.value?.questions.filter((item) => item.status === 'open') ?? [],
)
const openIssues = computed(
  () => project.data.value?.logicIssues.filter((item) => item.status === 'open') ?? [],
)
const answerItems = computed(() => {
  if (project.data.value?.stage === 'STRUCTURING') return openQuestions.value
  if (project.data.value?.stage === 'LOGIC_VALIDATING') return openIssues.value
  return []
})
const gateErrors = computed(() => project.data.value?.gateErrors ?? [])
const canSubmitAnswers = computed(() => {
  const required = answerItems.value.filter(
    (item) =>
      !('severity' in item) ||
      item.severity === 'blocking' ||
      item.severity === 'important',
  )
  return required.length > 0 && required.every((item) => answers[itemId(item)]?.trim())
})

const jobMutation = useMutation({
  mutationFn: async (action: 'answers' | 'advance' | 'retry' | 'feedback') => {
    if (action === 'answers') {
      return api.submitAnswers(
        projectId.value,
        answerItems.value
          .filter((item) => answers[itemId(item)]?.trim())
          .map((item) => ({
            itemId: itemId(item),
            answer: answers[itemId(item)].trim(),
          })),
      )
    }
    if (action === 'advance') return api.advance(projectId.value)
    if (action === 'retry') return api.retry(projectId.value)
    return api.submitFeedback(projectId.value, feedback.value)
  },
  onSuccess: () => {
    Object.keys(answers).forEach((key) => delete answers[key])
    feedback.value = ''
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    ElMessage.success('已提交，后台任务开始执行')
  },
})

const waiveMutation = useMutation({
  mutationFn: () =>
    api.waive(projectId.value, waiver.issueId, waiver.reason),
  onSuccess: () => {
    waiverVisible.value = false
    waiver.reason = ''
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    ElMessage.success('问题已豁免')
  },
})

const archiveMutation = useMutation({
  mutationFn: (value: boolean) => api.archive(projectId.value, value),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    ElMessage.success('项目归档状态已更新')
  },
})

const configMutation = useMutation({
  mutationFn: () =>
    api.changeProjectLlmConfig(projectId.value, selectedConfigId.value),
  onSuccess: () => {
    configVisible.value = false
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    ElMessage.success('项目 LLM 配置已更新')
  },
})

const rollbackMutation = useMutation({
  mutationFn: () =>
    api.rollback(
      projectId.value,
      rollbackTargetStage.value,
      rollbackFeedback.value,
    ),
  onSuccess: () => {
    rollbackVisible.value = false
    rollbackFeedback.value = ''
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    ElMessage.success('已提交回退修改，后台任务开始执行')
  },
})

const regenerateSddMutation = useMutation({
  mutationFn: () => api.regenerateSdd(projectId.value),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    ElMessage.success('已提交重新生成SDD，后台任务开始执行')
  },
})

const overrideMutation = useMutation({
  mutationFn: () => api.overridePrdReview(projectId.value, overrideReason.value),
  onSuccess: () => {
    overrideVisible.value = false
    overrideReason.value = ''
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    ElMessage.success('已强行同意终审，进入SDD确认')
  },
})

function itemId(item: (typeof answerItems.value)[number]) {
  return 'questionId' in item ? item.questionId : item.issueId
}

function openWaiver(issue: LogicIssue) {
  waiver.issueId = issue.issueId
  waiver.reason = ''
  waiverVisible.value = true
}

async function archiveProject() {
  const value = !project.data.value?.archivedAt
  await ElMessageBox.confirm(
    value ? '确认归档此项目？' : '确认恢复此项目？',
    value ? '归档项目' : '恢复项目',
  )
  archiveMutation.mutate(value)
}

function openConfigDialog() {
  selectedConfigId.value = project.data.value?.llmConfig?.id || ''
  configVisible.value = true
}

function openRollbackDialog() {
  rollbackTargetStage.value = project.data.value?.rollbackTargets[0]?.stage || ''
  rollbackFeedback.value = ''
  rollbackVisible.value = true
}

function openOverrideDialog() {
  overrideReason.value = ''
  overrideVisible.value = true
}
</script>

<template>
  <div v-if="project.isLoading.value" class="surface empty-state">
    <el-skeleton :rows="12" animated />
  </div>
  <el-result
    v-else-if="project.isError.value"
    icon="error"
    title="项目加载失败"
    class="surface"
  >
    <template #extra>
      <el-button @click="project.refetch()">重试</el-button>
    </template>
  </el-result>
  <template v-else-if="project.data.value">
    <div class="page-header workspace-header">
      <div>
        <div class="header-tags">
          <el-tag
            :type="stageTagType(project.data.value.stageStatus)"
            effect="light"
          >
            {{ stageLabel(project.data.value.stage) }}
          </el-tag>
          <span class="mono">{{ projectId.slice(0, 8) }}</span>
          <span>第 {{ project.data.value.roundNumber }} 轮</span>
        </div>
        <h1>{{ project.data.value.requirementSpec.title || '需求分析中' }}</h1>
        <p>{{ project.data.value.requirementSpec.summary || 'Agent 正在形成当前需求理解。' }}</p>
      </div>
      <div class="toolbar">
        <el-button
          :disabled="Boolean(project.data.value.activeJob)"
          @click="openConfigDialog"
        >
          {{ project.data.value.llmConfig?.name || '选择 LLM' }}
        </el-button>
        <el-button
          v-if="project.data.value.allowedActions.includes('rollback')"
          type="warning"
          :disabled="Boolean(project.data.value.activeJob)"
          @click="openRollbackDialog"
        >
          回退修改
        </el-button>
        <el-button
          v-if="project.data.value.allowedActions.includes('regenerateSdd')"
          type="primary"
          :disabled="Boolean(project.data.value.activeJob)"
          :loading="regenerateSddMutation.isPending.value"
          @click="regenerateSddMutation.mutate()"
        >
          重新生成SDD
        </el-button>
        <el-dropdown v-if="project.data.value.artifacts.length">
          <el-button>查看文档</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="artifact in project.data.value.artifacts"
                :key="`${artifact.artifactType}-${artifact.version}`"
                @click="$router.push(
                  `/projects/${projectId}/artifacts/${artifact.artifactType}/${artifact.version}`,
                )"
              >
                {{ artifact.artifactType.toUpperCase() }} v{{ artifact.version }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button @click="archiveProject">
          {{ project.data.value.archivedAt ? '恢复项目' : '归档项目' }}
        </el-button>
      </div>
    </div>

    <StageProgress
      :stage="project.data.value.stage"
      :status="project.data.value.stageStatus"
    />

    <div class="workspace-grid">
      <main class="work-column">
        <JobBanner
          v-if="project.data.value.activeJob"
          :job="project.data.value.activeJob"
        />
        <JobBanner
          v-else-if="project.data.value.lastJob?.status === 'failed'"
          :job="project.data.value.lastJob"
        />

        <el-alert
          v-if="project.data.value.stageStatus === 'failed' && !project.data.value.activeJob"
          title="当前阶段执行失败"
          description="失败状态已保存，可以直接重试当前阶段。"
          type="error"
          show-icon
          :closable="false"
        >
          <template #default>
            <div class="failed-actions">
              <el-input
                v-if="project.data.value.allowedActions.includes('feedback')"
                v-model="feedback"
                type="textarea"
                :rows="4"
                placeholder="可输入PRD修订意见，例如：补充原始消息持久化、重启恢复、失败消息查询API"
              />
              <div class="submit-bar">
                <el-button
                  v-if="project.data.value.allowedActions.includes('feedback')"
                  :disabled="!feedback.trim()"
                  :loading="jobMutation.isPending.value"
                  @click="jobMutation.mutate('feedback')"
                >
                  提交修订意见
                </el-button>
                <el-button
                  type="danger"
                  :loading="jobMutation.isPending.value"
                  @click="jobMutation.mutate('retry')"
                >
                  重试当前阶段
                </el-button>
                <el-button
                  v-if="project.data.value.allowedActions.includes('overrideReview')"
                  type="warning"
                  :loading="overrideMutation.isPending.value"
                  @click="openOverrideDialog"
                >
                  强行同意
                </el-button>
              </div>
            </div>
          </template>
        </el-alert>

        <section
          v-if="
            gateErrors.length &&
            !answerItems.length &&
            !project.data.value.activeJob &&
            project.data.value.allowedActions.includes('feedback')
          "
          class="surface gate-gap-card"
        >
          <span class="eyebrow">NEEDS MORE DETAIL</span>
          <h2>结构化仍需补充</h2>
          <p>代码门禁还没有通过，请补充下面缺口后再进入下一阶段。</p>
          <ul class="gate-errors">
            <li v-for="error in gateErrors" :key="error">{{ error }}</li>
          </ul>
          <el-input
            v-model="feedback"
            type="textarea"
            :rows="4"
            placeholder="请补充交互逻辑、操作影响、数据来源或依赖关系等信息"
          />
          <div class="submit-bar">
            <span class="muted">补充内容会重新进入需求结构化</span>
            <el-button
              type="primary"
              :disabled="!feedback.trim()"
              :loading="jobMutation.isPending.value"
              @click="jobMutation.mutate('feedback')"
            >
              提交补充信息
            </el-button>
          </div>
        </section>

        <section
          v-if="answerItems.length && !project.data.value.activeJob"
          class="surface answer-surface"
        >
          <div class="section-heading">
            <div>
              <span class="eyebrow">ACTION REQUIRED</span>
              <h2>
                {{ project.data.value.stage === 'STRUCTURING' ? '补齐需求信息' : '处理逻辑问题' }}
              </h2>
            </div>
            <span>{{ answerItems.length }} 项待处理</span>
          </div>

          <article
            v-for="item in answerItems"
            :key="itemId(item)"
            class="answer-card"
          >
            <div class="answer-head">
              <span class="item-id">{{ itemId(item) }}</span>
              <el-tag
                v-if="'severity' in item"
                :type="item.severity === 'blocking' ? 'danger' : item.severity === 'important' ? 'warning' : 'info'"
                size="small"
              >
                {{ item.severity }}
              </el-tag>
              <span v-else class="question-type">{{ item.questionType }}</span>
            </div>
            <h3>{{ item.description }}</h3>
            <p v-if="'importance' in item">{{ item.importance }}</p>
            <el-input
              v-model="answers[itemId(item)]"
              type="textarea"
              :rows="3"
              placeholder="输入明确、可验证的答案"
            />
            <el-button
              v-if="'severity' in item && item.severity !== 'blocking'"
              text
              type="warning"
              @click="openWaiver(item)"
            >
              提供原因并豁免
            </el-button>
          </article>

          <div class="submit-bar">
            <span class="muted">本轮答案将合并为一次 Agent 调用</span>
            <el-button
              type="primary"
              size="large"
              :disabled="!canSubmitAnswers"
              :loading="jobMutation.isPending.value"
              @click="jobMutation.mutate('answers')"
            >
              提交本轮答案
            </el-button>
          </div>
        </section>

        <section
          v-else-if="
            project.data.value.stage === 'PRD_TYPE_CONFIRMING' &&
            !project.data.value.activeJob
          "
          class="surface answer-surface"
        >
          <span class="eyebrow">PRODUCT TYPE</span>
          <h2>确认产品类型</h2>
          <div class="type-card">
            <strong>主类型：{{ project.data.value.productType?.primary }}</strong>
            <p>次类型：{{ project.data.value.productType?.secondary.join('、') || '无' }}</p>
            <p>{{ project.data.value.productType?.rationale }}</p>
          </div>
          <el-input
            v-model="feedback"
            type="textarea"
            :rows="4"
            placeholder="识别不准确时，在这里输入修正意见"
          />
          <div class="submit-bar">
            <el-button
              :disabled="!feedback.trim()"
              @click="jobMutation.mutate('feedback')"
            >
              提交修正意见
            </el-button>
            <el-button
              type="primary"
              @click="jobMutation.mutate('advance')"
            >
              确认并生成 PRD
            </el-button>
          </div>
        </section>

        <section
          v-else-if="
            project.data.value.allowedActions.includes('advance') &&
            !project.data.value.activeJob
          "
          class="surface gate-card"
        >
          <span class="eyebrow">GATE READY</span>
          <h2>
            {{
              project.data.value.stage === 'SDD_CONFIRMING'
                ? 'PRD 终审通过'
                : '当前阶段信息充分'
            }}
          </h2>
          <p>
            {{
              project.data.value.stage === 'SDD_CONFIRMING'
                ? '确认后将基于终审通过的 PRD 生成 SDD。'
                : '代码门禁已满足，可以进入下一阶段。'
            }}
          </p>
          <el-button
            type="primary"
            size="large"
            @click="jobMutation.mutate('advance')"
          >
            进入下一步
          </el-button>
        </section>

        <el-result
          v-else-if="project.data.value.stage === 'COMPLETED'"
          icon="success"
          title="需求到 SDD 流程已完成"
          sub-title="所有文档均已保存版本，可在上方查看和下载。"
          class="surface"
        />
      </main>

      <RequirementPanel :spec="project.data.value.requirementSpec" />
    </div>

    <el-dialog v-model="waiverVisible" title="豁免逻辑问题" width="520px">
      <p class="muted">豁免会进入审计记录，请说明接受风险的具体原因。</p>
      <el-input v-model="waiver.reason" type="textarea" :rows="4" />
      <template #footer>
        <el-button @click="waiverVisible = false">取消</el-button>
        <el-button
          type="warning"
          :disabled="!waiver.reason.trim()"
          :loading="waiveMutation.isPending.value"
          @click="waiveMutation.mutate()"
        >
          确认豁免
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="configVisible" title="切换项目 LLM 配置" width="520px">
      <p class="muted">
        新配置只影响后续任务，已有 Artifact 保留原配置 metadata。
      </p>
      <el-select v-model="selectedConfigId" style="width: 100%">
        <el-option
          v-for="item in configs.data.value?.items || []"
          :key="item.id"
          :label="`${item.name} · ${item.provider}/${item.model}`"
          :value="item.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!selectedConfigId"
          :loading="configMutation.isPending.value"
          @click="configMutation.mutate()"
        >
          确认切换
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="overrideVisible" title="强行同意PRD终审" width="520px">
      <p class="muted">
        不会修改终审报告，只记录用户放行原因，并进入SDD生成确认。
      </p>
      <el-input
        v-model="overrideReason"
        type="textarea"
        :rows="4"
        placeholder="请填写强行同意理由"
      />
      <template #footer>
        <el-button @click="overrideVisible = false">取消</el-button>
        <el-button
          type="warning"
          :disabled="!overrideReason.trim()"
          :loading="overrideMutation.isPending.value"
          @click="overrideMutation.mutate()"
        >
          确认强行同意
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="rollbackVisible" title="回退修改" width="560px">
      <p class="muted">
        回退会从所选阶段重新生成后续结果，历史文档仍会保留。
      </p>
      <el-radio-group v-model="rollbackTargetStage" class="rollback-options">
        <el-radio
          v-for="target in project.data.value.rollbackTargets"
          :key="target.stage"
          :value="target.stage"
          border
        >
          <strong>{{ target.label }}</strong>
          <span>{{ target.description }}</span>
        </el-radio>
      </el-radio-group>
      <el-input
        v-model="rollbackFeedback"
        type="textarea"
        :rows="4"
        placeholder="说明要补充或修正的内容，Agent 会把它纳入回退后的重新生成"
      />
      <template #footer>
        <el-button @click="rollbackVisible = false">取消</el-button>
        <el-button
          type="warning"
          :disabled="!rollbackTargetStage"
          :loading="rollbackMutation.isPending.value"
          @click="rollbackMutation.mutate()"
        >
          确认回退
        </el-button>
      </template>
    </el-dialog>
  </template>
</template>

<style scoped>
.workspace-header {
  margin-bottom: 18px;
}

.header-tags {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
  color: #859088;
  font-size: 11px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 22px;
  align-items: start;
  margin-top: 22px;
}

.work-column {
  display: grid;
  gap: 16px;
}

.failed-actions {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.rollback-options {
  display: grid;
  gap: 10px;
  width: 100%;
  margin: 12px 0;
}

.rollback-options :deep(.el-radio) {
  width: 100%;
  height: auto;
  padding: 12px;
  white-space: normal;
}

.rollback-options strong,
.rollback-options span {
  display: block;
  line-height: 1.5;
}

.rollback-options span {
  color: #7b857f;
  font-size: 12px;
}

.answer-surface,
.gate-card,
.gate-gap-card {
  padding: 26px;
}

.section-heading,
.submit-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-heading {
  margin-bottom: 18px;
}

.section-heading h2,
.gate-card h2,
.gate-gap-card h2 {
  margin: 5px 0 0;
  font-size: 20px;
}

.section-heading > span {
  color: #849087;
  font-size: 12px;
}

.eyebrow {
  color: #78904a;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.13em;
}

.answer-card {
  margin-bottom: 14px;
  padding: 18px;
  background: #f9faf6;
  border: 1px solid #e4e7e1;
  border-radius: 12px;
}

.answer-head {
  display: flex;
  gap: 8px;
  align-items: center;
}

.item-id {
  color: #315d47;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
}

.question-type {
  color: #869189;
  font-size: 11px;
}

.answer-card h3 {
  margin: 10px 0 6px;
  font-size: 15px;
}

.answer-card p {
  margin: 0 0 12px;
  color: #7b857f;
  font-size: 12px;
}

.submit-bar {
  margin-top: 22px;
}

.type-card {
  margin: 16px 0;
  padding: 18px;
  background: #f4f7ec;
  border-left: 3px solid #9ab958;
}

.type-card p,
.gate-card p,
.gate-gap-card p {
  color: #6e7a73;
  line-height: 1.7;
}

.gate-card {
  text-align: center;
}

.gate-errors {
  margin: 14px 0 18px;
  padding-left: 20px;
  color: #9f3a38;
  line-height: 1.8;
}
</style>
