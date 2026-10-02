import { describe, expect, it } from 'vitest'

import { filterIssues, hasActiveFilters, labelOptions, NO_FILTERS } from './boardFilters'
import type { IssueListItem } from '@/api/types'

const today = new Date(2026, 9, 1)
const label = (name: string) => ({ id: name.length, name, color: '#ccc' })
const issue = (id: number, o: Partial<IssueListItem>) =>
  ({
    id,
    key: `T-${id}`,
    priority: 'medium',
    due_date: null,
    labels: [],
    assignee: null,
    status: { id: 1, name: 'To do', category: 'todo', order: 1 },
    ...o,
  }) as IssueListItem

const issues = [
  issue(1, { priority: 'high', due_date: '2026-09-29', labels: [label('VAT')], assignee: { id: 7 } as IssueListItem['assignee'] }),
  issue(2, { priority: 'low', due_date: '2026-10-03' }),
  issue(3, { priority: 'high', labels: [label('Payroll')] }),
  issue(4, { due_date: '2026-09-20', status: { id: 6, name: 'Done', category: 'done', order: 5 } }),
]
const keys = (f: Partial<typeof NO_FILTERS>, me?: number) =>
  filterIssues(issues, { ...NO_FILTERS, ...f }, me, today).map((i) => i.id)

describe('board filters', () => {
  it('shows everything with no filters', () => {
    expect(keys({})).toEqual([1, 2, 3, 4])
    expect(hasActiveFilters(NO_FILTERS)).toBe(false)
  })

  it('filters by assignee, only mine, priority and label', () => {
    expect(keys({ assigneeId: 7 })).toEqual([1])
    expect(keys({ onlyMine: true }, 7)).toEqual([1])
    expect(keys({ priority: 'high' })).toEqual([1, 3])
    expect(keys({ label: 'vat' })).toEqual([1])
    expect(keys({ priority: 'high', label: 'Payroll' })).toEqual([3])
  })

  it('filters by due date; finished jobs are never overdue', () => {
    expect(keys({ due: 'overdue' })).toEqual([1])
    expect(keys({ due: 'due_soon' })).toEqual([2])
    expect(keys({ due: 'has_date' })).toEqual([1, 2, 4])
    expect(keys({ due: 'none' })).toEqual([3])
  })

  it('lists each label name once, sorted', () => {
    expect(labelOptions([...issues, issue(5, { labels: [label('vat')] })])).toEqual(['Payroll', 'vat'])
  })
})
