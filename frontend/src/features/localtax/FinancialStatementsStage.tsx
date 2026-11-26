import { BarChart3, BookOpen, Download, FileSpreadsheet, FileText, Landmark, Layers, Scale, ShieldCheck, Sparkles, Wallet } from 'lucide-react'
import { Fragment, useState } from 'react'

import { EditableAmount, FsEditsBanner } from './FsFigures'
import { JournalRegister } from './Journals'
import styles from './LocalTax.module.css'
import { PpeSection } from './Ppe'
import { ReportView } from './Report'
import { AiAssistant, Alerts, Completion, SectionNav, StageControls } from './Shared'
import { CashFlowStatement, EquityStatement, NotesView, PoliciesView } from './Statements'
import { TbMapping } from './TbMapping'
import { UpdateButton } from './Update'
import { extractErrorMessage } from '@/api/errors'
import { type Financials, type FsEdits, type LocalTaxState, type PlFigures, downloadLocalTax, money, useSaveLocalTax } from '@/api/localTax'
import { Button } from '@/design-system'

type Section = 'report' | 'pl' | 'bs' | 'equity' | 'cash' | 'notes' | 'policies' | 'journals' | 'ppe'
type Edited = Record<string, { from: string; by: string }>

const editedOf = (edits: FsEdits | null | undefined): Edited =>
  Object.fromEntries((edits?.items ?? []).map((i) => [i.heading, { from: i.from, by: i.by }]))

/** Stage 2 (AFIT screens, 22 Nov 2026): the statements from the mapped trial balance (companies) or the statement
 * of income and expenses (individuals), with the framework, the comparatives, the checks, journals and the draft
 * audit report template. Every figure is the engine's; Local_Tax_AI suggests headings and explains. */
export function FinancialStatementsStage({ taskKey, state, onNext, onBack, onDocuments }: {
  taskKey: string; state: LocalTaxState; onNext: () => void; onBack?: () => void; onDocuments?: () => void
}) {
  const e = state.engagement
  const fin = state.financials
  const save = useSaveLocalTax(taskKey)
  // the books: companies and partnerships, and an individual (sole proprietor) whose trial balance is uploaded
  const company = e.entity_type !== 'individual' || fin?.kind === 'company'
  const incomeOnly = (e.data.fs_scope ?? 'full') === 'income_statement'
  // The report comes first, before the statements (AFIT, 26 Nov 2026): the auditor's or the compilation report, as chosen in Client Info.
  const report = { key: 'report' as Section, label: e.audited ? 'Audit Report' : 'Compilation Report', icon: <ShieldCheck size={16} /> }
  const sections: { key: Section; label: string; icon: React.ReactNode }[] = company && incomeOnly
    ? [
        report,
        { key: 'pl', label: 'Income Statement', icon: <BarChart3 size={16} /> },
        { key: 'notes', label: 'Notes', icon: <FileText size={16} /> },
        { key: 'policies', label: 'Accounting Policies', icon: <BookOpen size={16} /> },
        { key: 'ppe', label: 'PPE & Depreciation', icon: <Layers size={16} /> },
        { key: 'journals', label: 'Journal Entries', icon: <Scale size={16} /> },
      ]
    : company
    ? [
        report,
        { key: 'pl', label: 'Profit or Loss (P&L)', icon: <BarChart3 size={16} /> },
        { key: 'bs', label: 'Financial Position', icon: <FileText size={16} /> },
        { key: 'equity', label: 'Changes in Equity', icon: <Landmark size={16} /> },
        { key: 'cash', label: 'Cash Flows', icon: <Wallet size={16} /> },
        { key: 'notes', label: 'Notes to the FS', icon: <FileText size={16} /> },
        { key: 'policies', label: 'Accounting Policies', icon: <BookOpen size={16} /> },
        { key: 'ppe', label: 'PPE & Depreciation', icon: <Layers size={16} /> },
        { key: 'journals', label: 'Journal Entries', icon: <Scale size={16} /> },
      ]
    : [{ key: 'pl', label: 'Income & Expenses', icon: <BarChart3 size={16} /> }, { key: 'journals', label: 'Journal Entries', icon: <Scale size={16} /> }]
  const [section, setSection] = useState<Section>(sections[0].key)
  // Statement figures edited and out of balance: nothing goes forward until the other side is edited.
  const blocked = !!state.fs_edits && !state.fs_edits.balanced
  const edited = editedOf(state.fs_edits)
  const [downloadError, setDownloadError] = useState('')
  const download = (doc: 'fs', fmt: 'pdf' | 'xlsx' | 'docx') => {
    setDownloadError('')
    downloadLocalTax(taskKey, doc, fmt).catch((err) => setDownloadError(extractErrorMessage(err, 'The download failed.')))
  }
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
          <UpdateButton taskKey={taskKey} stage="fs" label="Update FS" />
          <Button variant="secondary" onClick={() => setSection('journals')}>
            <Scale size={15} /> Journal Entries ({state.adjustments.filter((a) => a.scope === 'accounting' && a.status !== 'rejected').length})
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
              <span>Report</span>
              <select value={e.audited ? 'audit' : 'compilation'} onChange={(ev) => save.mutate({ audited: ev.target.value === 'audit', stage: 'fs' })}>
                <option value="audit">Audit report</option>
                <option value="compilation">Compilation report</option>
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
      {e.data.tb_source?.kind === 'story' && (
        <p className={styles.error} role="note" style={{ margin: 0 }}>
          DUMMY DATA: this trial balance was made up by Local_Tax_AI from a story, for illustration only — every statement made from it says so.
        </p>
      )}
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
          {company && fin && section !== 'journals' && section !== 'ppe' && <FsEditsBanner taskKey={taskKey} edits={state.fs_edits} notes={e.data.fs_edits?.notes} />}
          {!fin && company && section !== 'journals' && section !== 'ppe' ? (
            <>
              <p className={styles.muted}>No trial balance yet. Upload it in Client Info › Supporting Documents (Excel, CSV, or a PDF read by Local_Tax_AI), or enter it by hand in TB Mapping (right).</p>
              <div className={styles.actions}>
                {onDocuments && <Button variant="primary" onClick={onDocuments}>Upload the trial balance</Button>}
              </div>
            </>
          ) : section === 'report' ? (
            <ReportView taskKey={taskKey} state={state} />
          ) : section === 'pl' && company && fin?.pl ? (
            <>
              <h3 className={styles.cardTitle}>Statement of Profit or Loss and Other Comprehensive Income</h3>
              <p className={styles.muted}>For the year ended {ye}. Click a figure to change it; totals follow from the lines.</p>
              <ProfitOrLoss taskKey={taskKey} cur={fin.pl.current} comp={fin.pl.comparative} edited={edited} />
            </>
          ) : section === 'pl' && !company && fin ? (
            <IndividualStatement fin={fin} />
          ) : section === 'bs' && fin?.bs ? (
            <>
              <h3 className={styles.cardTitle}>Statement of Financial Position</h3>
              <p className={styles.muted}>As at {ye}. Click a figure to change it; totals follow from the lines.</p>
              <Position taskKey={taskKey} fin={fin} edited={edited} />
            </>
          ) : section === 'journals' ? (
            <JournalRegister taskKey={taskKey} state={state} />
          ) : section === 'ppe' ? (
            <PpeSection taskKey={taskKey} state={state} />
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
              <Button variant="primary" onClick={onNext} disabled={blocked} title={blocked ? 'Balance the edited figures first' : undefined}>Next: Tax Computation →</Button>
            )}
          </div>
        </section>

        <div className={styles.side}>
          {company && <TbMapping taskKey={taskKey} fin={fin} />}
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
            <Button variant="primary" onClick={() => download('fs', 'pdf')}><Download size={14} /> Financial Statements (PDF)</Button>
            <Button variant="secondary" onClick={() => download('fs', 'docx')}><FileText size={14} /> FS (Word)</Button>
            <Button variant="secondary" onClick={() => download('fs', 'xlsx')}><FileSpreadsheet size={14} /> FS (Excel)</Button>
          </div>
          {downloadError && <p className={styles.error} role="alert">{downloadError}</p>}
          {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
        </div>
      </div>
      <div className={styles.actions}>
        {onBack && <Button variant="secondary" onClick={onBack}>← Back: Client Info</Button>}
        <span className={styles.spacer} />
        {blocked && <span className={styles.error}>Balance the edited figures before you continue.</span>}
        <Button variant="primary" onClick={onNext} disabled={blocked}>Next: Tax Computation →</Button>
      </div>
    </>
  )
}

// The lines of the statement of profit or loss the accountant may overwrite: never gross profit, profit before tax or the profit.
const PL_EDITABLE = new Set<keyof PlFigures>(['revenue', 'cost_of_sales', 'other_income', 'admin_expenses', 'distribution_expenses', 'finance_costs', 'income_tax_expense'])

function ProfitOrLoss({ taskKey, cur, comp, edited }: { taskKey: string; cur: PlFigures; comp: PlFigures | null; edited: Edited }) {
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
              <td className={styles.num}>
                {PL_EDITABLE.has(k)
                  ? <EditableAmount taskKey={taskKey} heading={k} label={label} value={cur[k]} shown={sign * Number(cur[k])} edited={edited[k]} />
                  : money(sign * Number(cur[k]))}
              </td>
              {comp && <td className={styles.num}>{money(sign * Number(comp[k]))}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Position({ taskKey, fin, edited }: { taskKey: string; fin: Financials; edited: Edited }) {
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
                  <td className={styles.num}>
                    <EditableAmount taskKey={taskKey} heading={h} label={v.label} value={v.amount} shown={Number(v.amount)} edited={edited[h]} />
                  </td>
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
