import { BarChart3, BookOpen, Download, FileSpreadsheet, FileText, GitBranch, Landmark, Plus, Scale, ShieldCheck, Sparkles, Table2, Trash2, Wallet } from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'

import styles from './LocalTax.module.css'
import { Adjustments } from './Adjustments'
import { AuditReport, CashFlowStatement, EquityStatement, NotesView, PoliciesView } from './Statements'
import { AiAssistant, Alerts, Completion, SectionNav, StageControls } from './Shared'
import { extractErrorMessage } from '@/api/errors'
import {
  type Financials,
  type LocalTaxState,
  type PlFigures,
  downloadLocalTax,
  money,
  useAiAgent,
  useMapLine,
  useProposeAdjustment,
  usePutTb,
  useSaveLocalTax,
} from '@/api/localTax'
import { Button } from '@/design-system'

type Section = 'pl' | 'bs' | 'equity' | 'cash' | 'notes' | 'policies' | 'audit' | 'tb' | 'journals'
const HEADINGS: [string, string][] = [
  ['revenue', 'Revenue'], ['cost_of_sales', 'Cost of sales'], ['other_income', 'Other income'], ['admin_expenses', 'Administrative expenses'],
  ['distribution_expenses', 'Selling and distribution expenses'], ['finance_costs', 'Finance costs'], ['income_tax_expense', 'Income tax expense'],
  ['oci', 'Other comprehensive income'], ['ppe', 'Property, plant and equipment'], ['intangibles', 'Intangible assets'], ['investments', 'Investments'],
  ['inventories', 'Inventories'], ['trade_receivables', 'Trade and other receivables'], ['other_current_assets', 'Other current assets'],
  ['cash', 'Cash and cash equivalents'], ['share_capital', 'Stated capital'], ['reserves', 'Reserves'], ['retained_earnings', 'Retained earnings'], ['dividends', 'Dividends'],
  ['borrowings_non_current', 'Non-current borrowings'], ['deferred_tax', 'Deferred tax'], ['borrowings_current', 'Current borrowings'],
  ['trade_payables', 'Trade and other payables'], ['tax_payable', 'Income tax payable'], ['other_current_liabilities', 'Other current liabilities'],
]

/** Stage 2 (AFIT screens, 22 Nov 2026): the statements from the mapped trial balance (companies) or the statement
 * of income and expenses (individuals), with the framework, the comparatives, the checks, journals and the draft
 * audit report template. Every figure is the engine's; Local_Tax_AI suggests headings and explains. */
export function FinancialStatementsStage({ taskKey, state, onNext, onBack, onDocuments }: {
  taskKey: string; state: LocalTaxState; onNext: () => void; onBack?: () => void; onDocuments?: () => void
}) {
  const e = state.engagement
  const fin = state.financials
  const save = useSaveLocalTax(taskKey)
  const company = e.entity_type === 'company'
  const [section, setSection] = useState<Section>(company ? 'pl' : 'pl')
  const incomeOnly = (e.data.fs_scope ?? 'full') === 'income_statement'
  const sections: { key: Section; label: string; icon: React.ReactNode }[] = company && incomeOnly
    ? [
        { key: 'pl', label: 'Income Statement', icon: <BarChart3 size={16} /> },
        { key: 'notes', label: 'Notes', icon: <FileText size={16} /> },
        { key: 'policies', label: 'Accounting Policies', icon: <BookOpen size={16} /> },
        ...(e.audited ? [{ key: 'audit' as Section, label: 'Audit Report (Draft)', icon: <ShieldCheck size={16} /> }] : []),
        { key: 'tb', label: 'TB Mapping', icon: <GitBranch size={16} /> },
        { key: 'journals', label: 'Adjustments', icon: <Scale size={16} /> },
      ]
    : company
    ? [
        { key: 'pl', label: 'Profit or Loss (P&L)', icon: <BarChart3 size={16} /> },
        { key: 'bs', label: 'Financial Position', icon: <FileText size={16} /> },
        { key: 'equity', label: 'Changes in Equity', icon: <Landmark size={16} /> },
        { key: 'cash', label: 'Cash Flows', icon: <Wallet size={16} /> },
        { key: 'notes', label: 'Notes to the FS', icon: <FileText size={16} /> },
        { key: 'policies', label: 'Accounting Policies', icon: <BookOpen size={16} /> },
        { key: 'audit', label: 'Audit Report (Draft)', icon: <ShieldCheck size={16} /> },
        { key: 'tb', label: 'TB Mapping', icon: <GitBranch size={16} /> },
        { key: 'journals', label: 'Adjustments', icon: <Scale size={16} /> },
      ]
    : [{ key: 'pl', label: 'Income & Expenses', icon: <BarChart3 size={16} /> }, { key: 'journals', label: 'Adjustments', icon: <Scale size={16} /> }]
  const year = e.fy_end ? new Date(e.fy_end) : null
  const ye = year ? year.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : 'the year end'
  const checks = fin?.checks ?? []

  return (
    <>
      <div className={styles.stageHead}>
        <FileText size={22} className={styles.stageIcon} aria-hidden="true" />
        <div>
          <h2 className={styles.stageTitle}>Financial Statements</h2>
          <p className={styles.stageLead}>Generate, review and edit financial statements{company && e.audited ? ' and the audit report' : ''}.</p>
        </div>
        <span className={styles.spacer} />
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => setSection('tb')} disabled={!company}><GitBranch size={15} /> View TB Mapping</Button>
          <Button variant="secondary" onClick={() => setSection('journals')}>
            <Scale size={15} /> Adjustments ({state.adjustments.filter((a) => a.scope === 'accounting' && a.status !== 'rejected').length})
          </Button>
        </div>
      </div>
      {company && (
        <div className={styles.card}>
          <div className={styles.formGrid} style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))' }}>
            <label className={styles.field}>
              <span>Reporting Framework</span>
              <select value={e.reporting_framework} onChange={(ev) => save.mutate({ reporting_framework: ev.target.value as typeof e.reporting_framework, stage: 'fs' })}>
                <option value="full">Full LKAS/SLFRS</option>
                <option value="smes">SLFRS for SMEs</option>
                <option value="smaller">SLAS for Smaller Entities</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>Financial Year End</span>
              <input type="date" value={e.fy_end ?? ''} onChange={(ev) => save.mutate({ fy_end: ev.target.value || null, stage: 'fs' })} />
            </label>
            <label className={styles.field}>
              <span>Comparative Year</span>
              <input readOnly value={year ? `${year.getDate()} ${year.toLocaleString('en-GB', { month: 'short' })} ${year.getFullYear() - 1}` : '—'} />
            </label>
            <label className={styles.field}>
              <span>Engagement Type</span>
              <select value={e.audited ? 'audit' : 'unaudited'} onChange={(ev) => save.mutate({ audited: ev.target.value === 'audit', stage: 'fs' })}>
                <option value="audit">Audit</option>
                <option value="unaudited">Unaudited</option>
              </select>
            </label>
            <div className={styles.field}>
              <span>Preparation Status</span>
              <StageControls taskKey={taskKey} state={state} stage="fs" />
            </div>
          </div>
        </div>
      )}
      {!company && <StageControls taskKey={taskKey} state={state} stage="fs" />}
      {company && (
        <p className={styles.hint} style={{ margin: 0 }}>
          Preparing: <b>{incomeOnly ? 'the income statement only' : 'the full set of financial statements'}</b> (chosen in Client Info).{' '}
          The trial balance is uploaded in Client Info › Supporting Documents.{' '}
          {onDocuments && <Button size="sm" variant="subtle" onClick={onDocuments}>Open Supporting Documents</Button>}
        </p>
      )}

      <div className={styles.columns}>
        <div className={styles.card}>
          <h3 className={styles.cardTitle} style={{ color: 'var(--tf-text)' }}>Financial Statements</h3>
          <SectionNav items={sections} value={section} onChange={setSection} label="Financial statement sections" />
          <Completion pct={state.progress?.fs ?? 0} />
        </div>

        <section className={styles.card} aria-label={sections.find((s) => s.key === section)?.label}>
          {!fin && company && section !== 'tb' && section !== 'journals' ? (
            <>
              <p className={styles.muted}>No trial balance yet. Upload it in Client Info › Supporting Documents (Excel, CSV, or a PDF read by Local_Tax_AI), or enter it by hand under TB Mapping.</p>
              <div className={styles.actions}>
                {onDocuments && <Button variant="primary" onClick={onDocuments}>Upload the trial balance</Button>}
                <Button variant="secondary" onClick={() => setSection('tb')}>Enter it by hand</Button>
              </div>
            </>
          ) : section === 'pl' && company && fin?.pl ? (
            <>
              <h3 className={styles.cardTitle}>Statement of Profit or Loss and Other Comprehensive Income</h3>
              <p className={styles.muted}>For the year ended {ye}</p>
              <ProfitOrLoss cur={fin.pl.current} comp={fin.pl.comparative} />
            </>
          ) : section === 'pl' && !company && fin ? (
            <IndividualStatement fin={fin} />
          ) : section === 'bs' && fin?.bs ? (
            <>
              <h3 className={styles.cardTitle}>Statement of Financial Position</h3>
              <p className={styles.muted}>As at {ye}</p>
              <Position fin={fin} />
            </>
          ) : section === 'tb' ? (
            <TbMapping taskKey={taskKey} fin={fin} />
          ) : section === 'journals' ? (
            <>
              <h3 className={styles.cardTitle}>Journal adjustments and reclassifications</h3>
              <JournalForm taskKey={taskKey} />
              <Adjustments taskKey={taskKey} state={state} scope="accounting" />
            </>
          ) : section === 'audit' ? (
            <AuditReport state={state} />
          ) : section === 'equity' && state.statements ? (
            <EquityStatement st={state.statements} ye={ye} />
          ) : section === 'cash' && state.statements ? (
            <CashFlowStatement st={state.statements} ye={ye} />
          ) : section === 'notes' && state.statements ? (
            <NotesView taskKey={taskKey} state={state} />
          ) : section === 'policies' && state.statements ? (
            <PoliciesView taskKey={taskKey} state={state} />
          ) : (
            <p className={styles.muted}>Map the trial balance first: this statement is worked out from it.</p>
          )}
          <div className={styles.actions} style={{ justifyContent: 'flex-end' }}>
            {sections.findIndex((x) => x.key === section) > 0 && (
              <Button variant="secondary" onClick={() => setSection(sections[sections.findIndex((x) => x.key === section) - 1].key)}>
                ← Back: {sections[sections.findIndex((x) => x.key === section) - 1].label}
              </Button>
            )}
            {sections.findIndex((x) => x.key === section) < sections.length - 1 ? (
              <Button variant="primary" onClick={() => setSection(sections[sections.findIndex((x) => x.key === section) + 1].key)}>
                Next: {sections[sections.findIndex((x) => x.key === section) + 1].label} →
              </Button>
            ) : (
              <Button variant="primary" onClick={onNext}>Next: Tax Computation →</Button>
            )}
          </div>
        </section>

        <div className={styles.side}>
          <AiAssistant taskKey={taskKey} lead="I can help you review the financial statements, check compliance with the framework and draft the audit report."
            suggestions={['Are there unusual balances I should look at?', 'Which disclosures are missing?']} />
          <section className={styles.card} aria-label="Key Insights">
            <h3 className={styles.cardTitle}><BarChart3 size={18} aria-hidden="true" /> Key Insights</h3>
            <ul className={styles.ticks}>
              {checks.map((c) => (
                <li key={c.label} data-off={!c.passed || undefined}><Sparkles size={14} aria-hidden="true" /> {c.label}{c.passed ? '' : `: difference ${money(c.difference)}`}</li>
              ))}
              <li><Sparkles size={14} aria-hidden="true" /> {state.adjustments.filter((a) => a.scope === 'accounting' && a.status === 'approved').length} adjustment entries applied.</li>
              {fin?.pl?.comparative && Number(fin.pl.comparative.revenue) !== 0 && (
                <li><Sparkles size={14} aria-hidden="true" /> Revenue {Number(fin.pl.current.revenue) >= Number(fin.pl.comparative.revenue) ? 'increased' : 'decreased'} by{' '}
                  {Math.abs(((Number(fin.pl.current.revenue) - Number(fin.pl.comparative.revenue)) / Number(fin.pl.comparative.revenue)) * 100).toFixed(1)}% from the prior year.</li>
              )}
            </ul>
          </section>
          <Alerts alerts={state.alerts.filter((a) => a.stage === 'fs')} />
          <div className={styles.actions}>
            <Button variant="primary" onClick={() => downloadLocalTax(taskKey, 'fs', 'pdf')}><Download size={14} /> Download Financial Statements (PDF)</Button>
            <Button variant="secondary" onClick={() => downloadLocalTax(taskKey, 'fs', 'xlsx')}><FileSpreadsheet size={14} /> Download FS (Excel)</Button>
          </div>
          {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
        </div>
      </div>
      <div className={styles.actions}>
        {onBack && <Button variant="secondary" onClick={onBack}>← Back: Client Info</Button>}
        <span className={styles.spacer} />
        <Button variant="primary" onClick={onNext}>Next: Tax Computation →</Button>
      </div>
    </>
  )
}

function ProfitOrLoss({ cur, comp }: { cur: PlFigures; comp: PlFigures | null }) {
  const rows: [keyof PlFigures, string, number, string?][] = [
    ['revenue', 'Revenue', 1], ['cost_of_sales', 'Cost of Sales', -1], ['gross_profit', 'Gross Profit', 1, 'subtotal'], ['other_income', 'Other Income', 1],
    ['admin_expenses', 'Administrative Expenses', -1], ['distribution_expenses', 'Selling and Distribution Expenses', -1], ['finance_costs', 'Finance Costs', -1],
    ['pbt', 'Profit Before Tax', 1, 'subtotal'], ['income_tax_expense', 'Income Tax Expense', -1], ['profit', 'Profit for the Year', 1, 'total'],
  ]
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} aria-label="Statement of profit or loss">
        <thead>
          <tr><th>Item</th><th className={styles.num}>Current year (LKR)</th>{comp && <th className={styles.num}>Prior year (LKR)</th>}</tr>
        </thead>
        <tbody>
          {rows.map(([k, label, sign, kind]) => (
            <tr key={k} data-kind={kind}>
              <th scope="row">{label}</th>
              <td className={styles.num}>{money(sign * Number(cur[k]))}</td>
              {comp && <td className={styles.num}>{money(sign * Number(comp[k]))}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Position({ fin }: { fin: Financials }) {
  const groups: [string, string][] = [['asset', 'Assets'], ['equity', 'Equity'], ['liability', 'Liabilities']]
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} aria-label="Statement of financial position">
        <thead>
          <tr><th>Item</th><th className={styles.num}>Current year (LKR)</th>{fin.has_comparative && <th className={styles.num}>Prior year (LKR)</th>}</tr>
        </thead>
        <tbody>
          {groups.map(([kind, title]) => (
            <Fragment key={kind}>
              <tr data-kind="head"><th colSpan={fin.has_comparative ? 3 : 2}>{title}</th></tr>
              {Object.entries(fin.bs ?? {}).filter(([, v]) => v.kind === kind && (Number(v.amount) || Number(v.comparative))).map(([h, v]) => (
                <tr key={h} data-level="1">
                  <th scope="row">{v.label}</th>
                  <td className={styles.num}>{money(v.amount)}</td>
                  {fin.has_comparative && <td className={styles.num}>{money(v.comparative)}</td>}
                </tr>
              ))}
              {kind === 'equity' && (
                <tr data-level="1"><th scope="row">Profit for the year</th><td className={styles.num}>{money(fin.pl?.current.total_comprehensive_income)}</td>{fin.has_comparative && <td />}</tr>
              )}
            </Fragment>
          ))}
          <tr data-kind="subtotal"><th>Total assets</th><td className={styles.num}>{money(fin.totals?.assets)}</td>{fin.has_comparative && <td />}</tr>
          <tr data-kind="subtotal"><th>Total equity and liabilities</th>
            <td className={styles.num}>{money(Number(fin.totals?.equity) + Number(fin.totals?.liabilities))}</td>{fin.has_comparative && <td />}</tr>
        </tbody>
      </table>
    </div>
  )
}

function IndividualStatement({ fin }: { fin: Financials }) {
  return (
    <>
      <h3 className={styles.cardTitle}>Statement of Income and Expenses</h3>
      <table className={styles.table} aria-label="Statement of income and expenses">
        <thead>
          <tr><th>Source</th><th className={styles.num}>Income</th><th className={styles.num}>Expenses</th><th className={styles.num}>Net</th></tr>
        </thead>
        <tbody>
          {(fin.sources ?? []).map((s) => (
            <tr key={s.id}>
              <th scope="row">{s.description || s.category.replace('_', ' ')}</th>
              <td className={styles.num}>{money(s.income)}</td>
              <td className={styles.num}>{money(-Number(s.expenses_total))}</td>
              <td className={styles.num}>{money(s.net)}</td>
            </tr>
          ))}
          <tr data-kind="total"><th>Total</th><td className={styles.num}>{money(fin.total_income)}</td><td className={styles.num}>{money(-Number(fin.total_expenses))}</td>
            <td className={styles.num}>{money(fin.net)}</td></tr>
        </tbody>
      </table>
    </>
  )
}

/** The trial balance: each account's heading (a person's choice kept across re-uploads), AI suggestions to
 * accept one by one, and entering accounts by hand. */
function TbMapping({ taskKey, fin }: { taskKey: string; fin: Financials | null }) {
  const map = useMapLine(taskKey)
  const put = usePutTb(taskKey)
  const suggest = useAiAgent<{ suggestions: { code: string; heading: string; reason: string }[]; notes: string[] }>(taskKey, 'map-tb')
  const [rows, setRows] = useState<{ code: string; name: string; amount: string; comparative: string }[]>([])
  const tb = fin?.tb ?? []
  const unmapped = fin?.unmapped?.length ?? 0
  const asked = useRef(false)
  useEffect(() => {
    if (unmapped > 0 && !asked.current) {
      asked.current = true
      suggest.mutate(undefined)
    }
  }, [unmapped, suggest])
  return (
    <>
      <h3 className={styles.cardTitle}><Table2 size={18} aria-hidden="true" /> Trial balance mapping</h3>
      <div className={styles.actions}>
        <Button size="sm" variant="secondary" disabled={!tb.length || suggest.isPending} onClick={() => suggest.mutate(undefined)}>
          <Sparkles size={13} /> {suggest.isPending ? 'Local_Tax_AI is checking…' : 'Suggest headings with AI'}
        </Button>
        {suggest.isError && <span className={styles.error}>{extractErrorMessage(suggest.error)}</span>}
      </div>
      {suggest.data && (
        <div className={styles.card} aria-label="AI mapping suggestions">
          <strong>Local_Tax_AI suggests ({suggest.data.suggestions.length})</strong>
          {suggest.data.suggestions.map((s) => (
            <div key={s.code} className={styles.actions}>
              <span>{s.code} → {HEADINGS.find((h) => h[0] === s.heading)?.[1]} <span className={styles.muted}>{s.reason}</span></span>
              <Button size="sm" variant="subtle" onClick={() => map.mutate({ code: s.code, heading: s.heading })}>Accept</Button>
            </div>
          ))}
          {suggest.data.notes.map((n) => <p key={n} className={styles.muted}>{n}</p>)}
        </div>
      )}
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Trial balance">
          <thead>
            <tr><th>Code</th><th>Account</th><th className={styles.num}>Current (Dr +)</th><th className={styles.num}>Prior</th><th>Heading</th></tr>
          </thead>
          <tbody>
            {tb.map((ln) => (
              <tr key={ln.code} data-missing={!ln.heading || undefined}>
                <td>{ln.code}</td>
                <th scope="row">{ln.name}{ln.adjusted ? ' (adjusted)' : ''}</th>
                <td className={styles.num}>{money(ln.amount)}</td>
                <td className={styles.num}>{money(ln.comparative)}</td>
                <td className={styles.cell}>
                  <select aria-label={`Heading for ${ln.name}`} value={ln.heading} onChange={(ev) => map.mutate({ code: ln.code, heading: ev.target.value })}>
                    <option value="">Not mapped</option>
                    {HEADINGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Enter or replace the trial balance by hand</summary>
        <table className={styles.table}>
          <thead>
            <tr><th>Code</th><th>Account</th><th className={styles.num}>Current (Dr + / Cr −)</th><th className={styles.num}>Prior</th><th /></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const set = (p: Partial<typeof r>) => setRows(rows.map((x, n) => (n === i ? { ...x, ...p } : x)))
              return (
                <tr key={i}>
                  <td className={styles.cell}><input aria-label="Code" value={r.code} onChange={(ev) => set({ code: ev.target.value })} /></td>
                  <td className={styles.cell}><input aria-label="Account" value={r.name} onChange={(ev) => set({ name: ev.target.value })} /></td>
                  <td className={styles.cell}><input aria-label="Current" inputMode="decimal" value={r.amount} onChange={(ev) => set({ amount: ev.target.value })} /></td>
                  <td className={styles.cell}><input aria-label="Prior" inputMode="decimal" value={r.comparative} onChange={(ev) => set({ comparative: ev.target.value })} /></td>
                  <td><Button size="sm" variant="subtle" iconOnly aria-label="Remove" onClick={() => setRows(rows.filter((_, n) => n !== i))}><Trash2 size={13} /></Button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className={styles.actions}>
          <Button size="sm" variant="subtle" onClick={() => setRows([...rows, { code: '', name: '', amount: '', comparative: '' }])}><Plus size={13} /> Add account</Button>
          <Button size="sm" variant="primary" disabled={!rows.length || put.isPending}
            onClick={() => put.mutate(rows.map((r) => ({ ...r, comparative: r.comparative || null })), { onSuccess: () => setRows([]) })}>
            Replace the trial balance
          </Button>
        </div>
        {put.isError && <p className={styles.error}>{extractErrorMessage(put.error)}</p>}
      </details>
    </>
  )
}

function JournalForm({ taskKey }: { taskKey: string }) {
  const propose = useProposeAdjustment(taskKey)
  const [lines, setLines] = useState([{ code: '', name: '', amount: '' }, { code: '', name: '', amount: '' }])
  const [reason, setReason] = useState('')
  const [label, setLabel] = useState('')
  const total = lines.reduce((s, l) => s + (Number(l.amount) || 0), 0)
  return (
    <details>
      <summary>Propose a journal (debit +, credit −)</summary>
      <div className={styles.formGrid}>
        <label className={styles.field}><span>Title</span><input value={label} onChange={(ev) => setLabel(ev.target.value)} /></label>
        <label className={styles.field}><span>Why</span><input value={reason} onChange={(ev) => setReason(ev.target.value)} /></label>
      </div>
      <table className={styles.table}>
        <tbody>
          {lines.map((l, i) => {
            const set = (p: Partial<typeof l>) => setLines(lines.map((x, n) => (n === i ? { ...x, ...p } : x)))
            return (
              <tr key={i}>
                <td className={styles.cell}><input aria-label="Account code" placeholder="Account code" value={l.code} onChange={(ev) => set({ code: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Account name (new account)" placeholder="Name (a new account)" value={l.name} onChange={(ev) => set({ name: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Amount" inputMode="decimal" placeholder="Amount" value={l.amount} onChange={(ev) => set({ amount: ev.target.value })} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => setLines([...lines, { code: '', name: '', amount: '' }])}><Plus size={13} /> Line</Button>
        <span className={total === 0 ? styles.muted : styles.error}>Difference: {money(total)}</span>
        <Button size="sm" variant="primary" disabled={total !== 0 || reason.trim().length < 5 || propose.isPending}
          onClick={() => propose.mutate({ kind: 'journal', label, reason, lines: lines.filter((l) => l.code && l.amount) },
            { onSuccess: () => (setLines([{ code: '', name: '', amount: '' }, { code: '', name: '', amount: '' }]), setReason(''), setLabel('')) })}>
          Propose for approval
        </Button>
      </div>
      {propose.isError && <p className={styles.error}>{extractErrorMessage(propose.error)}</p>}
    </details>
  )
}
