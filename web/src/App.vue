<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <el-container class="app-shell">
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
      <div class="local-badge">
        <span class="status-dot" />
        Local workspace
      </div>
    </el-aside>
    <el-main class="main-area">
      <router-view />
    </el-main>
  </el-container>
</template>
