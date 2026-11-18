import { describe, expect, it } from 'vitest'

import { employeeTypeLabel } from './employeeType'

describe('employee types (AFIT, 16 Nov 2026)', () => {
  it('the CEO stays CEO, an admin is a Team Lead, everyone else is Standard', () => {
    expect(employeeTypeLabel({ role: 'ceo', is_staff: true })).toBe('CEO')
    expect(employeeTypeLabel({ role: 'member', is_staff: true })).toBe('Team Lead')
    expect(employeeTypeLabel({ role: 'member', is_staff: false })).toBe('Standard')
    expect(employeeTypeLabel(null)).toBe('Standard')
  })
})
