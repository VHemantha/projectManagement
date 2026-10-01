import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { LegacyProjectsRedirect } from './LegacyProjectsRedirect'

function Where() {
  const { pathname, search, hash } = useLocation()
  return <div data-testid="where">{`${pathname}${search}${hash}`}</div>
}

function renderAt(url: string) {
  const { unmount } = render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/projects/*" element={<LegacyProjectsRedirect />} />
        <Route path="/workspaces/*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
  const where = screen.getByTestId('where').textContent
  unmount()
  return where
}

describe('LegacyProjectsRedirect', () => {
  it('sends the old section root to /workspaces', () => {
    expect(renderAt('/projects')).toBe('/workspaces')
  })

  it('keeps the rest of the path, the query and the hash', () => {
    expect(renderAt('/projects/Pochin/board?quickFilter=mine#top')).toBe('/workspaces/Pochin/board?quickFilter=mine#top')
    expect(renderAt('/projects/TRK/issues/TRK-12')).toBe('/workspaces/TRK/issues/TRK-12')
    expect(renderAt('/projects/all-issues?client=3')).toBe('/workspaces/all-issues?client=3')
  })
})
