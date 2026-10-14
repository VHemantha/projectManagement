import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CreateIssueModal } from './CreateIssueModal'
import type { CreateIssueDefaults } from '@/store/uiStore'

const mocks = vi.hoisted(() => ({
  defaults: {} as CreateIssueDefaults,
  create: vi.fn(),
}))

const PROJECTS = [
  { key: 'SMITH', name: 'Smith year end', client: { id: 12, name: 'Smith Rentals' }, primary_team: { id: 3, name: 'Rentals team' },
    is_client_workspace: false, task_names: [], labels: [] },
  { key: 'JONES', name: 'Jones GST', client: { id: 20, name: 'Jones Ltd' }, primary_team: { id: 4, name: 'Business team' },
    is_client_workspace: false, task_names: [], labels: [] },
]
const CLIENTS = [
  { id: 12, name: 'Smith Rentals', team_id: 3, requires_projects: true, workspace_project_key: null },
  { id: 20, name: 'Jones Ltd', team_id: 4, requires_projects: true, workspace_project_key: null },
]
const TEAMS = [{ id: 3, name: 'Rentals team' }, { id: 4, name: 'Business team' }]
const USERS = [{ id: 5, display_name: 'Pat' }, { id: 6, display_name: 'Rita' }]

vi.mock('@/store/uiStore', () => ({
  useUiStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ createIssueOpen: true, createIssueDefaults: mocks.defaults, closeCreateIssue: vi.fn(), openIssueModal: vi.fn() }),
}))
vi.mock('@/api/projects', () => ({
  useProjects: () => ({ data: PROJECTS }),
  useProject: (key?: string) => ({ data: PROJECTS.find((p) => p.key === key) }),
}))
vi.mock('@/api/clients', () => ({ useClients: () => ({ data: CLIENTS }) }))
vi.mock('@/api/teams', () => ({
  useTeams: () => ({ data: TEAMS }),
  useTeam: (id?: number) => ({ data: id ? { id, memberships: USERS.map((user) => ({ user })) } : undefined }),
}))
vi.mock('@/api/users', () => ({ useUsers: () => ({ data: USERS }) }))
vi.mock('@/api/issues', () => ({
  useIssueTypes: () => ({ data: [{ id: 1, name: 'Task' }] }),
  useIssues: () => ({ data: { results: [{ id: 42, summary: 'Year end 2026' }] } }),
  useCreateIssue: () => ({ mutate: mocks.create, isPending: false, isError: false, reset: vi.fn() }),
}))
vi.mock('@/design-system', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, RichTextEditor: () => null }
})

describe('CreateIssueModal: filled from where it was opened', () => {
  beforeEach(() => {
    mocks.create.mockClear()
  })

  it("from a board column: the project's workspace and sub-workspace, the column, the lane's epic and assignee", async () => {
    mocks.defaults = { projectKey: 'SMITH', statusId: 7, columnName: 'In review', epicId: 42, assigneeId: 6 }
    render(<CreateIssueModal />)
    expect(screen.getByLabelText('Workspace')).toHaveValue('3')
    expect(screen.getByLabelText('Sub-workspace')).toHaveValue('12')
    expect(screen.getByLabelText('Project')).toHaveValue('SMITH')
    expect(screen.getByLabelText('Epic')).toHaveValue('42')
    expect(screen.getByLabelText('Assignee')).toHaveValue('6')
    expect(screen.getByText('In review')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/Job Name/), 'Rental property year end')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create).toHaveBeenCalledWith(
      expect.objectContaining({ project: 'SMITH', summary: 'Rental property year end', status_id: 7, epic_id: 42, assignee_id: 6 }),
      expect.anything(),
    )
  })

  it("from a board across projects: the filters' workspace and sub-workspace, and the column's category", async () => {
    mocks.defaults = { teamId: 4, clientId: 20, statusCategory: 'in_progress', columnName: 'In progress' }
    render(<CreateIssueModal />)
    expect(screen.getByLabelText('Workspace')).toHaveValue('4')
    expect(screen.getByLabelText('Sub-workspace')).toHaveValue('20')
    expect(screen.getByLabelText('Project')).toHaveValue('JONES')
    await userEvent.type(screen.getByLabelText(/Job Name/), 'GST return')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ project: 'JONES', status_category: 'in_progress' }), expect.anything())
    expect(mocks.create.mock.calls[0][0]).not.toHaveProperty('status_id')
  })

  it('the person can drop the column and start in the first one', async () => {
    mocks.defaults = { projectKey: 'SMITH', statusId: 7, columnName: 'In review' }
    render(<CreateIssueModal />)
    await userEvent.click(screen.getByRole('button', { name: 'Use the first column instead' }))
    await userEvent.type(screen.getByLabelText(/Job Name/), 'Something')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create.mock.calls[0][0]).not.toHaveProperty('status_id')
  })
})
