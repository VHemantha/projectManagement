import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  ClipboardList,
  Coins,
  FileText,
  FileUp,
  Home,
  Layers,
  Plus,
  Receipt,
  Save,
  Sparkles,
  Target,
  Trash2,
  User,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import styles from './LocalTax.module.css'
import { AiAssistant, Alerts, Completion, SectionNav, StageControls } from './Shared'
import { SupportingDocuments } from './SupportingDocuments'
import { extractErrorMessage } from '@/api/errors'
import {
  type AssetLine,
  type Engagement,
  type EngagementData,
  type IncomeLine,
  type LiabilityLine,
  type LocalTaxState,
  type PaymentLine,
  money,
  useSaveLocalTax,
} from '@/api/localTax'
import { UpdateButton } from './Update'
import { Button } from '@/design-system'

export type ClientInfoSection = 'client' | 'documents' | 'income' | 'expenses' | 'assets' | 'payments' | 'expected'
type Section = ClientInfoSection
const SECTIONS: { key: Section; label: string; icon: React.ReactNode }[] = [
  { key: 'client', label: 'A. Client Details', icon: <User size={16} /> },
  { key: 'documents', label: 'B. Supporting Documents', icon: <FileUp size={16} /> },
  { key: 'income', label: 'C. Income Sources', icon: <Coins size={16} /> },
  { key: 'expenses', label: 'D. Expenses', icon: <Layers size={16} /> },
  { key: 'assets', label: 'E. Assets & Liabilities', icon: <Home size={16} /> },
  { key: 'payments', label: 'F. Tax Credits & Payments', icon: <Receipt size={16} /> },
  { key: 'expected', label: 'G. Expected Tax Payment', icon: <Target size={16} /> },
]
const CATEGORIES: [string, string][] = [
  ['employment', 'Employment income'], ['business', 'Business / professional'], ['rent', 'Rental income'], ['interest', 'Interest income'],
  ['dividend', 'Dividend income'], ['foreign_service', 'Foreign service income'], ['foreign_other', 'Other foreign-source income'],
  ['investment_gain', 'Gains from investment assets'], ['other', 'Other income'],
]
const TREATMENTS: [IncomeLine['treatment'], string][] = [
  ['auto', 'Decide by the rules'], ['taxable', 'Taxable'], ['exempt', 'Exempt'], ['final_wht', 'Final withholding'], ['special_rate', 'Special rate'],
]
const EXPENSE_CLASSES: [string, string][] = [['allowable', 'Allowable'], ['disallowable', 'Disallowable'], ['capital', 'Capital'], ['clarify', 'Needs clarifying']]
const PAYMENT_TYPES: [string, string][] = [
  ['APIT', 'APIT'], ['AIT', 'AIT'], ['WHT', 'WHT (creditable)'], ['provisional', 'Provisional instalment'], ['foreign_tax_credit', 'Foreign tax credit'],
  ['final_wht', 'Final withholding (not a credit)'], ['other', 'Other credit'],
]

const TAX_TYPE = { company: 'CIT', partnership: 'PIT', individual: 'IIT' } as const
// A company's figures come from its trial balance (AFIT, 26 Nov 2026): no income, expense or asset and liability
// sections to fill in - the TB is attached under Supporting Documents.
const COMPANY_HIDDEN = new Set<Section>(['income', 'expenses', 'assets'])
const sectionsFor = (entity: string) =>
  SECTIONS.filter((s) => entity !== 'company' || !COMPANY_HIDDEN.has(s.key))
    .map((s, n) => ({ ...s, label: `${String.fromCharCode(65 + n)}. ${s.label.slice(3)}` }))

type Basics = Pick<Engagement, 'legal_name' | 'client_name' | 'tin' | 'nic_or_reg' | 'address' | 'entity_type' | 'residency' | 'year_of_assessment' |
  'fy_end' | 'tax_type' | 'activity' | 'expected_tax' | 'expected_basis' | 'audited'>

function basicsOf(e: Engagement): Basics {
  const { legal_name, client_name, tin, nic_or_reg, address, entity_type, residency, year_of_assessment, fy_end, tax_type, activity, expected_tax,
    expected_basis, audited } = e
  return { legal_name, client_name, tin, nic_or_reg, address, entity_type, residency, year_of_assessment, fy_end, tax_type, activity, expected_tax, expected_basis,
    audited }
}

const emptyIncome = (): IncomeLine => ({ category: 'business', description: '', amount: '', treatment: 'auto', expenses: [] })

/** Stage 1, Client Info (AFIT screens): client details and the financial statements required, the supporting
 * documents (uploaded or from the client's Google Drive folder, read by Local_Tax_AI to pre-fill the rest, each value
 * verified by the accountant), income (with foreign income), expenses by income source, assets and liabilities, tax
 * payments and credits, and the expected tax payment. Saved as it is typed; Back and Next keep everything entered. */
export function QuestionnaireStage({ taskKey, state, onNext, section: initial = 'client' }: {
  taskKey: string; state: LocalTaxState; onNext: () => void; section?: Section
}) {
  const e = state.engagement
  const save = useSaveLocalTax(taskKey)
  const [chosen, setSection] = useState<Section>(initial)
  const [basics, setBasics] = useState<Basics>(() => basicsOf(e))
  const [data, setData] = useState<EngagementData>(() => e.data ?? {})
  const [dirty, setDirty] = useState(false)
  const timer = useRef<number | null>(null)
  // A value confirmed from the documents changes the client info on the server: take it in (nothing typed is lost -
  // the screen only refreshes while there are no unsaved changes).
  const seen = useRef(e.version)
  useEffect(() => {
    if (e.version !== seen.current && !dirty && !save.isPending) {
      seen.current = e.version
      setBasics(basicsOf(e))
      setData(e.data ?? {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e.version, dirty, save.isPending])
  const go = (s: Section) => {
    setSection(s)
    document.querySelector('[data-localtax-top]')?.scrollIntoView?.({ block: 'start' })
  }
  const from = (field: string) => e.data.field_sources?.[field]

  const payload = () => ({ ...basics, data: { income: data.income ?? [], assets: data.assets ?? [], liabilities: data.liabilities ?? [],
    payments: data.payments ?? [], qualifying_payments: data.qualifying_payments ?? '', losses_bf: data.losses_bf ?? '',
    expected_skipped: !!data.expected_skipped, fs_scope: data.fs_scope ?? 'full', directors: data.directors ?? '',
    company_secretary: data.company_secretary ?? '', shares_issued: data.shares_issued ?? '' }, stage: 'questionnaire' as const })
  const flush = (then?: () => void) => {
    if (timer.current) window.clearTimeout(timer.current)
    save.mutate(payload(), { onSuccess: () => (setDirty(false), then?.()) })
  }
  // Autosave: a moment after the last change.
  useEffect(() => {
    if (!dirty) return
    timer.current = window.setTimeout(() => flush(), 1500)
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basics, data, dirty])

  const setB = <K extends keyof Basics>(k: K, v: Basics[K]) => (setBasics((b) => ({ ...b, [k]: v })), setDirty(true))
  const setD = (patch: Partial<EngagementData>) => (setData((d) => ({ ...d, ...patch })), setDirty(true))
  const income = data.income ?? []
  const setIncome = (i: number, patch: Partial<IncomeLine>) => setD({ income: income.map((x, n) => (n === i ? { ...x, ...patch } : x)) })
  const errors = (save.error as { response?: { data?: Record<string, string> } } | null)?.response?.data ?? {}
  const SECTIONS_SHOWN = sectionsFor(basics.entity_type)
  const section: Section = SECTIONS_SHOWN.some((s) => s.key === chosen) ? chosen : 'client'
  const idx = SECTIONS_SHOWN.findIndex((s) => s.key === section)
  const saveFirst = () => (dirty ? save.mutateAsync(payload()).then(() => setDirty(false)) : Promise.resolve())

  return (
    <>
      <div className={styles.stageHead}>
        <ClipboardList size={22} className={styles.stageIcon} aria-hidden="true" />
        <div>
          <h2 className={styles.stageTitle}>Client Info</h2>
          <p className={styles.stageLead}>
            {basics.entity_type === 'company'
              ? 'Client details, the report required, the trial balance and supporting documents, and tax payments.'
              : 'Client details, supporting documents (pre-filled by AI, verified by you), income, expenses, assets, liabilities and tax payments.'}
          </p>
        </div>
        <span className={styles.spacer} />
        <div className={styles.actions}>
          <span className={styles.muted} role="status">{save.isPending ? 'Saving…' : dirty ? 'Unsaved changes' : 'All changes saved'}</span>
          <UpdateButton taskKey={taskKey} stage="questionnaire" before={saveFirst} />
          <Button variant="secondary" onClick={() => flush()} disabled={save.isPending}>
            <Save size={15} /> Save Draft
          </Button>
          <Button variant="primary" onClick={() => flush(onNext)} disabled={save.isPending}>
            Save & Continue <ArrowRight size={15} />
          </Button>
        </div>
      </div>
      <StageControls taskKey={taskKey} state={state} stage="questionnaire" />
      {save.isError && <p className={styles.error}>{Object.values(errors).join(' ') || extractErrorMessage(save.error)}</p>}

      <div className={styles.columns}>
        <div className={styles.card}>
          <SectionNav items={SECTIONS_SHOWN} value={section} onChange={go} label="Client info sections" />
          <Completion pct={state.progress?.questionnaire ?? 0} />
        </div>

        <section className={styles.card} aria-label={SECTIONS_SHOWN[idx].label}>
          <h3 className={styles.cardTitle}>{SECTIONS_SHOWN[idx].label}</h3>
          {section === 'client' && (
            <div className={styles.formGrid}>
              <label className={styles.field}>
                <span>Legal Name <span className={styles.req}>*</span></span>
                <input value={basics.legal_name} onChange={(ev) => setB('legal_name', ev.target.value)} />
                <FieldSource text={from('legal_name')} />
              </label>
              <label className={styles.field}>
                <span>TIN <span className={styles.req}>*</span></span>
                <input value={basics.tin} onChange={(ev) => setB('tin', ev.target.value)} />
                <FieldSource text={from('tin')} />
              </label>
              <label className={styles.field}>
                <span>Entity Type <span className={styles.req}>*</span></span>
                <select value={basics.entity_type} onChange={(ev) => (setB('entity_type', ev.target.value as Basics['entity_type']),
                  setB('tax_type', TAX_TYPE[ev.target.value as Basics['entity_type']]))}>
                  <option value="company">Company</option>
                  <option value="partnership">Partnership</option>
                  <option value="individual">Individual</option>
                </select>
              </label>
              <label className={styles.field}>
                <span>{{ company: 'Registration No.', partnership: 'Business Registration No.', individual: 'NIC No.' }[basics.entity_type]}</span>
                <input value={basics.nic_or_reg} onChange={(ev) => setB('nic_or_reg', ev.target.value)} />
                <FieldSource text={from('nic_or_reg')} />
              </label>
              <label className={styles.field}>
                <span>Tax Residency <span className={styles.req}>*</span></span>
                <select value={basics.residency} onChange={(ev) => setB('residency', ev.target.value as Basics['residency'])}>
                  <option value="resident">Resident</option>
                  <option value="non_resident">Non-resident</option>
                </select>
              </label>
              <label className={styles.field}>
                <span>Year of Assessment <span className={styles.req}>*</span></span>
                <select value={basics.year_of_assessment} onChange={(ev) => setB('year_of_assessment', ev.target.value)}>
                  {state.years.map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </label>
              <label className={styles.field}>
                <span>Financial Year End <span className={styles.req}>*</span></span>
                <input type="date" value={basics.fy_end ?? ''} onChange={(ev) => setB('fy_end', ev.target.value || null)} />
                <FieldSource text={from('fy_end')} />
              </label>
              <label className={styles.field}>
                <span>Tax Type <span className={styles.req}>*</span></span>
                <select value={basics.tax_type} onChange={(ev) => setB('tax_type', ev.target.value as Basics['tax_type'])}>
                  <option value="CIT">Corporate Income Tax</option>
                  <option value="PIT">Partnership Income Tax</option>
                  <option value="IIT">Individual Income Tax</option>
                </select>
              </label>
              <label className={`${styles.field} ${styles.wide}`}>
                <span>Nature of Business / Main Activity <span className={styles.req}>*</span></span>
                <textarea rows={2} value={basics.activity} onChange={(ev) => setB('activity', ev.target.value)} maxLength={1000} />
                <FieldSource text={from('activity')} />
              </label>
              <label className={`${styles.field} ${styles.wide}`}>
                <span>Address (optional)</span>
                <input value={basics.address} onChange={(ev) => setB('address', ev.target.value)} maxLength={500} />
                <FieldSource text={from('address')} />
              </label>
              {(
                <>
                  <fieldset className={`${styles.field} ${styles.wide}`} style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend><span>Financial statements required <span className={styles.req}>*</span></span></legend>
                    <div className={styles.actions}>
                      <label className={styles.check}>
                        <input type="radio" name="fs_scope" checked={(data.fs_scope ?? 'full') === 'income_statement'} onChange={() => setD({ fs_scope: 'income_statement' })} />
                        Income statement only
                      </label>
                      <label className={styles.check}>
                        <input type="radio" name="fs_scope" checked={(data.fs_scope ?? 'full') === 'full'} onChange={() => setD({ fs_scope: 'full' })} />
                        Full set of financial statements
                      </label>
                    </div>
                    <span className={styles.hint}>
                      {(data.fs_scope ?? 'full') === 'full'
                        ? 'Income statement, financial position, changes in equity, cash flows, accounting policies and notes.'
                        : 'A one-page income statement, account by account (the sole proprietor format); the trial balance may hold just the income and expense accounts.'}
                      {basics.entity_type === 'individual' && ' For an individual, the statements are prepared from the trial balance (Supporting Documents) when the business keeps books; otherwise from the income and expenses entered.'}
                    </span>
                  </fieldset>
                  <fieldset className={`${styles.field} ${styles.wide}`} style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend><span>Report on the financial statements <span className={styles.req}>*</span></span></legend>
                    <div className={styles.actions}>
                      <label className={styles.check}>
                        <input type="radio" name="report_type" checked={!!basics.audited} onChange={() => setB('audited', true)} />
                        Audit report
                      </label>
                      <label className={styles.check}>
                        <input type="radio" name="report_type" checked={!basics.audited} onChange={() => setB('audited', false)} />
                        Compilation report
                      </label>
                    </div>
                    <span className={styles.hint}>
                      {basics.audited
                        ? "The independent auditor's report, in the firm's format, issued with the financial statements."
                        : "The compilation report (SLSRS 4410), in the firm's format: no assurance is expressed."}
                    </span>
                  </fieldset>
                  <label className={`${styles.field} ${styles.wide}`}>
                    <span>{{ company: 'Directors', partnership: 'Partners', individual: 'Proprietor' }[basics.entity_type]} (for the financial statements)</span>
                    <input value={data.directors ?? ''} placeholder={basics.entity_type === 'individual' ? 'e.g. Mr. A. Perera' : 'e.g. Mr. A. Perera, Ms. B. Silva'} onChange={(ev) => setD({ directors: ev.target.value })} maxLength={500} />
                  </label>
                  {basics.entity_type === 'company' && (data.fs_scope ?? 'full') === 'full' && (
                    <>
                      <label className={styles.field}>
                        <span>Company secretary</span>
                        <input value={data.company_secretary ?? ''} placeholder="e.g. ABC Secretarial Services (Pvt) Ltd" onChange={(ev) => setD({ company_secretary: ev.target.value })} maxLength={300} />
                      </label>
                      <label className={styles.field}>
                        <span>Shares issued (stated capital note)</span>
                        <input value={data.shares_issued ?? ''} placeholder="e.g. 100,000 ordinary shares" onChange={(ev) => setD({ shares_issued: ev.target.value })} maxLength={120} />
                      </label>
                    </>
                  )}
                </>
              )}
            </div>
          )}

          {section === 'income' && (
            <>
              <p className={styles.hint}>Add every income source with its amount. For foreign income, give the currency, amount and rate: the LKR amount is worked out.</p>
              {income.map((inc, i) => (
                <IncomeRow key={inc.id ?? i} inc={inc} onChange={(p) => setIncome(i, p)} onRemove={() => setD({ income: income.filter((_, n) => n !== i) })} />
              ))}
              <Button variant="subtle" size="sm" onClick={() => setD({ income: [...income, emptyIncome()] })}>
                <Plus size={14} /> Add income source
              </Button>
            </>
          )}

          {section === 'expenses' && (
            <>
              <p className={styles.hint}>The expenses of each income source. Mark each allowable, disallowable, capital or needing clarification.</p>
              {income.length === 0 && <p className={styles.muted}>Add the income sources first.</p>}
              {income.map((inc, i) => (
                <div key={inc.id ?? i} className={styles.card} style={{ background: 'var(--tf-surface-sunken)' }}>
                  <strong>{inc.description || CATEGORIES.find((c) => c[0] === inc.category)?.[1]}: {money(inc.amount)}</strong>
                  <table className={styles.table}>
                    <thead>
                      <tr><th>Expense</th><th className={styles.num}>Amount (LKR)</th><th>Classification</th><th /></tr>
                    </thead>
                    <tbody>
                      {inc.expenses.map((ex, j) => (
                        <tr key={ex.id ?? j}>
                          <td className={styles.cell}>
                            <input aria-label="Expense" value={ex.description}
                              onChange={(ev) => setIncome(i, { expenses: inc.expenses.map((x, n) => (n === j ? { ...x, description: ev.target.value } : x)) })} />
                          </td>
                          <td className={styles.cell}>
                            <input aria-label="Expense amount" inputMode="decimal" value={ex.amount}
                              onChange={(ev) => setIncome(i, { expenses: inc.expenses.map((x, n) => (n === j ? { ...x, amount: ev.target.value } : x)) })} />
                          </td>
                          <td className={styles.cell}>
                            <select aria-label="Classification" value={ex.classification}
                              onChange={(ev) => setIncome(i, { expenses: inc.expenses.map((x, n) => (n === j ? { ...x, classification: ev.target.value as typeof x.classification } : x)) })}>
                              {EXPENSE_CLASSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                          </td>
                          <td>
                            <Button size="sm" variant="subtle" iconOnly aria-label="Remove expense"
                              onClick={() => setIncome(i, { expenses: inc.expenses.filter((_, n) => n !== j) })}>
                              <Trash2 size={13} />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <Button variant="subtle" size="sm"
                    onClick={() => setIncome(i, { expenses: [...inc.expenses, { description: '', amount: '', classification: 'clarify' }] })}>
                    <Plus size={14} /> Add expense
                  </Button>
                </div>
              ))}
            </>
          )}

          {section === 'assets' && (
            <>
              <LinesTable<AssetLine> title="Assets" rows={data.assets ?? []} onChange={(rows) => setD({ assets: rows })}
                kinds={[['immovable', 'Immovable (land, buildings)'], ['vehicle', 'Motor vehicle'], ['investment', 'Investment'], ['shares', 'Shares'],
                  ['bank', 'Bank balance'], ['movable', 'Other movable'], ['other', 'Other']]}
                blank={{ kind: 'immovable', description: '', value: '', ownership: '' }} extra={['ownership', 'Ownership']} />
              <LinesTable<LiabilityLine> title="Liabilities" rows={data.liabilities ?? []} onChange={(rows) => setD({ liabilities: rows })}
                kinds={[['loan', 'Loan'], ['mortgage', 'Mortgage'], ['other', 'Other obligation']]}
                blank={{ kind: 'loan', description: '', value: '', lender: '' }} extra={['lender', 'Lender']} />
            </>
          )}

          {section === 'payments' && (
            <>
              <p className={styles.hint}>Final withholding taxes are shown but never credited, so nothing is counted twice.</p>
              <table className={styles.table}>
                <thead>
                  <tr><th>Type</th><th className={styles.num}>Amount (LKR)</th><th>Date</th><th>Reference</th><th /></tr>
                </thead>
                <tbody>
                  {(data.payments ?? []).map((p, i) => {
                    const set = (patch: Partial<PaymentLine>) => setD({ payments: (data.payments ?? []).map((x, n) => (n === i ? { ...x, ...patch } : x)) })
                    return (
                      <tr key={p.id ?? i}>
                        <td className={styles.cell}>
                          <select aria-label="Payment type" value={p.type} onChange={(ev) => set({ type: ev.target.value })}>
                            {PAYMENT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                          </select>
                        </td>
                        <td className={styles.cell}><input aria-label="Payment amount" inputMode="decimal" value={p.amount} onChange={(ev) => set({ amount: ev.target.value })} /></td>
                        <td className={styles.cell}><input aria-label="Payment date" type="date" value={p.date ?? ''} onChange={(ev) => set({ date: ev.target.value })} /></td>
                        <td className={styles.cell}><input aria-label="Reference" value={p.reference ?? ''} onChange={(ev) => set({ reference: ev.target.value })} /></td>
                        <td>
                          <Button size="sm" variant="subtle" iconOnly aria-label="Remove payment"
                            onClick={() => setD({ payments: (data.payments ?? []).filter((_, n) => n !== i) })}>
                            <Trash2 size={13} />
                          </Button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <Button variant="subtle" size="sm" onClick={() => setD({ payments: [...(data.payments ?? []), { type: 'AIT', amount: '', date: '', reference: '' }] })}>
                <Plus size={14} /> Add payment or credit
              </Button>
              <div className={styles.formGrid}>
                <label className={styles.field}>
                  <span>Qualifying payments (LKR)</span>
                  <input inputMode="decimal" value={data.qualifying_payments ?? ''} onChange={(ev) => setD({ qualifying_payments: ev.target.value })} />
                </label>
                <label className={styles.field}>
                  <span>Tax losses brought forward (LKR)</span>
                  <input inputMode="decimal" value={data.losses_bf ?? ''} onChange={(ev) => setD({ losses_bf: ev.target.value })} />
                </label>
              </div>
            </>
          )}

          {section === 'documents' && <SupportingDocuments taskKey={taskKey} isCompany={basics.entity_type !== 'individual'} tbCount={state.financials?.tb?.length ?? 0} state={state} />}

          {section === 'expected' && (
            <div className={styles.formGrid}>
              <label className={styles.field}>
                <span>Client&apos;s expected tax payment (LKR, optional)</span>
                <input inputMode="decimal" value={basics.expected_tax ?? ''} onChange={(ev) => setB('expected_tax', ev.target.value || null)} />
              </label>
              <label className={styles.field}>
                <span>The expected amount is</span>
                <select value={basics.expected_basis} onChange={(ev) => setB('expected_basis', ev.target.value as Basics['expected_basis'])}>
                  <option value="total">The total tax liability</option>
                  <option value="remaining">The remaining payable after credits and instalments</option>
                </select>
              </label>
              <p className={`${styles.hint} ${styles.wide}`}>
                With an expected payment, the tax computation compares it with the calculated tax and opens the reverse tax analysis.
              </p>
              <label className={`${styles.check} ${styles.wide}`}>
                <input type="checkbox" checked={!!data.expected_skipped} onChange={(ev) => setD({ expected_skipped: ev.target.checked })} />
                The client has not given an expected payment
              </label>
            </div>
          )}

          <div className={styles.actions} style={{ justifyContent: 'flex-end' }}>
            {idx > 0 && (
              <Button variant="secondary" onClick={() => go(SECTIONS_SHOWN[idx - 1].key)}>
                <ArrowLeft size={14} /> Back: {SECTIONS_SHOWN[idx - 1].label.slice(3)}
              </Button>
            )}
            {idx < SECTIONS_SHOWN.length - 1 ? (
              <Button variant="primary" onClick={() => go(SECTIONS_SHOWN[idx + 1].key)}>
                Next: {SECTIONS_SHOWN[idx + 1].label.slice(3)} <ArrowRight size={14} />
              </Button>
            ) : (
              <Button variant="primary" onClick={() => flush(onNext)}>
                Next: Financial Statements <ArrowRight size={14} />
              </Button>
            )}
          </div>
        </section>

        <div className={styles.side}>
          <AiAssistant taskKey={taskKey} lead="I can help you complete the client info, classify income and explain tax treatments."
            suggestions={['Which of these income sources are taxable, exempt or final withholding?', 'What documents are still missing?']} />
          <section className={styles.card} aria-label="Quick Guide">
            <h3 className={styles.cardTitle}><BookOpen size={18} aria-hidden="true" /> Quick Guide</h3>
            <ul className={styles.ticks}>
              {['Enter basic client and tax details.', 'Add all income sources (local and foreign).', 'Include related expenses.',
                'Provide assets and liabilities (for individuals).', 'Add tax credits and payments.', 'Upload the TB and supporting documents, or link the client’s Drive folder; verify what the AI pre-fills.'].map((t) => (
                <li key={t}><Sparkles size={14} aria-hidden="true" /> {t}</li>
              ))}
            </ul>
          </section>
          <Alerts alerts={state.alerts.filter((a) => a.stage === 'questionnaire')} />
        </div>
      </div>
    </>
  )
}

function IncomeRow({ inc, onChange, onRemove }: { inc: IncomeLine; onChange: (p: Partial<IncomeLine>) => void; onRemove: () => void }) {
  const foreign = inc.category === 'foreign_service' || inc.category === 'foreign_other'
  const f = inc.foreign ?? { country: '', currency: '', foreign_amount: '', rate: '', service_used_outside: false, received_in_fx_through_bank: false, foreign_tax_paid: '' }
  const setF = (p: Partial<typeof f>) => onChange({ foreign: { ...f, ...p } })
  return (
    <div className={styles.card} style={{ background: 'var(--tf-surface-sunken)' }} aria-label={`Income: ${inc.description || inc.category}`}>
      <div className={styles.formGrid}>
        <label className={styles.field}>
          <span>Category</span>
          <select value={inc.category} onChange={(ev) => onChange({ category: ev.target.value })}>
            {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className={styles.field}>
          <span>Treatment</span>
          <select value={inc.treatment} onChange={(ev) => onChange({ treatment: ev.target.value as IncomeLine['treatment'] })}>
            {TREATMENTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className={styles.field}>
          <span>Description</span>
          <input value={inc.description} onChange={(ev) => onChange({ description: ev.target.value })} />
        </label>
        <label className={styles.field}>
          <span>Amount (LKR)</span>
          <input inputMode="decimal" value={inc.amount} disabled={foreign && !!f.foreign_amount && !!f.rate}
            onChange={(ev) => onChange({ amount: ev.target.value })} />
        </label>
        {foreign && (
          <>
            <label className={styles.field}><span>Country</span><input value={f.country} onChange={(ev) => setF({ country: ev.target.value })} /></label>
            <label className={styles.field}><span>Currency</span><input value={f.currency} maxLength={3} onChange={(ev) => setF({ currency: ev.target.value })} /></label>
            <label className={styles.field}><span>Foreign amount</span><input inputMode="decimal" value={f.foreign_amount} onChange={(ev) => setF({ foreign_amount: ev.target.value })} /></label>
            <label className={styles.field}><span>Exchange rate (LKR)</span><input inputMode="decimal" value={f.rate} onChange={(ev) => setF({ rate: ev.target.value })} /></label>
            <label className={styles.check}>
              <input type="checkbox" checked={f.service_used_outside} onChange={(ev) => setF({ service_used_outside: ev.target.checked })} />
              The service is used outside Sri Lanka
            </label>
            <label className={styles.check}>
              <input type="checkbox" checked={f.received_in_fx_through_bank} onChange={(ev) => setF({ received_in_fx_through_bank: ev.target.checked })} />
              Received in foreign currency through a bank
            </label>
            <label className={styles.field}><span>Foreign tax paid</span><input inputMode="decimal" value={f.foreign_tax_paid} onChange={(ev) => setF({ foreign_tax_paid: ev.target.value })} /></label>
          </>
        )}
      </div>
      <div className={styles.actions} style={{ justifyContent: 'space-between' }}>
        <span className={styles.muted}>{inc.lkr_amount ? `LKR equivalent: ${money(inc.lkr_amount)}` : ''}</span>
        <Button size="sm" variant="subtle" onClick={onRemove}><Trash2 size={13} /> Remove</Button>
      </div>
    </div>
  )
}

function LinesTable<T extends { kind: string; description: string; value: string }>({ title, rows, onChange, kinds, blank, extra }: {
  title: string
  rows: T[]
  onChange: (rows: T[]) => void
  kinds: [string, string][]
  blank: T
  extra: [keyof T & string, string]
}) {
  const set = (i: number, patch: Partial<T>) => onChange(rows.map((r, n) => (n === i ? { ...r, ...patch } : r)))
  return (
    <>
      <h4 style={{ margin: '8px 0 0' }}>{title}</h4>
      <table className={styles.table} aria-label={title}>
        <thead>
          <tr><th>Kind</th><th>Description</th><th>{extra[1]}</th><th className={styles.num}>Value (LKR)</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className={styles.cell}>
                <select aria-label="Kind" value={r.kind} onChange={(ev) => set(i, { kind: ev.target.value } as Partial<T>)}>
                  {kinds.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </td>
              <td className={styles.cell}><input aria-label="Description" value={r.description} onChange={(ev) => set(i, { description: ev.target.value } as Partial<T>)} /></td>
              <td className={styles.cell}>
                <input aria-label={extra[1]} value={String(r[extra[0]] ?? '')} onChange={(ev) => set(i, { [extra[0]]: ev.target.value } as Partial<T>)} />
              </td>
              <td className={styles.cell}><input aria-label="Value" inputMode="decimal" value={r.value} onChange={(ev) => set(i, { value: ev.target.value } as Partial<T>)} /></td>
              <td><Button size="sm" variant="subtle" iconOnly aria-label="Remove" onClick={() => onChange(rows.filter((_, n) => n !== i))}><Trash2 size={13} /></Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button variant="subtle" size="sm" onClick={() => onChange([...rows, { ...blank }])}><Plus size={14} /> Add</Button>
    </>
  )
}

/** Where a value pre-filled from the documents came from (and whether it was changed by hand since). */
function FieldSource({ text }: { text?: string }) {
  return text ? <span className={styles.hint}><FileText size={11} aria-hidden="true" /> From: {text}</span> : null
}
