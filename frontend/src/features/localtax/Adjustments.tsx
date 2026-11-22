import { Check, Pencil, Sparkles, X } from 'lucide-react'
import { useState } from 'react'

import styles from './LocalTax.module.css'
import { StatusChip } from './Shared'
import { extractErrorMessage } from '@/api/errors'
import { useAttachments } from '@/api/issues'
import {
  type AiItems,
  type LocalTaxState,
  type WhatIf,
  money,
  reverseEffect,
  useAiAgent,
  useDecideAdjustment,
  useEditAdjustment,
  useProposeAdjustment,
} from '@/api/localTax'
import { Button } from '@/design-system'

const KIND = { journal: 'Journal', reclass: 'Reclassification', tax: 'Tax adjustment', reverse: 'Reverse tax correction' } as const

/** The adjustments of one scope: original, proposed, difference, reason and evidence; a reviewer approves or
 * rejects; a proposal can be edited (its earlier version kept). Only approved ones are in the figures. */
export function Adjustments({ taskKey, state, scope }: { taskKey: string; state: LocalTaxState; scope?: 'accounting' | 'tax' }) {
  const decide = useDecideAdjustment(taskKey)
  const edit = useEditAdjustment(taskKey)
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState({ proposed: '', reason: '', evidence_note: '' })
  const rows = state.adjustments.filter((a) => !scope || a.scope === scope)
  if (!rows.length) return <p className={styles.muted}>No adjustments yet.</p>
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} aria-label="Adjustments">
        <thead>
          <tr><th>Adjustment</th><th className={styles.num}>Original</th><th className={styles.num}>Proposed</th><th className={styles.num}>Difference</th><th>Status</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <th scope="row">
                <strong>{a.label}</strong> <span className={styles.muted}>({KIND[a.kind]}{a.scope === 'tax' ? ', tax only' : ''})</span>
                <div className={styles.muted}>{a.reason}</div>
                {a.lines.length > 0 && <div className={styles.muted}>{a.lines.map((l) => `${l.code} ${money(l.amount)}`).join(' · ')}</div>}
                <div className={styles.muted}>Evidence: {a.evidence?.name ?? (a.evidence_note || 'none yet')} · {a.created_by}</div>
                {a.decided_by && <div className={styles.muted}>{a.status} by {a.decided_by}{a.decision_note ? ` — ${a.decision_note}` : ''}</div>}
                {editing === a.id && (
                  <div className={styles.formGrid} style={{ marginTop: 6 }}>
                    {a.scope === 'tax' && (
                      <label className={styles.field}><span>Proposed amount</span><input inputMode="decimal" value={draft.proposed} onChange={(ev) => setDraft({ ...draft, proposed: ev.target.value })} /></label>
                    )}
                    <label className={styles.field}><span>Reason</span><input value={draft.reason} onChange={(ev) => setDraft({ ...draft, reason: ev.target.value })} /></label>
                    <label className={`${styles.field} ${styles.wide}`}><span>Evidence (what supports it)</span>
                      <input value={draft.evidence_note} onChange={(ev) => setDraft({ ...draft, evidence_note: ev.target.value })} /></label>
                    <div className={styles.actions}>
                      <Button size="sm" variant="primary" disabled={edit.isPending}
                        onClick={() => edit.mutate({ id: a.id, ...(a.scope === 'tax' ? { proposed: draft.proposed } : {}), reason: draft.reason, evidence_note: draft.evidence_note },
                          { onSuccess: () => setEditing(null) })}>Save</Button>
                      <Button size="sm" variant="subtle" onClick={() => setEditing(null)}>Cancel</Button>
                    </div>
                  </div>
                )}
              </th>
              <td className={styles.num}>{money(a.original)}</td>
              <td className={styles.num}>{money(a.proposed)}</td>
              <td className={styles.num}>{money(a.difference)}</td>
              <td><StatusChip status={a.status} /></td>
              <td>
                {a.status === 'proposed' && (
                  <div className={styles.rowActions}>
                    {state.engagement.can_approve && (
                      <>
                        <Button size="sm" variant="primary" aria-label={`Approve correction ${a.label}`} disabled={decide.isPending}
                          onClick={() => decide.mutate({ id: a.id, decision: 'approve' })}><Check size={13} /> Approve</Button>
                        <Button size="sm" variant="subtle" aria-label={`Reject correction ${a.label}`} disabled={decide.isPending}
                          onClick={() => decide.mutate({ id: a.id, decision: 'reject' })}><X size={13} /> Reject</Button>
                      </>
                    )}
                    <Button size="sm" variant="subtle" aria-label={`Edit correction ${a.label}`}
                      onClick={() => (setEditing(a.id), setDraft({ proposed: a.proposed ?? '', reason: a.reason, evidence_note: a.evidence_note }))}>
                      <Pencil size={13} /> Edit
                    </Button>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {(decide.isError || edit.isError) && <p className={styles.error}>{extractErrorMessage(decide.error ?? edit.error)}</p>}
    </div>
  )
}

/** Reverse tax (AFIT, 22 Nov 2026): expected against calculated tax, the taxable income the expected tax needs, each
 * line's scenario from the engine; the accountant picks a line, gives the corrected amount, the reason and the
 * evidence, sees the effect (hypothetical), and proposes it for approval. Nothing changes until it is approved. */
export function ReversePanel({ taskKey, state }: { taskKey: string; state: LocalTaxState }) {
  const rev = state.reverse
  const propose = useProposeAdjustment(taskKey)
  const ask = useAiAgent<AiItems>(taskKey, 'reverse')
  const { data: files } = useAttachments(taskKey)
  const [lever, setLever] = useState('')
  const [proposed, setProposed] = useState('')
  const [reason, setReason] = useState('')
  const [evidenceId, setEvidenceId] = useState<number | null>(null)
  const [evidenceNote, setEvidenceNote] = useState('')
  const [effect, setEffect] = useState<WhatIf | null>(null)
  const [error, setError] = useState('')
  if (!rev) return <p className={styles.muted}>No expected tax payment was given in the questionnaire (G. Expected Tax Payment).</p>
  const levers = state.levers ?? []
  const chosen = levers.find((l) => l.key === lever)
  const scenario = rev.scenarios.find((s) => s.key === lever)
  const accounting = chosen?.scope === 'accounting'
  const preview = async (value: string) => {
    setProposed(value)
    setEffect(null)
    setError('')
    if (!lever || value.trim() === '') return
    try {
      setEffect(await reverseEffect(taskKey, lever, value))
    } catch (e) {
      setError(extractErrorMessage(e))
    }
  }
  return (
    <>
      <dl className={styles.summary}>
        <div><dt>Expected tax ({rev.basis === 'total' ? 'total liability' : 'remaining payable'})</dt><dd>LKR {money(rev.expected)}</dd></div>
        <div><dt>Calculated tax</dt><dd>LKR {money(rev.calculated)}</dd></div>
        <div><dt>Difference</dt><dd>LKR {money(rev.variance)}</dd></div>
        <div><dt>Taxable income needed for the expected tax</dt><dd>{rev.required_taxable_income ? `LKR ${money(rev.required_taxable_income)}` : 'Not reachable'}</dd></div>
        <div><dt>Current taxable income</dt><dd>LKR {money(rev.taxable_income)}</dd></div>
        <div><dt>Difference in taxable income</dt><dd>{rev.taxable_income_difference ? `LKR ${money(rev.taxable_income_difference)}` : '—'}</dd></div>
      </dl>
      {rev.unsupported && <p className={styles.error}>{rev.unsupported}</p>}
      <div className={styles.actions}>
        <Button size="sm" variant="secondary" disabled={ask.isPending} onClick={() => ask.mutate(undefined)}>
          <Sparkles size={13} /> {ask.isPending ? 'Local_Tax_AI is analysing…' : 'Analyse & suggest what to review'}
        </Button>
      </div>
      {ask.data && (
        <div className={styles.card} aria-label="Local_Tax_AI's questions">
          {ask.data.summary && <p className={styles.muted}>{ask.data.summary}</p>}
          {ask.data.questions.map((q) => <p key={q} style={{ margin: 0 }}><strong>{q}</strong></p>)}
          {ask.data.items.map((i) => (
            <div key={i.title} className={styles.actions}>
              <span><strong>{i.title}</strong> — {i.text}</span>
              {i.lever && <Button size="sm" variant="subtle" onClick={() => (setLever(i.lever!), setEffect(null), setProposed(''))}>Review this line</Button>}
            </div>
          ))}
        </div>
      )}
      {ask.isError && <p className={styles.error}>{extractErrorMessage(ask.error)}</p>}
      <h4 style={{ margin: '6px 0 0' }}>Lines that alone could explain the difference (engine scenarios — hypothetical)</h4>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Reverse tax scenarios">
          <thead>
            <tr><th>Line</th><th className={styles.num}>Current</th><th className={styles.num}>Would need</th><th className={styles.num}>Change</th><th /></tr>
          </thead>
          <tbody>
            {rev.scenarios.slice(0, 15).map((s) => (
              <tr key={s.key}>
                <th scope="row">{s.label} <span className={styles.muted}>({s.group})</span></th>
                <td className={styles.num}>{money(s.amount)}</td>
                <td className={styles.num}>{s.feasible ? money(s.proposed) : '—'}</td>
                <td className={styles.num}>{s.feasible ? money(s.change) : <span className={styles.muted}>{s.reason}</span>}</td>
                <td><Button size="sm" variant="subtle" onClick={() => (setLever(s.key), setEffect(null), setProposed(''))}>Select</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <section className={styles.card} aria-label="Investigate a line">
        <strong>Investigate a line</strong>
        <label className={styles.field}>
          <span>Account or tax line</span>
          <select value={lever} onChange={(ev) => (setLever(ev.target.value), setEffect(null), setProposed(''))}>
            <option value="">Choose…</option>
            {levers.map((l) => <option key={l.key} value={l.key}>{l.group}: {l.label} ({money(l.amount)})</option>)}
          </select>
        </label>
        {chosen && (
          <>
            <div className={styles.formGrid}>
              <label className={styles.field}><span>Corrected amount</span>
                <input inputMode="decimal" value={proposed} onChange={(ev) => preview(ev.target.value)} placeholder={scenario?.proposed ?? ''} /></label>
              <label className={styles.field}><span>Explanation</span><input value={reason} onChange={(ev) => setReason(ev.target.value)} /></label>
              <label className={styles.field}><span>Supporting document</span>
                <select value={evidenceId ?? ''} onChange={(ev) => setEvidenceId(ev.target.value ? Number(ev.target.value) : null)}>
                  <option value="">None attached</option>
                  {(files ?? []).map((f) => <option key={f.id} value={f.id}>{f.filename}</option>)}
                </select></label>
              <label className={styles.field}><span>Or describe the evidence</span><input value={evidenceNote} onChange={(ev) => setEvidenceNote(ev.target.value)} /></label>
            </div>
            {effect && (
              <dl className={styles.summary} aria-label="Effect of the proposed change">
                <div><dt>Original amount</dt><dd>{money(effect.original)}</dd></div>
                <div><dt>Proposed amount</dt><dd>{money(effect.proposed)}</dd></div>
                <div><dt>Difference</dt><dd>{money(effect.difference)}</dd></div>
                <div><dt>Revised taxable income</dt><dd>{money(effect.taxable_after)}</dd></div>
                <div><dt>Revised tax</dt><dd>{money(effect.tax_after)}</dd></div>
                <div><dt>Remaining variance</dt><dd>{money(effect.remaining_variance)}</dd></div>
              </dl>
            )}
            {accounting && (
              <p className={styles.hint}>An accounting line is corrected with a journal (Financial Statements › Adjustments), so the statements stay balanced.</p>
            )}
            <div className={styles.actions}>
              <Button size="sm" variant="primary" disabled={accounting || !proposed || reason.trim().length < 5 || propose.isPending}
                onClick={() => propose.mutate({ kind: 'reverse', target: lever, proposed, reason, evidence_id: evidenceId, evidence_note: evidenceNote },
                  { onSuccess: () => (setLever(''), setProposed(''), setReason(''), setEffect(null), setEvidenceNote(''), setEvidenceId(null)) })}>
                Propose correction for approval
              </Button>
            </div>
          </>
        )}
        {(error || propose.isError) && <p className={styles.error}>{error || extractErrorMessage(propose.error)}</p>}
      </section>
      <h4 style={{ margin: 0 }}>Corrections</h4>
      <Adjustments taskKey={taskKey} state={state} scope="tax" />
    </>
  )
}
