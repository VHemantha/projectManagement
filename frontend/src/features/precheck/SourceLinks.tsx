import { ExternalLink } from 'lucide-react'

import styles from './PrecheckResult.module.css'
import type { PrecheckOutput, SourceRef } from '@/api/precheck'

type Evidence = PrecheckOutput['evidence']

/** One source behind a statement or figure: opens the document at the quoted line when there is one. */
export function Source({ source, evidence }: { source: SourceRef; evidence: Evidence }) {
  const ev = source.evidence_id ? evidence[source.evidence_id] : undefined
  if (!ev) return <span className={styles.source}>{source.label}</span>
  return (
    <a className={styles.source} href={ev.drive_url} target="_blank" rel="noreferrer" title={`${ev.file_name} — ${ev.location}: ${ev.quote}`}>
      {source.label} <ExternalLink size={11} aria-hidden="true" />
    </a>
  )
}

export function Sources({ sources, evidence }: { sources: SourceRef[]; evidence: Evidence }) {
  if (!sources.length) return null
  return (
    <span className={styles.sources}>
      {sources.map((s) => (
        <Source key={s.id || s.label} source={s} evidence={evidence} />
      ))}
    </span>
  )
}
