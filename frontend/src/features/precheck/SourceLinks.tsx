import { DocIcon, DocIcons } from './DocIcons'
import { classify } from './docKinds'
import type { PrecheckOutput, SourceRef } from '@/api/precheck'

type Evidence = PrecheckOutput['evidence']

/** One source behind a statement or figure, as its document icon (AFIT reference icons, 19 Nov
 * 2026): it opens the document at the quoted line when there is one. */
export function Source({ source, evidence }: { source: SourceRef; evidence: Evidence }) {
  return <DocIcon doc={classify(source, evidence)} />
}

/** The sources behind a statement, inline: an icon each (one per document), "+N more" past four. */
export function Sources({ sources, evidence }: { sources: SourceRef[]; evidence: Evidence }) {
  return <DocIcons sources={sources} evidence={evidence} label="" max={4} />
}
