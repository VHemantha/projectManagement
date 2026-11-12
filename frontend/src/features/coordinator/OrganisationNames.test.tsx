import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OrganisationNames } from './OrganisationNames'

const mocks = vi.hoisted(() => ({ rename: vi.fn(), kinds: [] as string[] }))
vi.mock('@/api/organisation', () => ({
  useOrganisation: () => ({ data: { id: 1, name: 'TASKO', can_edit: true } }),
  useOrganisationNames: () => ({
    isLoading: false,
    data: {
      people: [{ id: 2, display_name: 'Ann Lee', job_title: 'Accountant', email: 'ann@x.nz', avatar: null }],
      teams: [{ id: 3, name: 'Team 1', avatar_color: '#800000', parent: null }],
      clients: [{ id: 4, name: 'RWCA', team_name: 'Team 1' }],
      projects: [{ id: 5, key: 'Pochin', name: 'Pochin Group', client: { id: 4, name: 'RWCA' }, is_client_workspace: false }],
    },
  }),
  useRename: (kind: string) => {
    mocks.kinds.push(kind)
    return { mutate: (body: unknown) => mocks.rename(kind, body), isError: false }
  },
}))
vi.mock('@/design-system', () => ({ Avatar: () => null, Skeleton: () => null }))

describe("The CEO's Names tab (AFIT, 12 Nov 2026)", () => {
  beforeEach(() => mocks.rename.mockReset())

  it('lists every name in the organisation, by kind', () => {
    render(<OrganisationNames />)
    expect(screen.getByLabelText('Organisation name')).toHaveValue('TASKO')
    expect(within(screen.getByRole('region', { name: 'People' })).getByLabelText('Name of ann@x.nz')).toHaveValue('Ann Lee')
    expect(screen.getByLabelText('Job title of ann@x.nz')).toHaveValue('Accountant')
    expect(screen.getByLabelText('Name of workspace Team 1')).toBeInTheDocument()
    expect(screen.getByLabelText('Name of sub-workspace RWCA')).toBeInTheDocument()
    expect(screen.getByLabelText('Name of project Pochin')).toHaveValue('Pochin Group')
  })

  it('saves a changed name on Enter, tidied; nothing for an unchanged one; Escape puts it back', async () => {
    render(<OrganisationNames />)
    const org = screen.getByLabelText('Organisation name')
    await userEvent.clear(org)
    await userEvent.type(org, '  AFIT   Connect {Enter}')
    expect(mocks.rename).toHaveBeenCalledWith('organisation', expect.objectContaining({ id: 1, body: { name: 'AFIT Connect' } }))

    mocks.rename.mockReset()
    const project = screen.getByLabelText('Name of project Pochin')
    await userEvent.click(project)
    await userEvent.tab()
    expect(mocks.rename).not.toHaveBeenCalled()

    await userEvent.type(project, ' Ltd{Escape}')
    expect(project).toHaveValue('Pochin Group')
    expect(mocks.rename).not.toHaveBeenCalled()

    const person = screen.getByLabelText('Name of ann@x.nz')
    await userEvent.clear(person)
    await userEvent.type(person, 'Ann Lee-Smith{Enter}')
    expect(mocks.rename).toHaveBeenCalledWith('person', expect.objectContaining({ id: 2, body: { display_name: 'Ann Lee-Smith' } }))
  })

  it("won't empty a name, but a job title may be cleared", async () => {
    render(<OrganisationNames />)
    const name = screen.getByLabelText('Name of workspace Team 1')
    await userEvent.clear(name)
    await userEvent.tab()
    expect(mocks.rename).not.toHaveBeenCalled()
    expect(name).toHaveValue('Team 1')
    await userEvent.clear(screen.getByLabelText('Job title of ann@x.nz'))
    await userEvent.tab()
    expect(mocks.rename).toHaveBeenCalledWith('person', expect.objectContaining({ id: 2, body: { job_title: '' } }))
  })

  it('finds a name', async () => {
    render(<OrganisationNames />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Find a name' }), 'pochin')
    expect(screen.queryByLabelText('Name of ann@x.nz')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Name of project Pochin')).toBeInTheDocument()
  })
})
