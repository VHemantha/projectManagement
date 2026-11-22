import { ArrowRight, BookOpen, Calculator, CircleMinus, CirclePlus, Download, FileSpreadsheet, Flag, Layers, Percent, Plus, Receipt, Target, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './LocalTax.module.css'
import { ReversePanel } from './Adjustments'
import { FixedAssetRegister, LossHistory } from './Schedules'
import { AiAssistant, Alerts, SectionNav, StageControls } from './Shared'
import { extractErrorMessage } from '@/api/errors'
import { type AiItems, type CompLine, type LocalTaxState, downloadLocalTax, money, useAiAgent, useSaveLocalTax } from '@/api/localTax'
import { Button } from '@/design-system'

type Section = 'computation' | 'add_backs' | 'deductions' | 'capital_allowances' | 'losses' | 'credits' | 'special' | 'reverse' | 'notes'
const ASSET_CLASSES: [string, string][] = [['plant_machinery', 'Plant, machinery and fixtures'], ['buildings', 'Buildings'],
  ['computers_software', 'Computer hardware and software'], ['motor_vehicles', 'Motor vehicles'], ['intangibles', 'Intangible assets'], ['', 'Enter the allowance']]
const SPECIAL_RATES: [string, string][] = [['qualifying_export_services', '15% – Qualifying Export Service Income'],
  ['betting_gaming_liquor_tobacco', '45% – Betting, gaming, liquor and tobacco']]

/** Stage 3 (AFIT screens, 22 Nov 2026): the income tax computation by the engine, from the financial statements
 * and the questionnaire, with its add backs, deductions, capital allowances, losses, credits and special rates
 * editable here; the reverse tax analysis; and the rules applied, with which still need professional validation. */
export function ComputationStage({ taskKey, state, onNext, onQuestionnaire }: { taskKey: string; state: LocalTaxState; onNext: () => void; onQuestionnaire: () => void }) {
  const e = state.engagement
  const comp = state.computation
  const company = e.entity_type === 'company'
  const save = useSaveLocalTax(taskKey)
  const analyse = useAiAgent<AiItems>(taskKey, 'analyse')
  const [section, setSection] = useState<Section>('computation')
  const c = e.data.computation ?? {}
  const setComp = (patch: typeof c) => save.mutate({ data: { computation: patch }, stage: 'computation' })
  const sections: { key: Section; label: string; icon: React.ReactNode }[] = [
    { key: 'computation', label: 'Tax Computation', icon: <Calculator size={16} /> },
    ...(company ? [{ key: 'add_backs' as Section, label: 'Add Backs (Disallowable)', icon: <CirclePlus size={16} /> },
      { key: 'deductions' as Section, label: 'Deductions / Allowances', icon: <CircleMinus size={16} /> },
      { key: 'capital_allowances' as Section, label: 'Capital Allowances', icon: <Layers size={16} /> }] : []),
    { key: 'losses', label: 'Tax Losses & Qualifying Payments', icon: <Flag size={16} /> },
    { key: 'credits', label: 'Tax Credits & Payments', icon: <Receipt size={16} /> },
    ...(company ? [{ key: 'special' as Section, label: 'Concessionary Rate (Special Rate)', icon: <Percent size={16} /> }] : []),
    { key: 'reverse', label: 'Expected vs Calculated', icon: <Target size={16} /> },
    { key: 'notes', label: 'Working & Notes', icon: <BookOpen size={16} /> },
  ]
  const rev = state.reverse

  return (
    <>
      <div className={styles.stageHead}>
        <Calculator size={44} className={styles.stageIcon} aria-hidden="true" />
        <div>
          <h2 className={styles.stageTitle}>Tax Computation</h2>
          <p className={styles.stageLead}>Calculate taxable income, apply the applicable tax rates (including concessionary rates), credits and final tax payable.</p>
        </div>
        <span className={styles.spacer} />
        <div className={styles.actions}>
          <span className={styles.chip}>{company ? 'Corporate Income Tax' : 'Individual Income Tax'}</span>
          <Link to={`/local-tax/rules/${e.year_of_assessment.replace('/', '-')}`} className={styles.chip}><BookOpen size={12} /> Tax Rules (YA {e.year_of_assessment})</Link>
          <Button variant="secondary" size="sm" onClick={() => setSection('reverse')}>
            Adjustments ({state.adjustments.filter((a) => a.scope === 'tax' && a.status !== 'rejected').length})
          </Button>
        </div>
      </div>
      <StageControls taskKey={taskKey} state={state} stage="computation" />
      {comp?.unvalidated && <p className={styles.validation}>{state.rules_status || 'The rules used are drafts awaiting professional validation.'}</p>}

      <div className={styles.columns}>
        <div className={styles.card}>
          <h3 className={styles.cardTitle} style={{ color: 'var(--tf-text)' }}>Computation Sections</h3>
          <SectionNav items={sections} value={section} onChange={setSection} label="Computation sections" />
        </div>

        <section className={styles.card} aria-label={sections.find((s) => s.key === section)?.label}>
          {!comp ? (
            <Alerts alerts={state.alerts.filter((a) => a.stage === 'computation')} />
          ) : section === 'computation' ? (
            <>
              <h3 className={styles.cardTitle}>{company ? 'Corporate' : 'Individual'} Income Tax Computation</h3>
              <p className={styles.muted}>Year of assessment {e.year_of_assessment}{e.fy_end ? ` · for the year ended ${e.fy_end}` : ''}</p>
              <div className={styles.tableWrap}>
                <table className={styles.table} aria-label="Tax computation">
                  <thead>
                    <tr><th>Description</th><th className={styles.num}>Amount (LKR)</th></tr>
                  </thead>
                  <tbody>
                    {comp.lines.map((ln) => (
                      <tr key={ln.key} data-kind={ln.kind || undefined} data-level={ln.level || undefined}>
                        <th scope="row" title={ln.ref || ln.note}>
                          {ln.label}
                          {ln.note && <div className={styles.muted}>{ln.note}</div>}
                        </th>
                        <td className={styles.num}>{ln.amount === null ? '' : money(ln.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : section === 'add_backs' || section === 'deductions' ? (
            <LineEditor title={section === 'add_backs' ? 'Add backs (disallowable expenses)' : 'Allowable deductions not in the accounts'}
              rows={(c[section] ?? []) as CompLine[]} onSave={(rows) => setComp({ [section]: rows })} busy={save.isPending} />
          ) : section === 'capital_allowances' ? (
            <>
              <FixedAssetRegister rows={e.data.fixed_assets ?? []} schedule={comp.capital_allowance_schedule}
                onSave={(rows) => save.mutate({ data: { fixed_assets: rows }, stage: 'computation' })} busy={save.isPending} />
              <CapitalAllowances rows={c.capital_allowances ?? []} onSave={(rows) => setComp({ capital_allowances: rows })} busy={save.isPending} />
            </>
          ) : section === 'losses' || section === 'credits' ? (
            <>
              <dl className={styles.summary}>
                {section === 'losses' ? (
                  <>
                    <div><dt>Qualifying payments</dt><dd>{money(e.data.qualifying_payments)}</dd></div>
                    <div><dt>Tax losses brought forward</dt><dd>{money(e.data.losses_bf)}</dd></div>
                  </>
                ) : (
                  (e.data.payments ?? []).map((p, i) => (
                    <div key={i}><dt>{p.type} {p.reference}{p.type === 'final_wht' ? ' — final, not credited' : ''}</dt><dd>{money(p.amount)}</dd></div>
                  ))
                )}
              </dl>
              <p className={styles.hint}>Entered in the questionnaire; corrections from the reverse analysis are proposed and approved under Expected vs Calculated.</p>
              <Button size="sm" variant="secondary" onClick={onQuestionnaire}>Edit in the questionnaire</Button>
              {section === 'losses' && (
                <LossHistory rows={e.data.loss_history ?? []} comp={comp}
                  onSave={(rows) => save.mutate({ data: { loss_history: rows }, stage: 'computation' })} busy={save.isPending} />
              )}
            </>
          ) : section === 'special' ? (
            <SpecialIncome rows={c.special_income ?? []} onSave={(rows) => setComp({ special_income: rows })} busy={save.isPending} />
          ) : section === 'reverse' ? (
            <ReversePanel taskKey={taskKey} state={state} />
          ) : (
            <>
              <h3 className={styles.cardTitle}>Rules applied</h3>
              <table className={styles.table} aria-label="Rules applied">
                <thead>
                  <tr><th>Rule</th><th>Reference</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {comp.rules.map((r) => (
                    <tr key={r.rule}><td>{r.rule}</td><td>{r.ref}</td><td>{r.validated
                      ? <span className={styles.chip} data-status="approved">Validated{r.reviewed_by ? ` by ${r.reviewed_by}` : ''}</span>
                      : <span className={styles.chip} data-tone="review">Requires validation</span>}</td></tr>
                  ))}
                </tbody>
              </table>
              <Link to={`/local-tax/rules/${e.year_of_assessment.replace('/', '-')}`} className={styles.chip}><BookOpen size={12} /> Open the YA {e.year_of_assessment} rules review</Link>
              <div className={styles.actions}>
                <Button size="sm" variant="secondary" disabled={analyse.isPending} onClick={() => analyse.mutate(undefined)}>
                  {analyse.isPending ? 'Local_Tax_AI is reviewing…' : 'Explain the tax treatment (AI)'}
                </Button>
              </div>
              {analyse.data && (
                <div className={styles.card}>
                  {analyse.data.summary && <p className={styles.muted}>{analyse.data.summary}</p>}
                  {analyse.data.items.map((i) => (
                    <p key={i.title} style={{ margin: 0 }}><strong>{i.title}</strong> — {i.text} <span className={styles.muted}>{i.reference}</span>
                      {i.needs_review && <span className={styles.chip} data-tone="review" style={{ marginLeft: 6 }}>Review</span>}</p>
                  ))}
                  {analyse.data.questions.map((q) => <p key={q} className={styles.muted}>Ask: {q}</p>)}
                </div>
              )}
              {analyse.isError && <p className={styles.error}>{extractErrorMessage(analyse.error)}</p>}
            </>
          )}
          {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
        </section>

        <div className={styles.side}>
          {company && (
            <section className={styles.card} aria-label="Tax Rate & Concessionary Rate">
              <h3 className={styles.cardTitle}><Percent size={18} aria-hidden="true" /> Tax Rate & Concessionary Rate</h3>
              <p className={styles.muted}>
                {(c.special_income ?? []).length
                  ? (c.special_income ?? []).map((s) => `${SPECIAL_RATES.find((r) => r[0] === s.rate_key)?.[1] ?? s.rate_key}: LKR ${money(s.amount)}`).join('; ')
                  : 'Standard rate. Add concessionary-rate income only where its conditions are met.'}
              </p>
              <Button size="sm" variant="subtle" onClick={() => setSection('special')}>Set concessionary income</Button>
            </section>
          )}
          {comp && (
            <section className={styles.card} aria-label="Tax Summary">
              <h3 className={styles.cardTitle}>Tax Summary</h3>
              <dl className={styles.summary}>
                {company && <div><dt>Accounting Profit (PBT)</dt><dd>LKR {money(comp.pbt)}</dd></div>}
                <div><dt>Taxable Income</dt><dd>LKR {money(comp.taxable_income)}</dd></div>
                <div><dt>Income Tax</dt><dd>LKR {money(comp.income_tax)}</dd></div>
                <div><dt>Tax Credits & Payments</dt><dd>(LKR {money(comp.credits)})</dd></div>
                <div data-total><dt>{Number(comp.payable) >= 0 ? 'Final Tax Payable' : 'Tax Refundable'}</dt><dd>LKR {money(Math.abs(Number(comp.payable)))}</dd></div>
              </dl>
            </section>
          )}
          {rev && (
            <section className={styles.card} aria-label="Expected vs. Calculated Tax">
              <h3 className={styles.cardTitle}><Target size={18} aria-hidden="true" /> Expected vs. Calculated Tax</h3>
              <dl className={styles.summary}>
                <div><dt>Expected Tax Payment</dt><dd>LKR {money(rev.expected)}</dd></div>
                <div><dt>Calculated Tax Payment</dt><dd>LKR {money(rev.calculated)}</dd></div>
              </dl>
              <p className={styles.diff} data-up={Number(rev.variance) > 0 || undefined}>
                Difference: LKR {money(Math.abs(Number(rev.variance)))} ({Number(rev.variance) > 0 ? 'Higher' : Number(rev.variance) < 0 ? 'Lower' : 'none'})
              </p>
              <Button variant="primary" onClick={() => setSection('reverse')}>Reverse Calculation & Adjust <ArrowRight size={14} /></Button>
            </section>
          )}
          <AiAssistant taskKey={taskKey} lead="I can help you check the concessionary rate eligibility, explain the tax treatment and review the calculation."
            suggestions={['Why is this expense disallowed?', 'How was the tax calculated?', 'What if travel expenses change by Rs. 100,000?']} />
          <Alerts alerts={state.alerts.filter((a) => a.stage === 'computation')} />
        </div>
      </div>
      <div className={styles.actions}>
        <StageControls taskKey={taskKey} state={state} stage="computation" />
        <Button variant="secondary" onClick={() => downloadLocalTax(taskKey, 'computation', 'pdf')}><Download size={14} /> Download Computation (PDF)</Button>
        <Button variant="secondary" onClick={() => downloadLocalTax(taskKey, 'computation', 'xlsx')}><FileSpreadsheet size={14} /> Download Working (Excel)</Button>
        <span className={styles.spacer} />
        <Button variant="primary" onClick={onNext}>Next: Draft Tax Return <ArrowRight size={14} /></Button>
      </div>
    </>
  )
}

function LineEditor({ title, rows, onSave, busy }: { title: string; rows: CompLine[]; onSave: (rows: CompLine[]) => void; busy: boolean }) {
  const [draft, setDraft] = useState<CompLine[]>(rows)
  const set = (i: number, p: Partial<CompLine>) => setDraft(draft.map((r, n) => (n === i ? { ...r, ...p } : r)))
  return (
    <>
      <h3 className={styles.cardTitle}>{title}</h3>
      <table className={styles.table}>
        <thead>
          <tr><th>Description</th><th className={styles.num}>Amount (LKR)</th><th>Note / reason</th><th /></tr>
        </thead>
        <tbody>
          {draft.map((r, i) => (
            <tr key={r.id ?? i}>
              <td className={styles.cell}><input aria-label="Description" value={r.label} onChange={(ev) => set(i, { label: ev.target.value })} /></td>
              <td className={styles.cell}><input aria-label="Amount" inputMode="decimal" value={r.amount} onChange={(ev) => set(i, { amount: ev.target.value })} /></td>
              <td className={styles.cell}><input aria-label="Note" value={r.note ?? ''} onChange={(ev) => set(i, { note: ev.target.value })} /></td>
              <td><Button size="sm" variant="subtle" iconOnly aria-label="Remove" onClick={() => setDraft(draft.filter((_, n) => n !== i))}><Trash2 size={13} /></Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => setDraft([...draft, { label: '', amount: '', note: '' }])}><Plus size={13} /> Add line</Button>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onSave(draft)}>Save and recalculate</Button>
      </div>
    </>
  )
}

function CapitalAllowances({ rows, onSave, busy }: { rows: { id?: string; label: string; asset_class: string; cost: string; amount: string }[]; onSave: (r: typeof rows) => void; busy: boolean }) {
  const [draft, setDraft] = useState(rows)
  const set = (i: number, p: Partial<(typeof rows)[number]>) => setDraft(draft.map((r, n) => (n === i ? { ...r, ...p } : r)))
  return (
    <>
      <h3 className={styles.cardTitle}>Capital allowances</h3>
      <p className={styles.hint}>Give the cost and the asset class for the year&apos;s rate, or enter the allowance itself.</p>
      <table className={styles.table}>
        <thead>
          <tr><th>Asset</th><th>Class</th><th className={styles.num}>Cost</th><th className={styles.num}>Allowance (blank: by rate)</th><th /></tr>
        </thead>
        <tbody>
          {draft.map((r, i) => (
            <tr key={r.id ?? i}>
              <td className={styles.cell}><input aria-label="Asset" value={r.label} onChange={(ev) => set(i, { label: ev.target.value })} /></td>
              <td className={styles.cell}>
                <select aria-label="Asset class" value={r.asset_class} onChange={(ev) => set(i, { asset_class: ev.target.value })}>
                  {ASSET_CLASSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </td>
              <td className={styles.cell}><input aria-label="Cost" inputMode="decimal" value={r.cost} onChange={(ev) => set(i, { cost: ev.target.value })} /></td>
              <td className={styles.cell}><input aria-label="Allowance" inputMode="decimal" value={r.amount} onChange={(ev) => set(i, { amount: ev.target.value })} /></td>
              <td><Button size="sm" variant="subtle" iconOnly aria-label="Remove" onClick={() => setDraft(draft.filter((_, n) => n !== i))}><Trash2 size={13} /></Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => setDraft([...draft, { label: '', asset_class: 'plant_machinery', cost: '', amount: '' }])}><Plus size={13} /> Add asset</Button>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onSave(draft)}>Save and recalculate</Button>
      </div>
    </>
  )
}

function SpecialIncome({ rows, onSave, busy }: { rows: { id?: string; label: string; amount: string; rate_key: string }[]; onSave: (r: typeof rows) => void; busy: boolean }) {
  const [draft, setDraft] = useState(rows)
  const set = (i: number, p: Partial<(typeof rows)[number]>) => setDraft(draft.map((r, n) => (n === i ? { ...r, ...p } : r)))
  return (
    <>
      <h3 className={styles.cardTitle}>Concessionary-rate income</h3>
      <p className={styles.validation}>
        Eligible income (e.g. foreign service income received in foreign currency) may be taxed at a concessionary rate, subject to the Inland Revenue Act and
        its conditions. Enter only the part of the taxable income that qualifies; the rest is taxed at the standard rate.
      </p>
      <table className={styles.table}>
        <thead>
          <tr><th>Income</th><th>Rate</th><th className={styles.num}>Taxable amount (LKR)</th><th /></tr>
        </thead>
        <tbody>
          {draft.map((r, i) => (
            <tr key={r.id ?? i}>
              <td className={styles.cell}><input aria-label="Income" value={r.label} onChange={(ev) => set(i, { label: ev.target.value })} /></td>
              <td className={styles.cell}>
                <select aria-label="Concessionary rate" value={r.rate_key} onChange={(ev) => set(i, { rate_key: ev.target.value })}>
                  {SPECIAL_RATES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </td>
              <td className={styles.cell}><input aria-label="Taxable amount" inputMode="decimal" value={r.amount} onChange={(ev) => set(i, { amount: ev.target.value })} /></td>
              <td><Button size="sm" variant="subtle" iconOnly aria-label="Remove" onClick={() => setDraft(draft.filter((_, n) => n !== i))}><Trash2 size={13} /></Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => setDraft([...draft, { label: 'Qualifying export service income', amount: '', rate_key: 'qualifying_export_services' }])}>
          <Plus size={13} /> Add concessionary income
        </Button>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onSave(draft)}>Save and recalculate</Button>
      </div>
    </>
  )
}
