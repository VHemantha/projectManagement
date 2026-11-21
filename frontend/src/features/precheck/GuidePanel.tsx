import { AlertTriangle, CheckSquare, Clock, ExternalLink, Loader2, RotateCcw, Sparkles } from 'lucide-react'

import styles from './GuidePanel.module.css'
import { fromV2, GuideView } from './GuideView'
import { StopRun } from './StopRun'
import { extractErrorMessage } from '@/api/errors'
import { type GuideOutput, type GuideStep, type GuideV2, type GuideV3, useJobGuide, useRunGuide } from '@/api/guide'
import type { SourceRef } from '@/api/precheck'
import { Button, Skeleton } from '@/design-system'

type Evidence = GuideV2['evidence']

const FLAG_TEXT: Record<string, string> = {
  no_source: 'The AI gave no source for this step',
  figure_not_in_documents: 'It has an amount not found in the documents (it may be calculated) — check it',
  confirmation_not_documented: 'The AI called this confirmed, but no document in the folder shows it — treat it as suspected',
  longer_than_a_page_and_a_half: 'This guide is longer than one and a half pages',
  added_by_code: 'Rolled forward from the earlier guide but not taken up by the AI — settle it this year',
}

/** The preparation guide: after the pre-check, a briefing for the accountant preparing this year's
 * financial statements (format 3, AFIT 21 Nov 2026: points, never questions; areas of caution; the steps
 * to finalisation as a flow chart; tables and charts throughout). An eight-section guide (format 2) is
 * shown the same way; one written before those is shown as its steps. */
export function GuidePanel({ jobKey }: { jobKey: string }) {
  const { data, isLoading, isError } = useJobGuide(jobKey)
  const run = useRunGuide(jobKey)
  if (isLoading) return <Skeleton height={64} />
  if (isError || !data) return <p className={styles.muted}>The guide could not be loaded. Refresh the page to try again.</p>

  const latest = data.latest
  const body = (latest?.guide ?? {}) as { format?: number }
  const v3 = body.format === 3 ? (body as GuideV3) : body.format === 2 ? fromV2(body as GuideV2) : null
  const legacy = !v3 && 'steps' in body ? (body as unknown as GuideOutput) : null
  const written = Boolean(v3 || legacy)
  const running = latest?.status === 'running'

  return (
    <div className={styles.guide}>
      <div className={styles.head}>
        <p className={styles.lead}>
          A briefing for preparing this year&apos;s financial statements: where to be careful, the job, what carries over from last
          year, the main risks, every step from the start to finalisation, the areas needing judgment, the points to note and a
          completion checklist.
          {!data.has_precheck && ' Run the pre-check first for the best guide: it knows what is still to come from the client.'}
        </p>
        <Button variant="primary" size="sm" disabled={running || run.isPending} onClick={() => run.mutate()}>
          {running || run.isPending ? (
            <Loader2 size={14} className={styles.spin} aria-hidden="true" />
          ) : written ? (
            <RotateCcw size={14} aria-hidden="true" />
          ) : (
            <Sparkles size={14} aria-hidden="true" />
          )}
          {running ? 'Writing the guide…' : written ? 'Write it again' : 'Write the preparation guide'}
        </Button>
        {running && <StopRun jobKey={jobKey} runId={latest?.run_id} />}
      </div>
      {run.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(run.error, 'The guide could not be started.')}
        </p>
      )}
      {latest?.status === 'failed' && <p role="alert" className={styles.error}>{latest.failure_reason || 'The guide stopped.'}</p>}
      {v3 && <GuideView guide={v3} earlier={body.format === 2} />}
      {legacy && <LegacySteps guide={legacy} />}
      {!written && !running && <p className={styles.muted}>No guide yet.</p>}
    </div>
  )
}

function Sources({ sources, evidence }: { sources?: SourceRef[]; evidence: Evidence }) {
  if (!sources?.length) return null
  return (
    <span className={styles.sources}>
      {sources.map((src) => {
        const ev = src.evidence_id ? evidence[src.evidence_id] : undefined
        return ev ? (
          <a key={src.id} className={styles.source} href={ev.drive_url} target="_blank" rel="noreferrer" title={`${ev.file_name} — ${ev.location}: ${ev.quote}`}>
            {src.label} <ExternalLink size={11} aria-hidden="true" />
          </a>
        ) : (
          <span key={src.id} className={styles.source}>
            {src.label}
          </span>
        )
      })}
    </span>
  )
}

function Flags({ flags }: { flags?: string[] }) {
  if (!flags?.length) return null
  return (
    <>
      {flags.map((f) => (
        <p key={f} className={styles.flag}>
          <AlertTriangle size={12} aria-hidden="true" /> {FLAG_TEXT[f] ?? f}
        </p>
      ))}
    </>
  )
}

// ---- guides written before the eight sections ------------------------------------------------------

function LegacySteps({ guide }: { guide: GuideOutput }) {
  const groups = new Map<string, GuideStep[]>()
  for (const s of guide.steps) groups.set(s.area, [...(groups.get(s.area) ?? []), s])
  return (
    <>
      <div className={styles.summary}>
        <strong>{guide.decision.reason}</strong>
        {guide.summary && <p>{guide.summary}</p>}
      </div>
      {[...groups.entries()].map(([area, steps]) => (
        <section key={area} aria-label={area}>
          <h3 className={styles.area}>{area}</h3>
          <ol className={styles.steps}>
            {steps.map((s) => (
              <li key={s.step} className={styles.step}>
                <p className={styles.text}>{s.step}</p>
                {s.check && (
                  <p className={styles.check}>
                    <CheckSquare size={13} aria-hidden="true" /> {s.check}
                  </p>
                )}
                {s.waits_on_client && (
                  <p className={styles.waits}>
                    <Clock size={13} aria-hidden="true" /> Waits on information from the client
                  </p>
                )}
                <Sources sources={s.sources} evidence={guide.evidence} />
                <Flags flags={s.flags} />
              </li>
            ))}
          </ol>
        </section>
      ))}
    </>
  )
}
