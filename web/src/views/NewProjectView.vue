<script setup lang="ts">
import { useMutation, useQuery } from '@tanstack/vue-query'
import DOMPurify from 'dompurify'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const markdown = new MarkdownIt({ html: false, linkify: true, typographer: true })
const fileInput = ref<HTMLInputElement | null>(null)
const inputMode = ref<'edit' | 'preview'>('edit')
const files = ref<File[]>([])
const form = reactive({
  requirement: '',
  llmConfigId: '',
})
const maxFiles = 8
const maxBytes = 20 * 1024 * 1024
const acceptedTypes = '.md,.txt,.html,.htm,.pdf,.docx,.png,.jpg,.jpeg,.webp'
const renderedRequirement = computed(() =>
  DOMPurify.sanitize(markdown.render(form.requirement || '')),
)
const totalFileBytes = computed(() =>
  files.value.reduce((total, file) => total + file.size, 0),
)

const configs = useQuery({
  queryKey: ['llm-configs'],
  queryFn: () => api.listLlmConfigs(),
})

const createMutation = useMutation({
  mutationFn: () =>
    api.createProject(
      form.requirement,
      form.llmConfigId || undefined,
      files.value,
    ),
  onSuccess: ({ projectId }) => {
    ElMessage.success('项目已创建，Agent 开始结构化需求')
    router.push(`/projects/${projectId}`)
  },
})

function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || [])
  const merged = [...files.value, ...selected]
  if (merged.length > maxFiles) {
    ElMessage.warning(`最多只能上传 ${maxFiles} 个附件`)
    input.value = ''
    return
  }
  const total = merged.reduce((sum, file) => sum + file.size, 0)
  if (total > maxBytes) {
    ElMessage.warning('附件总大小不能超过 20MB')
    input.value = ''
    return
  }
  files.value = merged
  input.value = ''
}

function removeFile(index: number) {
  files.value = files.value.filter((_, itemIndex) => itemIndex !== index)
}

function submit() {
  if (!form.requirement.trim() && files.value.length === 0) {
    ElMessage.warning('请先输入产品需求或上传附件')
    return
  }
  createMutation.mutate()
}

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
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
          <div class="markdown-input">
            <el-segmented
              v-model="inputMode"
              :options="[
                { label: '编辑', value: 'edit' },
                { label: '预览', value: 'preview' },
              ]"
            />
            <el-input
              v-if="inputMode === 'edit'"
              v-model="form.requirement"
              type="textarea"
              :rows="12"
              maxlength="6000"
              show-word-limit
              placeholder="支持 Markdown，例如：## 背景&#10;- 目标用户&#10;- 核心流程&#10;- 数据来源"
            />
            <article
              v-else
              class="markdown-preview"
              v-html="renderedRequirement"
            />
          </div>
        </el-form-item>
        <el-form-item label="需求附件">
          <div class="upload-box">
            <input
              ref="fileInput"
              class="file-input"
              type="file"
              multiple
              :accept="acceptedTypes"
              @change="selectFiles"
            >
            <div class="upload-actions">
              <el-button @click="fileInput?.click()">选择文件</el-button>
              <span class="muted">
                md、txt、html、pdf、docx、图片；最多 {{ maxFiles }} 个，合计 20MB
              </span>
            </div>
            <ul v-if="files.length" class="file-list">
              <li v-for="(file, index) in files" :key="`${file.name}-${index}`">
                <span>{{ file.name }}</span>
                <small>{{ formatSize(file.size) }}</small>
                <el-button text type="danger" @click="removeFile(index)">
                  移除
                </el-button>
              </li>
            </ul>
            <p v-if="files.length" class="file-total">
              已选择 {{ files.length }} 个附件，合计 {{ formatSize(totalFileBytes) }}
            </p>
          </div>
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

.markdown-input {
  display: grid;
  gap: 12px;
  width: 100%;
}

.markdown-preview {
  min-height: 282px;
  padding: 14px 16px;
  overflow: auto;
  color: #28342e;
  font-size: 14px;
  line-height: 1.75;
  background: #fbfcf8;
  border: 1px solid #dcded7;
  border-radius: 6px;
}

.markdown-preview :deep(h1),
.markdown-preview :deep(h2),
.markdown-preview :deep(h3) {
  margin: 12px 0 8px;
}

.markdown-preview :deep(p),
.markdown-preview :deep(ul),
.markdown-preview :deep(ol) {
  margin: 8px 0;
}

.upload-box {
  display: grid;
  gap: 12px;
  width: 100%;
}

.file-input {
  display: none;
}

.upload-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.file-list {
  display: grid;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.file-list li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 10px;
  align-items: center;
  padding: 9px 10px;
  background: #f8faf4;
  border: 1px solid #e2e5df;
  border-radius: 6px;
}

.file-list span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-list small,
.file-total {
  color: #77837c;
  font-size: 12px;
}

.file-total {
  margin: 0;
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
