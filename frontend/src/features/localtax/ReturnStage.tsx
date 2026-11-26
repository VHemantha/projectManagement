import { BarChart3, CheckCircle2, Download, Eye, FileText, Info, Sparkles } from 'lucide-react'
import { useState } from 'react'

import styles from './LocalTax.module.css'
import { AiAssistant, Alerts, SectionNav, StageControls, UnvalidatedConfirm } from './Shared'
import { extractErrorMessage } from '@/api/errors'
import { type AiItems, type LocalTaxState, downloadLocalTax, money, needsAcknowledgement, useAiAgent, useSaveLocalTax, useSetStage } from '@/api/localTax'
import { UpdateButton } from './Update'
import { Button } from '@/design-system'

/** Stage 4 (AFIT screens, 22 Nov 2026): the draft income tax return from the approved figures - its sections and
 * fields editable (an accountant's correction is kept apart from the computed value), the missing mandatory fields
 * highlighted, and the draft PDF for the accountant to enter into RAMIS. Nothing is submitted. */
export function ReturnStage({ taskKey, state, onBack }: { taskKey: string; state: LocalTaxState; onBack?: () => void }) {
  const e = state.engagement
  const ret = state.return
  const comp = state.computation
  const save = useSaveLocalTax(taskKey)
  const finalise = useSetStage(taskKey)
  const review = useAiAgent<AiItems>(taskKey, 'return')
  const [section, setSection] = useState(ret?.sections[0]?.key ?? 'basic')
  const [overrides, setOverrides] = useState<Record<string, string | null>>(e.data.return_overrides ?? {})
  if (!ret) {
    return <Alerts alerts={state.alerts.filter((a) => a.stage === 'return' || a.stage === 'computation')} />
  }
  const current = ret.sections.find((s) => s.key === section) ?? ret.sections[0]
  const dirty = JSON.stringify(overrides) !== JSON.stringify(e.data.return_overrides ?? {})
  const approvedComputation = e.stages.computation?.status === 'approved'
  const ticks: [boolean, string][] = [
    [!ret.missing.some((m) => m.section.startsWith('A.')), 'Basic information completed'],
    [!!comp && comp.taxable_income !== null, 'Taxable income transferred'],
    [!!comp?.lines.some((l) => l.rule.includes('special_rates')), 'Concessionary rate applied'],
    [!!comp && Number(comp.credits) > 0, 'Tax credits & payments included'],
    [approvedComputation && !ret.missing.length, 'Return is ready for review'],
  ]

  return (
    <>
      <div className={styles.stageHead}>
        <FileText size={22} className={styles.stageIcon} aria-hidden="true" />
        <div>
          <h2 className={styles.stageTitle}>Draft Tax Return</h2>
          <p className={styles.stageLead}>Generate, review and finalise the Income Tax Return ({e.tax_type}) for submission to the Inland Revenue Department (IRD).</p>
        </div>
        <span className={styles.spacer} />
        <UpdateButton taskKey={taskKey} stage="return" />
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => downloadLocalTax(taskKey, 'return', 'pdf', true)}><Eye size={15} /> Preview (PDF)</Button>
          <Button variant="secondary" onClick={() => downloadLocalTax(taskKey, 'return', 'pdf')}><Download size={15} /> Download Draft</Button>
          {e.can_approve && (
            <Button variant="primary" disabled={finalise.isPending || e.stages.return?.status === 'approved'}
              onClick={() => finalise.mutate({ stage: 'return', status: 'approved' })}>
              <CheckCircle2 size={15} /> {e.stages.return?.status === 'approved' ? 'Return finalised' : 'Finalise Return'}
            </Button>
          )}
        </div>
      </div>
      <StageControls taskKey={taskKey} state={state} stage="return" />
      {finalise.isError && (needsAcknowledgement(finalise.error)
        ? <UnvalidatedConfirm rules={needsAcknowledgement(finalise.error) ?? []} busy={finalise.isPending} onCancel={() => finalise.reset()}
            onConfirm={() => finalise.mutate({ stage: 'return', status: 'approved', acknowledge: true })} />
        : <p className={styles.error}>{extractErrorMessage(finalise.error)}</p>)}

      <div className={styles.columns}>
        <div className={styles.card}>
          <h3 className={styles.cardTitle} style={{ color: 'var(--tf-text)' }}>Return Sections</h3>
          <SectionNav items={ret.sections.map((s) => ({ key: s.key, label: s.title, icon: <FileText size={16} /> }))} value={section}
            onChange={setSection} label="Return sections" />
        </div>

        <section className={styles.card} aria-label={current.title}>
          <h3 className={styles.cardTitle}>{current.title}</h3>
          <div className={styles.formGrid}>
            {current.fields.map((f) => {
              const value = f.code in overrides ? overrides[f.code] ?? '' : f.value ?? ''
              return (
                <label key={f.code} className={styles.field} data-missing={f.missing || undefined}>
                  <span>{f.label} {f.required && <span className={styles.req}>*</span>} {f.validated && f.official ? <span className={styles.chip} data-status="approved" title={`TASKO code ${f.code}`}>RAMIS {f.official}</span>
                    : <span className={styles.muted} title="Placeholder reference: to be checked against the year's RAMIS return">[{f.code}*]</span>}</span>
                  <input value={f.kind === 'amount' && !(f.code in overrides) ? money(value) : value} aria-invalid={f.missing || undefined}
                    style={f.missing ? { borderColor: 'var(--tf-danger)' } : undefined}
                    onChange={(ev) => setOverrides({ ...overrides, [f.code]: ev.target.value })} />
                  {f.overridden && <span className={styles.hint}>Corrected by the accountant (computed: {money(f.computed)})</span>}
                  {f.source && <span className={styles.hint}>From: {f.source}</span>}
                </label>
              )
            })}
          </div>
          <p className={styles.validation}>
            <Info size={13} aria-hidden="true" /> {ret.note} The draft return is prepared from the financial statements and the tax computation; review every
            section before finalising.
          </p>
          <div className={styles.actions} style={{ justifyContent: 'flex-end' }}>
            <Button variant="secondary" disabled={!dirty || save.isPending}
              onClick={() => save.mutate({ data: { return_overrides: overrides }, stage: 'return' })}>Save corrections</Button>
            {(() => {
              const i = ret.sections.findIndex((s) => s.key === current.key)
              const prev = ret.sections[i - 1]
              const next = ret.sections[i + 1]
              return (
                <>
                  {prev && <Button variant="secondary" onClick={() => setSection(prev.key)}>← Back: {prev.title.replace(/^[A-Z]\.\s*/, '')}</Button>}
                  {next && <Button variant="primary" onClick={() => setSection(next.key)}>Next: {next.title.replace(/^[A-Z]\.\s*/, '')}</Button>}
                </>
              )
            })()}
          </div>
          {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
        </section>

        <div className={styles.side}>
          {comp && (
            <section className={styles.card} aria-label="Tax Return Summary">
              <h3 className={styles.cardTitle}><BarChart3 size={18} aria-hidden="true" /> Tax Return Summary</h3>
              <dl className={styles.summary}>
                <div><dt>Taxable Income</dt><dd>LKR {money(comp.taxable_income)}</dd></div>
                <div><dt>Income Tax</dt><dd>LKR {money(comp.income_tax)}</dd></div>
                <div><dt>Tax Credits & Payments</dt><dd>(LKR {money(comp.credits)})</dd></div>
                <div data-total><dt>Final Tax Payable</dt><dd>LKR {money(comp.payable)}</dd></div>
              </dl>
            </section>
          )}
          <section className={styles.card} aria-label="Return checklist">
            <h3 className={styles.cardTitle}><Sparkles size={18} aria-hidden="true" /> AI Assistant</h3>
            <p className={styles.muted}>I have prepared the draft return from your financials and tax computation. Review the return, check disclosures and complete the declaration.</p>
            <ul className={styles.ticks}>
              {ticks.map(([ok, label]) => <li key={label} data-off={!ok || undefined}><CheckCircle2 size={16} aria-hidden="true" /> {label}</li>)}
            </ul>
            <Button size="sm" variant="secondary" disabled={review.isPending} onClick={() => review.mutate(undefined)}>
              {review.isPending ? 'Local_Tax_AI is checking…' : 'Check the return with AI'}
            </Button>
            {review.data && review.data.items.map((i) => <p key={i.title} style={{ margin: 0 }}><strong>{i.title}</strong> — {i.text}</p>)}
            {review.isError && <p className={styles.error}>{extractErrorMessage(review.error)}</p>}
          </section>
          <AiAssistant taskKey={taskKey} lead="Ask about any field of the draft return." />
          {onBack && <Button variant="secondary" onClick={onBack}>← Back: Tax Computation</Button>}
          <Alerts alerts={state.alerts.filter((a) => a.stage === 'return')} />
        </div>
      </div>
    </>
  )
}
