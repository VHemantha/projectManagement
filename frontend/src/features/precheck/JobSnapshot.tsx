import {
  ArrowDownRight,
  ArrowUpRight,
  BookOpenText,
  Briefcase,
  Building2,
  ChevronDown,
  Coins,
  Home,
  Landmark,
  Lightbulb,
  PiggyBank,
  RefreshCw,
  ShoppingCart,
  Target,
  Users,
} from 'lucide-react'
import type { ReactNode } from 'react'

import styles from './JobSnapshot.module.css'
import { Sources } from './SourceLinks'
import type { JobSnapshot as Snapshot, PrecheckOutput, SnapshotGroup, SnapshotKpi, SnapshotLine, SnapshotStatus } from '@/api/precheck'

type Evidence = PrecheckOutput['evidence']

const money = (n: number | null | undefined) =>
  n == null ? '—' : new Intl.NumberFormat('en-NZ', { style: 'currency', currency: 'NZD', maximumFractionDigits: 0 }).format(n)

const STATUS_LABEL: Record<SnapshotStatus, string> = { confirmed: 'Confirmed', inferred: 'Inferred', unresolved: 'Not yet known' }
const STATUS_HINT: Record<SnapshotStatus, string> = {
  confirmed: 'A document shows this.',
  inferred: 'The records suggest this; it is not yet confirmed.',
  unresolved: 'Something changed, but the records do not say what.',
}
// Restrained, professional colours for the composition bars, in order.
const SERIES = ['var(--tf-primary)', 'var(--tf-solid-teal)', 'var(--tf-solid-blue)', 'var(--tf-solid-orange)', 'var(--tf-solid-violet)', 'var(--tf-solid-grey)']

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

/** The Job Snapshot (AFIT design requirements, 16 Nov 2026): the story of the client and its year,
 * read in two or three minutes before the findings. The figures are worked out by code from the
 * records, and each opens to the line it came from; the words are the AI's, with their sources and
 * whether each is confirmed, inferred or not yet known. */
export function JobSnapshot({ snapshot, evidence }: { snapshot: Snapshot; evidence: Evidence }) {
  const f = snapshot.figures
  const basis = f.basis === 'trial_balance' ? "last year's trial balance" : "last year's financial statements"
  const owners = snapshot.ownership?.shareholders ?? []
  const withShare = owners.filter((o) => o.percent != null)
  const accounts = f.current_accounts ?? []

  return (
    <section className={styles.snapshot} aria-label="Job Snapshot">
      <header className={styles.head}>
        <BookOpenText size={20} aria-hidden="true" />
        <div>
          <h3 className={styles.title}>Job Snapshot</h3>
          <p className={styles.subtitle}>
            The story of the client and its year: read this first, then the findings below.
            {f.available && ` Figures are worked out by code from ${basis}${f.comparative_label ? ', with the year before beside them' : ''}.`}
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

      {/* 1 | The business */}
      <div className={styles.block}>
        <h4 className={styles.blockTitle}>
          <Building2 size={15} aria-hidden="true" /> The business
        </h4>
        {snapshot.business_story ? (
          <p className={styles.story}>
            {snapshot.business_story}
            <Flagged flags={snapshot.story_flags} />
          </p>
        ) : (
          <p className={styles.muted}>The AI did not write a story for this run. Run the pre-check again to get one.</p>
        )}
        {(snapshot.revenue_sources?.length ?? 0) > 0 && (
          <ul className={styles.revenue} aria-label="How it earns money">
            {snapshot.revenue_sources!.map((r) => (
              <li key={r.label} className={styles.revenueBox}>
                <span className={styles.revenueIcon}>{iconFor(`${r.label} ${r.detail}`)}</span>
                <span>
                  <strong>{r.label}</strong>
                  {r.detail && <span className={styles.muted}> {r.detail}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
        {f.available && (f.kpis?.length ?? 0) > 0 && (
          <div className={styles.kpis}>
            {f.kpis!.map((k) => (
              <Kpi key={k.label} kpi={k} comparativeLabel={f.comparative_label} />
            ))}
          </div>
        )}
        {snapshot.financial_story && (
          <p className={styles.story}>
            {snapshot.financial_story}
            <Flagged flags={snapshot.financial_flags} />
          </p>
        )}
        {!f.available && (
          <p className={styles.muted}>
            No figures yet: last year&apos;s trial balance or financial statements were not found in the folder.
          </p>
        )}
      </div>

      {f.available && ((f.asset_mix?.length ?? 0) > 0 || (f.funding_mix?.length ?? 0) > 0) && (
        /* 2 | What it owns and how it is funded */
        <div className={styles.block}>
          <h4 className={styles.blockTitle}>
            <Landmark size={15} aria-hidden="true" /> What it owns and how it is funded
            <span className={styles.yearTag}>{f.year_label}</span>
          </h4>
          <div className={styles.mixes}>
            <Composition title="What it owns" groups={f.asset_mix ?? []} evidence={evidence} />
            <Composition title="How it is funded" groups={f.funding_mix ?? []} evidence={evidence} />
          </div>
        </div>
      )}

      {(owners.length > 0 || accounts.length > 0 || snapshot.current_accounts || snapshot.ownership?.note) && (
        /* 3 | Owners and current accounts */
        <div className={styles.block}>
          <h4 className={styles.blockTitle}>
            <Users size={15} aria-hidden="true" /> Owners and their current accounts
          </h4>
          {withShare.length > 0 ? (
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
                    <Sources sources={o.sources} evidence={evidence} />
                  </li>
                ))}
              </ul>
            </>
          ) : owners.length > 0 ? (
            <p className={styles.small}>
              Shareholders: {owners.map((o) => o.name).join(', ')}. Their shares are not shown in the documents read.
            </p>
          ) : null}
          {snapshot.ownership?.note && <p className={styles.small}>{snapshot.ownership.note}</p>}
          {accounts.length > 0 && (
            <table className={styles.table}>
              <caption className={styles.srOnly}>Shareholder current accounts</caption>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.label}>
                    <th scope="row">{a.label}</th>
                    <td className={styles.num}>{money(Math.abs(a.amount))}</td>
                    <td className={styles.muted}>{a.direction}</td>
                    <td>
                      <Sources sources={a.source ? [a.source] : []} evidence={evidence} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {snapshot.current_accounts && <p className={styles.small}>{snapshot.current_accounts}</p>}
          <p className={styles.note}>Ownership shares and current-account balances are different things: one is who owns the business, the other is money owed between it and its owners.</p>
        </div>
      )}

      {f.available && ((f.income?.length ?? 0) > 0 || (f.expenses?.length ?? 0) > 0) && (
        /* 4 | Income and costs */
        <div className={styles.block}>
          <h4 className={styles.blockTitle}>
            <Coins size={15} aria-hidden="true" /> How it earns and spends
          </h4>
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
        </div>
      )}

      {((snapshot.events?.length ?? 0) > 0 || (snapshot.focus_areas?.length ?? 0) > 0) && (
        <div className={styles.block}>
          {(snapshot.events?.length ?? 0) > 0 && (
            <>
              <h4 className={styles.blockTitle}>
                <Lightbulb size={15} aria-hidden="true" /> Significant events this year
              </h4>
              <ul className={styles.events}>
                {snapshot.events!.map((e) => (
                  <li key={e.text}>
                    <StatusChip status={e.status} /> {e.text}
                    <Flagged flags={e.flags} />
                    <Sources sources={e.sources} evidence={evidence} />
                  </li>
                ))}
              </ul>
            </>
          )}
          {(snapshot.focus_areas?.length ?? 0) > 0 && (
            <div className={styles.takeaway}>
              <h4 className={styles.blockTitle}>
                <Target size={15} aria-hidden="true" /> Where to focus
              </h4>
              <ul>
                {snapshot.focus_areas!.map((a) => (
                  <li key={a.area}>
                    <strong>{a.area}.</strong> {a.why} <Sources sources={a.sources} evidence={evidence} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {(snapshot.understood?.length ?? 0) > 0 && (
        /* 5 | What the AI understood */
        <div className={styles.understood}>
          <strong>What the AI understood</strong>
          <ul>
            {snapshot.understood!.map((u) => (
              <li key={u.text}>
                <StatusChip status={u.status} /> {u.text} <Sources sources={u.sources} evidence={evidence} />
              </li>
            ))}
          </ul>
          <span className={styles.muted}>The pre-check findings below say what needs attention.</span>
        </div>
      )}
    </section>
  )
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
                      <Sources sources={[ln.source]} evidence={evidence} />
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
              {ln.label} <Sources sources={[ln.source]} evidence={evidence} />
            </th>
            <td className={styles.num}>{money(ln.amount)}</td>
            {f.comparative_label && <td className={styles.num}>{money(ln.comparative)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
