import { fireEvent, render, screen } from '@testing-library/react'
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
  useIssueTypes: () => ({ data: [{ id: 2, name: 'Story' }, { id: 1, name: 'Task' }] }),
  useStageDates: () => ({ data: { start: '2026-11-02', stages: [
    { name: 'Pre-check', due_date: '2026-11-05' }, { name: 'Preparation', due_date: '2026-11-12' },
    { name: 'Internal Review', due_date: '2026-11-13' }, { name: 'Client Review', due_date: null }] } }),
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
    expect(screen.getByLabelText('Team Lead')).toHaveValue('6')
    expect(screen.getByText('In review')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/Job Name/), 'Rental property year end')
    await userEvent.type(screen.getByLabelText('Group'), '  Rental properties ')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create).toHaveBeenCalledWith(
      expect.objectContaining({ project: 'SMITH', summary: 'Rental property year end', group: 'Rental properties', status_id: 7, epic_id: 42, assignee_id: 6 }),
      expect.anything(),
    )
  })

  it('the group is optional', async () => {
    mocks.defaults = { projectKey: 'SMITH' }
    render(<CreateIssueModal />)
    await userEvent.type(screen.getByLabelText(/Job Name/), 'GST return')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ summary: 'GST return', group: '' }), expect.anything())
  })

  it('adds the standard sub-tasks with their dates, due on the internal review unless later', async () => {
    mocks.defaults = { projectKey: 'SMITH' }
    render(<CreateIssueModal />)
    const list = screen.getByRole('list', { name: 'Standard sub-tasks' })
    expect(list).toHaveTextContent('Pre-check — due Thu 5 Nov')
    expect(list).toHaveTextContent('Preparation — due Thu 12 Nov')
    expect(list).toHaveTextContent('Internal Review — due Fri 13 Nov')
    expect(list).toHaveTextContent('Client Review — once the client advises')
    expect(screen.getByLabelText('Due date')).toHaveValue('2026-11-13')
    await userEvent.type(screen.getByLabelText(/Job Name/), 'Smith FY26')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create).toHaveBeenLastCalledWith(expect.objectContaining({ default_subtasks: true, due_date: '2026-11-13' }), expect.anything())
  })

  it("won't create a task due before its internal review, and can leave the sub-tasks out", async () => {
    mocks.defaults = { projectKey: 'SMITH' }
    mocks.create.mockClear()
    render(<CreateIssueModal />)
    await userEvent.type(screen.getByLabelText(/Job Name/), 'Smith FY26')
    fireEvent.change(screen.getByLabelText('Due date'), { target: { value: '2026-11-10' } })
    expect(screen.getByRole('alert')).toHaveTextContent("can't be before the internal review (Fri 13 Nov)")
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Add the standard sub-tasks' }))
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create).toHaveBeenLastCalledWith(expect.objectContaining({ default_subtasks: false, due_date: '2026-11-10' }), expect.anything())
  })

  it('creates every task as a Task, with no type to choose', async () => {
    mocks.defaults = { projectKey: 'SMITH' }
    render(<CreateIssueModal />)
    expect(screen.queryByLabelText('Task type')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/Job Name/), 'Rental year end')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ issue_type_id: 1 }), expect.anything())
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
