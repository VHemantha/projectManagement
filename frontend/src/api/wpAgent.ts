import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { ProgressEvent, RunSummary } from './precheck'

export type GstBasis = 'payments' | 'invoice' | 'hybrid'
export type GstFrequency = 'monthly' | 'two_monthly' | 'six_monthly'
export type GstStatus = 'Reconciled' | 'Reconciled subject to corrections' | 'Unreconciled' | 'Incomplete evidence'
/** The WP Agent's reconciliation agents (10 Nov 2026): GST, wages (PAYE) and imputation (ICA). */
export type WpAgentKey = 'gst' | 'wages' | 'ica'

/** The job settings the accountant confirms before a run (AFIT spec, section 4). */
export interface GstSetup {
  entity: string
  ird_number: string
  fy_start: string
  balance_date: string
  basis: GstBasis
  frequency: GstFrequency
  software: string
  currency: string
  gl_version: string
  /** The GST control account(s), by name or code, comma-separated; empty: found by the agent. */
  gst_accounts: string
  first_year: boolean
  tolerance: string
  /** The wages and ICA agents' own settings (opening balances, accounts, retained earnings, ...). */
  [extra: string]: string | boolean
}

/** What a run is given: the Drive link(s), the ageing reports' own links, the settings and the
 * preparer's choices (continue with GL analysis when an ageing report has no GST column). */
export interface WpOptions {
  drive_link: string
  ar_link: string
  ap_link: string
  setup: GstSetup
  choices: { ar_gl_fallback?: boolean; ap_gl_fallback?: boolean }
}

/** Amounts arrive as strings (exact decimals); GST payable positive, receivable negative. */
export interface GstBridge {
  A: string
  A_current: string
  A_prior: string
  B: string
  C: string
  D: string
  E: string
  reported: string | null
  corrections: string
  F: string | null
  unexplained: string | null
  tolerance: string
}

export interface GstException {
  id: string
  code: string
  severity: 'blocking' | 'review' | 'info'
  text: string
  next_evidence: string
  refs: string[]
  amount: string | null
}

export interface GstCorrection {
  id: string
  title: string
  lines: { account: string; debit: string; credit: string }[]
  gst_effect?: string
  /** The wages agent's corrections act on the expense and the liability. */
  expense_effect?: string
  liability_effect?: string
  explanation: string
  evidence: string[]
  status: string
}

export interface GstAdjustment {
  id: string
  category: string
  direction: string
  effect: string
  status: string
  review: boolean
  /** False for a journal candidate no late claim confirms: listed, not in the bridge. */
  included?: boolean
  journals: string[]
  late_claims: string[]
  subsequent_return: string | null
  unmatched: string | null
  description: string
}

export interface GstPeriod {
  id: string
  period_end: string
  version: string
  filed: string | null
  net: string | null
  outstanding_bd: string | null
  settled_after: string
  standing: string
  prior_year: boolean
  origin: string
}

export interface GstPause {
  kind: 'no_gst_column' | 'missing_report'
  report: string
  message: string
}

export interface GstResult {
  status: GstStatus
  summary: string
  bridge: GstBridge
  settings: Record<string, unknown>
  detected: { return_periods: string[]; frequency: string; gst_accounts: string[]; ar_control: string[]; ap_control: string[]; latest_return: string }
  paused: Partial<Record<'ar' | 'ap', GstPause>>
  exceptions: GstException[]
  corrections: GstCorrection[]
  adjustments: GstAdjustment[]
  periods: GstPeriod[]
  receivables: { source: string; total: string; identified?: string; basis_note: string }
  payables: { source: string; total: string; identified?: string; basis_note: string }
  imports: { items: { id: string; description: string; amount: string; finding: string; treatment: string }[]; note: string }
  counts: { blocking: number; review: number; outstanding_returns: number }
  sources: { sid: string; name: string; path: string; kind: string; kind_how: string; error: string; url: string }[]
  /** Wages and ICA: each conclusion, and the statement lines in the workpaper's own labels. */
  conclusions: WpConclusion[]
  lines: WpLine[]
}

export interface WpConclusion {
  label: string
  status: string
  residual: string | null
}

export interface WpLine {
  label: string
  value?: string | null
  note?: string
  heading?: boolean
  strong?: boolean
  indent?: number
  ratio?: boolean
}

export interface WpRun extends RunSummary {
  kind: WpAgentKey
  gst: Partial<GstResult>
  progress: ProgressEvent[]
  failure_reason: string
  options: Partial<WpOptions>
  has_workpaper: boolean
}

export interface WpAgentState {
  agent?: WpAgentKey
  agents?: { key: WpAgentKey; name: string; settings: string[] }[]
  latest: WpRun | null
  history: RunSummary[]
  defaults: Partial<WpOptions>
}

export function useWpAgent(jobKey: string, agent: WpAgentKey = 'gst') {
  return useQuery({
    queryKey: ['precheck', jobKey, 'wp-agent', agent],
    queryFn: async () => (await apiClient.get<WpAgentState>(`/precheck/jobs/${jobKey}/wp-agent/`, { params: { agent } })).data,
    refetchInterval: (query) => (query.state.data?.latest?.status === 'running' ? 3000 : false),
  })
}

export function useRunWpAgent(jobKey: string, agent: WpAgentKey = 'gst') {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (options: WpOptions) => (await apiClient.post<WpRun>(`/precheck/jobs/${jobKey}/wp-agent/`, { ...options, agent })).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] }),
  })
}

/** The run's Excel workpaper, saved by the browser. */
export async function downloadWorkpaper(runId: string, fileName: string) {
  const { data } = await apiClient.get<Blob>(`/precheck/runs/${runId}/workpaper.xlsx`, { responseType: 'blob' })
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}
