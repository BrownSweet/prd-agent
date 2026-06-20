<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import DOMPurify from 'dompurify'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const projectId = computed(() => String(route.params.projectId))
const artifactType = computed(() => String(route.params.type))
const version = computed(() => Number(route.params.version))
const markdown = new MarkdownIt({ html: false, linkify: true, typographer: true })

const artifacts = useQuery({
  queryKey: ['artifacts', projectId],
  queryFn: () => api.listArtifacts(projectId.value),
})
const artifact = useQuery({
  queryKey: ['artifact', projectId, artifactType, version],
  queryFn: () => api.getArtifact(projectId.value, artifactType.value, version.value),
})
const regenerateSddMutation = useMutation({
  mutationFn: () => api.regenerateSdd(projectId.value),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['artifacts', projectId] })
    queryClient.invalidateQueries({
      queryKey: ['artifact', projectId, artifactType, version],
    })
    ElMessage.success('已提交重新生成SDD，后台任务开始执行')
  },
})

const rendered = computed(() =>
  DOMPurify.sanitize(markdown.render(artifact.data.value?.content || '')),
)

function switchVersion(value: string) {
  const [type, rawVersion] = value.split(':')
  router.push(`/projects/${projectId.value}/artifacts/${type}/${rawVersion}`)
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>{{ artifactType.toUpperCase() }} v{{ version }}</h1>
      <p>只读版本文档，所有生成上下文已记录在 Artifact metadata。</p>
    </div>
    <div class="toolbar">
      <el-select
        :model-value="`${artifactType}:${version}`"
        style="width: 190px"
        @change="switchVersion"
      >
        <el-option
          v-for="item in artifacts.data.value?.items || []"
          :key="`${item.artifactType}:${item.version}`"
          :label="`${item.artifactType.toUpperCase()} v${item.version}`"
          :value="`${item.artifactType}:${item.version}`"
        />
      </el-select>
      <el-button
        tag="a"
        :href="api.artifactDownloadUrl(projectId, artifactType, version)"
      >
        下载 Markdown
      </el-button>
      <el-button
        v-if="artifactType === 'sdd'"
        type="primary"
        :loading="regenerateSddMutation.isPending.value"
        @click="regenerateSddMutation.mutate()"
      >
        重新生成SDD
      </el-button>
      <el-button @click="$router.push(`/projects/${projectId}`)">返回项目</el-button>
    </div>
  </div>

  <section v-if="artifact.isLoading.value" class="surface document-shell">
    <el-skeleton :rows="15" animated />
  </section>
  <el-result
    v-else-if="artifact.isError.value"
    icon="error"
    title="文档加载失败"
    class="surface"
  >
    <template #extra>
      <el-button @click="artifact.refetch()">重试</el-button>
    </template>
  </el-result>
  <section v-else class="surface document-shell">
    <article class="markdown-body" v-html="rendered" />
  </section>
</template>

<style scoped>
.document-shell {
  max-width: 980px;
  min-height: 600px;
  padding: 48px 64px;
  margin: 0 auto;
}

.markdown-body {
  color: #28342e;
  font-size: 14px;
  line-height: 1.8;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2) {
  font-family: Georgia, "Songti SC", serif;
}

.markdown-body :deep(h2) {
  padding-bottom: 8px;
  margin-top: 36px;
  border-bottom: 1px solid #e2e5df;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 9px 12px;
  border: 1px solid #dde1db;
}

.markdown-body :deep(th) {
  background: #f1f4ee;
}

.markdown-body :deep(pre) {
  padding: 16px;
  overflow: auto;
  background: #17231e;
  border-radius: 10px;
}

.markdown-body :deep(code) {
  font-family: "SFMono-Regular", Consolas, monospace;
}

.markdown-body :deep(pre code) {
  color: #e8f2ec;
}
</style>
