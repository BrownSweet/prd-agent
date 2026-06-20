export type Stage =
  | 'STRUCTURING'
  | 'LOGIC_VALIDATING'
  | 'PRD_TYPE_CONFIRMING'
  | 'PRD_GENERATING'
  | 'PRD_REVIEWING'
  | 'PRD_REVISING'
  | 'SDD_CONFIRMING'
  | 'SDD_GENERATING'
  | 'COMPLETED'

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface ApiResponse<T> {
  code: string
  data: T
  message: string
}

export interface Job {
  jobId: string
  projectId: string | null
  jobType: string
  status: JobStatus
  result: Record<string, unknown>
  errorMessage: string | null
  createdAt: string
  updatedAt: string
}

export interface LlmConfig {
  id: string
  name: string
  provider: string
  model: string
  baseUrl: string | null
  temperature: number
  timeoutSeconds: number
  nativeStructuredOutput: boolean | null
  version: number
  isDefault: boolean
  archivedAt: string | null
  hasApiKey: boolean
  apiKeyMask: string | null
}

export interface ProjectSummary {
  projectId: string
  title: string
  summary: string
  stage: Stage
  stageStatus: string
  roundNumber: number
  archivedAt: string | null
  updatedAt: string
}

export interface Question {
  questionId: string
  questionType: string
  description: string
  importance: string
  status: string
  answer: string | null
}

export interface LogicIssue {
  issueId: string
  dimension: string
  description: string
  severity: 'blocking' | 'important' | 'suggestion'
  status: string
  resolution: string | null
}

export interface ArtifactSummary {
  artifactType: 'prd' | 'prd-review' | 'sdd'
  version: number
  metadata: Record<string, unknown>
  createdAt: string
  content?: string
}

export interface RequirementSpec {
  title: string
  summary: string
  modules: Array<{
    name: string
    description: string
    features: Array<{
      name: string
      description: string
      dataSource: string
      interactionLogic: string
      operationImpact: string
      dependencies: string[]
    }>
  }>
  dataSources: Array<Record<string, unknown>>
  interactions: Array<Record<string, unknown>>
  operationImpacts: Array<Record<string, unknown>>
  dependencies: Array<Record<string, unknown>>
  states: Array<Record<string, unknown>>
  assumptions: string[]
  completeness: Record<string, boolean>
}

export interface ProjectDetail {
  projectId: string
  stage: Stage
  stageStatus: string
  roundNumber: number
  reviewRound: number
  requirementSpec: RequirementSpec
  questions: Question[]
  logicIssues: LogicIssue[]
  productType: {
    primary: string
    secondary: string[]
    matchedFeatures: string[]
    rationale: string
    confirmed: boolean
  } | null
  activeJob: Job | null
  lastJob: Job | null
  llmConfig: LlmConfig | null
  artifacts: ArtifactSummary[]
  gateErrors: string[]
  allowedActions: string[]
  rollbackTargets: Array<{
    stage: Stage
    label: string
    description: string
  }>
  archivedAt: string | null
}

export interface SetupStatus {
  ready: boolean
  setupRequired: boolean
  databaseConfigured: boolean
  databaseUrl: string | null
  testDatabaseUrl: string | null
  error: string | null
}

export interface DatabaseSetupResult {
  ok?: boolean
  saved?: boolean
  restartRequired?: boolean
  envPath?: string
  databaseUrl: string | null
  testDatabaseUrl: string | null
}
