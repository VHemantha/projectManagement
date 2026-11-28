import { BookOpen, Check, CheckCircle2, Info, PenLine, Sparkles } from 'lucide-react'
import { useState } from 'react'

import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type LocalTaxState, type Money, type Statements, money, useAiAgent, useSaveLocalTax } from '@/api/localTax'
import { Button } from '@/design-system'

/** Phase 3 of the Local Tax workflow (AFIT): the rest of a full set of financial statements, every figure the
 * engine's - the statement of changes in equity, the statement of cash flows (indirect), the notes, the accounting
 * policies (standard wording the accountant tailors, with Local_Tax_AI's suggestions). The auditor's or compilation
 * report is its own document (Report.tsx). */

function CheckLine({ check }: { check: { label: string; passed: boolean; difference: string | null } }) {
  return (
    <p className={check.passed ? styles.muted : styles.error} role="status">
      {check.passed ? <CheckCircle2 size={13} aria-hidden="true" /> : <Info size={13} aria-hidden="true" />} {check.label}
      {check.passed ? '' : `: difference ${money(check.difference)}`}
    </p>
  )
}

export function EquityStatement({ st, ye }: { st: Statements; ye: string }) {
  const eq = st.equity
  if (!eq) return <p className={styles.muted}>Income statement only: no statement of changes in equity.</p>
  return (
    <>
      <h3 className={styles.cardTitle}>Statement of Changes in Equity</h3>
      <p className={styles.muted}>For the year ended {ye}</p>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Statement of changes in equity">
          <thead>
            <tr><th /><th className={styles.num}>Stated capital</th><th className={styles.num}>Reserves</th><th className={styles.num}>Retained earnings</th><th className={styles.num}>Total</th></tr>
          </thead>
          <tbody>
            {eq.rows.map((r) => (
              <tr key={r.label} data-kind={r.kind}>
                <th scope="row">{r.label}</th>
                <td className={styles.num}>{money(r.share_capital)}</td><td className={styles.num}>{money(r.reserves)}</td>
                <td className={styles.num}>{money(r.retained_earnings)}</td><td className={styles.num}>{money(r.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CheckLine check={eq.check} />
      {eq.notes.map((n) => <p key={n} className={styles.hint}>{n}</p>)}
    </>
  )
}

export function CashFlowStatement({ st, ye }: { st: Statements; ye: string }) {
  const cf = st.cash_flows
  if (!cf) return <p className={styles.muted}>Income statement only: no statement of cash flows.</p>
  if (!cf.available) return <><h3 className={styles.cardTitle}>Statement of Cash Flows</h3><p className={styles.muted}>{cf.reason}</p></>
  // Last year's column (28 Nov 2026): from last year's statement of cash flows, read with last year's statements.
  const comp = !!cf.has_comparative
  const year = /\d{4}$/.exec(ye)?.[0]
  const cols = comp ? 3 : 2
  const py = (v?: Money) => (comp ? <td className={styles.num}>{money(v ?? '0')}</td> : null)
  return (
    <>
      <h3 className={styles.cardTitle}>Statement of Cash Flows</h3>
      <p className={styles.muted}>For the year ended {ye} (indirect method)</p>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Statement of cash flows">
          <thead><tr><th />{comp ? (
            <><th className={styles.num}>{year ?? 'This year'} LKR</th><th className={styles.num}>{year ? Number(year) - 1 : 'Last year'} LKR</th></>
          ) : <th className={styles.num}>LKR</th>}</tr></thead>
          <tbody>
            {cf.sections.map((s) => [
              <tr key={s.key} data-kind="head"><th colSpan={cols}>{s.title}</th></tr>,
              ...s.rows.map((r) => (
                <tr key={`${s.key}-${r.label}`} data-level="1">
                  <th scope="row">{r.label}{r.note && <span className={styles.hint}> — {r.note}</span>}{r.prior_only && <span className={styles.hint}> — last year only</span>}</th>
                  <td className={styles.num}>{money(r.amount)}</td>{py(r.comparative)}
                </tr>
              )),
              s.subtotal && <tr key={`${s.key}-sub`} data-kind="subtotal"><th scope="row">{s.subtotal.label}</th><td className={styles.num}>{money(s.subtotal.amount)}</td>{py(s.subtotal.comparative)}</tr>,
              ...(s.after ?? []).map((r) => (
                <tr key={`${s.key}-a-${r.label}`} data-level="1">
                  <th scope="row">{r.label}{r.note && <span className={styles.hint}> — {r.note}</span>}</th><td className={styles.num}>{money(r.amount)}</td>{py(r.comparative)}
                </tr>
              )),
              <tr key={`${s.key}-total`} data-kind="subtotal"><th scope="row">{s.total.label}</th><td className={styles.num}>{money(s.total.amount)}</td>{py(s.total.comparative)}</tr>,
            ])}
            <tr data-kind="total"><th scope="row">Net increase / (decrease) in cash</th><td className={styles.num}>{money(cf.net_change)}</td>{py(cf.net_change_comparative)}</tr>
            <tr><th scope="row">Cash and cash equivalents at the start of the year</th><td className={styles.num}>{money(cf.opening_cash)}</td>{py(cf.opening_cash_comparative)}</tr>
            <tr data-kind="total"><th scope="row">Cash and cash equivalents at the end of the year</th><td className={styles.num}>{money(cf.closing_cash)}</td>{py(cf.closing_cash_comparative)}</tr>
          </tbody>
        </table>
      </div>
      {!comp && <p className={styles.hint}>Last year's figures appear once last year's financial statements, with their statement of cash flows, are read (Trial balance › Comparatives from last year).</p>}
      {comp && cf.comparative_source && <p className={styles.hint}>Last year: {cf.comparative_source}, statement of cash flows.</p>}
      <CheckLine check={cf.check} />
      {cf.notes.map((n) => <p key={n} className={styles.hint}>{n}</p>)}
    </>
  )
}

export function NotesView({ taskKey, state }: { taskKey: string; state: LocalTaxState }) {
  const notes = state.statements?.notes ?? []
  const save = useSaveLocalTax(taskKey)
  const [editing, setEditing] = useState<string | null>(null)
  const [text, setText] = useState('')
  return (
    <>
      <h3 className={styles.cardTitle}>Notes to the Financial Statements</h3>
      {notes.filter((n) => n.key !== 'policies').map((n) => (
        <section key={n.key} aria-label={`Note ${n.no}`} style={{ marginBottom: 12 }}>
          <h4 style={{ margin: '6px 0' }}>{n.no}. {n.title}</h4>
          {n.lines && (
            <table className={styles.table} aria-label={n.title}>
              <thead><tr><th>Account</th><th className={styles.num}>Current year</th><th className={styles.num}>Comparative</th></tr></thead>
              <tbody>
                {n.lines.map((ln) => (
                  <tr key={ln.code}><th scope="row">{ln.code} {ln.name}</th><td className={styles.num}>{money(ln.amount)}</td><td className={styles.num}>{money(ln.comparative)}</td></tr>
                ))}
                <tr data-kind="subtotal"><th scope="row">Total</th><td className={styles.num}>{money(n.total)}</td><td className={styles.num}>{money(n.total_comparative)}</td></tr>
              </tbody>
            </table>
          )}
          {n.rows && (
            <table className={styles.table} aria-label={n.title}>
              <tbody>{n.rows.map((r) => <tr key={r.label}><th scope="row">{r.label}</th><td className={styles.num}>{money(r.amount)}</td></tr>)}</tbody>
            </table>
          )}
          {n.text !== undefined && editing !== n.key && (
            <p className={n.to_complete ? styles.hint : undefined} style={{ margin: 0 }}>
              {n.text}{' '}
              {n.editable && <Button size="sm" variant="subtle" onClick={() => { setEditing(n.key); setText(n.to_complete ? '' : n.text ?? '') }}><PenLine size={12} /> Write</Button>}
            </p>
          )}
          {editing === n.key && (
            <div className={styles.field}>
              <textarea rows={3} value={text} aria-label={`${n.title} text`} onChange={(ev) => setText(ev.target.value)} />
              <div className={styles.actions}>
                <Button size="sm" variant="primary" disabled={save.isPending} onClick={() => save.mutate(
                  { data: { note_text: { ...(state.engagement.data.note_text ?? {}), [n.key]: text } }, stage: 'fs' }, { onSuccess: () => setEditing(null) })}>
                  <Check size={12} /> Save
                </Button>
                <Button size="sm" variant="subtle" onClick={() => setEditing(null)}>Cancel</Button>
              </div>
            </div>
          )}
        </section>
      ))}
      {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
    </>
  )
}

export function PoliciesView({ taskKey, state }: { taskKey: string; state: LocalTaxState }) {
  const policies = state.statements?.notes.find((n) => n.key === 'policies')?.policies ?? []
  const save = useSaveLocalTax(taskKey)
  const tailor = useAiAgent<{ policies: { key: string; title: string; text: string }[]; notes: string[] }>(taskKey, 'policies')
  const [editing, setEditing] = useState<string | null>(null)
  const [text, setText] = useState('')
  const custom = state.engagement.data.policy_text ?? {}
  const store = (key: string, value: string, done?: () => void) =>
    save.mutate({ data: { policy_text: { ...custom, [key]: value } }, stage: 'fs' }, { onSuccess: () => done?.() })
  const suggestion = (key: string) => tailor.data?.policies.find((p) => p.key === key)
  return (
    <>
      <h3 className={styles.cardTitle}><BookOpen size={18} aria-hidden="true" /> Significant Accounting Policies</h3>
      <div className={styles.actions}>
        <Button size="sm" variant="secondary" disabled={tailor.isPending || !policies.length} onClick={() => tailor.mutate(undefined)}>
          <Sparkles size={13} /> {tailor.isPending ? 'Local_Tax_AI is drafting…' : 'Tailor the policies with AI'}
        </Button>
        {tailor.isError && <span className={styles.error}>{extractErrorMessage(tailor.error)}</span>}
      </div>
      {policies.map((p) => {
        const s = suggestion(p.key)
        return (
          <section key={p.key} aria-label={p.title} style={{ marginBottom: 12 }}>
            <h4 style={{ margin: '6px 0' }}>{p.title} {p.standard ? <span className={styles.chip}>Standard wording</span> : <span className={styles.chip} data-status="approved">Tailored</span>}</h4>
            {editing === p.key ? (
              <div className={styles.field}>
                <textarea rows={4} value={text} aria-label={`${p.title} policy`} onChange={(ev) => setText(ev.target.value)} />
                <div className={styles.actions}>
                  <Button size="sm" variant="primary" disabled={save.isPending} onClick={() => store(p.key, text, () => setEditing(null))}><Check size={12} /> Save</Button>
                  <Button size="sm" variant="subtle" onClick={() => setEditing(null)}>Cancel</Button>
                </div>
              </div>
            ) : (
              <p style={{ margin: 0 }}>{p.text} <Button size="sm" variant="subtle" onClick={() => { setEditing(p.key); setText(p.text) }}><PenLine size={12} /> Edit</Button>
                {!p.standard && <Button size="sm" variant="subtle" onClick={() => store(p.key, '')}>Use the standard wording</Button>}</p>
            )}
            {s && s.text !== p.text && (
              <div className={styles.card} style={{ background: 'var(--tf-surface-sunken)' }} aria-label={`AI suggestion for ${p.title}`}>
                <span className={styles.hint}><Sparkles size={12} /> Local_Tax_AI suggests (check the [bracketed] items):</span>
                <p style={{ margin: 0 }}>{s.text}</p>
                <Button size="sm" variant="secondary" disabled={save.isPending} onClick={() => store(p.key, s.text)}>Accept</Button>
              </div>
            )}
          </section>
        )
      })}
      {tailor.data?.notes.map((n) => <p key={n} className={styles.hint}>{n}</p>)}
      {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
    </>
  )
}
