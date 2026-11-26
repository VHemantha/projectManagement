import { Check, Download, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import styles from './LocalTax.module.css'
import { HEADINGS } from './headings'
import { StatusChip } from './Shared'
import { extractErrorMessage } from '@/api/errors'
import {
  type Adjustment,
  type LocalTaxState,
  downloadLocalTax,
  money,
  useDecideAdjustment,
  useProposeAdjustment,
  useReverseJournal,
} from '@/api/localTax'
import { Button } from '@/design-system'

interface Line { code: string; name: string; heading: string; debit: string; credit: string }
const blank = (): Line => ({ code: '', name: '', heading: '', debit: '', credit: '' })
const num = (v: string) => Number(String(v).replace(/,/g, '')) || 0

/** The journal register (AFIT, 24 Nov 2026): journal entries entered with debit and credit columns, numbered (JE-001…),
 * dated and explained; a reviewer approves each one before it reaches the trial balance and the financial statements; an
 * approved journal is never edited or deleted - it is reversed by a reversing journal, so the whole trail stays. The
 * depreciation journal (JE-DEP) is posted from the depreciation schedule. */
export function JournalRegister({ taskKey, state }: { taskKey: string; state: LocalTaxState }) {
  const reg = state.journals
  const tb = (state.financials?.tb ?? []).filter((ln) => !ln.edit)  // not the statement edits waiting to be posted
  return (
    <>
      <div className={styles.actions}>
        <h3 className={styles.cardTitle} style={{ margin: 0 }}>Journal entries</h3>
        <span className={styles.muted}>{reg ? `${reg.approved} approved · ${reg.proposed} awaiting approval` : ''}</span>
        <span className={styles.spacer} />
        <Button size="sm" variant="subtle" onClick={() => void downloadLocalTax(taskKey, 'journals', 'xlsx')}><Download size={13} /> Register (Excel)</Button>
        <Button size="sm" variant="subtle" onClick={() => void downloadLocalTax(taskKey, 'journals', 'pdf')}><Download size={13} /> Register (PDF)</Button>
      </div>
      <p className={styles.hint} style={{ margin: 0 }}>
        A journal reaches the trial balance and the financial statements once a reviewer approves it. An approved journal is reversed, never edited or deleted.
      </p>
      <JournalForm taskKey={taskKey} accounts={tb} fyEnd={state.engagement.fy_end} />
      <JournalList taskKey={taskKey} state={state} journals={reg?.journals ?? []} />
      {(reg?.accounts.length ?? 0) > 0 && (
        <details>
          <summary>Accounts changed by approved journals ({reg?.accounts.length})</summary>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Accounts changed by journals">
              <thead><tr><th>Code</th><th>Account</th><th className={styles.num}>Trial balance</th><th className={styles.num}>Journals</th><th className={styles.num}>Adjusted</th></tr></thead>
              <tbody>
                {reg?.accounts.map((a) => (
                  <tr key={a.code}><td>{a.code}</td><td>{a.name}</td><td className={styles.num}>{money(a.original)}</td>
                    <td className={styles.num}>{money(a.journals)}</td><td className={styles.num}><strong>{money(a.adjusted)}</strong></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </>
  )
}

function JournalForm({ taskKey, accounts, fyEnd }: { taskKey: string; accounts: { code: string; name: string; heading: string }[]; fyEnd: string | null }) {
  const propose = useProposeAdjustment(taskKey)
  const [lines, setLines] = useState<Line[]>([blank(), blank()])
  const [reason, setReason] = useState('')
  const [label, setLabel] = useState('')
  const [date, setDate] = useState(fyEnd ?? '')
  const byCode = useMemo(() => new Map(accounts.map((a) => [a.code, a])), [accounts])
  const byName = useMemo(() => new Map(accounts.map((a) => [a.name.trim().toLowerCase(), a])), [accounts])
  const dr = lines.reduce((s, l) => s + num(l.debit), 0)
  const cr = lines.reduce((s, l) => s + num(l.credit), 0)
  const used = lines.filter((l) => l.code && (num(l.debit) || num(l.credit)))
  const unknown = used.filter((l) => !byCode.has(l.code) && (!l.name || !l.heading))
  const ok = used.length >= 2 && Math.abs(dr - cr) < 0.005 && dr > 0 && reason.trim().length >= 5 && !unknown.length
  const submit = () =>
    propose.mutate({
      kind: 'journal', label, reason, entry_date: date || undefined,
      lines: used.map((l) => ({ code: l.code, name: byCode.get(l.code)?.name ?? l.name, heading: byCode.get(l.code)?.heading ?? l.heading,
        amount: String(num(l.debit) - num(l.credit)) })),
    }, { onSuccess: () => (setLines([blank(), blank()]), setReason(''), setLabel('')) })
  return (
    <details open>
      <summary>New journal entry</summary>
      <div className={styles.formGrid}>
        <label className={styles.field}><span>Date</span><input type="date" value={date} onChange={(ev) => setDate(ev.target.value)} /></label>
        <label className={styles.field}><span>Title</span><input value={label} placeholder="e.g. Accrue audit fee" onChange={(ev) => setLabel(ev.target.value)} /></label>
        <label className={`${styles.field} ${styles.wide}`}><span>Narration (why) *</span>
          <input value={reason} placeholder="What the entry corrects or records, and the evidence" onChange={(ev) => setReason(ev.target.value)} /></label>
      </div>
      <datalist id={`accounts-${taskKey}`}>
        {accounts.map((a) => <option key={a.code} value={a.code}>{a.name}</option>)}
      </datalist>
      <datalist id={`account-names-${taskKey}`}>
        {accounts.map((a) => <option key={a.code} value={a.name}>{a.code}</option>)}
      </datalist>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Journal lines">
          <thead><tr><th>Account</th><th>Name / new account</th><th className={styles.num}>Debit</th><th className={styles.num}>Credit</th><th /></tr></thead>
          <tbody>
            {lines.map((l, i) => {
              const set = (p: Partial<Line>) => setLines(lines.map((x, n) => (n === i ? { ...x, ...p } : x)))
              const known = byCode.get(l.code)
              return (
                <tr key={i}>
                  <td className={styles.cell}><input aria-label="Account code" list={`accounts-${taskKey}`} placeholder="Code" value={l.code} onChange={(ev) => set({ code: ev.target.value })} /></td>
                  <td className={styles.cell}>
                    {/* The account found by its name as well as its code (AFIT, 26 Nov 2026): picking a name fills the code;
                        a name the trial balance doesn't have is a new account, given a code and a heading. */}
                    <span className={styles.actions} style={{ flexWrap: 'nowrap' }}>
                      <input aria-label="Account name" list={`account-names-${taskKey}`} placeholder="Search by name…"
                        value={known ? known.name : l.name}
                        onChange={(ev) => {
                          const v = ev.target.value
                          const match = byName.get(v.trim().toLowerCase())
                          set(match ? { code: match.code, name: match.name, heading: match.heading } : { name: v, code: known ? '' : l.code })
                        }} />
                      {!known && l.code && (
                        <select aria-label="New account heading" value={l.heading} onChange={(ev) => set({ heading: ev.target.value })}>
                          <option value="">Heading…</option>
                          {HEADINGS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                        </select>
                      )}
                    </span>
                    {!known && l.name && !l.code && <span className={styles.hint}>New account: give it a code.</span>}
                  </td>
                  <td className={styles.cell}><input aria-label="Debit" inputMode="decimal" value={l.debit} onChange={(ev) => set({ debit: ev.target.value, credit: ev.target.value ? '' : l.credit })} /></td>
                  <td className={styles.cell}><input aria-label="Credit" inputMode="decimal" value={l.credit} onChange={(ev) => set({ credit: ev.target.value, debit: ev.target.value ? '' : l.debit })} /></td>
                  <td>{lines.length > 2 && <Button size="sm" variant="subtle" aria-label="Remove line" onClick={() => setLines(lines.filter((_, n) => n !== i))}><Trash2 size={13} /></Button>}</td>
                </tr>
              )
            })}
            <tr><th scope="row" colSpan={2}>Total</th><td className={styles.num}>{money(dr)}</td><td className={styles.num}>{money(cr)}</td><td /></tr>
          </tbody>
        </table>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => setLines([...lines, blank()])}><Plus size={13} /> Line</Button>
        <span className={Math.abs(dr - cr) < 0.005 ? styles.muted : styles.error}>{Math.abs(dr - cr) < 0.005 ? 'Balanced' : `Out of balance by ${money(dr - cr)}`}</span>
        {unknown.length > 0 && <span className={styles.error}>Give a name and heading for each new account.</span>}
        <span className={styles.spacer} />
        <Button size="sm" variant="primary" disabled={!ok || propose.isPending} onClick={submit}>Propose for approval</Button>
      </div>
      {propose.isError && <p className={styles.error}>{extractErrorMessage(propose.error)}</p>}
    </details>
  )
}

function JournalList({ taskKey, state, journals }: { taskKey: string; state: LocalTaxState; journals: Adjustment[] }) {
  const decide = useDecideAdjustment(taskKey)
  const reverse = useReverseJournal(taskKey)
  const [reversing, setReversing] = useState<number | null>(null)
  const [why, setWhy] = useState('')
  const refOf = new Map(journals.map((j) => [j.id, j.ref]))
  if (!journals.length) return <p className={styles.muted}>No journal entries yet.</p>
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} aria-label="Journal register">
        <thead><tr><th>Ref</th><th>Date</th><th>Journal</th><th className={styles.num}>Debit</th><th className={styles.num}>Credit</th><th>Status</th><th /></tr></thead>
        <tbody>
          {[...journals].reverse().map((j) => {
            const dr = j.lines.reduce((s, l) => s + Math.max(Number(l.amount), 0), 0)
            const canReverse = j.status === 'approved' && !j.managed && !(j.reversed_by?.length) && j.lines.length > 0
            return (
              <tr key={j.id}>
                <td><strong>{j.ref || '—'}</strong></td>
                <td>{j.entry_date ?? ''}</td>
                <th scope="row" style={{ fontWeight: 400 }}>
                  <strong>{j.label}</strong>{j.reverses ? <span className={styles.muted}> (reverses {refOf.get(j.reverses)})</span> : null}
                  {j.managed && <span className={styles.chip} style={{ marginLeft: 6 }}>From the depreciation schedule</span>}
                  <div className={styles.muted}>{j.reason}</div>
                  <table className={styles.table} style={{ marginTop: 4 }}>
                    <tbody>
                      {j.lines.map((l, n) => {
                        const a = Number(l.amount)
                        return (
                          <tr key={n}><td style={{ paddingLeft: a < 0 ? 24 : 4 }}>{l.code} {l.name}</td>
                            <td className={styles.num}>{a > 0 ? money(a) : ''}</td><td className={styles.num}>{a < 0 ? money(-a) : ''}</td></tr>
                        )
                      })}
                    </tbody>
                  </table>
                  <div className={styles.muted}>Proposed by {j.created_by}{j.decided_by ? ` · ${j.status} by ${j.decided_by}` : ''}{j.history.length ? ` · ${j.history.length} earlier version(s)` : ''}</div>
                  {reversing === j.id && (
                    <div className={styles.actions} style={{ marginTop: 6 }}>
                      <input aria-label="Why reverse" placeholder="Why it is reversed" value={why} onChange={(ev) => setWhy(ev.target.value)} style={{ flex: 1 }} />
                      <Button size="sm" variant="primary" disabled={why.trim().length < 5 || reverse.isPending}
                        onClick={() => reverse.mutate({ id: j.id, reason: why }, { onSuccess: () => (setReversing(null), setWhy('')) })}>Propose reversal</Button>
                      <Button size="sm" variant="subtle" onClick={() => setReversing(null)}>Cancel</Button>
                    </div>
                  )}
                </th>
                <td className={styles.num}>{money(dr)}</td>
                <td className={styles.num}>{money(dr)}</td>
                <td><StatusChip status={j.status} /></td>
                <td>
                  <div className={styles.rowActions}>
                    {j.status === 'proposed' && state.engagement.can_approve && (
                      <>
                        <Button size="sm" variant="primary" aria-label={`Approve ${j.ref}`} disabled={decide.isPending}
                          onClick={() => decide.mutate({ id: j.id, decision: 'approve' })}><Check size={13} /> Approve</Button>
                        <Button size="sm" variant="subtle" aria-label={`Reject ${j.ref}`} disabled={decide.isPending}
                          onClick={() => decide.mutate({ id: j.id, decision: 'reject' })}><X size={13} /> Reject</Button>
                      </>
                    )}
                    {canReverse && <Button size="sm" variant="subtle" aria-label={`Reverse ${j.ref}`} onClick={() => setReversing(j.id)}><RotateCcw size={13} /> Reverse</Button>}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {(decide.isError || reverse.isError) && <p className={styles.error}>{extractErrorMessage(decide.error ?? reverse.error)}</p>}
    </div>
  )
}
