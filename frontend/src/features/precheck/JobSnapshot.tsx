import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BookOpenText,
  Briefcase,
  Building2,
  CalendarClock,
  ChevronDown,
  Coins,
  Globe2,
  History,
  Home,
  Landmark,
  PiggyBank,
  RefreshCw,
  Scale,
  ShoppingCart,
  Sunrise,
  TrendingUp,
  Users,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { DocIcons } from './DocIcons'
import styles from './JobSnapshot.module.css'
import type {
  JobSnapshot as Snapshot,
  PrecheckOutput,
  SnapshotFinding,
  SnapshotGroup,
  SnapshotKpi,
  SnapshotLine,
  SnapshotSection,
  SnapshotSectionKey,
  SnapshotStatus,
  SourceRef,
} from '@/api/precheck'

type Evidence = PrecheckOutput['evidence']

const money = (n: number | null | undefined) =>
  n == null ? '—' : new Intl.NumberFormat('en-NZ', { style: 'currency', currency: 'NZD', maximumFractionDigits: 0 }).format(n)

const STATUS_LABEL: Record<SnapshotStatus, string> = { confirmed: 'Confirmed', inferred: 'Inferred', unresolved: 'Not yet known' }
const STATUS_HINT: Record<SnapshotStatus, string> = {
  confirmed: 'A document shows this.',
  inferred: 'The records suggest this; it is not yet confirmed.',
  unresolved: 'Something changed, but the records do not say what.',
}
const LEVEL_LABEL = { high: 'High risk', medium: 'Medium risk', low: 'Low risk' } as const
// Restrained, professional colours for the composition bars, in order.
const SERIES = ['var(--tf-primary)', 'var(--tf-solid-teal)', 'var(--tf-solid-blue)', 'var(--tf-solid-orange)', 'var(--tf-solid-violet)', 'var(--tf-solid-grey)']

/** The firm's eleven headings, in this order (AFIT, 21 Nov 2026). */
export const SECTIONS: { key: SnapshotSectionKey; title: string; icon: LucideIcon }[] = [
  { key: 'company_background', title: 'Company background', icon: Building2 },
  { key: 'nature_of_business', title: 'Nature of business', icon: Briefcase },
  { key: 'business_environment', title: 'Business environment', icon: Globe2 },
  { key: 'management_governance', title: 'Management and governance', icon: Users },
  { key: 'financial_performance', title: 'Financial performance', icon: TrendingUp },
  { key: 'financial_position', title: 'Financial position', icon: Landmark },
  { key: 'significant_events', title: 'Significant transactions and events', icon: CalendarClock },
  { key: 'accounting_policies', title: 'Accounting policies and reporting framework', icon: Scale },
  { key: 'key_risks', title: 'Key accounting risks', icon: AlertTriangle },
  { key: 'prior_year_matters', title: 'Prior-year accounting matters', icon: History },
  { key: 'going_concern', title: 'Going concern and future outlook', icon: Sunrise },
]

function iconFor(label: string): ReactNode {
  const l = label.toLowerCase()
  if (/rent|lease|tenant|property/.test(l)) return <Home size={16} aria-hidden="true" />
  if (/sale|sell|retail|wholesale|product|goods/.test(l)) return <ShoppingCart size={16} aria-hidden="true" />
  if (/service|fee|consult|contract/.test(l)) return <Briefcase size={16} aria-hidden="true" />
  if (/interest|dividend|invest|share|fund/.test(l)) return <PiggyBank size={16} aria-hidden="true" />
  return <Coins size={16} aria-hidden="true" />
}

export function StatusChip({ status }: { status: SnapshotStatus }) {
  return (
    <span className={styles.status} data-status={status} title={STATUS_HINT[status]}>
      {STATUS_LABEL[status]}
    </span>
  )
}

/** The documents behind a statement or a figure: the reference icons, at their full size. */
function Refs({ sources, evidence }: { sources: SourceRef[]; evidence: Evidence }) {
  return <DocIcons sources={sources} evidence={evidence} label="" variant="row" max={4} />
}

/** A run from before the eleven headings: its findings put under the heading each belongs to. */
function legacySections(s: Snapshot): SnapshotSection[] {
  const f = (text: string, status: SnapshotStatus, sources: SourceRef[], label = '', flags: string[] = []): SnapshotFinding => ({
    label, text, status, level: 'none', sources, flags,
  })
  const by: Partial<Record<SnapshotSectionKey, SnapshotSection>> = {
    nature_of_business: { key: 'nature_of_business', title: '', summary: s.business_story ?? '',
      findings: (s.revenue_sources ?? []).map((r) => f(r.detail || r.label, 'confirmed', r.sources, r.label)) },
    financial_performance: { key: 'financial_performance', title: '', summary: s.financial_story ?? '', findings: [] },
    significant_events: { key: 'significant_events', title: '', summary: '',
      findings: (s.events ?? []).map((e) => f(e.text, e.status, e.sources, '', e.flags)) },
    key_risks: { key: 'key_risks', title: '', summary: '',
      findings: (s.focus_areas ?? []).map((a) => f(a.why, 'inferred', a.sources, a.area)) },
  }
  return SECTIONS.map(({ key, title }) => ({ ...(by[key] ?? { key, summary: '', findings: [] }), key, title }))
}

/** The Job Snapshot (AFIT design requirements, 16 Nov 2026; the firm's eleven headings, 21 Nov 2026): the
 * client and its year under Company background, Nature of business, Business environment, Management
 * and governance, Financial performance, Financial position, Significant transactions and events,
 * Accounting policies, Key accounting risks, Prior-year matters, and Going concern. Every figure and
 * chart is worked out by code from the records and opens to the line it came from; the words are the
 * AI's, each confirmed, inferred or not yet known, with the documents behind it as icons. */
export function JobSnapshot({ snapshot, evidence }: { snapshot: Snapshot; evidence: Evidence }) {
  const f = snapshot.figures
  const basis = f.basis === 'trial_balance' ? "last year's trial balance" : "last year's financial statements"
  const sections = snapshot.sections?.length ? snapshot.sections : legacySections(snapshot)
  const byKey = new Map(sections.map((s) => [s.key, s]))

  return (
    <section className={styles.snapshot} aria-label="Job Snapshot">
      <header className={styles.head}>
        <BookOpenText size={20} aria-hidden="true" />
        <div>
          <h3 className={styles.title}>Job Snapshot</h3>
          <p className={styles.subtitle}>
            The client and its year under the firm&apos;s eleven headings: read this first, then the points.
            {f.available && ` Figures and charts are worked out by code from ${basis}${f.comparative_label ? ', with the year before beside them' : ''}.`}
          </p>
        </div>
      </header>

      {snapshot.changes.length > 0 && (
        <div className={styles.changes} role="status">
          <RefreshCw size={14} aria-hidden="true" />
          <div>
            <strong>Changed since the last pre-check</strong>
            <ul>
              {snapshot.changes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <Overview sections={sections} />

      {SECTIONS.map(({ key, title, icon: Icon }, i) => {
        const section = byKey.get(key) ?? { key, title, summary: '', findings: [] }
        const graphic = <Graphic sectionKey={key} snapshot={snapshot} evidence={evidence} />
        return (
          <article key={key} id={`snapshot-${key}`} className={styles.section} aria-labelledby={`snapshot-${key}-title`}>
            <h4 id={`snapshot-${key}-title`} className={styles.sectionTitle}>
              <span className={styles.sectionNo} aria-hidden="true">
                {i + 1}
              </span>
              <Icon size={16} aria-hidden="true" /> {title}
            </h4>
            {section.summary ? <p className={styles.story}>{section.summary}</p> : null}
            {graphic}
            {section.findings.length > 0 ? (
              key === 'key_risks' ? (
                <RiskFindings findings={section.findings} evidence={evidence} />
              ) : (
                <ul className={styles.findings}>
                  {section.findings.map((x) => (
                    <Finding key={`${x.label}-${x.text}`} finding={x} evidence={evidence} />
                  ))}
                </ul>
              )
            ) : (
              !section.summary && <p className={styles.muted}>Not shown in the documents read.</p>
            )}
          </article>
        )
      })}

      {(snapshot.understood?.length ?? 0) > 0 && (
        <div className={styles.understood}>
          <strong>What the AI understood</strong>
          <ul>
            {snapshot.understood!.map((u) => (
              <li key={u.text}>
                <StatusChip status={u.status} /> {u.text} <Refs sources={u.sources} evidence={evidence} />
              </li>
            ))}
          </ul>
          <span className={styles.muted}>The pre-check points say what needs attention.</span>
        </div>
      )}
    </section>
  )
}

/** The eleven headings at a glance: how much each has, and the risks by level; each opens its panel. */
function Overview({ sections }: { sections: SnapshotSection[] }) {
  const risks = sections.find((s) => s.key === 'key_risks')?.findings ?? []
  const count = (level: SnapshotFinding['level']) => risks.filter((r) => r.level === level).length
  return (
    <nav className={styles.overview} aria-label="Snapshot headings">
      <ol>
        {SECTIONS.map(({ key, title, icon: Icon }, i) => {
          const s = sections.find((x) => x.key === key)
          const n = s?.findings.length ?? 0
          const empty = !n && !s?.summary
          return (
            <li key={key} data-empty={empty || undefined}>
              <a href={`#snapshot-${key}`}>
                <span className={styles.overviewNo}>{i + 1}</span>
                <Icon size={14} aria-hidden="true" />
                <span className={styles.overviewTitle}>{title}</span>
                <span className={styles.overviewCount}>{empty ? '—' : n}</span>
              </a>
            </li>
          )
        })}
      </ol>
      {risks.length > 0 && (
        <div className={styles.riskMeter} role="img" aria-label={`Key accounting risks: ${count('high')} high, ${count('medium')} medium, ${count('low')} low`}>
          {(['high', 'medium', 'low'] as const).map((level) =>
            count(level) ? (
              <span key={level} data-level={level} style={{ flex: count(level) }}>
                {count(level)} {level}
              </span>
            ) : null,
          )}
        </div>
      )}
    </nav>
  )
}

function Finding({ finding, evidence }: { finding: SnapshotFinding; evidence: Evidence }) {
  return (
    <li className={styles.finding}>
      <div className={styles.findingHead}>
        <StatusChip status={finding.status} />
        {finding.label && <strong>{finding.label}</strong>}
      </div>
      <p className={styles.findingText}>
        {finding.text}
        <Flagged flags={finding.flags} />
      </p>
      <Refs sources={finding.sources} evidence={evidence} />
    </li>
  )
}

/** Key accounting risks as cards, the highest first, coloured by how significant each is. */
function RiskFindings({ findings, evidence }: { findings: SnapshotFinding[]; evidence: Evidence }) {
  const order = { high: 0, medium: 1, low: 2, none: 3 }
  return (
    <ul className={styles.risks}>
      {[...findings].sort((a, b) => order[a.level] - order[b.level]).map((x) => (
        <li key={`${x.label}-${x.text}`} className={styles.risk} data-level={x.level}>
          <div className={styles.findingHead}>
            {x.level !== 'none' && <span className={styles.riskLevel} data-level={x.level}>{LEVEL_LABEL[x.level]}</span>}
            {x.label && <strong>{x.label}</strong>}
            <StatusChip status={x.status} />
          </div>
          <p className={styles.findingText}>
            {x.text}
            <Flagged flags={x.flags} />
          </p>
          <Refs sources={x.sources} evidence={evidence} />
        </li>
      ))}
    </ul>
  )
}

/** The charts and tables code draws for a heading, from the records. */
function Graphic({ sectionKey, snapshot, evidence }: { sectionKey: SnapshotSectionKey; snapshot: Snapshot; evidence: Evidence }) {
  const f = snapshot.figures
  const owners = snapshot.ownership?.shareholders ?? []
  switch (sectionKey) {
    case 'company_background':
      return (
        <>
          {(snapshot.background?.length ?? 0) > 0 && (
            <dl className={styles.facts}>
              {snapshot.background!.map((b) => (
                <div key={b.label}>
                  <dt>{b.label}</dt>
                  <dd>{b.value}</dd>
                </div>
              ))}
            </dl>
          )}
          <Ownership owners={owners} evidence={evidence} />
        </>
      )
    case 'nature_of_business':
      return (snapshot.revenue_sources?.length ?? 0) > 0 ? (
        <ul className={styles.revenue} aria-label="How it earns money">
          {snapshot.revenue_sources!.map((r) => (
            <li key={r.label} className={styles.revenueBox}>
              <span className={styles.revenueIcon}>{iconFor(`${r.label} ${r.detail}`)}</span>
              <span>
                <strong>{r.label}</strong>
                {r.detail && <span className={styles.muted}> {r.detail}</span>}
              </span>
              <Refs sources={r.sources} evidence={evidence} />
            </li>
          ))}
        </ul>
      ) : null
    case 'management_governance':
      return (
        <>
          {snapshot.ownership?.note && <p className={styles.small}>{snapshot.ownership.note}</p>}
        </>
      )
    case 'financial_performance':
      if (!f.available) return <p className={styles.muted}>No figures yet: last year&apos;s trial balance or financial statements were not found in the folder.</p>
      return (
        <>
          {(f.kpis?.length ?? 0) > 0 && (
            <div className={styles.kpis}>
              {f.kpis!.filter((k) => ['Revenue', 'Expenses', 'Net profit'].includes(k.label)).map((k) => (
                <Kpi key={k.label} kpi={k} comparativeLabel={f.comparative_label} />
              ))}
            </div>
          )}
          <Comparison kpis={(f.kpis ?? []).filter((k) => ['Revenue', 'Expenses', 'Net profit'].includes(k.label))} labels={[f.comparative_label, f.year_label]} />
          {f.this_year && (
            <p className={styles.small}>
              This year so far (from the general ledger, {f.this_year.accounts_matched} accounts matched to last year): revenue{' '}
              <strong>{money(f.this_year.revenue)}</strong>, expenses <strong>{money(f.this_year.expenses)}</strong>, profit{' '}
              <strong>{money(f.this_year.net_profit)}</strong>.
            </p>
          )}
          <div className={styles.lineTables}>
            <LineTable title="Income" lines={f.income ?? []} f={f} evidence={evidence} />
            <LineTable title="Largest costs" lines={f.expenses ?? []} f={f} evidence={evidence} />
          </div>
        </>
      )
    case 'financial_position': {
      if (!f.available) return null
      const accounts = f.current_accounts ?? []
      return (
        <>
          {(f.kpis ?? []).some((k) => ['Total assets', 'Money customers owe'].includes(k.label)) && (
            <div className={styles.kpis}>
              {f.kpis!.filter((k) => ['Total assets', 'Money customers owe'].includes(k.label)).map((k) => (
                <Kpi key={k.label} kpi={k} comparativeLabel={f.comparative_label} />
              ))}
            </div>
          )}
          {((f.asset_mix?.length ?? 0) > 0 || (f.funding_mix?.length ?? 0) > 0) && (
            <div className={styles.mixes}>
              <Composition title="What it owns" groups={f.asset_mix ?? []} evidence={evidence} />
              <Composition title="How it is funded" groups={f.funding_mix ?? []} evidence={evidence} />
            </div>
          )}
          {accounts.length > 0 && (
            <table className={styles.table}>
              <caption>Shareholder current accounts</caption>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.label}>
                    <th scope="row">{a.label}</th>
                    <td className={styles.num}>{money(Math.abs(a.amount))}</td>
                    <td className={styles.muted}>{a.direction}</td>
                    <td>
                      <Refs sources={a.source ? [a.source] : []} evidence={evidence} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {snapshot.current_accounts && <p className={styles.small}>{snapshot.current_accounts}</p>}
          {(accounts.length > 0 || snapshot.current_accounts) && (
            <p className={styles.note}>
              Ownership shares and current-account balances are different things: one is who owns the business, the other is money owed between it
              and its owners.
            </p>
          )}
        </>
      )
    }
    case 'going_concern': {
      if (!f.available) return null
      const equity = (f.funding_mix ?? []).find((g) => g.derived)
      const profit = (f.kpis ?? []).find((k) => k.label === 'Net profit')
      if (!equity && !profit) return null
      return (
        <div className={styles.signals} aria-label="Signals from the records">
          {profit && (
            <span className={styles.signal} data-good={profit.amount >= 0 || undefined}>
              {profit.amount >= 0 ? 'Made a profit' : 'Made a loss'} last year: <strong>{money(profit.amount)}</strong>
            </span>
          )}
          {equity && (
            <span className={styles.signal} data-good={equity.amount >= 0 || undefined}>
              {equity.amount >= 0 ? 'Assets cover what is owed' : 'Owes more than its recorded assets'}: <strong>{money(Math.abs(equity.amount))}</strong>
            </span>
          )}
          {f.this_year && (
            <span className={styles.signal} data-good={f.this_year.net_profit >= 0 || undefined}>
              This year so far: <strong>{money(f.this_year.net_profit)}</strong>
            </span>
          )}
        </div>
      )
    }
    default:
      return null
  }
}

function Ownership({ owners, evidence }: { owners: NonNullable<Snapshot['ownership']>['shareholders']; evidence: Evidence }) {
  const withShare = owners.filter((o) => o.percent != null)
  if (withShare.length > 0) {
    return (
      <>
        <div className={styles.bar} role="img" aria-label={`Ownership: ${withShare.map((o) => `${o.name} ${o.percent}%`).join(', ')}`}>
          {withShare.map((o, i) => (
            <span key={o.name} style={{ width: `${o.percent}%`, background: SERIES[i % SERIES.length] }} />
          ))}
        </div>
        <ul className={styles.legend}>
          {withShare.map((o, i) => (
            <li key={o.name}>
              <i style={{ background: SERIES[i % SERIES.length] }} /> {o.name} <strong>{o.percent}%</strong>
              <Refs sources={o.sources} evidence={evidence} />
            </li>
          ))}
        </ul>
      </>
    )
  }
  return owners.length > 0 ? (
    <p className={styles.small}>Shareholders: {owners.map((o) => o.name).join(', ')}. Their shares are not shown in the documents read.</p>
  ) : null
}

function Flagged({ flags }: { flags?: string[] }) {
  if (!flags?.includes('figure_not_in_documents')) return null
  return (
    <span className={styles.flag} title="A figure in this sentence was not found in the documents read: check it before relying on it.">
      figure to check
    </span>
  )
}

function Kpi({ kpi, comparativeLabel }: { kpi: SnapshotKpi; comparativeLabel: string }) {
  const up = (kpi.change_pct ?? 0) > 0
  return (
    <div className={styles.kpi}>
      <span className={styles.kpiLabel}>{kpi.label}</span>
      <span className={styles.kpiValue}>{money(kpi.amount)}</span>
      {kpi.change_pct != null ? (
        <span className={styles.kpiChange} data-up={up || undefined}>
          {up ? <ArrowUpRight size={12} aria-hidden="true" /> : <ArrowDownRight size={12} aria-hidden="true" />}
          {up ? '+' : ''}
          {kpi.change_pct}% vs {comparativeLabel.toLowerCase()}
        </span>
      ) : (
        kpi.comparative != null && <span className={styles.kpiChange}>{comparativeLabel}: {money(kpi.comparative)}</span>
      )}
    </div>
  )
}

/** A composition bar (each group's share of the positive total) with its legend; each group opens
 * to the lines it is made of, and each line to its source. */
function Composition({ title, groups, evidence }: { title: string; groups: SnapshotGroup[]; evidence: Evidence }) {
  const positive = groups.filter((g) => g.amount > 0)
  const total = positive.reduce((s, g) => s + g.amount, 0)
  const shortfall = groups.find((g) => g.derived && g.amount < 0)
  return (
    <div className={styles.mix}>
      <div className={styles.mixHead}>
        <span>{title}</span>
        <strong>{money(total)}</strong>
      </div>
      <div className={styles.bar} role="img" aria-label={`${title}: ${positive.map((g) => `${g.label} ${money(g.amount)}`).join(', ')}`}>
        {positive.map((g, i) => (
          <span key={g.label} style={{ width: `${(g.amount / total) * 100}%`, background: SERIES[i % SERIES.length] }} title={`${g.label}: ${money(g.amount)}`} />
        ))}
      </div>
      <ul className={styles.groups}>
        {positive.map((g, i) => (
          <li key={g.label}>
            {g.lines.length ? (
              <details>
                <summary>
                  <ChevronDown size={12} aria-hidden="true" />
                  <i style={{ background: SERIES[i % SERIES.length] }} /> {g.label}
                  <span className={styles.num}>{money(g.amount)}</span>
                </summary>
                <ul className={styles.lines}>
                  {g.lines.map((ln) => (
                    <li key={ln.label}>
                      {ln.label} <span className={styles.num}>{money(ln.amount)}</span>
                      <Refs sources={[ln.source]} evidence={evidence} />
                    </li>
                  ))}
                </ul>
              </details>
            ) : (
              <span className={styles.groupRow}>
                <i style={{ background: SERIES[i % SERIES.length] }} /> {g.label}
                <span className={styles.num}>{money(g.amount)}</span>
              </span>
            )}
          </li>
        ))}
      </ul>
      {shortfall && (
        <p className={styles.small}>
          {shortfall.label}: {money(Math.abs(shortfall.amount))}. Assets held at cost, or not in the records read, can cause this.
        </p>
      )}
    </div>
  )
}

/** Revenue, expenses and profit: the year before beside last year, as labelled bars. */
function Comparison({ kpis, labels }: { kpis: SnapshotKpi[]; labels: [string, string] }) {
  if (!kpis.length) return null
  const max = Math.max(...kpis.flatMap((k) => [Math.abs(k.amount), Math.abs(k.comparative ?? 0)]), 1)
  const [before, last] = labels
  return (
    <div className={styles.compare}>
      {kpis.map((k) => (
        <div key={k.label} className={styles.compareRow}>
          <span className={styles.compareLabel}>{k.label}</span>
          <div className={styles.compareBars}>
            {k.comparative != null && before && (
              <span className={styles.compareBar} data-year="before" style={{ width: `${(Math.abs(k.comparative) / max) * 100}%` }}>
                <em>
                  {before} {money(k.comparative)}
                </em>
              </span>
            )}
            <span className={styles.compareBar} style={{ width: `${(Math.abs(k.amount) / max) * 100}%` }}>
              <em>
                {last} {money(k.amount)}
              </em>
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

function LineTable({ title, lines, f, evidence }: { title: string; lines: SnapshotLine[]; f: Snapshot['figures']; evidence: Evidence }) {
  if (!lines.length) return null
  return (
    <table className={styles.table}>
      <caption>{title}</caption>
      <thead>
        <tr>
          <th scope="col">
            <span className={styles.srOnly}>Line</span>
          </th>
          <th scope="col" className={styles.num}>
            {f.year_label}
          </th>
          {f.comparative_label && (
            <th scope="col" className={styles.num}>
              {f.comparative_label}
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {lines.map((ln) => (
          <tr key={ln.label}>
            <th scope="row">
              {ln.label} <Refs sources={[ln.source]} evidence={evidence} />
            </th>
            <td className={styles.num}>{money(ln.amount)}</td>
            {f.comparative_label && <td className={styles.num}>{money(ln.comparative)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
