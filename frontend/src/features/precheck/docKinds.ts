import type { PrecheckOutput, SourceRef } from '@/api/precheck'

/** The kinds of supporting document a pre-check point rests on, each shown as an icon with a short
 * badge and, where known, its financial year (AFIT reference icons, 19 Nov 2026). */
export type DocKind =
  | 'FS' | 'GL' | 'TB' | 'BANK' | 'INV' | 'AGR' | 'PROP' | 'INS' | 'LOAN' | 'STK' | 'PAY' | 'GST' | 'TAX' | 'WP' | 'CQ' | 'CHK' | 'NOTE' | 'SUP'

export const DOC_LABEL: Record<DocKind, string> = {
  FS: 'Financial statements', GL: 'General ledger', TB: 'Trial balance', BANK: 'Bank statements', INV: 'Invoices / receipts',
  AGR: 'Agreements / contracts', PROP: 'Property documents', INS: 'Insurance policy', LOAN: 'Loan statements', STK: 'Stock reports',
  PAY: 'Payroll / IRD reports', GST: 'GST returns', TAX: 'Tax returns', WP: 'Workpapers / schedules', CQ: 'Client questionnaire',
  CHK: 'Check by code', NOTE: 'Note from AFIT', SUP: 'Other supporting document',
}

export const DOC_BADGE: Record<DocKind, string> = {
  FS: 'FS', GL: 'GL', TB: 'TB', BANK: 'Bank', INV: 'INV', AGR: 'AGR', PROP: 'PROP', INS: 'INS', LOAN: 'LOAN', STK: 'STK', PAY: 'PAY',
  GST: 'GST', TAX: 'TAX', WP: 'WP', CQ: 'CQ', CHK: 'CHK', NOTE: 'NOTE', SUP: 'SUP',
}

// What a document is, from its name and the pre-check's label for it; the first match wins.
const BY_WORDS: [DocKind, RegExp][] = [
  ['FS', /financial statements?|statement of (financial position|profit|comprehensive)|annual report|\bfs\b|balance sheet|profit (and|&) loss/],
  ['TB', /trial balance|\btb\b/],
  ['GL', /general ledger|\bledger\b|\bgl\b/],
  ['GST', /\bgst\b/],
  ['TAX', /tax return|\bir[34][a-z]?\b|income tax|tax computation|terminal tax|provisional tax/],
  ['LOAN', /\bloan\b|mortgage|refinanc|lending/],
  ['BANK', /\bbank\b|transactions?|statement of account|\b\d{2}-\d{4}-\d{7}-\d{2,3}\b|anz|asb|bnz|westpac|kiwibank/],
  ['INV', /invoice|receipt|\bbill\b|purchase order/],
  ['AGR', /agreement|contract|lease|tenancy|deed|minutes|resolution/],
  ['INS', /insurance|policy|premium|insurer/],
  ['PROP', /property|rates|council|title|settlement|sale and purchase|body corporate|valuation/],
  ['STK', /stock|inventory/],
  ['PAY', /payroll|paye|payslip|wages|salar|\bird\b|myir|kiwisaver|employment/],
  ['WP', /workpaper|working paper|schedule|reconciliation|register|depreciation/],
  ['CQ', /questionnaire|checklist|\bcq\b/],
]

// What the pre-check's own source ids are (Q questionnaire, F last year's statements, T trial
// balance, W workpaper, B bank export, G ledger, C a code check, N Direction Note, M an
// accountant's answer, P an earlier request, SN a special note); D and R are read from the name.
const BY_ID: Record<string, DocKind> = { Q: 'CQ', F: 'FS', T: 'TB', W: 'WP', B: 'BANK', G: 'GL', C: 'CHK', N: 'NOTE', M: 'NOTE', P: 'SUP', SN: 'NOTE' }

export interface DocRef {
  kind: DocKind
  /** "FY25" when the document's year is known. */
  year: string
  /** Full description: what it is, the file and the place in it. */
  title: string
  href: string
  source: SourceRef
}

function yearOf(text: string): string {
  const fy = text.match(/\bfy\s?'?(\d{2})\b/i)
  if (fy) return `FY${fy[1]}`
  const full = text.match(/\b(20\d\d)\b/g)
  if (!full) return ''
  return `FY${full[full.length - 1].slice(2)}`
}

export function classify(source: SourceRef, evidence: PrecheckOutput['evidence']): DocRef {
  const ev = source.evidence_id ? evidence[source.evidence_id] : undefined
  const prefix = (source.id.match(/^(SN|[A-Z])\d/) ?? [])[1] ?? ''
  const words = `${source.label} ${ev?.file_name ?? ''}`.toLowerCase()
  let kind: DocKind = BY_ID[prefix] ?? 'SUP'
  // A received document (D, R), or a code check about one, is named by what it is.
  if (!BY_ID[prefix] || prefix === 'C' || kind === 'SUP') kind = BY_WORDS.find(([, re]) => re.test(words))?.[0] ?? kind
  const title = [DOC_LABEL[kind], ev ? `${ev.file_name}${ev.location ? `, ${ev.location}` : ''}` : source.label].join(': ')
  return { kind, year: yearOf(ev?.file_name ?? source.label), title: ev?.quote ? `${title} — “${ev.quote}”` : title, href: ev?.drive_url ?? '', source }
}

/** Each document once (several lines of the same file are one icon), in the order given. */
export function docRefs(sources: SourceRef[], evidence: PrecheckOutput['evidence']): DocRef[] {
  const seen = new Set<string>()
  const out: DocRef[] = []
  for (const s of sources) {
    const ref = classify(s, evidence)
    const key = s.evidence_id ? (evidence[s.evidence_id]?.file_name ?? s.label) : s.label
    if (seen.has(key)) continue
    seen.add(key)
    out.push(ref)
  }
  return out
}
