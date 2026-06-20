// @vitest-environment happy-dom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import { router } from './router'

vi.mock('./api', () => ({
  api: {
    getSetupStatus: vi.fn(),
    getAuthStatus: vi.fn(),
  },
}))

beforeEach(async () => {
  vi.mocked(api.getSetupStatus).mockResolvedValue({
    ready: true,
    setupRequired: false,
    databaseConfigured: true,
    databaseUrl: null,
    testDatabaseUrl: null,
    error: null,
  })
  vi.mocked(api.getAuthStatus).mockResolvedValue({
    adminConfigured: true,
    authenticated: true,
    username: 'admin',
  })
  await router.push('/login')
})

describe('router authentication guard', () => {
  it('redirects unauthenticated users to login with their target path', async () => {
    vi.mocked(api.getAuthStatus).mockResolvedValue({
      adminConfigured: true,
      authenticated: false,
      username: null,
    })

    await router.push('/projects/new')

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/projects/new')
  })
})
