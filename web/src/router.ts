import { createRouter, createWebHistory } from 'vue-router'
import ArtifactView from './views/ArtifactView.vue'
import LlmSettingsView from './views/LlmSettingsView.vue'
import LoginView from './views/LoginView.vue'
import NewProjectView from './views/NewProjectView.vue'
import ProjectListView from './views/ProjectListView.vue'
import ProjectWorkspaceView from './views/ProjectWorkspaceView.vue'
import SetupDatabaseView from './views/SetupDatabaseView.vue'
import { api } from './api'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/projects' },
    { path: '/login', component: LoginView },
    { path: '/projects', component: ProjectListView },
    { path: '/projects/new', component: NewProjectView },
    {
      path: '/projects/:projectId',
      component: ProjectWorkspaceView,
      props: true,
    },
    {
      path: '/projects/:projectId/artifacts/:type/:version',
      component: ArtifactView,
      props: true,
    },
    { path: '/settings/llm', component: LlmSettingsView },
    { path: '/setup/database', component: SetupDatabaseView },
  ],
})

router.beforeEach(async (to) => {
  try {
    const setup = await api.getSetupStatus()
    if (setup.setupRequired) {
      return to.path === '/setup/database' ? true : '/setup/database'
    }

    const auth = await api.getAuthStatus()
    if (!auth.authenticated) {
      if (to.path === '/login') return true
      return {
        path: '/login',
        query: { redirect: to.fullPath },
      }
    }

    if (to.path === '/login') return '/projects'
  } catch {
    return to.path === '/login' || to.path === '/setup/database'
      ? true
      : '/login'
  }
  return true
})
