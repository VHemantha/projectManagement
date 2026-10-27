import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ImportTasksDialog, TEMPLATE_URL } from './ImportTasksDialog'
import type { ImportResult } from '@/api/issues'

const mocks = vi.hoisted(() => ({
  calls: [] as { file: File; commit: boolean }[],
  next: [] as unknown[],
  exported: null as unknown,
}))
vi.mock('@/api/issues', () => ({
  useImportTasks: () => ({
    isPending: false,
    reset: () => {},
    mutate: (vars: { file: File; commit: boolean }, opts: { onSuccess: (r: ImportResult) => void }) => {
      mocks.calls.push(vars)
      opts.onSuccess(mocks.next.shift() as ImportResult)
    },
  }),
  downloadTasksCsv: async (params: unknown) => {
    mocks.exported = params
  },
}))

const result = (over: Partial<ImportResult>): ImportResult => ({
  rows: 2, failed: 0, create: 1, update: 1, unchanged: 0, imported: false,
  results: [
    { row: 2, key: '', summary: 'Smith FY26', action: 'create', errors: {} },
    { row: 3, key: 'RWCA-4', summary: 'Jones FY26', action: 'update', errors: {} },
  ],
  ...over,
})

const csv = new File(['Job Name\nSmith FY26\n'], 'tasks.csv', { type: 'text/csv' })

describe('Bulk import tasks', () => {
  it('offers the template and the current tasks to download', async () => {
    render(<ImportTasksDialog open onOpenChange={() => {}} exportParams={{ no_parent: true, project: 'RWCA' }} />)
    expect(screen.getByRole('link', { name: /Download template/ })).toHaveAttribute('href', TEMPLATE_URL)
    await userEvent.click(screen.getByRole('button', { name: /Download current tasks/ }))
    expect(mocks.exported).toEqual({ no_parent: true, project: 'RWCA' })
  })

  it('shows the problems by row and does not import until the file is right', async () => {
    mocks.calls = []
    mocks.next = [result({
      failed: 1,
      results: [{ row: 3, key: '', summary: 'Jones FY26', action: 'create', errors: { 'Due Date': '“31/31/2026” isn’t a date.' } }],
    })]
    render(<ImportTasksDialog open onOpenChange={() => {}} exportParams={{}} />)
    const importButton = screen.getByRole('button', { name: 'Import' })
    expect(importButton).toBeDisabled()
    await userEvent.upload(screen.getByLabelText('CSV file'), csv)
    await userEvent.click(screen.getByRole('button', { name: 'Check file' }))
    expect(mocks.calls[0].commit).toBe(false)
    expect(screen.getByRole('alert')).toHaveTextContent('1 of 2 rows have problems')
    const row = within(screen.getByLabelText('Check result')).getAllByRole('row')[1]
    expect(row).toHaveTextContent('3')
    expect(row).toHaveTextContent('Due Date: “31/31/2026” isn’t a date.')
    expect(screen.getByRole('button', { name: /^Import/ })).toBeDisabled()
  })

  it('checks, then imports every row', async () => {
    mocks.calls = []
    mocks.next = [result({}), result({ imported: true })]
    render(<ImportTasksDialog open onOpenChange={() => {}} exportParams={{}} />)
    await userEvent.upload(screen.getByLabelText('CSV file'), csv)
    await userEvent.click(screen.getByRole('button', { name: 'Check file' }))
    expect(screen.getByRole('status')).toHaveTextContent('All 2 rows are right: 1 to add, 1 to update.')
    await userEvent.click(screen.getByRole('button', { name: 'Import 2 tasks' }))
    expect(mocks.calls.map((c) => c.commit)).toEqual([false, true])
    expect(screen.getByRole('status')).toHaveTextContent('Imported: 1 added, 1 updated.')
  })
})
