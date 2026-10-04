import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LegacyTeamsRedirect, LegacyWorkspacesRedirect, WorkspaceRoute } from './LegacyRedirects'

vi.mock('@/features/teams/TeamDetailPage', () => ({ TeamDetailPage: () => <div data-testid="where">workspace page</div> }))

function Where() {
  const { pathname, search, hash } = useLocation()
  return <div data-testid="where">{`${pathname}${search}${hash}`}</div>
}

/** The same route table as router.tsx, with the real pages replaced by a location readout. */
function renderAt(url: string) {
  const { unmount } = render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/projects/*" element={<Where />} />
        <Route path="/workspaces" element={<Where />} />
        <Route path="/workspaces/:teamId" element={<WorkspaceRoute />} />
        <Route path="/workspaces/*" element={<LegacyWorkspacesRedirect />} />
        <Route path="/teams/*" element={<LegacyTeamsRedirect />} />
      </Routes>
    </MemoryRouter>,
  )
  const where = screen.getByTestId('where').textContent
  unmount()
  return where
}

describe('old links after the hierarchy rename', () => {
  it('opens a workspace by its id', () => {
    expect(renderAt('/workspaces/4')).toBe('workspace page')
    expect(renderAt('/workspaces')).toBe('/workspaces')
  })

  it('sends old project links under /workspaces to /projects, keeping path, query and hash', () => {
    expect(renderAt('/workspaces/Pochin')).toBe('/projects/Pochin')
    expect(renderAt('/workspaces/Pochin?tab=jobs#top')).toBe('/projects/Pochin?tab=jobs#top')
    expect(renderAt('/workspaces/TRK/issues/TRK-12')).toBe('/projects/TRK/issues/TRK-12')
    expect(renderAt('/workspaces/all-issues?client=3')).toBe('/projects/all-issues?client=3')
  })

  it('sends old team links to workspaces', () => {
    expect(renderAt('/teams')).toBe('/workspaces')
    expect(renderAt('/teams/7')).toBe('workspace page')
  })

  it('leaves project links alone', () => {
    expect(renderAt('/projects/Pochin/board?quickFilter=mine')).toBe('/projects/Pochin/board?quickFilter=mine')
  })
})
