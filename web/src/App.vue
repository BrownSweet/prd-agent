<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from './api'

const route = useRoute()
const loggingOut = ref(false)

async function logout() {
  loggingOut.value = true
  try {
    await api.logout()
    window.location.assign('/login')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '退出失败')
    loggingOut.value = false
  }
}
</script>

<template>
  <router-view v-if="route.path === '/login'" />
  <el-container v-else class="app-shell">
    <el-aside width="232px" class="sidebar">
      <router-link to="/projects" class="brand">
        <span class="brand-mark">P</span>
        <span>
          <strong>PRD Agent</strong>
          <small>需求到技术契约</small>
        </span>
      </router-link>
      <el-menu
        :default-active="
          route.path.startsWith('/setup')
            ? '/setup/database'
            : route.path.startsWith('/settings')
              ? '/settings/llm'
              : '/projects'
        "
        router
        class="nav-menu"
      >
        <el-menu-item index="/projects">
          <span>项目工作台</span>
        </el-menu-item>
        <el-menu-item index="/settings/llm">
          <span>LLM 配置</span>
        </el-menu-item>
        <el-menu-item index="/setup/database">
          <span>系统配置</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <div class="local-badge">
          <span class="status-dot" />
          Local workspace
        </div>
        <el-button
          text
          :loading="loggingOut"
          class="logout-button"
          @click="logout"
        >
          退出登录
        </el-button>
      </div>
    </el-aside>
    <el-main class="main-area">
      <router-view />
    </el-main>
  </el-container>
</template>
