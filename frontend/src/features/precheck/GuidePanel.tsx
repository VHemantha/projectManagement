import { AlertTriangle, CheckSquare, Clock, ExternalLink, Loader2, RotateCcw, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'

import styles from './GuidePanel.module.css'
import { StopRun } from './StopRun'
import { extractErrorMessage } from '@/api/errors'
import { type GuideEvent, type GuideOutput, type GuideStep, type GuideV2, useJobGuide, useRunGuide } from '@/api/guide'
import type { SourceRef } from '@/api/precheck'
import { Button, Skeleton } from '@/design-system'

type Evidence = GuideV2['evidence']

const FLAG_TEXT: Record<string, string> = {
  no_source: 'The AI gave no source for this step',
  figure_not_in_documents: 'It mentions a figure not found in the documents — check it',
  confirmation_not_documented: 'The AI called this confirmed, but no document in the folder shows it — treat it as suspected',
  longer_than_a_page_and_a_half: 'This guide is longer than one and a half pages',
}
const MISSING_TEXT: Record<string, string> = { sequence: 'a step to deal with it', checklist: 'a checklist line', query: 'a question to confirm it' }
const PRIOR_KIND: Record<string, string> = {
  error: 'Previous error', reviewer_point: 'Reviewer point', unresolved: 'Unresolved', policy: 'Policy', balance: 'Balance to follow through',
}
const CHECK_STATUS: Record<string, string> = { done: 'Done', open: 'Open', na: 'N/A' }

/** The preparation guide: after the pre-check, a briefing for the accountant preparing this year's
 * financial statements, in AFIT's eight sections — from the job snapshot and the significant events
 * of the year to the completion checklist. Guides written before then are shown as their steps. */
export function GuidePanel({ jobKey }: { jobKey: string }) {
  const { data, isLoading, isError } = useJobGuide(jobKey)
  const run = useRunGuide(jobKey)
  if (isLoading) return <Skeleton height={64} />
  if (isError || !data) return <p className={styles.muted}>The guide could not be loaded. Refresh the page to try again.</p>

  const latest = data.latest
  const body = (latest?.guide ?? {}) as Partial<GuideV2> & Partial<GuideOutput>
  const v2 = body.format === 2 ? (body as GuideV2) : null
  const legacy = !v2 && 'steps' in body ? (body as GuideOutput) : null
  const written = Boolean(v2 || legacy)
  const running = latest?.status === 'running'

  return (
    <div className={styles.guide}>
      <div className={styles.head}>
        <p className={styles.lead}>
          A briefing for preparing this year&apos;s financial statements: the job, the year&apos;s significant events, what carries
          over from last year, the main risks, where to start, the judgments, the queries and a completion checklist.
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
      {v2 && <EightSections guide={v2} />}
      {legacy && <LegacySteps guide={legacy} />}
      {!written && !running && <p className={styles.muted}>No guide yet.</p>}
    </div>
  )
}

// ---- the eight sections ----------------------------------------------------------------------------

function EightSections({ guide }: { guide: GuideV2 }) {
  const ev = guide.evidence
  const { snapshot: s, queries: q } = guide
  return (
    <>
      <div className={styles.summary}>
        <strong>{guide.decision.reason}</strong>
        <Flags flags={guide.flags} />
      </div>

      <Section n={1} title="Job snapshot">
        <dl className={styles.snapshot}>
          {(
            [
              ['Business', s.activities],
              ['Assets and funding', s.assets_and_funding],
              ['Records available', s.records],
              ['Bookkeeping', s.bookkeeping],
              ['Period', s.period],
            ] as const
          )
            .filter(([, v]) => v)
            .map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
        </dl>
        <Sources sources={s.sources} evidence={ev} />
        <Flags flags={s.flags} />
      </Section>

      <Section n={2} title="Significant events and alerts" empty={!guide.events.length && 'No significant events found in the documents.'}>
        {guide.events.map((e) => (
          <EventAlert key={e.id} e={e} evidence={ev} />
        ))}
      </Section>

      <Section n={3} title="Prior-year findings and continuity" empty={!guide.prior_year.length && 'Nothing carried over from last year in the documents.'}>
        <ul className={styles.list}>
          {guide.prior_year.map((p) => (
            <li key={p.item}>
              <span className={styles.tag}>{PRIOR_KIND[p.kind] ?? p.kind}</span> {p.item}
              {p.follow_through && <span className={styles.then}> — {p.follow_through}</span>}
              <Sources sources={p.sources} evidence={ev} />
              <Flags flags={p.flags} />
            </li>
          ))}
        </ul>
      </Section>

      <Section n={4} title="Priority risks and material areas" empty={!guide.risks.length && 'No job-specific risks identified.'}>
        <ol className={styles.list}>
          {guide.risks.map((r) => (
            <li key={r.what_could_be_wrong}>
              <strong>{r.area}:</strong> {r.what_could_be_wrong} <Refs ids={r.events} />
              <p className={styles.detail}>
                <span className={styles.label}>Examine</span> {r.examine}
              </p>
              <p className={styles.detail}>
                <span className={styles.label}>Evidence needed</span> {r.evidence}
              </p>
              <Sources sources={r.sources} evidence={ev} />
              <Flags flags={r.flags} />
            </li>
          ))}
        </ol>
      </Section>

      <Section n={5} title="Starting sequence" empty={!guide.sequence.length && 'No steps given.'}>
        <ol className={styles.list}>
          {guide.sequence.map((st) => (
            <li key={st.step}>
              {st.step} <Refs ids={st.events} />
              <p className={st.can_start_now ? styles.now : styles.waits}>
                {st.can_start_now ? (
                  <>
                    <CheckSquare size={13} aria-hidden="true" /> Can start now
                  </>
                ) : (
                  <>
                    <Clock size={13} aria-hidden="true" /> Waits on: {st.depends_on || 'an earlier step'}
                  </>
                )}
              </p>
              {st.escalate && (
                <p className={styles.flag}>
                  <AlertTriangle size={12} aria-hidden="true" /> Escalate: {st.escalate}
                </p>
              )}
              <Sources sources={st.sources} evidence={ev} />
              <Flags flags={st.flags} />
            </li>
          ))}
        </ol>
      </Section>

      <Section n={6} title="Judgments, assumptions and references" empty={!guide.judgments.length && 'No judgments identified.'}>
        <ul className={styles.list}>
          {guide.judgments.map((j) => (
            <li key={j.judgment}>
              {j.judgment} <Refs ids={j.events} />
              {j.manager_approval && <span className={styles.approval}>Manager approval</span>}
              <p className={styles.detail}>
                <span className={styles.label}>Evidence</span> {j.evidence}
              </p>
              {j.reference && (
                <p className={styles.detail}>
                  <span className={styles.label}>Reference</span> {j.reference}
                </p>
              )}
              <Sources sources={j.sources} evidence={ev} />
              <Flags flags={j.flags} />
            </li>
          ))}
        </ul>
      </Section>

      <Section n={7} title="Internal and client queries" empty={!(q.manager.length + q.client.length + q.outstanding.length) && 'No queries.'}>
        {(
          [
            ['For the manager', q.manager.map((x) => ({ text: x.question, item: x }))],
            ['For the client', q.client.map((x) => ({ text: x.question, item: x }))],
            ['Outstanding requests', q.outstanding.map((x) => ({ text: x.item, item: x }))],
          ] as const
        )
          .filter(([, rows]) => rows.length)
          .map(([title, rows]) => (
            <div key={title} className={styles.queryGroup}>
              <h4 className={styles.subhead}>{title}</h4>
              <ul className={styles.list}>
                {rows.map(({ text, item }) => (
                  <li key={text}>
                    {text} <Refs ids={item.events} />
                    <Flags flags={item.flags} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
      </Section>

      <Section n={8} title="Completion and handover checklist" empty={!guide.checklist.length && 'No checks given.'}>
        <ul className={styles.checklist}>
          {guide.checklist.map((c) => (
            <li key={c.check}>
              <span className={styles.status} data-status={c.status}>
                {CHECK_STATUS[c.status] ?? c.status}
              </span>{' '}
              {c.check} <Refs ids={c.events} />
            </li>
          ))}
        </ul>
      </Section>
    </>
  )
}

function Section({ n, title, empty, children }: { n: number; title: string; empty?: string | false; children: ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <h3 className={styles.area}>
        {n}. {title}
      </h3>
      {empty ? <p className={styles.muted}>{empty}</p> : children}
    </section>
  )
}

/** One alert: what happened → why it matters → what the accountant must do, and the likely effect. */
function EventAlert({ e, evidence }: { e: GuideEvent; evidence: Evidence }) {
  return (
    <article className={styles.alert} data-status={e.status} aria-label={`${e.id} ${e.event}`}>
      <div className={styles.alertHead}>
        <span className={styles.ref}>{e.id}</span>
        <span className={styles.eventStatus} data-status={e.status}>
          {e.status === 'confirmed' ? 'Confirmed' : 'Suspected — to confirm'}
        </span>
      </div>
      <p className={styles.chain}>
        <span className={styles.label}>What happened</span> {e.event}
      </p>
      <p className={styles.chain}>
        <span className={styles.label}>Why it matters</span> {e.why_it_matters}
      </p>
      <p className={styles.chain}>
        <span className={styles.label}>What to do</span> {e.action}
      </p>
      {e.effect && (
        <p className={styles.chain}>
          <span className={styles.label}>Effect on the figures</span> {e.effect}
        </p>
      )}
      <Sources sources={e.sources} evidence={evidence} />
      <Flags flags={e.flags.filter((f) => f !== 'not_followed_through')} />
      {e.not_followed_through.length > 0 && (
        <p className={styles.flag}>
          <AlertTriangle size={12} aria-hidden="true" /> Not followed through: no {e.not_followed_through.map((m) => MISSING_TEXT[m] ?? m).join(', no ')}
        </p>
      )}
    </article>
  )
}

function Refs({ ids }: { ids?: string[] }) {
  if (!ids?.length) return null
  return (
    <>
      {ids.map((id) => (
        <span key={id} className={styles.ref} title={`Follows through event ${id}`}>
          {id}
        </span>
      ))}
    </>
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
