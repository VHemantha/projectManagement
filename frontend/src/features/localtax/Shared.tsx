import { AlertTriangle, ArrowRight, Check, CheckCircle2, Info, Sparkles } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { ClientChanges } from './ClientChanges'
import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import {
  type Alert,
  type LocalTaxState,
  type StageKey,
  type StageStatus,
  STAGES,
  STATUS_LABEL,
  money,
  useAskLocalTax,
  useMessages,
  needsAcknowledgement,
  useSetStage,
} from '@/api/localTax'
import { Button, Skeleton } from '@/design-system'

export function StatusChip({ status }: { status: StageStatus | string }) {
  return (
    <span className={styles.chip} data-status={status}>
      {status === 'approved' && <Check size={11} aria-hidden="true" />}
      {STATUS_LABEL[status as StageStatus] ?? status}
    </span>
  )
}

/** The four stages, the current one maroon; a done one ticked. */
export function Stepper({ state, current, onPick }: { state: LocalTaxState; current: StageKey; onPick: (s: StageKey) => void }) {
  return (
    <ol className={styles.stepper} aria-label="Workflow stages">
      {STAGES.map((s) => {
        const status = state.engagement.stages[s.key]?.status ?? 'not_started'
        return (
          <li key={s.key} className={styles.step} data-active={s.key === current || undefined}>
            <button type="button" onClick={() => onPick(s.key)} aria-current={s.key === current ? 'step' : undefined}>
              <span className={styles.stepNo}>{s.n}</span>
              <span className={styles.stepText}>
                <strong>{s.title}</strong>
                <small>{s.purpose}</small>
              </span>
              {(status === 'approved' || status === 'ready_for_review') && (
                <CheckCircle2 size={20} className={styles.stepDone} aria-label={STATUS_LABEL[status]} />
              )}
            </button>
          </li>
        )
      })}
    </ol>
  )
}

export function Alerts({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) return null
  return (
    <ul className={styles.alerts} aria-label="Alerts">
      {alerts.map((a, n) => (
        <li key={n} data-severity={a.severity}>
          {a.severity === 'info' ? <Info size={14} aria-hidden="true" /> : <AlertTriangle size={14} aria-hidden="true" />}
          <span>{a.text}</span>
        </li>
      ))}
    </ul>
  )
}

/** Save for review / approve a stage (a reviewer, lead or admin approves; the earlier stages first). */
/** Approving a stage whose figures rest on rules no tax professional has validated asks for a conscious
 * acknowledgement (it is recorded in the audit trail). */
export function UnvalidatedConfirm({ rules, onConfirm, onCancel, busy }: { rules: string[]; onConfirm: () => void; onCancel: () => void; busy: boolean }) {
  return (
    <div className={styles.card} role="alertdialog" aria-label="Approve with unvalidated rules" style={{ borderColor: 'var(--tf-warning, #b54708)' }}>
      <strong>{rules.length} rule(s) used are not yet validated by a tax professional</strong>
      <p className={styles.muted} style={{ margin: 0 }}>{rules.slice(0, 10).join(', ')}{rules.length > 10 ? '…' : ''}</p>
      <p className={styles.hint} style={{ margin: 0 }}>Approving records that you accept the figures on these draft rules. A validator can review them in the rules review.</p>
      <div className={styles.actions}>
        <Button size="sm" variant="primary" disabled={busy} onClick={onConfirm}>I accept — approve</Button>
        <Button size="sm" variant="subtle" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  )
}

export function StageControls({ taskKey, state, stage }: { taskKey: string; state: LocalTaxState; stage: StageKey }) {
  const set = useSetStage(taskKey)
  const status = state.engagement.stages[stage]?.status ?? 'not_started'
  const pendingRules = set.isError ? needsAcknowledgement(set.error) : null
  if (pendingRules) {
    return (
      <UnvalidatedConfirm rules={pendingRules} busy={set.isPending} onCancel={() => set.reset()}
        onConfirm={() => set.mutate({ stage, status: 'approved', acknowledge: true })} />
    )
  }
  return (
    <div className={styles.actions}>
      <StatusChip status={status} />
      {status !== 'ready_for_review' && status !== 'approved' && (
        <Button size="sm" variant="secondary" disabled={set.isPending} onClick={() => set.mutate({ stage, status: 'ready_for_review' })}>
          Mark ready for review
        </Button>
      )}
      {state.engagement.can_approve && status !== 'approved' && (
        <Button size="sm" variant="primary" disabled={set.isPending} onClick={() => set.mutate({ stage, status: 'approved' })}>
          <Check size={14} /> Approve
        </Button>
      )}
      {state.engagement.can_approve && status === 'approved' && (
        <Button size="sm" variant="subtle" disabled={set.isPending} onClick={() => set.mutate({ stage, status: 'in_progress' })}>
          Reopen
        </Button>
      )}
      {set.isError && <span className={styles.error}>{extractErrorMessage(set.error)}</span>}
    </div>
  )
}

/** Local_Tax_AI's chat, kept with the engagement. A "what if" answer shows the engine's figures, marked
 * hypothetical. */
export function AiAssistant({ taskKey, lead, suggestions = [] }: { taskKey: string; lead: string; suggestions?: string[] }) {
  const { data, isLoading } = useMessages(taskKey)
  const ask = useAskLocalTax(taskKey)
  const [q, setQ] = useState('')
  const submit = (text: string) => {
    const t = text.trim()
    if (t.length < 2) return
    ask.mutate(t, { onSuccess: () => setQ('') })
  }
  const messages = data?.messages ?? []
  return (
    <section className={styles.card} aria-label="AI Assistant">
      <h3 className={styles.cardTitle}>
        <Sparkles size={18} aria-hidden="true" /> AI Assistant
      </h3>
      <p className={styles.muted}>{lead}</p>
      <p className={styles.hint} style={{ margin: 0 }}>
        Pass on a client&apos;s request (“the client says rent was Rs. 1.2 million”, “the address is now …”) and I&apos;ll set out the changes for you to
        check and apply. A journal or a tax adjustment goes in as a proposal, approved like any other.
      </p>
      {isLoading ? (
        <Skeleton height={40} />
      ) : messages.length > 0 ? (
        <div className={styles.chat} aria-label="Conversation">
          {messages.map((m) => (
            <div key={m.id} className={styles.bubble} data-role={m.role}>
              {m.text}
              {m.data?.points?.length ? (
                <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                  {m.data.points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              ) : null}
              {m.data?.what_if && (
                <div className={styles.whatIf}>
                  <strong>Hypothetical — not applied.</strong> {m.data.what_if.lever.label}: {money(m.data.what_if.original)} →{' '}
                  {money(m.data.what_if.proposed)}. Taxable income {money(m.data.what_if.taxable_before)} → {money(m.data.what_if.taxable_after)}; tax{' '}
                  {money(m.data.what_if.tax_before)} → {money(m.data.what_if.tax_after)}.
                </div>
              )}
              {m.data?.uncertain && <div className={styles.validation}>Needs professional review.</div>}
              {(m.data?.changes?.length || m.data?.changes_dropped?.length) ? (
                <ClientChanges taskKey={taskKey} message={m.id} changes={m.data.changes ?? []} dropped={m.data.changes_dropped ?? []} />
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        suggestions.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }} role="group" aria-label="Suggested questions">
            {suggestions.map((s) => (
              <button key={s} type="button" className={styles.prompt} onClick={() => submit(s)} disabled={ask.isPending}>
                {s}
              </button>
            ))}
          </div>
        )
      )}
      <form
        className={styles.askForm}
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          submit(q)
        }}
      >
        <input aria-label="Ask a question" placeholder="Ask a question, or pass on the client's request…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={2000} />
        <Button type="submit" variant="primary" size="sm" disabled={ask.isPending || q.trim().length < 2} aria-label="Ask">
          <ArrowRight size={14} />
        </Button>
      </form>
      {ask.isPending && <p className={styles.muted}>Local_Tax_AI is thinking…</p>}
      {ask.isError && <p className={styles.error}>{extractErrorMessage(ask.error)}</p>}
    </section>
  )
}

export function SectionNav<T extends string>({ items, value, onChange, label }: {
  items: { key: T; label: string; icon: React.ReactNode }[]
  value: T
  onChange: (k: T) => void
  label: string
}) {
  return (
    <ul className={styles.nav} aria-label={label}>
      {items.map((i) => (
        <li key={i.key}>
          <button type="button" aria-current={i.key === value ? 'true' : undefined} onClick={() => onChange(i.key)}>
            {i.icon} {i.label}
          </button>
        </li>
      ))}
    </ul>
  )
}

export function Completion({ pct }: { pct: number }) {
  return (
    <div className={styles.completion} aria-label={`Completion ${pct}%`}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>Completion</span>
        <span>{pct}%</span>
      </div>
      <span className={styles.bar}>
        <span style={{ width: `${pct}%` }} />
      </span>
    </div>
  )
}
