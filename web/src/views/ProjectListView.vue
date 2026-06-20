<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ref } from 'vue'
import { api } from '../api'
import { stageLabel, stageTagType } from '../stages'

const queryClient = useQueryClient()
const search = ref('')
const archived = ref(false)

const projects = useQuery({
  queryKey: ['projects', search, archived],
  queryFn: () =>
    api.listProjects({ search: search.value, archived: archived.value }),
})

const archiveMutation = useMutation({
  mutationFn: ({ id, value }: { id: string; value: boolean }) =>
    api.archive(id, value),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['projects'] })
    ElMessage.success('项目状态已更新')
  },
})

async function toggleArchive(id: string, value: boolean) {
  await ElMessageBox.confirm(
    value ? '归档后项目仍可恢复，确认归档？' : '确认恢复此项目？',
    value ? '归档项目' : '恢复项目',
  )
  archiveMutation.mutate({ id, value })
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>项目工作台</h1>
      <p>把模糊想法推进为经过终审的 PRD 与可执行 SDD。</p>
    </div>
    <el-button type="primary" size="large" @click="$router.push('/projects/new')">
      创建新项目
    </el-button>
  </div>

  <div class="toolbar list-toolbar">
    <el-input
      v-model="search"
      clearable
      placeholder="搜索项目标题或 ID"
      class="search-input"
    />
    <el-segmented v-model="archived" :options="[
      { label: '进行中', value: false },
      { label: '已归档', value: true },
    ]" />
  </div>

  <section class="surface project-surface">
    <div v-if="projects.isLoading.value" class="empty-state">
      <el-skeleton :rows="6" animated />
    </div>
    <div v-else-if="projects.isError.value" class="error-state">
      <el-result icon="error" title="项目加载失败">
        <template #extra>
          <el-button @click="projects.refetch()">重试</el-button>
        </template>
      </el-result>
    </div>
    <el-empty
      v-else-if="!projects.data.value?.items.length"
      :description="archived ? '暂无归档项目' : '还没有项目，从一个模糊需求开始吧'"
      class="empty-state"
    >
      <el-button
        v-if="!archived"
        type="primary"
        @click="$router.push('/projects/new')"
      >
        创建项目
      </el-button>
    </el-empty>
    <div v-else class="project-grid">
      <article
        v-for="project in projects.data.value.items"
        :key="project.projectId"
        class="project-card"
      >
        <div class="project-meta">
          <el-tag :type="stageTagType(project.stageStatus)" effect="light">
            {{ stageLabel(project.stage) }}
          </el-tag>
          <span>第 {{ project.roundNumber }} 轮</span>
        </div>
        <router-link :to="`/projects/${project.projectId}`">
          <h2>{{ project.title }}</h2>
          <p>{{ project.summary || '等待 Agent 形成需求摘要' }}</p>
        </router-link>
        <div class="project-footer">
          <span class="mono">{{ project.projectId.slice(0, 8) }}</span>
          <el-button
            text
            :loading="archiveMutation.isPending.value"
            @click="toggleArchive(project.projectId, !archived)"
          >
            {{ archived ? '恢复' : '归档' }}
          </el-button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.list-toolbar {
  margin-bottom: 18px;
}

.search-input {
  width: 360px;
}

.project-surface {
  min-height: 420px;
  padding: 20px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.project-card {
  min-height: 210px;
  padding: 20px;
  background: #fbfcf9;
  border: 1px solid #e2e5df;
  border-radius: 13px;
  transition: 0.18s ease;
}

.project-card:hover {
  border-color: #9db6a5;
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(35, 74, 55, 0.08);
}

.project-meta,
.project-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.project-meta span {
  color: #89948e;
  font-size: 11px;
}

h2 {
  margin: 22px 0 8px;
  font-size: 17px;
}

p {
  min-height: 54px;
  margin: 0;
  overflow: hidden;
  color: #6f7b74;
  font-size: 13px;
  line-height: 1.7;
}

.project-footer {
  margin-top: 18px;
  padding-top: 12px;
  color: #939d97;
  font-size: 11px;
  border-top: 1px solid #eceeea;
}
</style>
