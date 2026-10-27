import { Download, FileUp } from 'lucide-react'
import { useState } from 'react'

import styles from './ImportTasksDialog.module.css'
import { extractErrorMessage } from '@/api/errors'
import { downloadTasksCsv, type ImportResult, useImportTasks } from '@/api/issues'
import { Button, Dialog, DialogContent } from '@/design-system'

/** The standard template, served with the app's files from the cloud. */
export const TEMPLATE_URL = '/templates/tasks-import-template.csv'

const GUIDE: [string, string][] = [
  ['Task Key', 'Empty to add a new task. A key (e.g. RWCA-12) updates that task.'],
  ['Project Key', 'The project the new task goes in, e.g. RWCA. Or give the Sub-workspace instead.'],
  ['Sub-workspace', 'For a sub-workspace without projects: its name.'],
  ['Job Name', 'Required for a new task.'],
  ['Group', 'Free text.'],
  ['Status', 'A stage: To Start, In Progress, Waiting for Info, Sent to Client, Internal Adjustments, Client Adjustments, Complete, To be Archived.'],
  ['Priority', 'Highest, High, Medium, Low or Lowest.'],
  ['Team Lead, Accountant, Reviewer, Currently Responsible', 'An email address, or the name as it shows in the app.'],
  ['Start Date, Due Date', '2026-11-30 or 30/11/2026.'],
  ['Estimated Hours, Budgeted Hours', 'Numbers. Only a team lead or above can set budgeted hours.'],
  ['Labels', "The project's labels, separated by ; (semicolons)."],
  ['Description', 'Plain text.'],
  ['Add Standard Sub-tasks', 'yes adds Pre-check, Preparation, Internal Review and Client Review to a new task.'],
]

function counts(r: ImportResult) {
  const parts = [
    r.create && `${r.create} to add`,
    r.update && `${r.update} to update`,
    r.unchanged && `${r.unchanged} unchanged`,
  ].filter(Boolean)
  return parts.join(', ') || 'nothing to change'
}

/** Add or update tasks in bulk from a CSV file: download the template (or the current tasks),
 * fill it in, check it, then import. Nothing is saved while any row has a problem. */
export function ImportTasksDialog({ open, onOpenChange, exportParams }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The filters of the page it was opened from, for "Download current tasks". */
  exportParams: Record<string, string | number | boolean>
}) {
  const [file, setFile] = useState<File | null>(null)
  const [checked, setChecked] = useState<ImportResult | null>(null)
  const [done, setDone] = useState<ImportResult | null>(null)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')
  const run = useImportTasks()

  const reset = () => {
    setFile(null)
    setChecked(null)
    setDone(null)
    setError('')
    run.reset()
  }
  const close = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }
  const submit = (commit: boolean) => {
    if (!file) return
    setError('')
    run.mutate({ file, commit }, {
      onSuccess: (r) => (r.imported ? setDone(r) : setChecked(r)),
      onError: (e) => setError(extractErrorMessage(e, 'The file could not be read.')),
    })
  }
  const exportTasks = async () => {
    setExporting(true)
    setError('')
    try {
      await downloadTasksCsv(exportParams)
    } catch (e) {
      setError(extractErrorMessage(e, 'The tasks could not be downloaded.'))
    } finally {
      setExporting(false)
    }
  }
  const problems = checked?.results.filter((r) => Object.keys(r.errors).length > 0) ?? []

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent title="Bulk import tasks (CSV)" maxWidth={760}>
        {done ? (
          <div className={styles.section}>
            <p className={styles.success} role="status">
              Imported: {done.create} added, {done.update} updated{done.unchanged ? `, ${done.unchanged} unchanged` : ''}.
            </p>
            <div className={styles.actions}>
              <Button variant="secondary" onClick={reset}>Import another file</Button>
              <Button variant="primary" onClick={() => close(false)}>Done</Button>
            </div>
          </div>
        ) : (
          <>
            <ol className={styles.steps}>
              <li>
                Download the standard template, or the current tasks to update them.
                <div className={styles.links}>
                  <a className={styles.link} href={TEMPLATE_URL} download="tasks-import-template.csv">
                    <Download size={14} /> Download template
                  </a>
                  <button type="button" className={styles.link} onClick={exportTasks} disabled={exporting}>
                    <Download size={14} /> {exporting ? 'Preparing…' : 'Download current tasks'}
                  </button>
                </div>
              </li>
              <li>Fill in one task per row (Excel or Google Sheets), and save it as CSV. An empty cell keeps the task's value; - clears it.</li>
              <li>
                Choose the file and check it. Nothing is saved until every row is right.
                <label className={styles.file}>
                  <FileUp size={14} />
                  <span>{file ? file.name : 'Choose CSV file…'}</span>
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    aria-label="CSV file"
                    onChange={(e) => {
                      setFile(e.target.files?.[0] ?? null)
                      setChecked(null)
                      setError('')
                    }}
                  />
                </label>
              </li>
            </ol>

            <details className={styles.guide}>
              <summary>What goes in each column</summary>
              <table className={styles.table}>
                <tbody>
                  {GUIDE.map(([col, help]) => (
                    <tr key={col}>
                      <th scope="row">{col}</th>
                      <td>{help}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>

            {error && <p className={styles.error} role="alert">{error}</p>}

            {checked && (
              <div className={styles.section} aria-label="Check result">
                {problems.length ? (
                  <p className={styles.error} role="alert">
                    {problems.length} of {checked.rows} {checked.rows === 1 ? 'row has' : 'rows have'} problems. Fix them in the file and check it again.
                  </p>
                ) : (
                  <p className={styles.success} role="status">All {checked.rows} rows are right: {counts(checked)}.</p>
                )}
                <div className={styles.scroll}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Row</th>
                        <th>Task</th>
                        <th>Job Name</th>
                        <th>Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(problems.length ? problems : checked.results).map((r) => (
                        <tr key={r.row}>
                          <td className={styles.num}>{r.row}</td>
                          <td>{r.key || <span className={styles.muted}>New</span>}</td>
                          <td>{r.summary}</td>
                          <td>
                            {Object.keys(r.errors).length ? (
                              <ul className={styles.problems}>
                                {Object.entries(r.errors).map(([col, msg]) => (
                                  <li key={col}><strong>{col}:</strong> {msg}</li>
                                ))}
                              </ul>
                            ) : r.action === 'create' ? 'Add' : r.action === 'update' ? 'Update' : 'No change'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className={styles.actions}>
              <Button variant="secondary" onClick={() => close(false)}>Cancel</Button>
              <Button variant="secondary" disabled={!file || run.isPending} onClick={() => submit(false)}>
                {run.isPending && !checked ? 'Checking…' : 'Check file'}
              </Button>
              <Button
                variant="primary"
                disabled={!checked || problems.length > 0 || checked.create + checked.update === 0 || run.isPending}
                onClick={() => submit(true)}
              >
                {run.isPending && checked ? 'Importing…' : checked ? `Import ${checked.create + checked.update} tasks` : 'Import'}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
