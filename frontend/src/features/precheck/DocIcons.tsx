import {
  CircleCheck,
  ClipboardList,
  FileChartColumn,
  FileImage,
  FileSignature,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  HandCoins,
  House,
  Landmark,
  Package,
  Percent,
  ReceiptText,
  ShieldCheck,
  StickyNote,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'

import styles from './DocIcons.module.css'
import { DOC_BADGE, type DocKind, type DocRef, docRefs } from './docKinds'
import type { PrecheckOutput, SourceRef } from '@/api/precheck'

const ICON: Record<DocKind, LucideIcon> = {
  FS: FileChartColumn, GL: FileSpreadsheet, TB: FileSpreadsheet, BANK: Landmark, INV: ReceiptText, AGR: FileSignature, PROP: House,
  INS: ShieldCheck, LOAN: HandCoins, STK: Package, PAY: Users, GST: Percent, TAX: FileText, WP: FolderOpen, CQ: ClipboardList,
  CHK: CircleCheck, NOTE: StickyNote, SUP: FileImage,
}

/** One supporting document as an icon: what it is (its badge) and its year; opens the document at the
 * cited place when there is one. The full description is its tooltip and its accessible name. */
export function DocIcon({ doc }: { doc: DocRef }) {
  const Icon = ICON[doc.kind]
  const face = (
    <>
      <Icon size={12} strokeWidth={1.8} aria-hidden="true" />
      <span className={styles.badge}>{DOC_BADGE[doc.kind]}</span>
      {doc.year && <span className={styles.year}>{doc.year}</span>}
    </>
  )
  return /^https?:\/\//.test(doc.href) ? (
    <a className={styles.doc} data-kind={doc.kind} href={doc.href} target="_blank" rel="noreferrer" title={doc.title} aria-label={doc.title}>
      {face}
    </a>
  ) : (
    <span className={styles.doc} data-kind={doc.kind} title={doc.title} aria-label={doc.title} role="img">
      {face}
    </span>
  )
}

/** "Supporting documents:" and an icon per document behind a point (the AFIT reference icons, 19 Nov
 * 2026), in place of the documents' names; past `max`, "+N more" shows the rest. */
export function DocIcons({ sources, evidence, max = 5, label = 'Supporting documents', variant }: {
  sources: SourceRef[]
  evidence: PrecheckOutput['evidence']
  max?: number
  label?: string
  /** "row": the icons at their full size even without a label (the Job Snapshot, 21 Nov 2026). */
  variant?: 'row' | 'inline'
}) {
  const [all, setAll] = useState(false)
  const docs = docRefs(sources, evidence)
  if (!docs.length) return null
  const shown = all ? docs : docs.slice(0, max)
  return (
    <div className={(variant ? variant === 'row' : !!label) ? styles.row : styles.inline} role="group" aria-label={label || 'Sources'}>
      {label && <span className={styles.label}>{label}:</span>}
      {shown.map((d) => (
        <DocIcon key={`${d.source.id}-${d.title}`} doc={d} />
      ))}
      {docs.length > shown.length && (
        <button type="button" className={styles.more} onClick={() => setAll(true)}>
          +{docs.length - shown.length} more
        </button>
      )}
    </div>
  )
}
