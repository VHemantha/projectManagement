import { differenceInCalendarDays, parseISO } from 'date-fns'

export type BudgetStatus = 'none' | 'ok' | 'warning' | 'over'

/** Share of the budget at which the time bar turns amber. */
export const BUDGET_WARNING_RATIO = 0.9

export function budgetStatus(actual: number, budget: number | null): BudgetStatus {
  if (budget == null || budget <= 0) return 'none'
  if (actual > budget) return 'over'
  if (actual >= budget * BUDGET_WARNING_RATIO) return 'warning'
  return 'ok'
}

export type DeadlineStatus = 'none' | 'on_track' | 'due_soon' | 'overdue'

/** Deadlines this many days away or fewer count as due soon. */
export const DUE_SOON_DAYS = 7

export function deadlineStatus(deadline: string | null, today: Date = new Date()): {
  status: DeadlineStatus
  daysLeft: number | null
} {
  if (!deadline) return { status: 'none', daysLeft: null }
  const daysLeft = differenceInCalendarDays(parseISO(deadline), today)
  if (daysLeft < 0) return { status: 'overdue', daysLeft }
  if (daysLeft <= DUE_SOON_DAYS) return { status: 'due_soon', daysLeft }
  return { status: 'on_track', daysLeft }
}

export function countdownText(daysLeft: number): string {
  if (daysLeft === 0) return 'Due today'
  if (daysLeft === 1) return 'Due tomorrow'
  if (daysLeft > 1) return `${daysLeft} days left`
  if (daysLeft === -1) return '1 day overdue'
  return `${-daysLeft} days overdue`
}

export const DEADLINE_LABELS: Record<Exclude<DeadlineStatus, 'none'>, string> = {
  on_track: 'On track',
  due_soon: 'Due soon',
  overdue: 'Overdue',
}

/** "12.5 h", "40 h" — at most one decimal place. */
export function formatHours(hours: number): string {
  return `${Number(hours.toFixed(1)).toLocaleString()} h`
}
