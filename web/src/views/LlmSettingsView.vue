<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, reactive, ref } from 'vue'
import { api } from '../api'
import JobBanner from '../components/JobBanner.vue'
import type { LlmConfig } from '../types'

const queryClient = useQueryClient()
const dialogVisible = ref(false)
const editingId = ref<string | null>(null)
const testJobId = ref<string | null>(null)
const form = reactive({
  name: '',
  provider: 'deepseek',
  model: 'deepseek-chat',
  apiKey: '',
  clearApiKey: false,
  baseUrl: '',
  temperature: 0.2,
  timeoutSeconds: 120,
  nativeStructuredOutput: 'auto' as boolean | 'auto',
  makeDefault: false,
  archived: false,
})

const configs = useQuery({
  queryKey: ['llm-configs'],
  queryFn: () => api.listLlmConfigs(true),
})
const testJob = useQuery({
  queryKey: ['llm-test-job', testJobId],
  queryFn: () => api.getJob(testJobId.value as string),
  enabled: computed(() => Boolean(testJobId.value)),
  refetchInterval: (query) =>
    ['queued', 'running'].includes(query.state.data?.status || '')
      ? 2000
      : false,
})

const saveMutation = useMutation({
  mutationFn: () =>
    api.saveLlmConfig(editingId.value, {
      ...form,
      apiKey: form.apiKey || null,
      baseUrl: form.baseUrl || null,
      nativeStructuredOutput:
        form.nativeStructuredOutput === 'auto'
          ? null
          : form.nativeStructuredOutput,
    }),
  onSuccess: () => {
    dialogVisible.value = false
    queryClient.invalidateQueries({ queryKey: ['llm-configs'] })
    ElMessage.success('LLM 配置已保存')
  },
})

const testMutation = useMutation({
  mutationFn: (id: string) => api.testLlmConfig(id),
  onSuccess: (job) => {
    testJobId.value = job.jobId
    ElMessage.success('连通性测试已进入后台队列')
  },
})

function resetForm() {
  editingId.value = null
  Object.assign(form, {
    name: '',
    provider: 'deepseek',
    model: 'deepseek-chat',
    apiKey: '',
    clearApiKey: false,
    baseUrl: '',
    temperature: 0.2,
    timeoutSeconds: 120,
    nativeStructuredOutput: 'auto',
    makeDefault: false,
    archived: false,
  })
}

function createConfig() {
  resetForm()
  dialogVisible.value = true
}

function editConfig(config: LlmConfig) {
  editingId.value = config.id
  Object.assign(form, {
    name: config.name,
    provider: config.provider,
    model: config.model,
    apiKey: '',
    clearApiKey: false,
    baseUrl: config.baseUrl || '',
    temperature: config.temperature,
    timeoutSeconds: config.timeoutSeconds,
    nativeStructuredOutput: config.nativeStructuredOutput ?? 'auto',
    makeDefault: config.isDefault,
    archived: Boolean(config.archivedAt),
  })
  dialogVisible.value = true
}

async function archiveConfig(config: LlmConfig) {
  await ElMessageBox.confirm(
    config.archivedAt ? '确认恢复此配置？' : '归档后新项目不可选择，确认归档？',
    config.archivedAt ? '恢复配置' : '归档配置',
  )
  editConfig(config)
  form.archived = !config.archivedAt
  saveMutation.mutate()
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>LLM 配置</h1>
      <p>管理 provider、模型与 API key。密钥读取后永不从接口返回原值。</p>
    </div>
    <el-button type="primary" size="large" @click="createConfig">
      新增配置
    </el-button>
  </div>

  <el-alert
    title="当前为本机单用户模式"
    description="按已确认方案，API key 明文保存在 MySQL。部署到远程服务器前必须迁移为加密存储。"
    type="warning"
    :closable="false"
    show-icon
    class="security-alert"
  />

  <section class="surface config-surface">
    <JobBanner v-if="testJob.data.value" :job="testJob.data.value" />
    <el-alert
      v-if="testJob.data.value?.status === 'succeeded'"
      title="LLM 连通性测试通过"
      :description="String(testJob.data.value.result.response || 'OK')"
      type="success"
      show-icon
      :closable="false"
      class="test-result"
    />
    <el-skeleton v-if="configs.isLoading.value" :rows="8" animated />
    <el-result
      v-else-if="configs.isError.value"
      icon="error"
      title="配置加载失败"
    >
      <template #extra>
        <el-button @click="configs.refetch()">重试</el-button>
      </template>
    </el-result>
    <el-empty
      v-else-if="!configs.data.value?.items.length"
      description="尚未配置 LLM"
    >
      <el-button type="primary" @click="createConfig">新增配置</el-button>
    </el-empty>
    <el-table v-else :data="configs.data.value.items">
      <el-table-column label="配置" min-width="190">
        <template #default="{ row }">
          <strong>{{ row.name }}</strong>
          <div class="config-sub">{{ row.provider }} / {{ row.model }}</div>
        </template>
      </el-table-column>
      <el-table-column label="API Key" width="170">
        <template #default="{ row }">
          <span class="mono">{{ row.apiKeyMask || '未设置' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="参数" min-width="160">
        <template #default="{ row }">
          <span>T {{ row.temperature }} · {{ row.timeoutSeconds }}s</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <el-tag v-if="row.isDefault" type="success">默认</el-tag>
          <el-tag v-if="row.archivedAt" type="info">已归档</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button text @click="editConfig(row)">编辑</el-button>
          <el-button text @click="testMutation.mutate(row.id)">测试</el-button>
          <el-button text type="warning" @click="archiveConfig(row)">
            {{ row.archivedAt ? '恢复' : '归档' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>

  <el-dialog
    v-model="dialogVisible"
    :title="editingId ? '编辑 LLM 配置' : '新增 LLM 配置'"
    width="650px"
  >
    <el-form label-position="top">
      <div class="form-grid">
        <el-form-item label="配置名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Provider">
          <el-input v-model="form.provider" placeholder="deepseek" />
        </el-form-item>
      </div>
      <el-form-item label="Model">
        <el-input v-model="form.model" placeholder="deepseek-chat" />
      </el-form-item>
      <el-form-item label="API Key">
        <el-input
          v-model="form.apiKey"
          type="password"
          show-password
          :placeholder="editingId ? '留空表示保留现有密钥' : '输入 API key'"
        />
      </el-form-item>
      <el-checkbox v-if="editingId" v-model="form.clearApiKey">
        明确清除现有 API key
      </el-checkbox>
      <el-form-item label="Base URL（可选）">
        <el-input v-model="form.baseUrl" placeholder="https://api.example.com/v1" />
      </el-form-item>
      <div class="form-grid">
        <el-form-item label="Temperature">
          <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="Timeout">
          <el-input-number v-model="form.timeoutSeconds" :min="1" :max="600" />
        </el-form-item>
      </div>
      <el-form-item label="原生 Structured Output">
        <el-select v-model="form.nativeStructuredOutput" style="width: 100%">
          <el-option label="自动判断" value="auto" />
          <el-option label="启用" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
      </el-form-item>
      <el-checkbox v-model="form.makeDefault">设为全局默认配置</el-checkbox>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!form.name.trim() || !form.provider.trim() || !form.model.trim()"
        :loading="saveMutation.isPending.value"
        @click="saveMutation.mutate()"
      >
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.security-alert {
  margin-bottom: 18px;
}

.config-surface {
  padding: 22px;
}

.test-result {
  margin-bottom: 16px;
}

.config-sub {
  margin-top: 5px;
  color: #849087;
  font-size: 11px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
</style>
