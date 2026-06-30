// @vitest-environment happy-dom

import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import NewProjectView from './NewProjectView.vue'

const push = vi.fn()

vi.mock('../api', () => ({
  api: {
    listLlmConfigs: vi.fn(),
    createProject: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

function mountView() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return mount(NewProjectView, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        'el-button': {
          emits: ['click'],
          template: '<button @click="$emit(\'click\')"><slot /></button>',
        },
        'el-form': { template: '<form><slot /></form>' },
        'el-form-item': {
          props: ['label'],
          template: '<label>{{ label }}<slot /></label>',
        },
        'el-input': {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template:
            '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
        },
        'el-option': true,
        'el-select': {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<select><slot /></select>',
        },
        'el-segmented': {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<div><slot /></div>',
        },
      },
    },
  })
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('NewProjectView', () => {
  it('submits markdown text and selected files', async () => {
    vi.mocked(api.listLlmConfigs).mockResolvedValue({ items: [] })
    vi.mocked(api.createProject).mockResolvedValue({
      projectId: 'project-1',
      jobId: 'job-1',
    })

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('textarea').setValue('## 需求\n\n- 支持附件')
    const file = new File(['# brief'], 'brief.md', { type: 'text/markdown' })
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      value: [file],
      configurable: true,
    })
    await input.trigger('change')
    await wrapper.findAll('button').at(-1)?.trigger('click')
    await flushPromises()

    expect(api.createProject).toHaveBeenCalledWith(
      '## 需求\n\n- 支持附件',
      undefined,
      [file],
    )
    expect(push).toHaveBeenCalledWith('/projects/project-1')
  })
})
