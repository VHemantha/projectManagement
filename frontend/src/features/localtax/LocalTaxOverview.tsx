import { ArrowRight, BarChart3, Building2, Calculator, CheckCircle2, ClipboardList, ExternalLink, FileText, Layers, Receipt, Sparkles, Target } from 'lucide-react'
import { useState } from 'react'

import styles from './LocalTax.module.css'
import { AiAssistant, StatusChip } from './Shared'
import { LocalTaxWorkflow, type WorkflowPlace } from './LocalTaxPage'
import { extractErrorMessage } from '@/api/errors'
import { useAttachments } from '@/api/issues'
import { type LocalTaxState, type StageKey, money, useLocalTax } from '@/api/localTax'
import { Button, Dialog, DialogContent, Skeleton } from '@/design-system'

const CHECKLIST: Record<StageKey, [string, (s: LocalTaxState) => boolean][]> = {
  questionnaire: [
    ['Client & tax details', (s) => !!(s.engagement.legal_name && s.engagement.tin && s.engagement.fy_end)],
    ['Supporting documents verified', (s) => !!s.documents?.documents && !s.documents.to_verify && !s.documents.open_flags],
    ['Income & expenses', (s) => !!(s.engagement.data.income?.length) || s.engagement.entity_type === 'company'],
    ['Assets & liabilities', (s) => !!(s.engagement.data.assets?.length || s.engagement.data.liabilities?.length) || s.engagement.entity_type === 'company'],
    ['Tax payments & expected tax', (s) => !!s.engagement.data.payments?.length && (s.engagement.expected_tax !== null || !!s.engagement.data.expected_skipped)],
  ],
  fs: [
    ['Trial balance mapped', (s) => !!s.financials && !(s.financials.unmapped?.length)],
    ['Adjustments & reclassifications', (s) => !s.adjustments.some((a) => a.scope === 'accounting' && a.status === 'proposed')],
    ['Notes & disclosures', () => false],
    ['Audit report (draft)', (s) => !s.engagement.audited || s.engagement.stages.fs?.status === 'approved'],
  ],
  computation: [
    ['Accounting to tax adjustments', (s) => !!s.engagement.data.computation?.add_backs?.length || s.engagement.entity_type === 'individual'],
    ['Capital allowances / deductions', (s) => !!s.engagement.data.computation?.capital_allowances?.length || s.engagement.entity_type === 'individual'],
    ['Tax credits & payments', (s) => !!s.engagement.data.payments?.length],
    ['Final tax calculation', (s) => s.engagement.stages.computation?.status === 'approved'],
  ],
  return: [
    ['Return details & schedules', (s) => !!s.return && !s.return.missing.length],
    ['Asset and liability statement', (s) => s.engagement.entity_type === 'company' || !!s.engagement.data.assets?.length],
    ['Tax credits & payment details', (s) => !!s.engagement.data.payments?.length],
    ['Final draft (PDF)', (s) => s.engagement.stages.return?.status === 'approved'],
  ],
}
const CARDS: { key: StageKey; n: number; title: string; lead: string; icon: React.ReactNode }[] = [
  { key: 'questionnaire', n: 1, title: 'Client Info', lead: 'Client details and supporting documents (read by AI, verified by you), income, assets and tax payments.', icon: <ClipboardList size={36} /> },
  { key: 'fs', n: 2, title: 'Financial Statements', lead: 'Generate financial statements (as per LKAS/SLFRS), with adjustments and disclosures.', icon: <BarChart3 size={36} /> },
  { key: 'computation', n: 3, title: 'Tax Computation', lead: 'Prepare a detailed income tax computation, apply adjustments, reliefs and tax credits.', icon: <Calculator size={36} /> },
  { key: 'return', n: 4, title: 'Draft Tax Return', lead: 'Generate an editable draft income tax return and related schedules (e.g. assets and liabilities).', icon: <FileText size={36} /> },
]

/** On a Team 3 > Local card, in place of the AI workspace (AFIT screens, 22 Nov 2026): the engagement's four
 * stages with where each stands, the tax summary, the reverse tax analysis and the AI assistant. */
export function LocalTaxOverview({ taskKey }: { taskKey: string }) {
  const { data, isLoading, isError, error } = useLocalTax(taskKey)
  const { data: files } = useAttachments(taskKey)
  const [open, setOpen] = useState<WorkflowPlace | null>(null)
  if (isLoading) return <Skeleton height={160} />
  if (isError || !data) return <p className={styles.error}>{extractErrorMessage(error, 'The Local Tax workflow could not be loaded.')}</p>
  const e = data.engagement
  const comp = data.computation
  const rev = data.reverse
  const show = (stage: StageKey, section?: WorkflowPlace['section']) => setOpen({ stage, section })
  return (
    <section className={styles.page} style={{ padding: 0 }} aria-label="AI Workflow – Local Tax Engagement">
      <div className={styles.stageHead}>
        <Sparkles size={22} className={styles.stageIcon} aria-hidden="true" />
        <div>
          <h2 className={styles.stageTitle}>AI Workflow – Local Tax Engagement</h2>
          <p className={styles.stageLead}>End-to-end preparation of financials, tax computation and draft return for Sri Lankan income tax.</p>
        </div>
      </div>
      <div className={styles.clientBar}>
        <Building2 size={20} aria-hidden="true" />
        <div>
          <p className={styles.clientName}>{e.legal_name || taskKey}</p>
          <p className={styles.clientMeta}>TIN: {e.tin || '—'} | YA: {e.year_of_assessment} | Year End: {e.fy_end ?? '—'} | Tax Type:{' '}
            {e.tax_type === 'CIT' ? 'Corporate Income Tax' : 'Individual Income Tax'}</p>
        </div>
        <span className={styles.spacer} />
        <Button size="sm" variant="secondary" onClick={() => show('questionnaire')}><ExternalLink size={12} /> View Details</Button>
      </div>
      <div className={styles.overviewGrid}>
        <div className={styles.stageCards}>
          {CARDS.map((c) => {
            const status = e.stages[c.key]?.status ?? 'not_started'
            const pct = data.progress?.[c.key] ?? 0
            return (
              <article key={c.key} className={styles.stageCard} data-status={status} aria-label={`${c.n}. ${c.title}`}>
                <div className={styles.stageCardHead}>
                  <span className={styles.stageIcon}>{c.icon}</span>
                  <h3>{c.n}. {c.title}</h3>
                  <StatusChip status={status} />
                </div>
                <p className={styles.muted}>{c.lead}</p>
                <div className={styles.stageCardBody}>
                  <ul className={styles.ticks}>
                    {CHECKLIST[c.key].map(([label, ok]) => (
                      <li key={label} data-off={!ok(data) || undefined}><CheckCircle2 size={16} aria-hidden="true" /> {label}</li>
                    ))}
                  </ul>
                  <div className={styles.docs}>
                    <FileText size={22} aria-hidden="true" />
                    <strong>{c.key === 'questionnaire' ? data.documents?.documents ?? files?.length ?? 0 : c.key === 'fs' ? data.financials?.tb?.length ?? '–' : '–'}</strong>
                    {c.key === 'fs' ? 'Accounts' : 'Documents'}
                  </div>
                </div>
                <div className={styles.progressRow}>
                  <span className={styles.bar}><span style={{ width: `${pct}%` }} /></span> {pct}%
                </div>
                <div className={styles.actions}>
                  <Button variant="subtle" onClick={() => show(c.key)}>{status === 'not_started' ? 'View Template' : 'View / Edit'}</Button>
                  <Button variant="primary" onClick={() => show(c.key)}>{status === 'not_started' ? 'Start' : 'Continue'} <ArrowRight size={14} /></Button>
                </div>
              </article>
            )
          })}
        </div>
        <div className={styles.side}>
          <section className={styles.card} aria-label="Tax Summary">
            <h3 className={styles.cardTitle}><BarChart3 size={18} aria-hidden="true" /> Tax Summary</h3>
            <dl className={styles.summary}>
              <div><dt>Expected Tax Payment</dt><dd>{rev ? `LKR ${money(rev.expected)}` : '—'}</dd></div>
              <div><dt>Calculated Tax Payment</dt><dd>{comp ? `LKR ${money(rev ? rev.calculated : comp.payable)}` : '—'}</dd></div>
              {rev && <div data-total><dt>Difference</dt><dd>LKR {money(Math.abs(Number(rev.variance)))}</dd></div>}
            </dl>
            {rev && (
              <>
                <h4 style={{ margin: '8px 0 0', display: 'flex', alignItems: 'center', gap: 6 }}><Target size={16} aria-hidden="true" /> Reverse Tax Analysis</h4>
                <p className={styles.muted}>To achieve the expected tax of LKR {money(rev.expected)}:</p>
                <dl className={styles.summary}>
                  <div><dt>Required Taxable Income</dt><dd>{rev.required_taxable_income ? `LKR ${money(rev.required_taxable_income)}` : 'Not reachable'}</dd></div>
                  <div><dt>Current Taxable Income</dt><dd>LKR {money(rev.taxable_income)}</dd></div>
                  <div><dt>Adjustment Required</dt><dd>{rev.taxable_income_difference ? `LKR ${money(-Number(rev.taxable_income_difference))}` : '—'}</dd></div>
                </dl>
                <Button variant="secondary" onClick={() => show('computation')}><Sparkles size={14} /> Analyse & Suggest Adjustments</Button>
              </>
            )}
            {comp && (
              <>
                <h4 style={{ margin: '8px 0 0', display: 'flex', alignItems: 'center', gap: 6 }}><Layers size={16} aria-hidden="true" /> Key Results (Current)</h4>
                <dl className={styles.summary}>
                  {e.entity_type === 'company' && <div><dt>Accounting Profit Before Tax</dt><dd>LKR {money(comp.pbt)}</dd></div>}
                  <div><dt>Taxable Income</dt><dd>LKR {money(comp.taxable_income)}</dd></div>
                  <div><dt>Final Tax Payable</dt><dd><Receipt size={12} aria-hidden="true" /> LKR {money(comp.payable)}</dd></div>
                </dl>
              </>
            )}
          </section>
          {(data.documents?.to_verify || data.documents?.open_flags) ? (
            <section className={styles.card} aria-label="Documents to verify">
              <h3 className={styles.cardTitle}><FileText size={18} aria-hidden="true" /> Supporting documents</h3>
              <p className={styles.muted} style={{ margin: 0 }}>
                {data.documents.to_verify} value(s) to verify · {data.documents.open_flags} issue(s) to resolve
              </p>
              <Button size="sm" variant="primary" onClick={() => show('questionnaire', 'documents')}>Review the documents</Button>
            </section>
          ) : null}
          <AiAssistant taskKey={taskKey} lead="Ask anything about this engagement."
            suggestions={[rev ? `Why is there a LKR ${money(Math.abs(Number(rev.variance)))} difference?` : 'How was the tax calculated?',
              'Which accounts should we review?', 'Show adjustment scenarios to reach the expected tax.']} />
        </div>
      </div>
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        {open && (
          <DialogContent title="AI Workflow – Local Tax Engagement" fullScreen hideTitle>
            <LocalTaxWorkflow taskKey={taskKey} place={open} onPlace={setOpen} onClose={() => setOpen(null)} />
          </DialogContent>
        )}
      </Dialog>
    </section>
  )
}
