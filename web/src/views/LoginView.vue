<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const submitting = ref(false)
const loadError = ref('')
const adminConfigured = ref(true)
const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})

const isSetup = computed(() => !adminConfigured.value)
const canSubmit = computed(() => {
  if (form.username.trim().length < 3 || form.password.length < 8) {
    return false
  }
  return !isSetup.value || form.password === form.confirmPassword
})

function destination(): string {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/')
    ? redirect
    : '/projects'
}

async function loadStatus() {
  loading.value = true
  loadError.value = ''
  try {
    const status = await api.getAuthStatus()
    adminConfigured.value = status.adminConfigured
    if (status.authenticated) {
      await router.replace(destination())
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '无法读取登录状态'
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  try {
    if (isSetup.value) {
      await api.setupAdmin(form.username.trim(), form.password)
      ElMessage.success('管理员创建成功')
    } else {
      await api.login(form.username.trim(), form.password)
    }
    await router.replace(destination())
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <main class="auth-page">
    <section class="auth-context" aria-label="PRD Agent">
      <div class="auth-brand">
        <span class="auth-brand-mark">P</span>
        <span>
          <strong>PRD Agent</strong>
          <small>需求到技术契约</small>
        </span>
      </div>
      <div class="workflow-visual" aria-hidden="true">
        <span>需求结构化</span>
        <span>逻辑校验</span>
        <span>PRD 终审</span>
        <span>SDD 交付</span>
      </div>
      <div class="auth-local-status">
        <span class="status-dot" />
        Local workspace
      </div>
    </section>

    <section class="auth-form-area">
      <div class="auth-form-panel">
        <el-skeleton v-if="loading" :rows="5" animated />

        <div v-else-if="loadError" class="auth-load-error">
          <h1>无法连接服务</h1>
          <p>{{ loadError }}</p>
          <el-button type="primary" @click="loadStatus">重试</el-button>
        </div>

        <template v-else>
          <header class="auth-heading">
            <span class="auth-kicker">LOCAL ADMIN</span>
            <h1>{{ isSetup ? '创建管理员' : '登录 PRD Agent' }}</h1>
            <p>
              {{
                isSetup
                  ? '首次使用，请创建本机管理员账号。'
                  : '输入管理员账号以继续进入工作台。'
              }}
            </p>
          </header>

          <el-form label-position="top" class="auth-form" @submit.prevent="submit">
            <el-form-item label="用户名">
              <el-input
                v-model="form.username"
                autocomplete="username"
                maxlength="64"
                placeholder="3–64 个字符"
                autofocus
              />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="form.password"
                type="password"
                show-password
                :autocomplete="isSetup ? 'new-password' : 'current-password'"
                maxlength="128"
                placeholder="至少 8 个字符"
              />
            </el-form-item>
            <el-form-item v-if="isSetup" label="确认密码">
              <el-input
                v-model="form.confirmPassword"
                type="password"
                show-password
                autocomplete="new-password"
                maxlength="128"
                placeholder="再次输入密码"
              />
            </el-form-item>
            <p
              v-if="isSetup && form.confirmPassword && form.password !== form.confirmPassword"
              class="auth-validation"
            >
              两次输入的密码不一致
            </p>
            <el-button
              type="primary"
              native-type="submit"
              size="large"
              :loading="submitting"
              :disabled="!canSubmit"
              class="auth-submit"
            >
              {{ isSetup ? '创建并进入' : '登录' }}
            </el-button>
          </el-form>
        </template>
      </div>
    </section>
  </main>
</template>
