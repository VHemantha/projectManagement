import { BookOpen, CheckCircle2, ChevronLeft, FileSearch, PenLine, ShieldCheck, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type ReviewedRule, type RuleRegister, useReviewField, useReviewRule, useRuleCheck, useRuleRegister } from '@/api/localTax'
import { Button, Skeleton } from '@/design-system'

/** Phase 4 of the Local Tax workflow (AFIT): the tax professional's review of a year's rules and of the draft
 * return's field references. Every rule shows its value, the law it rests on and whether it has been validated;
 * a validator (staff or the "Local tax rule validators" group) validates it, corrects its value with the reference
 * relied on, or withdraws a review - every review is kept. Local_Tax_AI can read a law document for a rule and say
 * whether it agrees; it only assists. Until a rule is validated, approving figures on it needs an acknowledgement. */
export function RulesReviewPage() {
  const { ya = '2024-25' } = useParams<{ ya: string }>()
  const year = ya.replace('-', '/')
  const navigate = useNavigate()
  const { data, isLoading, isError, error } = useRuleRegister(year)
  const [tab, setTab] = useState<'rules' | 'fields'>('rules')
  if (isLoading) return <div className={styles.page}><Skeleton height={200} /></div>
  if (isError || !data) return <div className={styles.page}><p className={styles.error}>{extractErrorMessage(error, 'The rules could not be loaded.')}</p></div>
  const pct = data.total ? Math.round((data.validated / data.total) * 100) : 0
  return (
    <div className={styles.page}>
      <div className={styles.clientBar}>
        <button type="button" className={styles.chip} onClick={() => navigate(-1)} aria-label="Back"><ChevronLeft size={16} /></button>
        <div>
          <h1 className={styles.clientName} style={{ color: 'var(--tf-primary)' }}><ShieldCheck size={20} aria-hidden="true" /> Tax rules review — YA {year}</h1>
          <p className={styles.clientMeta}>{data.legislation}</p>
        </div>
        <span className={styles.spacer} />
        <div style={{ minWidth: 200 }}>
          <p className={styles.clientMeta}>{data.validated} of {data.total} rules validated</p>
          <span className={styles.bar}><span style={{ width: `${pct}%` }} /></span>
        </div>
      </div>
      <p className={styles.validation}>{data.status}</p>
      {!data.can_validate && (
        <p className={styles.hint}>Only a tax rule validator (staff or the “Local tax rule validators” group) can validate or correct a rule. You can see every rule and its review history.</p>
      )}
      <div className={styles.actions} role="tablist" aria-label="Review">
        <Button variant={tab === 'rules' ? 'primary' : 'secondary'} role="tab" aria-selected={tab === 'rules'} onClick={() => setTab('rules')}><BookOpen size={14} /> Rules</Button>
        <Button variant={tab === 'fields' ? 'primary' : 'secondary'} role="tab" aria-selected={tab === 'fields'} onClick={() => setTab('fields')}>Return field references</Button>
      </div>
      {tab === 'rules' ? (
        <div className={styles.card}>
          {data.rules.map((r) => <RuleRow key={r.rule} year={year} rule={r} canValidate={data.can_validate} />)}
        </div>
      ) : (
        <FieldRefs year={year} data={data} />
      )}
      <p className={styles.hint}><Link to="/">Back to TASKO</Link></p>
    </div>
  )
}

const show = (v: unknown) => {
  if (v === null || v === undefined) return 'No value — to be entered'
  if (Array.isArray(v)) return v.map((b) => `${b[0] === null ? 'balance' : Number(b[0]).toLocaleString()} @ ${Number(b[1]) * 100}%`).join(' · ')
  if (typeof v === 'number') return v < 1 ? `${+(v * 100).toFixed(4)}%` : v.toLocaleString()
  return String(v)
}

function RuleRow({ year, rule, canValidate }: { year: string; rule: ReviewedRule; canValidate: boolean }) {
  const review = useReviewRule(year)
  const check = useRuleCheck(year)
  const [mode, setMode] = useState<'validate' | 'correct' | null>(null)
  const [ref, setRef] = useState(rule.ref)
  const [value, setValue] = useState(Array.isArray(rule.value) ? JSON.stringify(rule.value) : rule.value === null ? '' : String(rule.value))
  const [note, setNote] = useState('')
  const submit = () => {
    let v: unknown = value
    if (mode === 'correct' && Array.isArray(rule.file_value)) {
      try { v = JSON.parse(value) } catch { v = value }
    }
    review.mutate({ rule: rule.rule, action: mode ?? 'validate', ref, note, value: mode === 'correct' ? v : undefined }, { onSuccess: () => setMode(null) })
  }
  return (
    <section aria-label={rule.rule} style={{ borderBottom: '1px solid var(--tf-border)', padding: '8px 0' }}>
      <div className={styles.actions} style={{ alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 220 }}>
          <strong>{rule.label || rule.rule}</strong> <code className={styles.muted}>{rule.rule}</code>
          <div>{show(rule.value)}{rule.value !== rule.file_value && JSON.stringify(rule.value) !== JSON.stringify(rule.file_value) && <span className={styles.muted}> (file: {show(rule.file_value)})</span>}</div>
          <div className={styles.hint}>{rule.ref}</div>
          {rule.conditions.length > 0 && <div className={styles.hint}>Conditions: {rule.conditions.join(', ')}</div>}
        </div>
        {rule.validated
          ? <span className={styles.chip} data-status="approved"><CheckCircle2 size={12} /> Validated{rule.reviewed_by ? ` by ${rule.reviewed_by}` : ''}</span>
          : <span className={styles.chip} data-tone="review">Requires validation</span>}
        {canValidate && (
          <div className={styles.rowActions}>
            {rule.file_value !== null && <Button size="sm" variant="secondary" onClick={() => setMode('validate')}><CheckCircle2 size={12} /> Validate</Button>}
            <Button size="sm" variant="subtle" onClick={() => setMode('correct')}><PenLine size={12} /> Correct</Button>
            {rule.validated && <Button size="sm" variant="subtle" disabled={review.isPending} onClick={() => review.mutate({ rule: rule.rule, action: 'withdraw' })}><Undo2 size={12} /> Withdraw</Button>}
            <label className={styles.chip} style={{ cursor: 'pointer' }}>
              <FileSearch size={12} /> Check against a law document (AI)
              <input type="file" hidden accept=".pdf,.txt,.png,.jpg,.jpeg" onChange={(ev) => ev.target.files?.[0] && check.mutate({ rule: rule.rule, file: ev.target.files[0] })} />
            </label>
          </div>
        )}
      </div>
      {check.isPending && <p className={styles.muted}>Local_Tax_AI is reading the document…</p>}
      {check.data && (
        <div className={styles.card} style={{ background: 'var(--tf-surface-sunken)' }} aria-label="AI check">
          <strong>{check.data.document}: {check.data.agrees === 'yes' ? 'agrees' : check.data.agrees === 'no' ? 'does NOT agree' : 'unclear'}</strong>
          {check.data.value_in_document && <span> — document says: {check.data.value_in_document}</span>}
          {check.data.quote && <blockquote style={{ margin: '4px 0' }}>“{check.data.quote}” <span className={styles.muted}>{check.data.cite}</span></blockquote>}
          {check.data.note && <p className={styles.muted} style={{ margin: 0 }}>{check.data.note}</p>}
          <p className={styles.hint} style={{ margin: 0 }}>Assistance only: you decide whether to validate or correct the rule.</p>
        </div>
      )}
      {check.isError && <p className={styles.error}>{extractErrorMessage(check.error)}</p>}
      {mode && (
        <div className={styles.formGrid}>
          {mode === 'correct' && (
            <label className={styles.field}>
              <span>Correct value {Array.isArray(rule.file_value) ? '(bands as [[width, rate], …, [null, rate]])' : typeof rule.file_value === 'number' && rule.file_value < 1 ? '(a rate: 0.15 for 15%)' : ''}</span>
              <input value={value} onChange={(ev) => setValue(ev.target.value)} />
            </label>
          )}
          <label className={styles.field}><span>Legal reference relied on</span><input value={ref} onChange={(ev) => setRef(ev.target.value)} /></label>
          <label className={styles.field}><span>Note {mode === 'correct' && '(why it is corrected)'}</span><input value={note} onChange={(ev) => setNote(ev.target.value)} /></label>
          <div className={styles.actions}>
            <Button size="sm" variant="primary" disabled={review.isPending} onClick={submit}>{mode === 'validate' ? 'Validate the rule' : 'Save the correction'}</Button>
            <Button size="sm" variant="subtle" onClick={() => setMode(null)}>Cancel</Button>
          </div>
        </div>
      )}
      {review.isError && <p className={styles.error}>{extractErrorMessage(review.error)}</p>}
      {rule.history.length > 0 && (
        <details>
          <summary className={styles.hint}>Review history ({rule.history.length})</summary>
          <ul className={styles.muted}>
            {rule.history.map((h, n) => (
              <li key={n}>{h.status} {h.status === 'corrected' ? `to ${show(h.value)}` : ''} by {h.by} on {new Date(h.at).toLocaleDateString('en-GB')} — {h.ref}
                {h.note ? ` — ${h.note}` : ''}{h.active ? '' : ' (replaced / withdrawn)'}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function FieldRefs({ year, data }: { year: string; data: RuleRegister }) {
  const review = useReviewField(year)
  const [form, setForm] = useState({ entity_type: 'company' as 'company' | 'individual', code: '', official: '', note: '' })
  const active = data.fields.filter((f) => f.active)
  return (
    <div className={styles.card}>
      <p className={styles.hint}>
        The draft return uses TASKO field codes (B1, C4, T3, schedule lines SCA1, SL1…). Record each code&apos;s cage / field reference in the year&apos;s RAMIS
        return; a family of numbered lines is recorded as e.g. “SCA*”. A field shows its RAMIS reference once recorded.
      </p>
      <table className={styles.table} aria-label="Return field references">
        <thead><tr><th>Return</th><th>TASKO code</th><th>RAMIS reference</th><th>Recorded by</th><th /></tr></thead>
        <tbody>
          {active.map((f) => (
            <tr key={f.id}>
              <td>{f.entity_type === 'company' ? 'Corporate' : 'Individual'}</td><td>{f.code}</td><td>{f.official}{f.note && <span className={styles.muted}> — {f.note}</span>}</td>
              <td>{f.by}</td>
              <td>{data.can_validate && <Button size="sm" variant="subtle" onClick={() => review.mutate({ entity_type: f.entity_type, code: f.code, withdraw: true })}>Withdraw</Button>}</td>
            </tr>
          ))}
          {!active.length && <tr><td colSpan={5} className={styles.muted}>No field has been checked against RAMIS yet.</td></tr>}
        </tbody>
      </table>
      {data.can_validate && (
        <div className={styles.formGrid}>
          <label className={styles.field}><span>Return</span>
            <select value={form.entity_type} onChange={(ev) => setForm({ ...form, entity_type: ev.target.value as 'company' | 'individual' })}>
              <option value="company">Corporate (CIT)</option><option value="individual">Individual (IIT)</option>
            </select>
          </label>
          <label className={styles.field}><span>TASKO code</span><input value={form.code} placeholder="T3 or SCA*" onChange={(ev) => setForm({ ...form, code: ev.target.value })} /></label>
          <label className={styles.field}><span>RAMIS reference</span><input value={form.official} placeholder="Cage 1250" onChange={(ev) => setForm({ ...form, official: ev.target.value })} /></label>
          <label className={styles.field}><span>Note</span><input value={form.note} onChange={(ev) => setForm({ ...form, note: ev.target.value })} /></label>
          <div className={styles.actions}>
            <Button size="sm" variant="primary" disabled={review.isPending || !form.code || !form.official}
              onClick={() => review.mutate(form, { onSuccess: () => setForm({ ...form, code: '', official: '', note: '' }) })}>Record the reference</Button>
          </div>
        </div>
      )}
      {review.isError && <p className={styles.error}>{extractErrorMessage(review.error)}</p>}
    </div>
  )
}
