import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { nestTeams } from './hierarchy'
import { PeopleDirectoryPage } from './PeopleDirectoryPage'
import type { HierarchyNode, HierarchyTeam, UserHierarchy } from '@/api/types'
import { TooltipProvider } from '@/design-system'

const person = (id: number, name: string, role: HierarchyNode['role'], teams: string[] = []): HierarchyNode => ({
  id,
  email: `${name.toLowerCase()}@example.com`,
  username: name.toLowerCase(),
  display_name: name,
  job_title: '',
  avatar: null,
  is_staff: role === 'admin',
  role,
  teams,
})

const team = (id: number, name: string, o: Partial<HierarchyTeam> = {}): HierarchyTeam => ({
  id,
  name,
  avatar_color: '#7B68EE',
  parent_id: null,
  leads: [],
  members: [],
  ...o,
})

const hierarchy: UserHierarchy = {
  derived: true,
  basis: 'Admins are organisation staff; everyone else is grouped by team membership.',
  admins: [person(1, 'Hema', 'admin', ['Accounts'])],
  teams: [
    team(10, 'Accounts', { leads: [person(2, 'Lena', 'lead', ['Accounts'])], members: [person(3, 'Ann', 'member', ['Accounts'])] }),
    team(11, 'Payroll', { parent_id: 10, members: [person(4, 'Pat', 'member', ['Payroll'])] }),
  ],
  no_team: [person(5, 'Solo', 'member')],
}

vi.mock('@/api/users', () => ({
  useUsers: () => ({ data: hierarchy.admins.concat(hierarchy.no_team), isLoading: false }),
  useUserHierarchy: (enabled: boolean) => ({ data: enabled ? hierarchy : undefined, isLoading: false }),
}))

function renderPage(url = '/people') {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[url]}>
          <PeopleDirectoryPage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

describe('People page', () => {
  it('shows the list by default and switches to the diagram', async () => {
    renderPage()
    expect(screen.getByRole('button', { name: 'List' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('group', { name: 'Admins' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Diagram' }))
    expect(screen.getByRole('button', { name: 'Diagram' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('group', { name: 'Admins' })).toBeInTheDocument()
  })

  it('draws admins on top and people under their teams, leads first', () => {
    renderPage('/people?view=diagram')
    const admins = screen.getByRole('group', { name: 'Admins' })
    expect(within(admins).getByText('Hema')).toBeInTheDocument()
    expect(within(admins).getByText('Admin')).toBeInTheDocument()

    const accounts = screen.getByRole('region', { name: 'Accounts workspace' })
    const names = within(accounts).getAllByRole('button').map((b) => b.textContent)
    expect(names[0]).toContain('Lena')
    expect(names[0]).toContain('Workspace lead')
    expect(names[1]).toContain('Ann')
    // Payroll is a sub-team of Accounts, so it sits inside the Accounts branch.
    expect(within(accounts).getByRole('region', { name: 'Payroll workspace' })).toHaveTextContent('Pat')

    expect(screen.getByRole('region', { name: 'No workspace' })).toHaveTextContent('Solo')
    expect(screen.getByText(/grouped by team membership/)).toBeInTheDocument()
  })
})

describe('nestTeams', () => {
  it('nests sub-teams to any depth and keeps orphans at the top', () => {
    const tree = nestTeams([
      team(1, 'A'),
      team(2, 'B', { parent_id: 1 }),
      team(3, 'C', { parent_id: 2 }),
      team(4, 'D', { parent_id: 99 }),
    ])
    expect(tree.map((t) => t.team.name)).toEqual(['A', 'D'])
    expect(tree[0].children[0].team.name).toBe('B')
    expect(tree[0].children[0].children[0].team.name).toBe('C')
  })
})
