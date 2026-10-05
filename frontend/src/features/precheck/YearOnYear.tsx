import { AlertTriangle, Check, ExternalLink, X } from 'lucide-react'
import { useState } from 'react'

import styles from './YearOnYear.module.css'
import type { YearOnYear as Analysis, YoyLine, YoyStatus } from '@/api/precheck'

const STATUS_LABELS: Record<YoyStatus, string> = {
  covered: 'Covered',
  partly: 'Partly',
  not_yet: 'Not received yet',
  at_year_end: 'At year end',
  not_expected: 'Not expected',
  unclear: 'Unclear',
}
const NEEDS_ATTENTION: YoyStatus[] = ['not_yet', 'partly', 'unclear']
const SECTIONS = ['Income', 'Expenses', 'Assets', 'Liabilities', 'Equity', 'Other']

const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-NZ', { minimumFractionDigits: 0, maximumFractionDigits: 2 })

function Source({ analysis, id, label }: { analysis: Analysis; id: string | null | undefined; label: string }) {
  const ev = id ? analysis.evidence?.[id] : undefined
  if (!ev) return <span className={styles.ref}>{label}</span>
  return (
    <a className={styles.ref} href={ev.drive_url} target="_blank" rel="noreferrer" title={`${ev.file_name} — ${ev.location}: ${ev.quote}`}>
      {label} <ExternalLink size={11} aria-hidden="true" />
    </a>
  )
}

/** This year's documents against last year's accounts. Every amount here was produced by code
 * from the documents; the AI only says what this year's material covers and writes the notes. */
export function YearOnYear({ analysis }: { analysis: Analysis }) {
  const [showAll, setShowAll] = useState(false)
  const attention = analysis.lines.filter((l) => NEEDS_ATTENTION.includes(l.status))
  const shown = showAll ? analysis.lines : attention
  return (
    <section className={styles.section} aria-labelledby="yoy-title">
      <h3 id="yoy-title" className={styles.title}>
        Compared with last year
        <span className={styles.years}>
          {analysis.last_year} → {analysis.this_year}
          {analysis.period && ` · ${analysis.period}`}
        </span>
      </h3>
      <p className={styles.basis}>
        Baseline: {analysis.baseline.join(', ') || 'last year’s accounts'} · {analysis.documents.this_year} document
        {analysis.documents.this_year === 1 ? '' : 's'} received this year
      </p>

      {analysis.summary.length > 0 && (
        <div className={styles.summary}>
          <span className={styles.aiTag}>AI summary</span>
          <ul>
            {analysis.summary.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      {analysis.checks.length > 0 && (
        <ul className={styles.checks} aria-label="Checks against last year">
          {analysis.checks.map((c) => (
            <li key={c.label + c.detail}>
              {c.passed ? <Check size={14} className={styles.pass} aria-label="Passed" /> : <X size={14} className={styles.fail} aria-label="Failed" />}
              <span className={styles.checkLabel}>{c.label}</span>
              <span className={styles.checkDetail}>{c.detail}</span>
              {c.evidence_ids.map((id, n) => (
                <Source key={id} analysis={analysis} id={id} label={n === 0 ? 'source' : 'last year'} />
              ))}
            </li>
          ))}
        </ul>
      )}

      {analysis.bank.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption className={styles.caption}>Bank received this year</caption>
            <thead>
              <tr>
                <th scope="col">Account</th>
                <th scope="col">Period</th>
                <th scope="col" className={styles.num}>Opening</th>
                <th scope="col" className={styles.num}>Money in</th>
                <th scope="col" className={styles.num}>Money out</th>
                <th scope="col" className={styles.num}>Closing</th>
              </tr>
            </thead>
            <tbody>
              {analysis.bank.map((b) => (
                <tr key={b.account}>
                  <td>{b.account}</td>
                  <td>
                    {b.from} – {b.to}
                  </td>
                  <td className={styles.num}>{money(b.opening)}</td>
                  <td className={styles.num}>{money(b.money_in)}</td>
                  <td className={styles.num}>{money(b.money_out)}</td>
                  <td className={styles.num}>{money(b.closing)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className={styles.linesHeader}>
        <span className={styles.caption}>
          Last year&apos;s accounts, line by line ({attention.length} of {analysis.lines.length} need attention)
        </span>
        <button type="button" className={styles.toggle} onClick={() => setShowAll((v) => !v)} aria-pressed={showAll}>
          {showAll ? 'Show only what needs attention' : 'Show all lines'}
        </button>
      </div>
      {shown.length === 0 ? (
        <p className={styles.empty}>Every line of last year&apos;s accounts is covered or expected at year end.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Line</th>
                <th scope="col" className={styles.num}>Last year</th>
                <th scope="col" className={styles.num}>Year before</th>
                <th scope="col" className={styles.num}>This year</th>
                <th scope="col">Status</th>
                <th scope="col">Note</th>
              </tr>
            </thead>
            {SECTIONS.map((section) => {
              const rows = shown.filter((l) => l.section === section)
              if (!rows.length) return null
              return (
                <tbody key={section}>
                  <tr className={styles.sectionRow}>
                    <th scope="rowgroup" colSpan={6}>
                      {section}
                    </th>
                  </tr>
                  {rows.map((l) => (
                    <LineRow key={l.id} line={l} analysis={analysis} />
                  ))}
                </tbody>
              )
            })}
          </table>
        </div>
      )}

      {analysis.new_this_year.length > 0 && (
        <div className={styles.newItems}>
          <span className={styles.caption}>New this year</span>
          <ul>
            {analysis.new_this_year.map((n) => (
              <li key={n.text}>
                {n.text}{' '}
                {n.refs.map((r) => (
                  <Source key={r.id} analysis={analysis} id={r.evidence_id} label={r.label} />
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function LineRow({ line, analysis }: { line: YoyLine; analysis: Analysis }) {
  const moved = line.change_pct != null && Math.abs(line.change_pct) >= 25
  return (
    <tr>
      <td>
        <Source analysis={analysis} id={line.evidence_ids[0]} label={line.label} />
      </td>
      <td className={styles.num}>{money(line.last_year)}</td>
      <td className={styles.num}>{money(line.year_before)}</td>
      <td className={styles.num}>
        {money(line.this_year)}
        {line.change_pct != null && (
          <span className={styles.change} data-moved={moved}>
            {moved && <AlertTriangle size={11} aria-hidden="true" />} {line.change_pct > 0 ? '+' : ''}
            {line.change_pct}%
          </span>
        )}
      </td>
      <td>
        <span className={styles.status} data-status={line.status}>
          {STATUS_LABELS[line.status]}
        </span>
      </td>
      <td className={styles.note}>
        {line.comment}
        {line.question && <span className={styles.question}>{line.question}</span>}
        {line.refs.length > 0 && (
          <span className={styles.refs}>
            {line.refs.map((r) => (
              <Source key={r.id} analysis={analysis} id={r.evidence_id} label={r.label} />
            ))}
          </span>
        )}
      </td>
    </tr>
  )
}
