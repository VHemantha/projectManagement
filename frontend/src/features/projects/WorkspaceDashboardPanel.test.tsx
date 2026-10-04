import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WorkspaceDashboardPanel } from './WorkspaceDashboardPanel'
import type { ProjectDetail } from '@/api/types'
import { TooltipProvider } from '@/design-system'
import { useSidebarStore } from '@/store/sidebarStore'

const { mutateAsync } = vi.hoisted(() => ({ mutateAsync: vi.fn(() => Promise.resolve({})) }))
vi.mock('@/api/projects', () => ({
  useUpdateProject: () => ({ mutateAsync, isError: false, error: null }),
}))

function makeProject(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    key: 'Dash',
    name: 'Dashboard',
    description: 'Year-end accounts',
    special_notes: '',
    budgeted_hours: 40,
    actual_hours: 10,
    deadline: null,
    can_manage: true,
    ...overrides,
  } as ProjectDetail
}

function renderPanel(project: ProjectDetail) {
  return render(
    <TooltipProvider>
      <WorkspaceDashboardPanel project={project} />
    </TooltipProvider>,
  )
}

beforeEach(() => {
  mutateAsync.mockClear()
  useSidebarStore.getState().setOpen('workspaceDashboard', true)
})
afterEach(() => vi.useRealTimers())

describe('WorkspaceDashboardPanel', () => {
  it('shows actual vs budgeted time, red when over budget', () => {
    renderPanel(makeProject({ actual_hours: 45.5, budgeted_hours: 40 }))
    expect(screen.getByText('45.5 h')).toHaveAttribute('data-tone', 'over')
    expect(screen.getByText('of 40 h budgeted')).toBeInTheDocument()
    expect(screen.getByText('Over budget by 5.5 h')).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Time used of budget' })).toHaveAttribute('aria-valuenow', '45.5')
  })

  it('turns amber close to the budget', () => {
    renderPanel(makeProject({ actual_hours: 38, budgeted_hours: 40 }))
    expect(screen.getByText('38 h')).toHaveAttribute('data-tone', 'warning')
    expect(screen.getByText(/Nearly over budget/)).toBeInTheDocument()
  })

  it('shows the deadline countdown and status', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 1))
    renderPanel(makeProject({ deadline: '2026-10-04' }))
    expect(screen.getByText('3 days left')).toBeInTheDocument()
    expect(screen.getByText('Due soon')).toBeInTheDocument()
  })

  it('autosaves special notes a moment after typing stops', async () => {
    vi.useFakeTimers()
    renderPanel(makeProject())
    fireEvent.change(screen.getByRole('textbox', { name: 'Special notes' }), { target: { value: 'Call the client first' } })
    expect(mutateAsync).not.toHaveBeenCalled()
    await act(async () => {
      vi.advanceTimersByTime(1000)
    })
    expect(mutateAsync).toHaveBeenCalledWith({ special_notes: 'Call the client first' })
    expect(screen.getByText('Saved')).toBeInTheDocument()
  })

  it('saves the description when leaving the box', () => {
    renderPanel(makeProject())
    const box = screen.getByLabelText('Project description')
    fireEvent.change(box, { target: { value: 'Quarterly VAT' } })
    fireEvent.blur(box)
    expect(mutateAsync).toHaveBeenCalledWith({ description: 'Quarterly VAT' })
  })

  it('edits the budget', async () => {
    renderPanel(makeProject())
    await userEvent.click(screen.getByRole('button', { name: 'Edit budget' }))
    const input = screen.getByLabelText('Budgeted hours')
    await userEvent.clear(input)
    await userEvent.type(input, '60{Enter}')
    expect(mutateAsync).toHaveBeenCalledWith({ budgeted_hours: 60 })
  })

  it('is read-only for people who cannot manage the workspace', () => {
    renderPanel(makeProject({ can_manage: false, special_notes: 'Keep receipts' }))
    expect(screen.getByText('Year-end accounts')).toBeInTheDocument()
    expect(screen.getByText('Keep receipts')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit budget' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Deadline', { selector: 'input' })).not.toBeInTheDocument()
  })

  it('collapses to an icon rail and expands again', async () => {
    renderPanel(makeProject({ actual_hours: 50 }))
    await userEvent.click(screen.getByRole('button', { name: 'Hide dashboard' }))
    expect(screen.queryByText('Special notes')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Time: 50 h of 40 h' })).toBeInTheDocument()
    expect(useSidebarStore.getState().open.workspaceDashboard).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Show dashboard' }))
    expect(screen.getByRole('region', { name: 'Special notes' })).toBeInTheDocument()
  })
})
