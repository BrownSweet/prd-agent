import { createRouter, createWebHistory } from 'vue-router'
import ArtifactView from './views/ArtifactView.vue'
import LlmSettingsView from './views/LlmSettingsView.vue'
import NewProjectView from './views/NewProjectView.vue'
import ProjectListView from './views/ProjectListView.vue'
import ProjectWorkspaceView from './views/ProjectWorkspaceView.vue'
import SetupDatabaseView from './views/SetupDatabaseView.vue'
import { api } from './api'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/projects' },
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
  if (to.path.startsWith('/setup')) {
    return true
  }
  try {
    const status = await api.getSetupStatus()
    if (status.setupRequired) {
      return '/setup/database'
    }
  } catch {
    return true
  }
  return true
})
