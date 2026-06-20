// @vitest-environment happy-dom

import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import LoginView from './LoginView.vue'

const replace = vi.fn()
const mountOptions = {
  global: {
    stubs: {
      'el-skeleton': true,
      'el-button': true,
      'el-input': true,
      'el-form': { template: '<form><slot /></form>' },
      'el-form-item': {
        props: ['label'],
        template: '<label>{{ label }}<slot /></label>',
      },
    },
  },
}

vi.mock('../api', () => ({
  api: {
    getAuthStatus: vi.fn(),
    setupAdmin: vi.fn(),
    login: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace }),
}))

afterEach(() => {
  vi.clearAllMocks()
})

describe('LoginView', () => {
  it('shows first-run admin setup when no administrator exists', async () => {
    vi.mocked(api.getAuthStatus).mockResolvedValue({
      adminConfigured: false,
      authenticated: false,
      username: null,
    })

    const wrapper = shallowMount(LoginView, mountOptions)
    await flushPromises()

    expect(wrapper.text()).toContain('创建管理员')
    expect(wrapper.text()).toContain('确认密码')
  })

  it('shows login when an administrator already exists', async () => {
    vi.mocked(api.getAuthStatus).mockResolvedValue({
      adminConfigured: true,
      authenticated: false,
      username: null,
    })

    const wrapper = shallowMount(LoginView, mountOptions)
    await flushPromises()

    expect(wrapper.text()).toContain('登录 PRD Agent')
    expect(wrapper.text()).not.toContain('确认密码')
  })
})
