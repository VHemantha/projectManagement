import type { Disposition, Finding, FindingKind, FindingStatus, ProgressEvent, Run, Severity, TrailStage, Verdict } from '@/api/precheck'

/** The screen builds its sentences from codes; the models only return codes and short lines. */
export const VERDICT_WORDS: Record<Exclude<Verdict, ''>, string> = {
  ready: 'Ready for review',
  ready_with_exceptions: 'Ready with exceptions',
  not_ready: 'Not ready',
}

export const KIND_LABELS: Record<FindingKind, string> = {
  fact: 'Fact',
  rule: 'Rule',
  client_preference: 'Client preference',
  ai_suggestion: 'AI suggestion',
}

export const STATUS_LABELS: Record<FindingStatus, string> = {
  addressed: 'Addressed',
  exception: 'Exception',
  missing: 'Missing',
  unclear: 'Needs an answer',
}

export const SEVERITY_LABELS: Record<Severity, string> = { high: 'High', medium: 'Medium', low: 'Low' }

export const DISPOSITION_LABELS: Record<Disposition, string> = {
  accepted: 'Accepted',
  rejected: 'Rejected',
  not_applicable: 'Not applicable',
  needs_clarification: 'Needs clarification',
}

export const DISPOSITION_ACTIONS: { value: Disposition; label: string }[] = [
  { value: 'accepted', label: 'Accept' },
  { value: 'rejected', label: 'Reject' },
  { value: 'not_applicable', label: 'Not applicable' },
  { value: 'needs_clarification', label: 'Needs clarification' },
]

export const BASIS_LABELS: Record<string, string> = {
  history: 'From past jobs',
  current: 'From this job\'s folder',
  standard: 'Standard for this kind of job',
}

export const TRAIL: { stage: TrailStage; name: string; waiting: string }[] = [
  { stage: 'read', name: 'Read', waiting: 'Documents in the job folder' },
  { stage: 'checked', name: 'Checked', waiting: 'Automatic checks' },
  { stage: 'compared', name: 'Compared', waiting: 'Direction Note items' },
  { stage: 'judged', name: 'Judged', waiting: 'Findings weighed' },
  { stage: 'verified', name: 'Verified', waiting: 'Sources linked' },
]

export type StepState = 'waiting' | 'running' | 'done'

/** One trail step's state and label: from the finished run's trail, or while running from the
 * latest live event for that step. A step is done once a later step has started. */
export function trailStep(run: Run, stage: TrailStage): { state: StepState; label: string } {
  const finished = run.trail?.[stage]
  if (finished) return { state: 'done', label: finished.label }
  const order = TRAIL.map((t) => t.stage)
  const events: ProgressEvent[] = run.progress ?? []
  const mine = events.filter((e) => e.stage === stage)
  if (!mine.length) return { state: 'waiting', label: TRAIL.find((t) => t.stage === stage)!.waiting }
  const last = mine[mine.length - 1]
  const laterStarted = events.some((e) => order.indexOf(e.stage) > order.indexOf(stage))
  const stopped = run.status !== 'running'
  return { state: last.state === 'done' || laterStarted || stopped ? 'done' : 'running', label: last.label }
}

export function openFindings(findings: Finding[]): Finding[] {
  return findings.filter((f) => f.status !== 'addressed')
}

export function formatTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}k` : String(n)
}

/** "9.1k tokens · 0% from cache · $0.012". */
export function costChip(run: Run): string | null {
  const totals = run.usage?.totals
  if (!totals) return null
  const tokens = totals.input + totals.output + totals.cache_read + totals.cache_write
  const parts = [`${formatTokens(tokens)} tokens`, `${Math.round((run.usage.cache_share ?? 0) * 100)}% from cache`]
  if (run.demo) parts.push('no cost (demo)')
  else if (run.usage.cost_usd != null) parts.push(`$${run.usage.cost_usd < 0.01 ? run.usage.cost_usd.toFixed(4) : run.usage.cost_usd.toFixed(2)}`)
  return parts.join(' · ')
}

export function duration(seconds: number | null): string {
  if (seconds == null) return ''
  return seconds < 60 ? `${Math.max(1, Math.round(seconds))} s` : `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`
}
