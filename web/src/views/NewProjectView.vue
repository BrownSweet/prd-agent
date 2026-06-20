<script setup lang="ts">
import { useMutation, useQuery } from '@tanstack/vue-query'
import { ElMessage } from 'element-plus'
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const form = reactive({
  requirement: '',
  llmConfigId: '',
})

const configs = useQuery({
  queryKey: ['llm-configs'],
  queryFn: () => api.listLlmConfigs(),
})

const createMutation = useMutation({
  mutationFn: () => api.createProject(form.requirement, form.llmConfigId || undefined),
  onSuccess: ({ projectId }) => {
    ElMessage.success('项目已创建，Agent 开始结构化需求')
    router.push(`/projects/${projectId}`)
  },
})

function submit() {
  if (!form.requirement.trim()) {
    ElMessage.warning('请先输入产品需求')
    return
  }
  createMutation.mutate()
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>创建项目</h1>
      <p>先把想法原样写下来，Agent 会通过追问逐步补齐产品定义。</p>
    </div>
    <el-button @click="$router.back()">返回</el-button>
  </div>

  <div class="create-layout">
    <section class="surface create-form">
      <el-form label-position="top" size="large">
        <el-form-item label="初始需求">
          <el-input
            v-model="form.requirement"
            type="textarea"
            :rows="12"
            maxlength="6000"
            show-word-limit
            placeholder="例如：我想做一个 Telegram 频道监听工具，读取加密货币相关的图文消息，并提取标的、买入价、止盈和止损……"
          />
        </el-form-item>
        <el-form-item label="LLM 配置">
          <el-select
            v-model="form.llmConfigId"
            clearable
            placeholder="使用全局默认配置"
            style="width: 100%"
          >
            <el-option
              v-for="item in configs.data.value?.items || []"
              :key="item.id"
              :label="`${item.name} · ${item.provider}/${item.model}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          :loading="createMutation.isPending.value"
          @click="submit"
        >
          创建并开始分析
        </el-button>
      </el-form>
    </section>
    <aside class="creation-note">
      <span>01</span>
      <h2>不必一开始就写得完整</h2>
      <p>
        首轮只需要描述目标、已有资源和大致流程。系统会固定保存原始输入，并围绕模块、
        数据来源、交互、影响和依赖提出编号问题。
      </p>
      <span>02</span>
      <h2>每一轮都有明确门禁</h2>
      <p>信息不足时不能跳过结构化；阻断逻辑未解决时也不能进入 PRD。</p>
    </aside>
  </div>
</template>

<style scoped>
.create-layout {
  display: grid;
  grid-template-columns: minmax(0, 760px) 320px;
  gap: 30px;
}

.create-form {
  padding: 30px;
}

.creation-note {
  padding: 18px 4px;
}

.creation-note > span {
  display: block;
  margin-top: 12px;
  color: #87a050;
  font-family: Georgia, serif;
  font-size: 34px;
}

.creation-note h2 {
  margin: 7px 0;
  font-size: 16px;
}

.creation-note p {
  color: #6f7b74;
  font-size: 13px;
  line-height: 1.8;
}
</style>
