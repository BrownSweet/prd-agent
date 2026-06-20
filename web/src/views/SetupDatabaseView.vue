<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import { api } from '../api'

const queryClient = useQueryClient()
const testPassed = ref(false)
const saved = ref(false)

const form = reactive({
  databaseUrl: '',
  testDatabaseUrl: '',
})

const status = useQuery({
  queryKey: ['setup-status'],
  queryFn: () => api.getSetupStatus(),
})

watch(
  () => [form.databaseUrl, form.testDatabaseUrl],
  () => {
    testPassed.value = false
    saved.value = false
  },
)

const canSubmit = computed(
  () => form.databaseUrl.trim() && form.testDatabaseUrl.trim(),
)

const testMutation = useMutation({
  mutationFn: () =>
    api.testDatabaseSetup(
      form.databaseUrl.trim(),
      form.testDatabaseUrl.trim(),
    ),
  onSuccess: () => {
    testPassed.value = true
    ElMessage.success('数据库连接测试通过')
  },
})

const saveMutation = useMutation({
  mutationFn: () =>
    api.saveDatabaseSetup(
      form.databaseUrl.trim(),
      form.testDatabaseUrl.trim(),
    ),
  onSuccess: () => {
    saved.value = true
    queryClient.invalidateQueries({ queryKey: ['setup-status'] })
    ElMessage.success('数据库配置已保存')
  },
})
</script>

<template>
  <div class="page-header">
    <div>
      <h1>系统配置</h1>
      <p>配置本地 MySQL 连接。保存后需要重启 API 和 Worker 才会生效。</p>
    </div>
  </div>

  <section class="surface setup-surface">
    <el-skeleton v-if="status.isLoading.value" :rows="5" animated />
    <template v-else>
      <el-alert
        v-if="status.data.value?.ready"
        title="当前数据库连接可用"
        type="success"
        show-icon
        :closable="false"
        class="setup-alert"
      >
        <p>生产库：{{ status.data.value.databaseUrl }}</p>
        <p>测试库：{{ status.data.value.testDatabaseUrl }}</p>
      </el-alert>
      <el-alert
        v-else
        title="需要完成数据库配置"
        type="warning"
        show-icon
        :closable="false"
        class="setup-alert"
      >
        <p>API 当前处于 setup-only 模式，项目和 LLM 配置接口会暂时不可用。</p>
        <p v-if="status.data.value?.error">原因：{{ status.data.value.error }}</p>
      </el-alert>

      <el-alert
        title=".env 会明文保存数据库密码"
        description="这是本机单用户 MVP 的启动配置。保存后不会热切换数据库，请停止 API，执行 uv run prd-agent db-upgrade，再重新启动 API 和 Worker。"
        type="info"
        show-icon
        :closable="false"
        class="setup-alert"
      />

      <el-form label-position="top" class="setup-form">
        <el-form-item label="DATABASE_URL">
          <el-input
            v-model="form.databaseUrl"
            placeholder="mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent?charset=utf8mb4"
            clearable
          />
        </el-form-item>
        <el-form-item label="TEST_DATABASE_URL">
          <el-input
            v-model="form.testDatabaseUrl"
            placeholder="mysql+pymysql://USER:PASSWORD@HOST:3306/prd_agent_test?charset=utf8mb4"
            clearable
          />
        </el-form-item>
        <div class="setup-actions">
          <el-button
            :disabled="!canSubmit"
            :loading="testMutation.isPending.value"
            @click="testMutation.mutate()"
          >
            测试连接
          </el-button>
          <el-button
            type="primary"
            :disabled="!testPassed"
            :loading="saveMutation.isPending.value"
            @click="saveMutation.mutate()"
          >
            保存到 .env
          </el-button>
        </div>
      </el-form>

      <el-result
        v-if="saved"
        icon="success"
        title="配置已保存，需要重启服务"
        sub-title="请停止当前 API，执行 uv run prd-agent db-upgrade，然后重新启动 prd-agent api 和 prd-agent worker。"
      >
        <template #extra>
          <el-button type="primary" @click="status.refetch()">刷新状态</el-button>
        </template>
      </el-result>
    </template>
  </section>
</template>

<style scoped>
.setup-surface {
  max-width: 880px;
  padding: 24px;
}

.setup-alert {
  margin-bottom: 16px;
}

.setup-alert p {
  margin: 4px 0;
}

.setup-form {
  margin-top: 18px;
}

.setup-actions {
  display: flex;
  gap: 12px;
}
</style>
