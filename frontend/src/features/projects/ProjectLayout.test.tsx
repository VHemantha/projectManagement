import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { ProjectLayout, WorkspaceSectionRedirect } from './ProjectLayout'
import { useProjectContext } from './useProjectContext'

const project = {
  key: 'Pochin',
  name: 'Pochin Group',
  project_type: 'scrum',
  is_client_workspace: false,
  avatar_color: '#7B68EE',
}

vi.mock('@/api/projects', () => ({
  useProject: (key: string) => ({ data: key.toLowerCase() === 'pochin' ? project : undefined, isLoading: false }),
}))

// Each tab's page is stubbed: these tests are about which one the workspace page shows.
function Stub({ name }: { name: string }) {
  const { project: p } = useProjectContext()
  return <div data-testid="tab-page">{`${name} for ${p.key}`}</div>
}
vi.mock('@/features/board/ProjectBoardPage', () => ({ ProjectBoardPage: () => <Stub name="board" /> }))
vi.mock('./ProjectIssuesPage', () => ({ ProjectIssuesPage: () => <Stub name="jobs" /> }))
vi.mock('./ProjectSettingsPage', () => ({ ProjectSettingsPage: () => <Stub name="settings" /> }))
vi.mock('./ProjectSummaryPage', () => ({ ProjectSummaryPage: () => <Stub name="summary" /> }))
vi.mock('@/features/timeline/TimelinePage', () => ({ TimelinePage: () => <Stub name="timeline" /> }))
vi.mock('@/features/backlog/BacklogPage', () => ({ BacklogPage: () => <Stub name="backlog" /> }))
vi.mock('@/features/reports/SprintReportPage', () => ({ SprintReportPage: () => <Stub name="reports" /> }))

function Where() {
  const { search } = useLocation()
  return <div data-testid="search">{search}</div>
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route
          path="/workspaces/:key"
          element={
            <>
              <ProjectLayout />
              <Where />
            </>
          }
        />
        <Route path="/workspaces/:key/:section" element={<WorkspaceSectionRedirect />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Workspace page', () => {
  it('opens on the Kanban tab, first in the tab bar', () => {
    renderAt('/workspaces/Pochin')
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['Kanban', 'Jobs', 'Timeline', 'Settings'])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('tab-page')).toHaveTextContent('board for Pochin')
  })

  it('deep-links to a tab with ?tab= and switches tabs in the URL', async () => {
    renderAt('/workspaces/Pochin?tab=jobs')
    expect(screen.getByTestId('tab-page')).toHaveTextContent('jobs for Pochin')
    await userEvent.click(screen.getByRole('tab', { name: 'Settings' }))
    expect(screen.getByTestId('tab-page')).toHaveTextContent('settings for Pochin')
    expect(screen.getByTestId('search')).toHaveTextContent('?tab=settings')
  })

  it('sends the hidden Summary (and Scrum backlog) to Kanban', () => {
    renderAt('/workspaces/Pochin?tab=summary')
    expect(screen.getByTestId('tab-page')).toHaveTextContent('board for Pochin')
    expect(screen.getByTestId('search')).toHaveTextContent('?tab=kanban')
    expect(screen.queryByRole('tab', { name: 'Summary' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Backlog' })).not.toBeInTheDocument()
  })

  it('opens old sub-page URLs on the matching tab', () => {
    renderAt('/workspaces/Pochin/issues?assignee=3')
    expect(screen.getByTestId('tab-page')).toHaveTextContent('jobs for Pochin')
    expect(screen.getByTestId('search')).toHaveTextContent('?assignee=3&tab=jobs')
  })

  it('goes to the canonical key, keeping the tab', () => {
    renderAt('/workspaces/POCHIN?tab=timeline')
    expect(screen.getByTestId('tab-page')).toHaveTextContent('timeline for Pochin')
  })
})
