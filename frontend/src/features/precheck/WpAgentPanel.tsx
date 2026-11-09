import { format, parseISO } from 'date-fns'
import { AlertTriangle, CheckCircle2, FileSpreadsheet, Loader2, Play, RotateCcw, Upload } from 'lucide-react'
import { type FormEvent, useRef, useState } from 'react'

import { StopRun } from './StopRun'
import styles from './WpAgentPanel.module.css'
import { extractErrorMessage } from '@/api/errors'
import {
  downloadWorkpaper,
  type GstBasis,
  type GstFrequency,
  type GstResult,
  type GstSetup,
  type WpOptions,
  type WpRun,
  useRunWpAgent,
  useWpAgent,
} from '@/api/wpAgent'
import { Button, Skeleton } from '@/design-system'

const BASES: { value: GstBasis; label: string }[] = [
  { value: 'payments', label: 'Payments' },
  { value: 'invoice', label: 'Invoice' },
  { value: 'hybrid', label: 'Hybrid' },
]
const FREQUENCIES: { value: GstFrequency; label: string }[] = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'two_monthly', label: '2 monthly' },
  { value: 'six_monthly', label: '6 monthly' },
]
const EMPTY_SETUP: GstSetup = {
  entity: '', ird_number: '', fy_start: '', balance_date: '', basis: 'payments', frequency: 'two_monthly', software: 'Xero', currency: 'NZD',
  gl_version: '', gst_accounts: '', first_year: false, tolerance: '0',
}
const STATUS_TONE: Record<string, string> = {
  Reconciled: 'success', 'Reconciled subject to corrections': 'warning', Unreconciled: 'danger', 'Incomplete evidence': 'danger',
}

const money = (v: string | null | undefined) => {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  const text = Math.abs(n).toLocaleString('en-NZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return n < 0 ? `(${text})` : text
}
const ddmmyy = (iso: string | null | undefined) => (iso ? format(parseISO(iso), 'dd-MM-yy') : '')

function fileName(run: WpRun) {
  const s = run.options.setup
  return `GST reconciliation ${s?.entity || ''} ${s?.balance_date || ''}`.replace(/\s+/g, ' ').trim() + '.xlsx'
}

/** The WP Agent (AFIT, 8 Nov 2026): the year-end GST reconciliation workpaper, from the documents in a
 * Google Drive folder — returns and IRD settlements, receivables and payables GST from the Xero ageing
 * reports, journals and late claims counted once, the import GST check and payment coding — as an
 * editable Excel workpaper in the firm's L1 layout. It prepares; the accountant reviews and signs off. */
export function WpAgentPanel({ jobKey }: { jobKey: string }) {
  const { data, isLoading, isError } = useWpAgent(jobKey)
  if (isLoading) return <Skeleton height={64} />
  if (isError || !data) return <p className={styles.muted}>The WP Agent could not be loaded. Refresh the page to try again.</p>
  const latest = data.latest
  return (
    <div className={styles.panel}>
      <p className={styles.lead}>
        Reconciles GST outstanding per the returns and IRD records at the balance date to the GST control balance, explains every
        difference with its evidence, and writes the workpaper (Excel, in the firm&apos;s L1 layout). It reads the Drive folder only; it
        never posts a journal or files a return.
      </p>
      <WpForm key={latest?.run_id ?? 'new'} jobKey={jobKey} defaults={data.defaults} latest={latest} />
      {latest && <Result run={latest} jobKey={jobKey} />}
      {data.history.length > 1 && (
        <details className={styles.box}>
          <summary>Earlier runs ({data.history.length - 1})</summary>
          <ul className={styles.list}>
            {data.history.slice(1).map((h) => (
              <li key={h.run_id}>
                {format(parseISO(h.created_at), 'dd-MM-yy HH:mm')} — {h.requested_by || 'someone'}: {h.status}
                {h.summary ? ` — ${h.summary}` : ''}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function WpForm({ jobKey, defaults, latest }: { jobKey: string; defaults: Partial<WpOptions>; latest: WpRun | null }) {
  const run = useRunWpAgent(jobKey)
  const [link, setLink] = useState(defaults.drive_link ?? '')
  const [arLink, setArLink] = useState(defaults.ar_link ?? '')
  const [apLink, setApLink] = useState(defaults.ap_link ?? '')
  const [setup, setSetup] = useState<GstSetup>({ ...EMPTY_SETUP, ...(defaults.setup ?? {}) })
  const [choices, setChoices] = useState(defaults.choices ?? {})
  const arRef = useRef<HTMLInputElement>(null)
  const apRef = useRef<HTMLInputElement>(null)
  const running = latest?.status === 'running'
  const detected = latest?.gst?.detected

  const set = <K extends keyof GstSetup>(key: K, value: GstSetup[K]) => setSetup((s) => ({ ...s, [key]: value }))
  const start = (extra: Partial<WpOptions['choices']> = {}) => {
    const next = { ...choices, ...extra }
    setChoices(next)
    run.mutate({ drive_link: link.trim(), ar_link: arLink.trim(), ap_link: apLink.trim(), setup, choices: next })
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    start()
  }

  return (
    <form className={styles.box} onSubmit={submit} aria-label="WP Agent inputs">
      <label className={styles.field}>
        <span>Google Drive link of the documents (folder or files; several separated by ;)</span>
        <textarea
          rows={2}
          value={link}
          onChange={(e) => setLink(e.target.value)}
          placeholder="https://drive.google.com/drive/folders/…"
          required
        />
      </label>
      <div className={styles.grid2}>
        <label className={styles.field}>
          <span>AR ageing report link (optional; with the GST column)</span>
          <input ref={arRef} value={arLink} onChange={(e) => setArLink(e.target.value)} placeholder="Drive link to the year-end Aged Receivables" />
        </label>
        <label className={styles.field}>
          <span>AP ageing report link (optional; with the GST column)</span>
          <input ref={apRef} value={apLink} onChange={(e) => setApLink(e.target.value)} placeholder="Drive link to the year-end Aged Payables" />
        </label>
      </div>
      <fieldset className={styles.settings}>
        <legend>Job settings — check them before the run</legend>
        <label className={styles.field}>
          <span>Entity</span>
          <input value={setup.entity} onChange={(e) => set('entity', e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>IRD number</span>
          <input value={setup.ird_number} onChange={(e) => set('ird_number', e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>Financial year start</span>
          <input type="date" value={setup.fy_start} onChange={(e) => set('fy_start', e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>Balance date</span>
          <input type="date" value={setup.balance_date} onChange={(e) => set('balance_date', e.target.value)} required />
        </label>
        <label className={styles.field}>
          <span>GST basis</span>
          <select value={setup.basis} onChange={(e) => set('basis', e.target.value as GstBasis)}>
            {BASES.map((b) => (
              <option key={b.value} value={b.value}>
                {b.label}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span>Filing frequency</span>
          <select value={setup.frequency} onChange={(e) => set('frequency', e.target.value as GstFrequency)}>
            {FREQUENCIES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          {detected?.frequency && detected.frequency !== setup.frequency && (
            <small className={styles.detected}>The returns look {detected.frequency.replace('_', '-')}</small>
          )}
        </label>
        <label className={styles.field}>
          <span>Software</span>
          <input value={setup.software} onChange={(e) => set('software', e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>Currency</span>
          <input value={setup.currency} onChange={(e) => set('currency', e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>GL version / date used for the statements</span>
          <input value={setup.gl_version} onChange={(e) => set('gl_version', e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>GST control account(s)</span>
          <input value={setup.gst_accounts} onChange={(e) => set('gst_accounts', e.target.value)} placeholder="Found automatically if empty" />
          {detected?.gst_accounts?.length ? <small className={styles.detected}>Found: {detected.gst_accounts.join(', ')}</small> : null}
        </label>
        <label className={styles.field}>
          <span>Rounding tolerance (NZD)</span>
          <input value={setup.tolerance} onChange={(e) => set('tolerance', e.target.value)} inputMode="decimal" />
        </label>
        <label className={styles.check}>
          <input type="checkbox" checked={setup.first_year} onChange={(e) => set('first_year', e.target.checked)} />
          First-year entity (no prior-year reconciliation)
        </label>
      </fieldset>
      {(choices.ar_gl_fallback || choices.ap_gl_fallback) && (
        <p className={styles.muted}>
          GL analysis chosen for {[choices.ar_gl_fallback && 'receivables', choices.ap_gl_fallback && 'payables'].filter(Boolean).join(' and ')} (the
          GST-inclusive ageing report is unavailable).{' '}
          <button type="button" className={styles.link} onClick={() => setChoices({})}>
            Use the ageing reports again
          </button>
        </p>
      )}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" size="sm" disabled={running || run.isPending || !link.trim() || !setup.balance_date}>
          {running || run.isPending ? (
            <Loader2 size={14} className={styles.spin} aria-hidden="true" />
          ) : latest ? (
            <RotateCcw size={14} aria-hidden="true" />
          ) : (
            <Play size={14} aria-hidden="true" />
          )}
          {running ? 'Reconciling…' : latest ? 'Run reconciliation again' : 'Run reconciliation'}
        </Button>
        {running && <StopRun jobKey={jobKey} runId={latest?.run_id} />}
      </div>
      {run.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(run.error, 'The reconciliation could not be started.')}
        </p>
      )}
      {latest && latest.status !== 'running' && latest.gst?.paused && Object.keys(latest.gst.paused).length > 0 && (
        <Paused
          paused={latest.gst.paused}
          onRevised={(side) => (side === 'ar' ? arRef : apRef).current?.focus()}
          onGl={(side) => start(side === 'ar' ? { ar_gl_fallback: true } : { ap_gl_fallback: true })}
          busy={running || run.isPending}
        />
      )}
    </form>
  )
}

/** An ageing report without its GST column (or missing): AFIT's message, and the preparer's two choices. */
function Paused({ paused, onRevised, onGl, busy }: {
  paused: GstResult['paused']
  onRevised: (side: 'ar' | 'ap') => void
  onGl: (side: 'ar' | 'ap') => void
  busy: boolean
}) {
  return (
    <>
      {(['ar', 'ap'] as const).map((side) => {
        const p = paused[side]
        if (!p) return null
        const [title, ...rest] = p.message.split('\n\n')
        return (
          <section key={side} className={styles.paused} role="alert" aria-label={`${p.report} paused`}>
            <h3>
              <AlertTriangle size={15} aria-hidden="true" /> {title}
            </h3>
            {rest.map((para, i) => (
              <p key={i}>{para}</p>
            ))}
            <div className={styles.actions}>
              <Button type="button" variant="secondary" size="sm" onClick={() => onRevised(side)}>
                <Upload size={13} aria-hidden="true" /> Upload revised report
              </Button>
              <Button type="button" variant="secondary" size="sm" disabled={busy} onClick={() => onGl(side)}>
                GST-inclusive report unavailable — continue with GL analysis
              </Button>
            </div>
          </section>
        )
      })}
    </>
  )
}

function Result({ run, jobKey }: { run: WpRun; jobKey: string }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (run.status === 'running') {
    return (
      <section className={styles.box} aria-label="Progress">
        <ol className={styles.progress}>
          {run.progress.map((p, i) => (
            <li key={i} data-state={p.state}>
              {p.state === 'done' ? <CheckCircle2 size={13} aria-hidden="true" /> : <Loader2 size={13} className={styles.spin} aria-hidden="true" />}
              {p.label}
            </li>
          ))}
          {run.progress.length === 0 && <li>Starting…</li>}
        </ol>
      </section>
    )
  }
  if (run.status === 'failed') return <p role="alert" className={styles.error}>{run.failure_reason || 'The reconciliation stopped.'}</p>
  const g = run.gst
  if (!g?.bridge) return null
  const b = g.bridge
  const exceptions = g.exceptions ?? []
  const download = async () => {
    setBusy(true)
    setError('')
    try {
      await downloadWorkpaper(run.run_id, fileName(run))
    } catch (e) {
      setError(extractErrorMessage(e, 'The workpaper could not be downloaded.'))
    } finally {
      setBusy(false)
    }
  }
  const rows: [string, string | null, string][] = [
    ['A  GST principal outstanding at balance date', b.A, `current periods ${money(b.A_current)}; prior-year periods ${money(b.A_prior)}`],
    ['B  Receivables GST not yet returned (added)', b.B, g.receivables?.source ?? ''],
    ['C  Payables GST not yet claimed (deducted)', b.C, g.payables?.source ?? ''],
    ['D  Other supported differences', b.D, `${g.adjustments?.length ?? 0} adjustment(s)`],
    ['E  Expected GST control balance', b.E, 'A + B − C + D'],
    ['Reported GL GST control balance', b.reported, ''],
    ['Proposed corrections (not posted)', b.corrections, `${g.corrections?.length ?? 0} proposed`],
    ['F  Adjusted GST control balance', b.F, ''],
    ['Unexplained difference (F − E)', b.unexplained, `tolerance ${money(b.tolerance)}`],
  ]
  return (
    <section className={styles.result} aria-label="Reconciliation result">
      <div className={styles.resultHead}>
        <span className={styles.status} data-tone={STATUS_TONE[g.status ?? ''] ?? ''}>
          {g.status}
        </span>
        <span className={styles.muted}>
          {run.finished_at ? format(parseISO(run.finished_at), 'dd-MM-yy HH:mm') : ''} · {run.requested_by}
          {run.demo ? ' · demo mode (no AI reading)' : ''}
        </span>
        {run.has_workpaper && (
          <Button type="button" variant="primary" size="sm" onClick={download} disabled={busy}>
            <FileSpreadsheet size={14} aria-hidden="true" /> {busy ? 'Preparing…' : 'Download workpaper (Excel)'}
          </Button>
        )}
      </div>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {g.summary && <p className={styles.summary}>{g.summary}</p>}
      <table className={styles.table} aria-label="Bridge">
        <tbody>
          {rows.map(([label, value, note]) => (
            <tr key={label} data-key={label.startsWith('E ') || label.startsWith('F ') || label.startsWith('Unexplained') ? 'total' : ''}>
              <th scope="row">{label}</th>
              <td className={styles.num}>{money(value)}</td>
              <td className={styles.note}>{note}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {exceptions.length > 0 && (
        <details className={styles.box} open={exceptions.some((x) => x.severity === 'blocking')}>
          <summary>
            Exceptions ({g.counts?.blocking ?? 0} blocking, {g.counts?.review ?? 0} to review)
          </summary>
          <ul className={styles.exceptions}>
            {exceptions.map((x) => (
              <li key={x.id} data-severity={x.severity}>
                <span className={styles.tag} data-severity={x.severity}>
                  {x.severity}
                </span>{' '}
                {x.text}
                {x.next_evidence && <small>Next evidence: {x.next_evidence}</small>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {(g.corrections?.length ?? 0) > 0 && (
        <details className={styles.box}>
          <summary>Proposed corrections ({g.corrections!.length}) — not posted</summary>
          <ul className={styles.list}>
            {g.corrections!.map((c) => (
              <li key={c.id}>
                <strong>{c.title}</strong> — GST control effect {money(c.gst_effect)}
                <small>
                  {c.lines.map((l) => (Number(l.debit) ? `Dr ${l.account} ${money(l.debit)}` : `Cr ${l.account} ${money(l.credit)}`)).join('; ')}.{' '}
                  {c.explanation}
                </small>
              </li>
            ))}
          </ul>
        </details>
      )}

      {(g.adjustments?.length ?? 0) > 0 && (
        <details className={styles.box}>
          <summary>Journals, late claims and other adjustments ({g.adjustments!.length})</summary>
          <ul className={styles.list}>
            {g.adjustments!.map((a) => (
              <li key={a.id}>
                {a.category}: {money(a.effect)} — {a.status}
                {a.included === false && <small>Not in the bridge: a candidate for review.</small>}
                {a.subsequent_return && <small>Cleared in the return for {ddmmyy(a.subsequent_return)} (evidence; the year-end difference stands)</small>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {(g.sources?.length ?? 0) > 0 && (
        <details className={styles.box}>
          <summary>Documents read ({g.sources!.length})</summary>
          <ul className={styles.list}>
            {g.sources!.map((s) => (
              <li key={s.sid}>
                {s.sid} {s.name} — {s.kind.replace(/_/g, ' ')}
                {s.error && <small className={styles.error}>{s.error}</small>}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className={styles.muted}>Prepared by the WP Agent for review; sign-off stays with the reviewer. Task {jobKey}.</p>
    </section>
  )
}
