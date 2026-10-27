import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { IssueDetailsPanel } from './IssueDetailsPanel'
import type { IssueDetail } from '@/api/types'

const wrap = (ui: React.ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter>{ui}</MemoryRouter>
  </QueryClientProvider>
)

const mocks = vi.hoisted(() => ({ update: vi.fn() }))
vi.mock('@/api/issues', () => ({
  useUpdateIssue: () => ({ mutate: mocks.update }),
  useToggleWatch: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/api/users', () => ({ useUsers: () => ({ data: [{ id: 2, display_name: 'Pat' }] }) }))
vi.mock('@/api/projects', () => ({
  useProject: () => ({ data: { job_value_currency: 'NZD', primary_team: null } }),
  useProjectBoard: () => ({ data: { statuses: [{ id: 1, name: 'To Start', category: 'todo' }] } }),
}))
vi.mock('@/api/teams', () => ({ useTeam: () => ({ data: undefined }) }))

const pat = { id: 2, display_name: 'Pat', avatar: null }
const issue = {
  key: 'RWCA-1', project: 'RWCA', status: { id: 1, name: 'To Start', category: 'todo' }, priority: 'medium', assignee: pat, reporter: pat,
  preparer: pat, reviewer: null, current_responsible: pat, story_points: null, budgeted_hours: 10, estimated_hours: null, actual_hours: 2,
  time_by_user: [], group: '', due_date: null, labels: [], is_watching: false, watcher_count: 0, allocated_value: null,
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
} as unknown as IssueDetail

describe('Task panel', () => {
  beforeEach(() => mocks.update.mockClear())

  it("uses AFIT's names for the roles and no longer shows the reporter", () => {
    render(wrap(<IssueDetailsPanel issue={issue} />))
    for (const label of ['Team Lead', 'Accountant', 'Reviewer', 'Currently Responsible', 'Estimated Hours']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    for (const old of ['Assignee', 'Preparer', 'Current responsible', 'Reporter']) {
      expect(screen.queryByText(old)).not.toBeInTheDocument()
    }
  })

  it('saves the estimated hours when you leave the box, and clears them when emptied', async () => {
    const { rerender } = render(wrap(<IssueDetailsPanel issue={issue} />))
    const box = screen.getByLabelText('Estimated Hours')
    await userEvent.type(box, '12.5')
    await userEvent.tab()
    expect(mocks.update).toHaveBeenCalledWith({ estimated_hours: 12.5 })
    rerender(wrap(<IssueDetailsPanel issue={{ ...issue, estimated_hours: 12.5 }} />))
    await userEvent.clear(screen.getByLabelText('Estimated Hours'))
    await userEvent.tab()
    expect(mocks.update).toHaveBeenLastCalledWith({ estimated_hours: null })
  })
})
