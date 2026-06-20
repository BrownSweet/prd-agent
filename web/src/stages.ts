import type { Stage } from './types'

export const stages: Array<{ key: Stage; label: string }> = [
  { key: 'STRUCTURING', label: '需求结构化' },
  { key: 'LOGIC_VALIDATING', label: '逻辑校验' },
  { key: 'PRD_TYPE_CONFIRMING', label: '类型确认' },
  { key: 'PRD_GENERATING', label: 'PRD生成' },
  { key: 'PRD_REVIEWING', label: 'PRD终审' },
  { key: 'PRD_REVISING', label: 'PRD修订' },
  { key: 'SDD_CONFIRMING', label: 'SDD确认' },
  { key: 'SDD_GENERATING', label: 'SDD生成' },
  { key: 'COMPLETED', label: '完成' },
]

export function stageIndex(stage: Stage): number {
  return stages.findIndex((item) => item.key === stage)
}

export function stageLabel(stage: Stage): string {
  return stages.find((item) => item.key === stage)?.label ?? stage
}

export function stageTagType(
  status: string,
): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'waiting_user') return 'warning'
  return 'info'
}
