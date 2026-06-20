import { VueQueryPlugin } from '@tanstack/vue-query'
import ElementPlus, { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './styles.css'

createApp(App)
  .use(router)
  .use(VueQueryPlugin, {
    queryClientConfig: {
      defaultOptions: {
        queries: {
          retry: 1,
          refetchOnWindowFocus: false,
        },
        mutations: {
          onError: (error) => {
            ElMessage.error(
              error instanceof Error ? error.message : '操作失败，请重试',
            )
          },
        },
      },
    },
  })
  .use(ElementPlus)
  .mount('#app')
