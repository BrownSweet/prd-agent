import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API writes', () => {
  it('sends admin setup, login, and logout requests without idempotency keys', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(
        JSON.stringify({
          code: 'success',
          data: { authenticated: true, adminConfigured: true, username: 'admin' },
          message: 'ok',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api.setupAdmin('admin', 'secure-password')
    await api.login('admin', 'secure-password')
    await api.logout()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/auth/setup')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      username: 'admin',
      password: 'secure-password',
    })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/login')
    expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/auth/logout')
    expect(fetchMock.mock.calls[0][1].headers['Idempotency-Key']).toBeUndefined()
  })

  it('tests database setup without idempotency key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'success',
          data: { ok: true, databaseUrl: 'mysql://***', testDatabaseUrl: 'mysql://***' },
          message: 'ok',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api.testDatabaseSetup('prod-url', 'test-url')

    const [path, options] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/setup/database/test')
    expect(options.method).toBe('POST')
    expect(options.headers['Idempotency-Key']).toBeUndefined()
    expect(JSON.parse(options.body)).toEqual({
      databaseUrl: 'prod-url',
      testDatabaseUrl: 'test-url',
    })
  })

  it('sends a unique idempotency key with project creation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'success',
          data: { projectId: 'project-1', jobId: 'job-1' },
          message: 'accepted',
        }),
        { status: 202, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: () => 'request-key-0001' })

    await api.createProject('测试需求')

    const [, options] = fetchMock.mock.calls[0]
    expect(options.method).toBe('POST')
    expect(options.headers['Idempotency-Key']).toBe('request-key-0001')
    expect(JSON.parse(options.body)).toEqual({
      requirement: '测试需求',
    })
  })

  it('submits controlled rollback with target stage and feedback', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'success',
          data: { jobId: 'job-1', projectId: 'project-1' },
          message: 'accepted',
        }),
        { status: 202, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: () => 'rollback-key-0001' })

    await api.rollback('project-1', 'LOGIC_VALIDATING', '补充恢复流程')

    const [path, options] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/projects/project-1/rollback')
    expect(options.method).toBe('POST')
    expect(options.headers['Idempotency-Key']).toBe('rollback-key-0001')
    expect(JSON.parse(options.body)).toEqual({
      targetStage: 'LOGIC_VALIDATING',
      feedback: '补充恢复流程',
    })
  })

  it('submits PRD review override with reason', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'success',
          data: { jobId: 'job-1', projectId: 'project-1' },
          message: 'accepted',
        }),
        { status: 202, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: () => 'override-key-0001' })

    await api.overridePrdReview('project-1', '接受风险')

    const [path, options] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/projects/project-1/prd-review/override')
    expect(options.method).toBe('POST')
    expect(options.headers['Idempotency-Key']).toBe('override-key-0001')
    expect(JSON.parse(options.body)).toEqual({
      reason: '接受风险',
    })
  })

  it('submits SDD regeneration request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'success',
          data: { jobId: 'job-1', projectId: 'project-1' },
          message: 'accepted',
        }),
        { status: 202, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: () => 'regenerate-sdd-key-0001' })

    await api.regenerateSdd('project-1')

    const [path, options] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/v1/projects/project-1/sdd/regenerate')
    expect(options.method).toBe('POST')
    expect(options.headers['Idempotency-Key']).toBe('regenerate-sdd-key-0001')
  })
})
