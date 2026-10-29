import { Download, FileUp } from 'lucide-react'
import { useState } from 'react'

import styles from './ImportTasksDialog.module.css'
import { extractErrorMessage } from '@/api/errors'
import { downloadTasksCsv, type ImportResult, useImportTasks } from '@/api/issues'
import { Button, Dialog, DialogContent } from '@/design-system'

/** The standard template, served with the app's files from the cloud. */
export const TEMPLATE_URL = '/templates/tasks-import-template.csv'

// The same guide as the template's second and third rows (backend csv_import.SPEC).
const GUIDE: { column: string; required: boolean; type: string; format: string }[] = [
  { column: 'Task Key', required: false, type: 'Text', format: 'Leave empty to add a new task; a task key (e.g. RWCA-12) updates that task.' },
  { column: 'Sub-workspace', required: true, type: 'Text', format: "The sub-workspace's name exactly as it shows in the app." },
  { column: 'Job Name', required: true, type: 'Text', format: 'Up to 500 characters.' },
  { column: 'Group', required: true, type: 'Text', format: 'Up to 100 characters.' },
  { column: 'Accountant', required: true, type: 'Person', format: 'Email address, or the name as it shows in the app.' },
  { column: 'Project Key', required: false, type: 'Text', format: "A project of that sub-workspace (e.g. RWCA). Empty: the sub-workspace's own task list." },
  { column: 'Status', required: false, type: 'Stage', format: 'To Start, In Progress, Waiting for Info, Sent to Client, Internal Adjustments, Client Adjustments, Complete or To be Archived. Empty: To Start.' },
  { column: 'Priority', required: false, type: 'Choice', format: 'Highest, High, Medium, Low or Lowest. Empty: Medium.' },
  { column: 'Team Lead, Reviewer', required: false, type: 'Person', format: 'Email address, or the name as it shows in the app.' },
  { column: 'Currently Responsible', required: false, type: 'Person', format: 'Email address, or the name. Empty: the accountant.' },
  { column: 'Start Date', required: false, type: 'Date', format: 'YYYY-MM-DD (e.g. 2026-11-02) or DD/MM/YYYY (e.g. 02/11/2026). Empty: today.' },
  { column: 'Due Date', required: false, type: 'Date', format: 'YYYY-MM-DD or DD/MM/YYYY. Empty: 5 days after the start date.' },
  { column: 'Estimated Hours', required: false, type: 'Number', format: 'Hours, with a point for decimals (e.g. 6.5); 0 to 10000.' },
  { column: 'Budgeted Hours', required: false, type: 'Number', format: 'Hours, with a point for decimals (e.g. 8). Set by a team lead or above.' },
  { column: 'Labels', required: false, type: 'List', format: "The project's existing labels, separated by ; (e.g. GST; Urgent)." },
  { column: 'Description', required: false, type: 'Text', format: 'Plain text.' },
  { column: 'Add Standard Sub-tasks', required: false, type: 'Yes/No', format: 'yes adds Pre-check, Preparation, Internal Review and Client Review. Empty: no.' },
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
              <li>
                Fill in one task per row (Excel or Google Sheets) and save it as CSV. A new task needs its <strong>Sub-workspace, Job Name, Group and
                Accountant</strong>; the rest is optional. When updating a task, an empty cell keeps its value and - clears it. The template&apos;s two
                rows starting with # are a guide and are skipped.
              </li>
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
              <summary>What goes in each column (required, type and format)</summary>
              <table className={styles.table} aria-label="Columns">
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Required</th>
                    <th>Type</th>
                    <th>Format and default</th>
                  </tr>
                </thead>
                <tbody>
                  {GUIDE.map((g) => (
                    <tr key={g.column}>
                      <th scope="row">{g.column}</th>
                      <td>{g.required ? <strong>Required for a new task</strong> : 'Optional'}</td>
                      <td>{g.type}</td>
                      <td>{g.format}</td>
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
