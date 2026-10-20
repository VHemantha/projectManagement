import { AlertTriangle, CheckSquare, Clock, ExternalLink, Loader2, RotateCcw, Sparkles } from 'lucide-react'

import styles from './GuidePanel.module.css'
import { StopRun } from './StopRun'
import { extractErrorMessage } from '@/api/errors'
import { type GuideOutput, type GuideStep, useJobGuide, useRunGuide } from '@/api/guide'
import { Button, Skeleton } from '@/design-system'

const FLAG_TEXT: Record<string, string> = {
  no_source: 'The AI gave no source for this step',
  figure_not_in_documents: 'It mentions a figure not found in the documents — check it',
}

/** The preparation guide: after the pre-check, the steps to prepare this year's financial
 * statements, each with the figures from the documents and how to verify it. */
export function GuidePanel({ jobKey }: { jobKey: string }) {
  const { data, isLoading, isError } = useJobGuide(jobKey)
  const run = useRunGuide(jobKey)
  if (isLoading) return <Skeleton height={64} />
  if (isError || !data) return <p className={styles.muted}>The guide could not be loaded. Refresh the page to try again.</p>

  const latest = data.latest
  const guide = latest && 'steps' in (latest.guide ?? {}) ? (latest.guide as GuideOutput) : null
  const running = latest?.status === 'running'
  const groups = new Map<string, GuideStep[]>()
  for (const s of guide?.steps ?? []) groups.set(s.area, [...(groups.get(s.area) ?? []), s])

  return (
    <div className={styles.guide}>
      <div className={styles.head}>
        <p className={styles.lead}>
          Step by step, how to prepare this year&apos;s financial statements from what is in the folder: each step with its
          figures and how to check them.
          {!data.has_precheck && ' Run the pre-check first for the best guide: it knows what is still to come from the client.'}
        </p>
        <Button variant="primary" size="sm" disabled={running || run.isPending} onClick={() => run.mutate()}>
          {running || run.isPending ? (
            <Loader2 size={14} className={styles.spin} aria-hidden="true" />
          ) : guide ? (
            <RotateCcw size={14} aria-hidden="true" />
          ) : (
            <Sparkles size={14} aria-hidden="true" />
          )}
          {running ? 'Writing the guide…' : guide ? 'Write it again' : 'Write the preparation guide'}
        </Button>
        {running && <StopRun jobKey={jobKey} runId={latest?.run_id} />}
      </div>
      {run.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(run.error, 'The guide could not be started.')}
        </p>
      )}
      {latest?.status === 'failed' && <p role="alert" className={styles.error}>{latest.failure_reason || 'The guide stopped.'}</p>}
      {guide && (
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
                    {s.sources.length > 0 && (
                      <span className={styles.sources}>
                        {s.sources.map((src) => {
                          const ev = src.evidence_id ? guide.evidence[src.evidence_id] : undefined
                          return ev ? (
                            <a key={src.id} className={styles.source} href={ev.drive_url} target="_blank" rel="noreferrer"
                              title={`${ev.file_name} — ${ev.location}: ${ev.quote}`}>
                              {src.label} <ExternalLink size={11} aria-hidden="true" />
                            </a>
                          ) : (
                            <span key={src.id} className={styles.source}>
                              {src.label}
                            </span>
                          )
                        })}
                      </span>
                    )}
                    {s.flags.map((f) => (
                      <p key={f} className={styles.flag}>
                        <AlertTriangle size={12} aria-hidden="true" /> {FLAG_TEXT[f] ?? f}
                      </p>
                    ))}
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </>
      )}
      {!guide && !running && <p className={styles.muted}>No guide yet.</p>}
    </div>
  )
}
