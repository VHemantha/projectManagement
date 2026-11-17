import { format, parseISO } from 'date-fns'
import { FileSpreadsheet, Save, Undo2 } from 'lucide-react'
import { useMemo, useState } from 'react'

import styles from './WpAgentPanel.module.css'
import { extractErrorMessage } from '@/api/errors'
import { downloadWorkpaper, type EwpField, type WpRun, useSaveWorkpaper } from '@/api/wpAgent'
import { Button } from '@/design-system'

const TONE: Record<string, string> = {
  Prepared: 'success', 'Prepared - review': 'warning', 'Incomplete evidence': 'danger', 'Nothing to enter': '',
  agrees: 'success', difference: 'warning', missing: 'danger', computed: '',
}

const money = (v: string | null | undefined) => {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return v
  const text = Math.abs(n).toLocaleString('en-NZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return n < 0 ? `(${text})` : text
}

function fileName(run: WpRun) {
  const s = run.options.setup
  return `Electronic workpapers ${s?.entity || ''} ${s?.balance_date || ''}`.replace(/\s+/g, ' ').trim() + '.xlsm'
}

/** The electronic workpapers (16 Nov 2026): each workpaper's cells as the agent filled them, with their
 * source; the accountant corrects any cell, saves (the workbook is rewritten, formulas untouched) and
 * downloads the macro workbook. */
export function EwpResult({ run, jobKey }: { run: WpRun; jobKey: string }) {
  const g = run.gst
  const workpapers = useMemo(() => g.workpapers ?? [], [g.workpapers])
  const [tab, setTab] = useState<string>(() => workpapers.find((w) => w.key !== 'Workbench')?.key ?? 'Workbench')
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const save = useSaveWorkpaper(jobKey, run.run_id)
  const fields = (g.fields ?? []).filter((f) => f.wp === tab)
  const exceptions = (g.exceptions ?? []).filter((x) => (tab === 'Documents' ? false : x.wp === tab))
  const current = workpapers.find((w) => w.key === tab)
  const dirty = Object.keys(draft).length

  const shown = (f: EwpField) => (f.id in draft ? draft[f.id] : (f.value ?? ''))
  const edit = (f: EwpField, value: string) =>
    setDraft((d) => {
      const next = { ...d }
      if (value === (f.value ?? '')) delete next[f.id]
      else next[f.id] = value
      return next
    })
  const submit = () =>
    save.mutate(Object.entries(draft).map(([id, value]) => ({ id, value: value === '' ? null : value })), { onSuccess: () => setDraft({}) })
  const download = async () => {
    setBusy(true)
    setError('')
    try {
      await downloadWorkpaper(run.run_id, fileName(run))
    } catch (e) {
      setError(extractErrorMessage(e, 'The workbook could not be downloaded.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={styles.result} aria-label="Electronic workpapers">
      <div className={styles.resultHead}>
        <span className={styles.status} data-tone={TONE[g.status ?? ''] ?? ''}>{g.status}</span>
        <span className={styles.muted}>
          {run.finished_at ? format(parseISO(run.finished_at), 'dd-MM-yy HH:mm') : ''} · {run.requested_by}
          {run.demo ? ' · demo mode (no AI reading)' : ''}
        </span>
        {run.has_workpaper && (
          <Button type="button" variant="primary" size="sm" onClick={download} disabled={busy || dirty > 0}
            title={dirty ? 'Save your changes first' : undefined}>
            <FileSpreadsheet size={14} aria-hidden="true" /> {busy ? 'Preparing…' : 'Download workbook (.xlsm)'}
          </Button>
        )}
      </div>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {g.summary && <p className={styles.summary}>{g.summary}</p>}

      <div className={styles.wpTabs} role="group" aria-label="Workpapers">
        {[...workpapers.map((w) => ({ key: w.key, label: w.key, status: w.status })), { key: 'Documents', label: 'Documents', status: '' }].map((w) => (
          <button key={w.key} type="button" className={styles.wpTab} aria-pressed={tab === w.key} data-tone={TONE[w.status] ?? ''}
            onClick={() => setTab(w.key)} title={w.status}>
            {w.label}
          </button>
        ))}
      </div>

      {tab === 'Documents' ? (
        <table className={styles.table} aria-label="Documents">
          <tbody>
            {(g.inventory ?? []).map((d) => (
              <tr key={d.sid} data-status={d.status}>
                <th scope="row">{d.path}{d.name}</th>
                <td>{d.kind.replace(/_/g, ' ')}{d.wp ? ` → ${d.wp}` : ''}</td>
                <td className={styles.note}>{d.status}{d.note ? ` — ${d.note}` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <>
          {current && (
            <p className={styles.muted}>
              <strong>{current.key} {current.title}</strong> — {current.purpose}.{' '}
              <span className={styles.status} data-tone={TONE[current.status] ?? ''}>{current.status}</span>
            </p>
          )}
          {(current?.checks.length ?? 0) > 0 && (
            <table className={styles.table} aria-label="Checks">
              <thead>
                <tr><th>Check</th><th className={styles.num}>Workpaper</th><th className={styles.num}>Ledger</th><th className={styles.num}>Variance</th><th /></tr>
              </thead>
              <tbody>
                {current!.checks.map((c, i) => (
                  <tr key={i}>
                    <th scope="row">{c.label}</th>
                    <td className={styles.num}>{money(c.workpaper)}</td>
                    <td className={styles.num}>{money(c.ledger)}</td>
                    <td className={styles.num}>{money(c.variance)}</td>
                    <td><span className={styles.status} data-tone={TONE[c.status] ?? ''}>{c.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {fields.length === 0 ? (
            <p className={styles.muted}>Nothing was entered on {tab}: see the exceptions for what is needed.</p>
          ) : (
            <table className={styles.table} aria-label={`${tab} cells`}>
              <thead>
                <tr><th>Cell</th><th>Item</th><th>Value</th><th>Source</th></tr>
              </thead>
              <tbody>
                {fields.map((f) => (
                  <tr key={f.id} data-changed={f.id in draft ? 'yes' : f.status === 'edited' ? 'edited' : ''}>
                    <td className={styles.note}>{f.sheet}!{f.cell}</td>
                    <th scope="row">{f.label}</th>
                    <td>
                      {f.editable ? (
                        <input
                          className={styles.cellInput}
                          aria-label={`${f.label} (${f.sheet}!${f.cell})`}
                          type={f.kind === 'date' ? 'date' : 'text'}
                          inputMode={f.kind === 'money' || f.kind === 'number' ? 'decimal' : undefined}
                          value={shown(f)}
                          onChange={(e) => edit(f, e.target.value)}
                        />
                      ) : (
                        <span>{f.value}</span>
                      )}
                    </td>
                    <td className={styles.note}>
                      <span className={styles.tag} data-severity={f.status === 'verified' ? 'info' : f.status === 'edited' ? 'info' : 'review'}>{f.status}</span>{' '}
                      {f.source}
                      {f.note ? ` — ${f.note}` : ''}
                      {f.edited_by ? ` — changed by ${f.edited_by} (agent: ${f.agent_value ?? '—'})` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {exceptions.length > 0 && (
            <ul className={styles.exceptions} aria-label={`${tab} exceptions`}>
              {exceptions.map((x) => (
                <li key={x.id} data-severity={x.severity}>
                  <span className={styles.tag} data-severity={x.severity}>{x.severity}</span> {x.text}
                  {x.next_evidence && <small>Next evidence: {x.next_evidence}</small>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <div className={styles.actions}>
        <Button type="button" variant="primary" size="sm" disabled={!dirty || save.isPending} onClick={submit}>
          <Save size={14} aria-hidden="true" /> {save.isPending ? 'Saving…' : dirty ? `Save ${dirty} change${dirty > 1 ? 's' : ''}` : 'No changes'}
        </Button>
        {dirty > 0 && (
          <Button type="button" variant="secondary" size="sm" onClick={() => setDraft({})} disabled={save.isPending}>
            <Undo2 size={14} aria-hidden="true" /> Discard
          </Button>
        )}
        {(g.edits?.length ?? 0) > 0 && <span className={styles.muted}>{g.edits!.length} change(s) saved to the workbook</span>}
      </div>
      {save.isError && <p role="alert" className={styles.error}>{extractErrorMessage(save.error, 'The changes could not be saved.')}</p>}
      {save.data?.errors && Object.keys(save.data.errors).length > 0 && (
        <p role="alert" className={styles.error}>{Object.values(save.data.errors).join(' ')}</p>
      )}
      <p className={styles.muted}>
        Prepared by the WP Agent in the firm&apos;s workbook — only input cells are filled; formulas and macros are untouched and Excel recalculates
        on opening. Journals on D1 are proposals, not posted. Task {jobKey}.
      </p>
    </section>
  )
}
