import { describe, expect, it } from 'vitest'

import { suggestKey } from './projectKey'

describe('suggestKey', () => {
  it('uses the full first word, as typed', () => {
    expect(suggestKey('Pochin Group')).toBe('Pochin')
    expect(suggestKey('Collier Group')).toBe('Collier')
    expect(suggestKey('RWCA')).toBe('RWCA')
  })

  it('drops punctuation and joins a too-short first word with the next', () => {
    expect(suggestKey("O'Neil & Co")).toBe('ONeil')
    expect(suggestKey('A Team')).toBe('ATeam')
  })

  it('never starts with a digit', () => {
    expect(suggestKey('2026 Accounts')).toBe('Accounts')
    expect(suggestKey('3M Audit')).toBe('MAudit')
  })
})
