import { describe, expect, it } from 'vitest'

import { budgetStatus, countdownText, deadlineStatus, formatHours } from './workspaceDashboard'

describe('budgetStatus', () => {
  it('is green under 90%, amber from 90% to the budget, red over it', () => {
    expect(budgetStatus(10, null)).toBe('none')
    expect(budgetStatus(10, 0)).toBe('none')
    expect(budgetStatus(35, 40)).toBe('ok')
    expect(budgetStatus(36, 40)).toBe('warning')
    expect(budgetStatus(40, 40)).toBe('warning')
    expect(budgetStatus(40.5, 40)).toBe('over')
  })
})

describe('deadlineStatus', () => {
  const today = new Date(2026, 9, 1) // 1 Oct 2026

  it('counts calendar days and flags due soon within a week', () => {
    expect(deadlineStatus(null, today)).toEqual({ status: 'none', daysLeft: null })
    expect(deadlineStatus('2026-10-20', today)).toEqual({ status: 'on_track', daysLeft: 19 })
    expect(deadlineStatus('2026-10-08', today)).toEqual({ status: 'due_soon', daysLeft: 7 })
    expect(deadlineStatus('2026-10-01', today)).toEqual({ status: 'due_soon', daysLeft: 0 })
    expect(deadlineStatus('2026-09-28', today)).toEqual({ status: 'overdue', daysLeft: -3 })
  })

  it('words the countdown', () => {
    expect(countdownText(0)).toBe('Due today')
    expect(countdownText(1)).toBe('Due tomorrow')
    expect(countdownText(12)).toBe('12 days left')
    expect(countdownText(-1)).toBe('1 day overdue')
    expect(countdownText(-4)).toBe('4 days overdue')
  })
})

it('formats hours to one decimal place', () => {
  expect(formatHours(12.25)).toBe('12.3 h')
  expect(formatHours(40)).toBe('40 h')
})
