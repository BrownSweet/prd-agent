import { describe, expect, it } from 'vitest'
import { stageIndex, stageLabel, stageTagType, stages } from './stages'

describe('workflow stage presentation', () => {
  it('keeps all nine stages in workflow order', () => {
    expect(stages).toHaveLength(9)
    expect(stageIndex('STRUCTURING')).toBe(0)
    expect(stageIndex('PRD_REVISING')).toBe(5)
    expect(stageIndex('COMPLETED')).toBe(8)
  })

  it('returns readable labels and status colors', () => {
    expect(stageLabel('SDD_CONFIRMING')).toBe('SDD确认')
    expect(stageTagType('completed')).toBe('success')
    expect(stageTagType('waiting_user')).toBe('warning')
    expect(stageTagType('failed')).toBe('danger')
    expect(stageTagType('running')).toBe('info')
  })
})
