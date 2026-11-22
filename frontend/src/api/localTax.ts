import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

/** The Local Tax workflow (AFIT, 22 Nov 2026), for Team 3 > Local's cards only. Money arrives as strings
 * (exact decimals from the engine). */
export type Money = string | null
export type StageKey = 'questionnaire' | 'fs' | 'computation' | 'return'
export type StageStatus = 'not_started' | 'in_progress' | 'ready_for_review' | 'approved'

export interface IncomeLine {
  id?: string
  category: string
  description: string
  amount: string
  lkr_amount?: string
  treatment: 'auto' | 'taxable' | 'exempt' | 'final_wht' | 'special_rate'
  source?: string
  foreign?: { country: string; currency: string; foreign_amount: string; rate: string; service_used_outside: boolean; received_in_fx_through_bank: boolean; foreign_tax_paid: string }
  expenses: { id?: string; description: string; amount: string; classification: 'allowable' | 'disallowable' | 'capital' | 'clarify' }[]
}
export interface AssetLine { id?: string; kind: string; description: string; value: string; ownership?: string; acquired?: string; notes?: string }
export interface LiabilityLine { id?: string; kind: string; description: string; value: string; lender?: string; notes?: string }
export interface PaymentLine { id?: string; type: string; amount: string; date: string; reference: string; creditable?: boolean | null }
export interface CompLine { id?: string; label: string; amount: string; note?: string; source?: string }
export interface CapitalAllowance { id?: string; label: string; asset_class: string; cost: string; amount: string }
export interface SpecialIncome { id?: string; label: string; amount: string; rate_key: string }

export interface FixedAsset { id?: string; description: string; asset_class: string; acquired?: string; cost: string; ca_claimed_bf?: string; allowance?: string; disposed?: string; proceeds?: string; source?: string }
export interface LossYear { id?: string; ya: string; amount: string; source?: string }
export interface EngagementData {
  income?: IncomeLine[]
  assets?: AssetLine[]
  liabilities?: LiabilityLine[]
  payments?: PaymentLine[]
  qualifying_payments?: string
  losses_bf?: string
  expected_skipped?: boolean
  computation?: { add_backs?: CompLine[]; deductions?: CompLine[]; capital_allowances?: CapitalAllowance[]; special_income?: SpecialIncome[]; pbt_manual?: string }
  return_overrides?: Record<string, string | null>
  fixed_assets?: FixedAsset[]
  loss_history?: LossYear[]
  prior_year?: { ya: string; source: string; items: { label: string; amount: string }[] }
  policy_text?: Record<string, string>
  note_text?: Record<string, string>
}

export interface Engagement {
  id: number
  task: string
  entity_type: 'individual' | 'company'
  residency: 'resident' | 'non_resident'
  year_of_assessment: string
  fy_end: string | null
  tax_type: 'CIT' | 'IIT'
  legal_name: string
  client_name: string
  tin: string
  nic_or_reg: string
  address: string
  activity: string
  reporting_framework: 'full' | 'smes' | 'smaller'
  audited: boolean
  expected_tax: Money
  expected_basis: 'total' | 'remaining'
  data: EngagementData
  stages: Record<StageKey, { status: StageStatus; by?: string; at?: string; reopened?: boolean }>
  version: number
  can_approve: boolean
  can_validate?: boolean
  updated_at: string
}

export interface CompLineOut { key: string; label: string; amount: Money; kind: string; note: string; rule: string; ref: string; source: string; level: number }
export interface Computation {
  lines: CompLineOut[]
  taxable_income: Money
  income_tax: Money
  credits: Money
  payable: Money
  pbt?: Money
  flags: { severity: string; text: string }[]
  rules: { rule: string; ref: string; validated: boolean; value: unknown; reviewed_by?: string }[]
  unvalidated: boolean
  capital_allowance_schedule?: CaSchedule | null
  loss_schedule?: { rows: { ya: string; bf: Money; utilised: Money; cf: Money; current?: boolean }[]; totals: { bf: Money; utilised: Money; cf: Money } }
}
export interface CaRow { id: string; description: string; asset_class: string; label: string; cost: Money; claimed_bf: Money; wdv_bf: Money; rate: Money; allowance: Money; balancing_charge: Money; balancing_allowance: Money; wdv_cf: Money; disposed: string; manual?: boolean; ref: string }
export interface CaSchedule { rows: CaRow[]; totals: Record<'cost' | 'claimed_bf' | 'allowance' | 'balancing_charge' | 'balancing_allowance' | 'wdv_cf', Money>; flags: { severity: string; text: string }[] }
export interface Check { label: string; passed: boolean; difference: Money }
export interface CashSection { key: string; title: string; rows: { label: string; amount: Money; note: string }[]; subtotal: { label: string; amount: Money } | null; after?: { label: string; amount: Money; note: string }[]; total: { label: string; amount: Money } }
export interface Note { no: number; key: string; title: string; text?: string; to_complete?: boolean; editable?: boolean; total?: Money; total_comparative?: Money; lines?: { code: string; name: string; amount: Money; comparative: Money }[]; rows?: { label: string; amount: Money }[]; policies?: { key: string; title: string; text: string; standard: boolean }[] }
export interface Statements {
  equity: { rows: { label: string; share_capital: Money; reserves: Money; retained_earnings: Money; total: Money; kind?: string }[]; check: Check; notes: string[] }
  cash_flows: { available: false; reason: string } | { available: true; sections: CashSection[]; net_change: Money; opening_cash: Money; closing_cash: Money; check: Check; notes: string[] }
  notes: Note[]
  audit_report: { label: string; title: string; addressee: string; sections: { title: string; text: string }[]; signature: string } | null
}
export interface TbRow { code: string; name: string; amount: Money; comparative: Money; heading: string; heading_by?: string; adjusted?: boolean; original?: Money }
export interface PlFigures { revenue: Money; cost_of_sales: Money; gross_profit: Money; other_income: Money; admin_expenses: Money; distribution_expenses: Money; finance_costs: Money; pbt: Money; income_tax_expense: Money; profit: Money; oci: Money; total_comprehensive_income: Money }
export interface Financials {
  kind: 'company' | 'individual'
  pl?: { current: PlFigures; comparative: PlFigures | null }
  bs?: Record<string, { label: string; kind: string; amount: Money; comparative: Money; lines: { code: string; name: string; amount: Money }[] }>
  totals?: { assets: Money; equity: Money; liabilities: Money }
  pbt?: Money
  checks?: { label: string; passed: boolean; difference: Money }[]
  unusual?: string[]
  unmapped?: { code: string; name: string; amount: Money }[]
  tb?: TbRow[]
  has_comparative?: boolean
  sources?: { id: string; category: string; description: string; income: Money; expenses: { description: string; amount: Money; classification: string }[]; expenses_total: Money; net: Money }[]
  total_income?: Money
  total_expenses?: Money
  net?: Money
}
export interface Scenario { key: string; label: string; group: string; amount: Money; scope: string; feasible: boolean; proposed?: Money; change?: Money; reason?: string }
export interface Reverse {
  expected: Money
  basis: 'total' | 'remaining'
  calculated: Money
  variance: Money
  taxable_income: Money
  required_taxable_income: Money
  taxable_income_difference: Money
  scenarios: Scenario[]
  unsupported?: string
}
export interface ReturnField { code: string; label: string; value: string | null; source: string; required: boolean; missing: boolean; kind: string; overridden?: boolean; computed?: string | null; validated?: boolean; official?: string }
export interface DraftReturn { sections: { key: string; title: string; fields: ReturnField[] }[]; missing: { section: string; code: string; label: string }[]; note: string; validated?: boolean; unchecked?: number }
export interface Adjustment {
  id: number
  kind: 'journal' | 'reclass' | 'tax' | 'reverse'
  scope: 'accounting' | 'tax'
  target: string
  label: string
  original: Money
  proposed: Money
  difference: Money
  lines: { code: string; name?: string; amount: string }[]
  reason: string
  evidence: { id: number; name: string } | null
  evidence_note: string
  status: 'proposed' | 'approved' | 'rejected'
  history: unknown[]
  created_by: string
  created_at: string
  decided_by: string
  decided_at: string | null
  decision_note: string
}
export interface Lever { key: string; label: string; group: string; amount: Money; scope: string }
export interface Alert { stage: StageKey; severity: 'blocking' | 'review' | 'info'; text: string }

export interface LocalTaxState {
  engagement: Engagement
  financials: Financials | null
  computation: Computation | null
  reverse: Reverse | null
  return: DraftReturn | null
  statements?: Statements | null
  alerts: Alert[]
  years: string[]
  rules_status?: string
  adjustments: Adjustment[]
  levers?: Lever[]
  progress?: Record<StageKey, number>
}

export interface AiMessage { id: number; role: 'person' | 'ai'; text: string; data: { points?: string[]; uncertain?: boolean; what_if?: WhatIf | null }; by: string; at: string }
export interface WhatIf { lever: { key: string; label: string }; original: Money; proposed: Money; difference: Money; taxable_before: Money; taxable_after: Money; tax_before: Money; tax_after: Money; remaining_variance?: Money; hypothetical: true }
export interface Extraction { id: number; kind: string; document: string; status: string; created_at: string; data: { lines: { description: string; amount: string; category: string; code: string; comparative: string; date?: string; cite: string }[]; gaps: string[]; summary: string; year_of_assessment?: string } }
export const EXTRACTION_USES: { key: string; label: string }[] = [
  { key: 'trial_balance', label: 'Trial balance' }, { key: 'general_ledger', label: 'General ledger (summed into the TB)' },
  { key: 'income', label: 'Income lines' }, { key: 'payments', label: 'Tax payments' },
  { key: 'prior_return', label: "Prior year's return / computation" }, { key: 'fixed_assets', label: 'Fixed asset register' },
]
export interface AiItems { summary: string; questions: string[]; items: { title: string; text: string; reference: string; lever: string | null; severity: string; needs_review: boolean }[] }

const base = (key: string) => `/local-tax/tasks/${key}/`
const qk = (key: string) => ['local-tax', key]

export function useLocalTax(key: string) {
  return useQuery({ queryKey: qk(key), queryFn: async () => (await apiClient.get<LocalTaxState>(base(key))).data })
}

function useStateMutation<T>(key: string, fn: (vars: T) => Promise<LocalTaxState>) {
  const queryClient = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: (data) => queryClient.setQueryData(qk(key), data) })
}

export function useSaveLocalTax(key: string) {
  return useStateMutation(key, async (patch: Partial<Omit<Engagement, 'data'>> & { data?: EngagementData; stage?: StageKey; reason?: string }) =>
    (await apiClient.patch<LocalTaxState>(base(key), patch)).data)
}

export function usePutTb(key: string) {
  return useStateMutation(key, async (rows: Partial<TbRow>[]) => (await apiClient.put<LocalTaxState>(`${base(key)}tb/`, { rows })).data)
}

export function useUploadTb(key: string) {
  return useStateMutation(key, async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return (await apiClient.post<LocalTaxState>(`${base(key)}tb/upload/`, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data
  })
}

export function useMapLine(key: string) {
  return useStateMutation(key, async ({ code, heading }: { code: string; heading: string }) =>
    (await apiClient.patch<LocalTaxState>(`${base(key)}tb/${encodeURIComponent(code)}/`, { heading })).data)
}

export interface AdjustmentInput {
  kind: Adjustment['kind']
  target?: string
  proposed?: string
  label?: string
  reason: string
  evidence_id?: number | null
  evidence_note?: string
  lines?: { code: string; name?: string; amount: string }[]
}

export function useProposeAdjustment(key: string) {
  return useStateMutation(key, async (body: AdjustmentInput) => (await apiClient.post<LocalTaxState>(`${base(key)}adjustments/`, body)).data)
}

export function useEditAdjustment(key: string) {
  return useStateMutation(key, async ({ id, ...body }: Partial<AdjustmentInput> & { id: number }) =>
    (await apiClient.patch<LocalTaxState>(`${base(key)}adjustments/${id}/`, body)).data)
}

export function useDecideAdjustment(key: string) {
  return useStateMutation(key, async ({ id, decision, note }: { id: number; decision: 'approve' | 'reject'; note?: string }) =>
    (await apiClient.post<LocalTaxState>(`${base(key)}adjustments/${id}/decide/`, { decision, note })).data)
}

export function useSetStage(key: string) {
  return useStateMutation(key, async ({ stage, status, acknowledge }: { stage: StageKey; status: StageStatus; acknowledge?: boolean }) =>
    (await apiClient.post<LocalTaxState>(`${base(key)}stages/${stage}/`, { status, acknowledge_unvalidated: acknowledge || undefined })).data)
}

/** The 409 the API answers when approving figures that rest on rules not yet validated: the rules, to confirm. */
export function needsAcknowledgement(error: unknown): string[] | null {
  const data = (error as { response?: { status?: number; data?: { needs_acknowledgement?: boolean; unvalidated?: string[] } } })?.response
  return data?.status === 409 && data.data?.needs_acknowledgement ? data.data.unvalidated ?? [] : null
}

// --- Phase 4: the tax professional's review of the rules and the return's field references -----------------------
export interface ReviewedRule {
  rule: string; label: string; value: unknown; file_value: unknown; ref: string; validated: boolean; reviewed_by: string; reviewed_at: string; conditions: string[]
  history: { status: 'validated' | 'corrected'; value: unknown; file_value: unknown; ref: string; note: string; active: boolean; by: string; at: string }[]
}
export interface FieldReview { id: number; entity_type: 'company' | 'individual'; code: string; official: string; note: string; active: boolean; by: string; at: string }
export interface RuleRegister { year_of_assessment: string; status: string; legislation: string; rules: ReviewedRule[]; validated: number; total: number; fields: FieldReview[]; can_validate: boolean }
export interface RuleCheckResult { agrees: 'yes' | 'no' | 'unclear'; value_in_document: string; quote: string; cite: string; note: string; document: string }

const ya = (year: string) => year.replace('/', '-')

export function useRuleRegister(year: string) {
  return useQuery({ queryKey: ['local-tax-rules', year], queryFn: async () => (await apiClient.get<RuleRegister>(`/local-tax/rules/${ya(year)}/review/`)).data })
}

function useRegisterMutation<T>(year: string, fn: (vars: T) => Promise<RuleRegister>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      queryClient.setQueryData(['local-tax-rules', year], data)
      queryClient.invalidateQueries({ queryKey: ['local-tax'] })
    },
  })
}

export function useReviewRule(year: string) {
  return useRegisterMutation(year, async (body: { rule: string; action: 'validate' | 'correct' | 'withdraw'; value?: unknown; ref?: string; note?: string }) =>
    (await apiClient.post<RuleRegister>(`/local-tax/rules/${ya(year)}/review/`, body)).data)
}

export function useReviewField(year: string) {
  return useRegisterMutation(year, async (body: { entity_type: 'company' | 'individual'; code: string; official?: string; note?: string; withdraw?: boolean }) =>
    (await apiClient.post<RuleRegister>(`/local-tax/rules/${ya(year)}/fields/`, body)).data)
}

export function useRuleCheck(year: string) {
  return useMutation({
    mutationFn: async ({ rule, file }: { rule: string; file: File }) => {
      const form = new FormData()
      form.append('rule', rule)
      form.append('file', file)
      return (await apiClient.post<RuleCheckResult>(`/local-tax/rules/${ya(year)}/review/check/`, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data
    },
  })
}

export async function reverseEffect(key: string, lever: string, proposed: string) {
  return (await apiClient.post<WhatIf>(`${base(key)}reverse/effect/`, { lever, proposed })).data
}

export function useMessages(key: string) {
  return useQuery({
    queryKey: [...qk(key), 'messages'],
    queryFn: async () => (await apiClient.get<{ messages: AiMessage[]; extractions: Extraction[] }>(`${base(key)}messages/`)).data,
  })
}

export function useAskLocalTax(key: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (question: string) => (await apiClient.post<{ message: AiMessage }>(`${base(key)}ai/chat/`, { question })).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: [...qk(key), 'messages'] }),
  })
}

export function useAiAgent<T>(key: string, agent: 'map-tb' | 'analyse' | 'reverse' | 'return' | 'policies') {
  return useMutation({ mutationFn: async (request?: string) => (await apiClient.post<T>(`${base(key)}ai/${agent}/`, { request })).data })
}

export function useExtract(key: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ attachmentId, kind }: { attachmentId: number; kind: string }) =>
      (await apiClient.post<{ extraction: Extraction }>(`${base(key)}ai/extract/`, { attachment_id: attachmentId, kind })).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: [...qk(key), 'messages'] }),
  })
}

export function useDecideExtraction(key: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, decision, use_as }: { id: number; decision: 'confirm' | 'reject'; use_as?: string }) =>
      (await apiClient.post<LocalTaxState>(`${base(key)}extractions/${id}/decide/`, { decision, use_as })).data,
    onSuccess: (data) => {
      queryClient.setQueryData(qk(key), data)
      queryClient.invalidateQueries({ queryKey: [...qk(key), 'messages'] })
    },
  })
}

/** A document (fs, computation or return) as PDF or Excel, saved by the browser - or, for a preview, opened. */
export async function downloadLocalTax(key: string, doc: 'fs' | 'computation' | 'return', fmt: 'pdf' | 'xlsx', open = false) {
  const res = await apiClient.get<Blob>(`${base(key)}export/${doc}.${fmt}`, { responseType: 'blob' })
  const url = URL.createObjectURL(res.data)
  if (open) {
    window.open(url, '_blank', 'noopener')
    return
  }
  const disposition = String(res.headers?.['content-disposition'] ?? '')
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `${key}-${doc}.${fmt}`
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export const money = (v: Money | number | undefined, opts: { brackets?: boolean } = {}) => {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  const text = Math.abs(n).toLocaleString('en-LK', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
  return n < 0 ? (opts.brackets === false ? `-${text}` : `(${text})`) : text
}

export const STAGES: { key: StageKey; n: number; title: string; purpose: string }[] = [
  { key: 'questionnaire', n: 1, title: 'Questionnaire', purpose: 'Collect client information' },
  { key: 'fs', n: 2, title: 'Financial Statements', purpose: 'Prepare financials' },
  { key: 'computation', n: 3, title: 'Tax Computation', purpose: 'Calculate income tax' },
  { key: 'return', n: 4, title: 'Draft Tax Return', purpose: 'Generate draft return' },
]

export const STATUS_LABEL: Record<StageStatus, string> = {
  not_started: 'Not Started',
  in_progress: 'In Progress',
  ready_for_review: 'Ready for Review',
  approved: 'Approved',
}
