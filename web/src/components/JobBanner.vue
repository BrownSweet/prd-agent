<script setup lang="ts">
import type { Job } from '../types'

defineProps<{ job: Job }>()
</script>

<template>
  <el-alert
    v-if="job.status === 'queued'"
    title="任务正在排队"
    description="Worker 将自动领取任务，可以安全刷新页面。"
    type="info"
    show-icon
    :closable="false"
  />
  <el-alert
    v-else-if="job.status === 'running'"
    title="Agent 正在处理当前阶段"
    description="模型推理可能需要几十秒，页面会自动刷新结果。"
    type="warning"
    show-icon
    :closable="false"
  />
  <el-alert
    v-else-if="job.status === 'failed'"
    title="任务执行失败"
    :description="job.errorMessage || '请重试当前阶段'"
    type="error"
    show-icon
    :closable="false"
  />
</template>
