import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, CheckCircle2, FileText, FolderOpen, HelpCircle, Link2, RefreshCw, Sparkles, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'

import styles from './LocalTax.module.css'
import { PriorYearComparatives, StoryTrialBalance } from './TbSources'
import { TbUpload } from './TbUpload'
import { extractErrorMessage } from '@/api/errors'
import { useUploadAttachment } from '@/api/issues'
import {
  DOC_KINDS,
  type DocFlag,
  type DocSource,
  type Suggestion,
  money,
  useDecideSuggestion,
  useDocuments,
  useDriveAccount,
  useLinkDrive,
  usePrefill,
  useResolveFlag,
  useSyncDrive,
  type LocalTaxState,
} from '@/api/localTax'
import { Button, Skeleton } from '@/design-system'

const FIELD_LABELS: Record<string, string> = {
  legal_name: 'Legal name', tin: 'TIN', nic_or_reg: 'Registration / NIC no.', address: 'Address', activity: 'Nature of business', fy_end: 'Financial year end',
  entity_type: 'Entity type',
}
const GROUPS: [string, string][] = [['field', 'Client details'], ['trial_balance', 'Trial balance'], ['bank_balance', 'Bank balances'], ['income', 'Income'],
  ['payments', 'Tax credits & payments'], ['assets', 'Assets'], ['liabilities', 'Liabilities']]
const FLAG_ICON = { missing: <HelpCircle size={14} aria-hidden="true" />, unclear: <AlertTriangle size={14} aria-hidden="true" />,
  inconsistent: <AlertTriangle size={14} aria-hidden="true" /> }

/** Client Info > Supporting Documents (Team 3 > Local cards): the trial balance and the client's other documents,
 * uploaded here or copied from the client's Google Drive folder once it is shared with TASKO. Local_Tax_AI reads
 * them and pre-fills the client info: every value shows where it came from, and is used only once the accountant
 * confirms it (as it is, or edited). What is missing, unclear or inconsistent across the documents is flagged. */
export function SupportingDocuments({ taskKey, isCompany, tbCount, state }: { taskKey: string; isCompany: boolean; tbCount: number; state?: LocalTaxState }) {
  const { data, isLoading, error } = useDocuments(taskKey)
  const queryClient = useQueryClient()
  const upload = useUploadAttachment(taskKey)
  const prefill = usePrefill(taskKey)
  const files = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState<string | null>(null)

  const uploadAll = async (list: FileList) => {
    for (const f of Array.from(list)) {
      setUploading(f.name)
      try { await upload.mutateAsync(f) } catch { /* shown below */ }
    }
    setUploading(null)
    void queryClient.invalidateQueries({ queryKey: ['local-tax', taskKey, 'documents'] })
  }
  if (isLoading) return <Skeleton height={160} />
  if (!data) return <p className={styles.error}>{extractErrorMessage(error, 'The documents could not be loaded.')}</p>
  const unread = data.documents.filter((d) => !d.read_at).length
  const pending = data.suggestions.filter((s) => s.status === 'pending')
  const decided = data.suggestions.filter((s) => s.status !== 'pending')
  const open = data.flags.filter((f) => f.status === 'open')
  const names = Object.fromEntries(data.documents.map((d) => [d.id, d.name]))

  return (
    <div className={styles.side} style={{ gap: 12 }}>
      <p className={styles.hint} style={{ margin: 0 }}>
        Upload the trial balance and the client&apos;s supporting documents — bank statements, bank balance confirmations, prior returns, certificates,
        registers — or link the client&apos;s Google Drive folder. Local_Tax_AI reads them and pre-fills the client info; you verify each value against its source
        before it flows into the financial statements and the tax computation.
      </p>

      {!isCompany && (
        <p className={styles.hint} style={{ margin: 0 }}>
          A trial balance is optional for an individual: upload one when the business keeps books (a sole proprietor), and the financial statements are
          prepared from it.
        </p>
      )}
      <TbUpload taskKey={taskKey} accounts={tbCount} />
      {state && <StoryTrialBalance taskKey={taskKey} state={state} />}
      {state && (isCompany || tbCount > 0) && <PriorYearComparatives taskKey={taskKey} state={state} />}

      <section className={styles.card} aria-label="Upload supporting documents">
        <div className={styles.actions}>
          <strong><Upload size={15} aria-hidden="true" /> Supporting documents</strong>
          <span className={styles.spacer} />
          <input ref={files} type="file" multiple hidden aria-label="Supporting documents files"
            onChange={(ev) => { if (ev.target.files?.length) void uploadAll(ev.target.files); ev.target.value = '' }} />
          <Button size="sm" variant="secondary" disabled={!!uploading} onClick={() => files.current?.click()}>
            <Upload size={13} /> {uploading ? `Uploading ${uploading}…` : 'Upload documents'}
          </Button>
        </div>
        {upload.isError && <p className={styles.error}>{extractErrorMessage(upload.error)}</p>}
      </section>

      <DriveFolder taskKey={taskKey} url={data.drive.url} syncedAt={data.drive.synced_at} />

      <section className={styles.card} aria-label="Documents">
        <div className={styles.actions}>
          <strong><FileText size={15} aria-hidden="true" /> Documents ({data.documents.length})</strong>
          <span className={styles.spacer} />
          <Button size="sm" variant="primary" disabled={prefill.isPending || !data.documents.length}
            onClick={() => prefill.mutate({ names })}>
            <Sparkles size={13} /> {unread ? `Read ${unread} new document${unread === 1 ? '' : 's'} with AI & pre-fill` : 'Check the documents again'}
          </Button>
          {data.documents.length > 0 && unread === 0 && (
            <Button size="sm" variant="subtle" disabled={prefill.isPending} onClick={() => prefill.mutate({ again: true, names })}>Read all again</Button>
          )}
        </div>
        {prefill.progress && (
          <div role="status" aria-label="Reading progress">
            <span className={styles.bar}><span style={{ width: `${prefill.progress.total ? (prefill.progress.done / prefill.progress.total) * 100 : 100}%` }} /></span>
            <span className={styles.muted}>
              {prefill.progress.done < prefill.progress.total
                ? `Local_Tax_AI is reading ${prefill.progress.done + 1} of ${prefill.progress.total}: ${prefill.progress.current}`
                : 'Checking the documents against each other and the client info…'}
            </span>
          </div>
        )}
        {prefill.isError && <p className={styles.error}>{extractErrorMessage(prefill.error)}</p>}
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="Supporting documents">
            <thead><tr><th>Document</th><th>From</th><th>What it is</th><th>Read</th></tr></thead>
            <tbody>
              {data.documents.map((d) => (
                <tr key={d.id}>
                  <td><a href={d.url} target="_blank" rel="noreferrer">{d.name}</a></td>
                  <td>{d.origin === 'drive' ? <span className={styles.chip}><FolderOpen size={11} /> Drive{d.drive_path ? ` · ${d.drive_path}` : ''}</span> : 'Uploaded'}</td>
                  <td>{d.kind ? DOC_KINDS[d.kind] ?? d.kind : '—'}{d.summary && <div className={styles.muted}>{d.summary}</div>}</td>
                  <td>{d.read_error ? <span className={styles.error}>{d.read_error}</span> : d.read_at ? <><CheckCircle2 size={13} aria-hidden="true" /> Read</> : 'Not yet'}</td>
                </tr>
              ))}
              {!data.documents.length && <tr><td colSpan={4} className={styles.muted}>No documents yet: upload them or link the client&apos;s Drive folder.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {open.length > 0 && <Flags taskKey={taskKey} flags={open} />}
      {pending.length > 0 && <Review taskKey={taskKey} suggestions={pending} />}
      {decided.length > 0 && (
        <details className={styles.card}>
          <summary>Verified from the documents ({decided.length})</summary>
          <ul className={styles.muted}>
            {decided.map((s) => (
              <li key={s.id}>{s.status === 'confirmed' ? 'Confirmed' : 'Rejected'}{s.edited ? ' (edited)' : ''}: {describe(s)} — {sourcesText(s.sources)} — {s.decided_by}</li>
            ))}
          </ul>
        </details>
      )}
      {data.flags.some((f) => f.status === 'resolved') && (
        <details className={styles.card}>
          <summary>Resolved issues ({data.flags.filter((f) => f.status === 'resolved').length})</summary>
          <ul className={styles.muted}>
            {data.flags.filter((f) => f.status === 'resolved').map((f) => <li key={f.id}>{f.text} — {f.resolution} ({f.resolved_by})</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}

function DriveFolder({ taskKey, url, syncedAt }: { taskKey: string; url: string; syncedAt: string | null }) {
  const account = useDriveAccount()
  const link = useLinkDrive(taskKey)
  const sync = useSyncDrive(taskKey)
  const [text, setText] = useState(url)
  const [editing, setEditing] = useState(!url)
  const email = account.data?.account_email
  const err = (link.error ?? sync.error) as { response?: { data?: { account_email?: string } } } | null
  return (
    <section className={styles.card} aria-label="Client's Google Drive folder">
      <strong><FolderOpen size={15} aria-hidden="true" /> Client&apos;s Google Drive folder</strong>
      <ol className={styles.muted} style={{ margin: '4px 0', paddingLeft: 18 }}>
        <li>In Google Drive, open the client&apos;s folder › <b>Share</b> › add <b>{email || 'TASKO’s service account'}</b> as <b>Viewer</b>.</li>
        <li>Paste the folder&apos;s link here. TASKO copies its documents to this card (read-only — nothing is changed in Drive).</li>
        <li>When the client adds documents, press <b>Sync now</b>, then read them with AI.</li>
      </ol>
      {account.data && !account.data.configured && <p className={styles.hint}>{account.data.detail}</p>}
      {editing ? (
        <div className={styles.actions}>
          <input aria-label="Google Drive folder link" style={{ flex: 1, minWidth: 240 }} placeholder="https://drive.google.com/drive/folders/…" value={text}
            onChange={(ev) => setText(ev.target.value)} />
          <Button size="sm" variant="primary" disabled={link.isPending || !text.trim()}
            onClick={() => link.mutate(text.trim(), { onSuccess: () => { setEditing(false); sync.mutate() } })}>
            <Link2 size={13} /> {link.isPending ? 'Checking access…' : 'Link folder'}
          </Button>
          {url && <Button size="sm" variant="subtle" onClick={() => setEditing(false)}>Cancel</Button>}
        </div>
      ) : (
        <div className={styles.actions}>
          <a href={url} target="_blank" rel="noreferrer" className={styles.chip}><FolderOpen size={12} /> Open the folder</a>
          <span className={styles.muted}>{syncedAt ? `Last synced ${new Date(syncedAt).toLocaleString('en-GB')}` : 'Not synced yet'}</span>
          <span className={styles.spacer} />
          <Button size="sm" variant="secondary" disabled={sync.isPending} onClick={() => sync.mutate()}>
            <RefreshCw size={13} /> {sync.isPending ? 'Copying documents…' : 'Sync now'}
          </Button>
          <Button size="sm" variant="subtle" onClick={() => setEditing(true)}>Change</Button>
        </div>
      )}
      {sync.data?.sync && (
        <p className={styles.muted} role="status" style={{ margin: 0 }}>
          {sync.data.sync.added} new, {sync.data.sync.updated} changed, {sync.data.sync.unchanged} unchanged
          {sync.data.sync.left ? ` — ${sync.data.sync.left} more: sync again` : ''}
          {sync.data.sync.skipped.map((s) => ` · ${s.name}: ${s.reason}`).join('')}
        </p>
      )}
      {(link.isError || sync.isError) && (
        <p className={styles.error}>
          {extractErrorMessage(link.error ?? sync.error)}
          {err?.response?.data?.account_email && !extractErrorMessage(link.error ?? sync.error).includes(err.response.data.account_email)
            ? ` Share it (Viewer) with ${err.response.data.account_email}.` : ''}
        </p>
      )}
    </section>
  )
}

function sourcesText(sources: DocSource[]) {
  return sources.map((s) => `${s.document}${s.cite ? ` (${s.cite})` : ''}`).join('; ')
}

function Sources({ sources }: { sources: DocSource[] }) {
  return (
    <span className={styles.hint}>
      Source: {sources.map((s, i) => <span key={i}>{i > 0 && '; '}<FileText size={11} aria-hidden="true" /> {s.document}{s.cite ? ` — ${s.cite}` : ''}</span>)}
    </span>
  )
}

type Line = { category?: string; type?: string; kind?: string; description?: string; reference?: string; amount?: string; value?: string; date?: string }

function describe(s: Suggestion): string {
  if (s.target.startsWith('field:')) return `${FIELD_LABELS[s.target.slice(6)] ?? s.target}: ${String(s.value)}`
  if (s.target === 'trial_balance') return `Trial balance (${(s.value as { lines: unknown[] }).lines.length} accounts)`
  if (s.target === 'bank_balance') {
    const b = s.value as { bank: string; account: string; date: string; balance: string }
    return `${b.bank} ${b.account} at ${b.date}: ${money(b.balance)}`
  }
  const v = s.value as Line
  return `${(v.category ?? v.type ?? v.kind ?? '').replace(/_/g, ' ')} ${v.description ?? v.reference ?? ''}: ${money(v.amount ?? v.value)}`
}

function Review({ taskKey, suggestions }: { taskKey: string; suggestions: Suggestion[] }) {
  const decide = useDecideSuggestion(taskKey)
  return (
    <section className={styles.card} aria-label="Values to verify">
      <h3 className={styles.cardTitle}><Sparkles size={16} aria-hidden="true" /> To verify ({suggestions.length}) — found by Local_Tax_AI</h3>
      <p className={styles.hint} style={{ margin: 0 }}>Check each value against its source. Edit it if needed, then confirm: only confirmed values are used.</p>
      {GROUPS.map(([g, title]) => {
        const items = suggestions.filter((s) => (g === 'field' ? s.target.startsWith('field:') : s.target === g))
        if (!items.length) return null
        return (
          <div key={g}>
            <h4 style={{ margin: '8px 0 4px' }}>{title}</h4>
            {items.map((s) => <SuggestionRow key={s.id} s={s} busy={decide.isPending} onDecide={(decision, value) => decide.mutate({ id: s.id, decision, value })} />)}
          </div>
        )
      })}
      {decide.isError && <p className={styles.error}>{extractErrorMessage(decide.error)}</p>}
    </section>
  )
}

function SuggestionRow({ s, busy, onDecide }: { s: Suggestion; busy: boolean; onDecide: (d: 'confirm' | 'reject', value?: unknown) => void }) {
  const isField = s.target.startsWith('field:')
  const isTb = s.target === 'trial_balance'
  const isBank = s.target === 'bank_balance'
  const v = s.value as Line & { balance?: string }
  const amountKey: 'amount' | 'value' | 'balance' = isBank ? 'balance' : v.amount !== undefined ? 'amount' : 'value'
  const [text, setText] = useState(isField ? String(s.value) : String((v as Record<string, unknown>)[amountKey] ?? ''))
  const original = isField ? String(s.value) : String((v as Record<string, unknown>)[amountKey] ?? '')
  const edited = !isTb && text !== original
  const value = !edited ? undefined : isField ? text : { ...(s.value as object), [amountKey]: text }
  return (
    <div className={styles.actions} style={{ alignItems: 'flex-start', borderBottom: '1px solid var(--tf-border)', padding: '6px 0' }} aria-label={describe(s)}>
      <div style={{ flex: 1, minWidth: 220 }}>
        <div>{isField ? FIELD_LABELS[s.target.slice(6)] : describe(s)}</div>
        <Sources sources={s.sources} />
        {isTb && (
          <details>
            <summary className={styles.hint}>Show the accounts</summary>
            <table className={styles.table}>
              <tbody>
                {(s.value as { lines: { code: string; name: string; amount: string; comparative: string }[] }).lines.map((ln, i) => (
                  <tr key={i}><td>{ln.code}</td><td>{ln.name}</td><td className={styles.num}>{money(ln.amount)}</td><td className={styles.num}>{money(ln.comparative)}</td></tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </div>
      {!isTb && (
        <input aria-label={`Value for ${describe(s)}`} value={text} onChange={(ev) => setText(ev.target.value)} style={{ maxWidth: isField ? 320 : 160 }}
          inputMode={isField ? undefined : 'decimal'} />
      )}
      <Button size="sm" variant="primary" disabled={busy} onClick={() => onDecide('confirm', value)}>
        <Check size={12} /> {edited ? 'Confirm edited' : isTb ? 'Use as the trial balance' : 'Confirm'}
      </Button>
      <Button size="sm" variant="subtle" disabled={busy} onClick={() => onDecide('reject')}><X size={12} /> Reject</Button>
    </div>
  )
}

function Flags({ taskKey, flags }: { taskKey: string; flags: DocFlag[] }) {
  const resolve = useResolveFlag(taskKey)
  const [notes, setNotes] = useState<Record<number, string>>({})
  return (
    <section className={styles.card} aria-label="Issues to resolve" style={{ borderColor: 'var(--tf-warning, #b54708)' }}>
      <h3 className={styles.cardTitle}><AlertTriangle size={16} aria-hidden="true" /> To resolve ({flags.length}) — missing, unclear or inconsistent</h3>
      {flags.map((f) => (
        <div key={f.id} style={{ borderBottom: '1px solid var(--tf-border)', padding: '6px 0' }} aria-label={f.text}>
          <div><span className={styles.chip} data-tone="review">{FLAG_ICON[f.kind]} {f.kind[0].toUpperCase() + f.kind.slice(1)}</span> {f.text}</div>
          {f.sources.length > 0 && <Sources sources={f.sources} />}
          <div className={styles.actions}>
            <input aria-label="How it was resolved" placeholder="How it was resolved (e.g. client sent page 3; TIN per registration certificate)"
              value={notes[f.id] ?? ''} onChange={(ev) => setNotes({ ...notes, [f.id]: ev.target.value })} style={{ flex: 1, minWidth: 220 }} />
            <Button size="sm" variant="secondary" disabled={resolve.isPending || (notes[f.id] ?? '').trim().length < 3}
              onClick={() => resolve.mutate({ id: f.id, resolution: notes[f.id] })}>
              <CheckCircle2 size={12} /> Resolved
            </Button>
          </div>
        </div>
      ))}
      {resolve.isError && <p className={styles.error}>{extractErrorMessage(resolve.error)}</p>}
    </section>
  )
}
