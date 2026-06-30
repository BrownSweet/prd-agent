import type {
  ApiResponse,
  ArtifactSummary,
  AuthStatus,
  DatabaseSetupResult,
  Job,
  LlmConfig,
  ProjectDetail,
  ProjectSummary,
  SetupStatus,
} from './types'

const API_ROOT = '/api/v1'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message)
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const isFormData = options.body instanceof FormData
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    credentials: 'same-origin',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  })
  const body = await response.json()
  if (!response.ok) {
    if (
      response.status === 401 &&
      !path.startsWith('/auth/') &&
      typeof window !== 'undefined'
    ) {
      const redirect = `${window.location.pathname}${window.location.search}`
      window.location.assign(`/login?redirect=${encodeURIComponent(redirect)}`)
    }
    throw new ApiError(body.message || '请求失败', response.status, body.details)
  }
  return (body as ApiResponse<T>).data
}

function writeOptions(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

export const api = {
  getAuthStatus() {
    return request<AuthStatus>('/auth/status')
  },
  setupAdmin(username: string, password: string) {
    return request<AuthStatus>('/auth/setup', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },
  login(username: string, password: string) {
    return request<AuthStatus>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },
  logout() {
    return request<AuthStatus>('/auth/logout', { method: 'POST' })
  },
  getSetupStatus() {
    return request<SetupStatus>('/setup/status')
  },
  testDatabaseSetup(databaseUrl: string, testDatabaseUrl: string) {
    return request<DatabaseSetupResult>(
      '/setup/database/test',
      {
        method: 'POST',
        body: JSON.stringify({ databaseUrl, testDatabaseUrl }),
      },
    )
  },
  saveDatabaseSetup(databaseUrl: string, testDatabaseUrl: string) {
    return request<DatabaseSetupResult>(
      '/setup/database/save',
      {
        method: 'POST',
        body: JSON.stringify({ databaseUrl, testDatabaseUrl }),
      },
    )
  },
  listProjects(params: {
    page?: number
    pageSize?: number
    search?: string
    archived?: boolean
  }) {
    const query = new URLSearchParams()
    query.set('page', String(params.page ?? 1))
    query.set('pageSize', String(params.pageSize ?? 20))
    if (params.search) query.set('search', params.search)
    if (params.archived) query.set('archived', 'true')
    return request<{
      items: ProjectSummary[]
      page: number
      pageSize: number
      total: number
    }>(`/projects?${query}`)
  },
  getProject(projectId: string) {
    return request<ProjectDetail>(`/projects/${projectId}`)
  },
  createProject(requirement: string, llmConfigId?: string, files: File[] = []) {
    if (files.length) {
      const body = new FormData()
      body.append('requirement', requirement)
      if (llmConfigId) body.append('llmConfigId', llmConfigId)
      files.forEach((file) => body.append('files', file))
      return request<{ projectId: string; jobId: string }>(
        '/projects',
        {
          method: 'POST',
          headers: { 'Idempotency-Key': crypto.randomUUID() },
          body,
        },
      )
    }
    return request<{ projectId: string; jobId: string }>(
      '/projects',
      writeOptions('POST', { requirement, llmConfigId }),
    )
  },
  submitAnswers(
    projectId: string,
    answers: Array<{ itemId: string; answer: string }>,
  ) {
    return request<Job>(
      `/projects/${projectId}/answers`,
      writeOptions('POST', { answers }),
    )
  },
  submitFeedback(projectId: string, feedback: string) {
    return request<Job>(
      `/projects/${projectId}/feedback`,
      writeOptions('POST', { feedback }),
    )
  },
  advance(projectId: string) {
    return request<Job>(
      `/projects/${projectId}/advance`,
      writeOptions('POST'),
    )
  },
  retry(projectId: string) {
    return request<Job>(
      `/projects/${projectId}/retry`,
      writeOptions('POST'),
    )
  },
  rollback(projectId: string, targetStage: string, feedback: string) {
    return request<Job>(
      `/projects/${projectId}/rollback`,
      writeOptions('POST', { targetStage, feedback }),
    )
  },
  overridePrdReview(projectId: string, reason: string) {
    return request<Job>(
      `/projects/${projectId}/prd-review/override`,
      writeOptions('POST', { reason }),
    )
  },
  regenerateSdd(projectId: string) {
    return request<Job>(
      `/projects/${projectId}/sdd/regenerate`,
      writeOptions('POST'),
    )
  },
  waive(projectId: string, issueId: string, reason: string) {
    return request<{ projectId: string; issueId: string }>(
      `/projects/${projectId}/logic-issues/${issueId}/waive`,
      writeOptions('POST', { reason }),
    )
  },
  archive(projectId: string, archived: boolean) {
    return request<{ projectId: string; archived: boolean }>(
      `/projects/${projectId}/archive`,
      writeOptions('POST', { archived }),
    )
  },
  changeProjectLlmConfig(projectId: string, llmConfigId: string) {
    return request<{ projectId: string; llmConfigId: string }>(
      `/projects/${projectId}/llm-config`,
      writeOptions('PUT', { llmConfigId }),
    )
  },
  getJob(jobId: string) {
    return request<Job>(`/jobs/${jobId}`)
  },
  listArtifacts(projectId: string) {
    return request<{ items: ArtifactSummary[] }>(
      `/projects/${projectId}/artifacts`,
    )
  },
  getArtifact(projectId: string, type: string, version: number) {
    return request<ArtifactSummary>(
      `/projects/${projectId}/artifacts/${type}/${version}`,
    )
  },
  artifactDownloadUrl(projectId: string, type: string, version: number) {
    return `${API_ROOT}/projects/${projectId}/artifacts/${type}/${version}/download`
  },
  attachmentDownloadUrl(projectId: string, attachmentId: string) {
    return `${API_ROOT}/projects/${projectId}/attachments/${attachmentId}/download`
  },
  listLlmConfigs(includeArchived = false) {
    return request<{ items: LlmConfig[] }>(
      `/llm-configs?include_archived=${includeArchived}`,
    )
  },
  saveLlmConfig(
    configId: string | null,
    body: Record<string, unknown>,
  ) {
    return request<LlmConfig>(
      configId ? `/llm-configs/${configId}` : '/llm-configs',
      writeOptions(configId ? 'PUT' : 'POST', body),
    )
  },
  testLlmConfig(configId: string) {
    return request<Job>(
      `/llm-configs/${configId}/test`,
      writeOptions('POST'),
    )
  },
}
