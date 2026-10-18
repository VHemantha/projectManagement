import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { TimeTracking } from './TimeTracking'
import type { IssueDetail } from '@/api/types'

vi.mock('@/api/issues', () => ({ useUpdateIssue: () => ({ mutate: vi.fn() }) }))

const issue = (over: Partial<IssueDetail>) =>
  ({ key: 'SMITH-1', budgeted_hours: 5, actual_hours: 2, time_by_user: [], ...over }) as IssueDetail

describe('TimeTracking', () => {
  it('lets a team lead or above set the budget, and shows it read-only to everyone else', () => {
    const { unmount } = render(<MemoryRouter><TimeTracking issue={issue({ can_set_budget: true })} /></MemoryRouter>)
    expect(screen.getByLabelText('Budgeted hours')).not.toHaveAttribute('readonly')
    unmount()
    render(<MemoryRouter><TimeTracking issue={issue({ can_set_budget: false })} /></MemoryRouter>)
    const input = screen.getByLabelText('Budgeted hours')
    expect(input).toHaveAttribute('readonly')
    expect(input).toHaveAttribute('title', 'Only a team lead or above can set the budgeted time')
  })
})
