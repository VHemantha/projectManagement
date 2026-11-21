import { AlertTriangle, ArrowDown, CheckCircle2, CircleDashed, Clock, Flag, ListChecks, Scale, ShieldAlert } from 'lucide-react'
import type { ReactNode } from 'react'

import { DocIcons } from './DocIcons'
import styles from './GuideView.module.css'
import { NotesConsidered } from './SpecialNotes'
import type { GuideLevel, GuidePhase, GuideV2, GuideV3 } from '@/api/guide'
import type { SourceRef } from '@/api/precheck'

type Evidence = GuideV3['evidence']

/** The phases of preparation, start to finalisation (the agent's PHASES). */
export const PHASES: { id: GuidePhase; label: string }[] = [
  { id: 'start', label: 'Start' },
  { id: 'records', label: 'Records and coding' },
  { id: 'reconcile', label: 'Bank and reconciliations' },
  { id: 'income_expenses', label: 'Income and expenses' },
  { id: 'assets_liabilities', label: 'Assets and liabilities' },
  { id: 'adjustments', label: 'Year-end adjustments' },
  { id: 'tax', label: 'Tax' },
  { id: 'draft', label: 'Draft statements' },
  { id: 'review', label: 'Review' },
  { id: 'finalise', label: 'Finalisation' },
]
const LEVEL_LABEL: Record<GuideLevel, string> = { high: 'High', medium: 'Medium', low: 'Low' }
const PRIOR_KIND: Record<string, string> = {
  error: 'Previous error', reviewer_point: 'Reviewer point', unresolved: 'Unresolved', policy: 'Policy', balance: 'Balance to follow through',
}
const POINT_KIND = { action: 'Action', note: 'Note', escalate: 'Escalate' } as const
const CHECK_STATUS = { done: 'Done', open: 'Open', na: 'N/A' } as const
const FLAG_TEXT: Record<string, string> = {
  figure_not_in_documents: 'An amount not found in the documents (it may be calculated): check it',
  longer_than_two_pages: 'This guide is longer than two pages',
  questions_dropped: 'The AI wrote some items as questions; they were left out (the guide gives points, not questions)',
  added_by_code: 'Added by code',
  worded_as_question: 'Worded as a question',
}

/** A guide written in the eight-section format (before 21 Nov 2026), shown the new way: no events
 * section, no questions (the documents still to come stay), its starting sequence as the steps. */
export function fromV2(g: GuideV2): GuideV3 {
  return {
    ...g,
    format: 3,
    cautions: [],
    steps: g.sequence.map((s, i) => ({ ...s, n: i + 1, phase: 'start' as GuidePhase })),
    judgments: g.judgments.map((j) => ({ ...j, area: '' })),
    points: [],
    outstanding: g.queries.outstanding.map((o) => ({ group: '', item: o.item, flags: o.flags })),
    roll_forward: g.roll_forward ?? [],
    phase_labels: { start: 'Steps (from the earlier guide)' },
  }
}

/** The preparation guide, format 3 (AFIT, 21 Nov 2026), in tables and charts: the areas of caution as
 * its summary; the job snapshot; prior-year continuity; the priority risks; the steps from the start of
 * preparation to finalisation as a flow chart and a table; the areas needing judgment; the points to
 * note and the documents still to come; and the completion checklist with its progress. Points, never
 * questions; the significant events are followed through inside these, not shown on their own. */
export function GuideView({ guide, earlier }: { guide: GuideV3; earlier?: boolean }) {
  const ev = guide.evidence
  return (
    <div className={styles.view}>
      <div className={styles.summary}>
        <strong>{guide.decision.reason}</strong>
        {earlier && <p className={styles.muted}>Written before 21 Nov 2026: write it again for the areas of caution and the steps to finalisation.</p>}
        <Flags flags={guide.flags} />
      </div>
      <NotesConsidered notes={guide.special_notes} />

      <Cautions guide={guide} evidence={ev} />

      <Section n={1} title="Job snapshot">
        <table className={styles.table}>
          <tbody>
            {(
              [
                ['FS preparation period', guide.snapshot.period],
                ['Business', guide.snapshot.activities],
                ['Assets and funding', guide.snapshot.assets_and_funding],
                ['Records available', guide.snapshot.records],
                ['Bookkeeping', guide.snapshot.bookkeeping],
              ] as const
            )
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <tr key={k}>
                  <th scope="row">{k}</th>
                  <td>{v}</td>
                </tr>
              ))}
          </tbody>
        </table>
        <Refs sources={guide.snapshot.sources} evidence={ev} />
      </Section>

      <Section n={2} title="Prior-year findings and continuity" empty={!guide.prior_year.length && 'Nothing carried over from last year in the documents.'}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Kind</th>
              <th scope="col">Matter</th>
              <th scope="col">What to do</th>
              <th scope="col">Sources</th>
            </tr>
          </thead>
          <tbody>
            {guide.prior_year.map((p) => (
              <tr key={p.item}>
                <td>
                  <span className={styles.tag}>{PRIOR_KIND[p.kind] ?? p.kind}</span>
                </td>
                <td>
                  {p.item}
                  <Flags flags={p.flags} />
                </td>
                <td>{p.follow_through}</td>
                <td>
                  <Refs sources={p.sources} evidence={ev} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section n={3} title="Priority risks and material areas" empty={!guide.risks.length && 'No job-specific risks identified.'}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Area</th>
              <th scope="col">What could be wrong</th>
              <th scope="col">Examine</th>
              <th scope="col">Evidence needed</th>
              <th scope="col">Sources</th>
            </tr>
          </thead>
          <tbody>
            {guide.risks.map((r) => (
              <tr key={r.what_could_be_wrong}>
                <th scope="row">{r.area}</th>
                <td>
                  {r.what_could_be_wrong}
                  <Flags flags={r.flags} />
                </td>
                <td>{r.examine}</td>
                <td>{r.evidence}</td>
                <td>
                  <Refs sources={r.sources} evidence={ev} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section n={4} title="Steps to finalisation" empty={!guide.steps.length && 'No steps given.'}>
        <Flowchart guide={guide} />
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Phase</th>
              <th scope="col">Step</th>
              <th scope="col">Depends on</th>
              <th scope="col">Status</th>
              <th scope="col">Sources</th>
            </tr>
          </thead>
          <tbody>
            {guide.steps.map((s) => (
              <tr key={`${s.n}-${s.step}`}>
                <td className={styles.num}>{s.n}</td>
                <td>{phaseLabel(guide, s.phase)}</td>
                <td>
                  {s.step}
                  {s.escalate && (
                    <span className={styles.escalate}>
                      <Flag size={11} aria-hidden="true" /> Escalate: {s.escalate}
                    </span>
                  )}
                  <Flags flags={s.flags} />
                </td>
                <td>{s.depends_on || 'Nothing'}</td>
                <td>
                  <StepStatus now={s.can_start_now} />
                </td>
                <td>
                  <Refs sources={s.sources} evidence={ev} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section n={5} title="Areas needing judgment" empty={!guide.judgments.length && 'No judgments identified.'}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Area</th>
              <th scope="col">Judgment</th>
              <th scope="col">Evidence</th>
              <th scope="col">Reference</th>
              <th scope="col">Manager approval</th>
              <th scope="col">Sources</th>
            </tr>
          </thead>
          <tbody>
            {guide.judgments.map((j) => (
              <tr key={j.judgment}>
                <th scope="row">{j.area || 'General'}</th>
                <td>
                  {j.judgment}
                  <Flags flags={j.flags} />
                </td>
                <td>{j.evidence}</td>
                <td>{j.reference}</td>
                <td>{j.manager_approval ? <span className={styles.approval}>Needed</span> : <span className={styles.muted}>No</span>}</td>
                <td>
                  <Refs sources={j.sources} evidence={ev} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section n={6} title="Points to note" empty={!guide.points.length && !guide.outstanding.length && 'Nothing further to note.'}>
        {guide.points.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col">Point</th>
                <th scope="col">Sources</th>
              </tr>
            </thead>
            <tbody>
              {guide.points.map((p) => (
                <tr key={p.text}>
                  <td>
                    <span className={styles.pointKind} data-kind={p.kind}>
                      {POINT_KIND[p.kind]}
                    </span>
                  </td>
                  <td>
                    {p.text}
                    <Flags flags={p.flags} />
                  </td>
                  <td>
                    <Refs sources={p.sources} evidence={ev} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {guide.outstanding.length > 0 && (
          <table className={styles.table}>
            <caption>Still to come from the client (from the pre-check)</caption>
            <thead>
              <tr>
                <th scope="col">For</th>
                <th scope="col">Document</th>
              </tr>
            </thead>
            <tbody>
              {guide.outstanding.map((o) => (
                <tr key={`${o.group}-${o.item}`}>
                  <td>{o.group || '—'}</td>
                  <td>{o.item}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section n={7} title="Completion and handover checklist" empty={!guide.checklist.length && 'No checks given.'}>
        <Progress checklist={guide.checklist} />
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">Check</th>
            </tr>
          </thead>
          <tbody>
            {guide.checklist.map((c) => (
              <tr key={c.check}>
                <td>
                  <span className={styles.check} data-status={c.status}>
                    {CHECK_STATUS[c.status] ?? c.status}
                  </span>
                </td>
                <td>{c.check}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {guide.roll_forward.length > 0 && (
          <table className={styles.table} aria-label="To roll forward to next year">
            <caption>To roll forward to next year</caption>
            <thead>
              <tr>
                <th scope="col">Matter</th>
                <th scope="col">Why</th>
              </tr>
            </thead>
            <tbody>
              {guide.roll_forward.map((r) => (
                <tr key={r.item}>
                  <td>{r.item}</td>
                  <td>{r.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  )
}

function phaseLabel(guide: GuideV3, phase: GuidePhase): string {
  return guide.phase_labels?.[phase] ?? PHASES.find((p) => p.id === phase)?.label ?? phase
}

/** The areas of caution: the summary of the job, with a bar of how many there are at each level. */
function Cautions({ guide, evidence }: { guide: GuideV3; evidence: Evidence }) {
  const c = guide.cautions
  if (!c.length) return null
  const count = (level: GuideLevel) => c.filter((x) => x.level === level).length
  return (
    <section className={styles.cautions} aria-label="Areas of caution">
      <h3 className={styles.sectionTitle}>
        <ShieldAlert size={16} aria-hidden="true" /> Areas of caution
      </h3>
      <div className={styles.meter} role="img" aria-label={`Areas of caution: ${count('high')} high, ${count('medium')} medium, ${count('low')} low`}>
        {(['high', 'medium', 'low'] as const).map((level) =>
          count(level) ? (
            <span key={level} data-level={level} style={{ flex: count(level) }}>
              {count(level)} {LEVEL_LABEL[level].toLowerCase()}
            </span>
          ) : null,
        )}
      </div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Level</th>
            <th scope="col">Area</th>
            <th scope="col">Caution</th>
            <th scope="col">Sources</th>
          </tr>
        </thead>
        <tbody>
          {c.map((x) => (
            <tr key={x.caution} data-level={x.level}>
              <td>
                <span className={styles.level} data-level={x.level}>
                  {LEVEL_LABEL[x.level]}
                </span>
              </td>
              <th scope="row">{x.area}</th>
              <td>
                {x.caution}
                <Flags flags={x.flags} />
              </td>
              <td>
                <Refs sources={x.sources} evidence={evidence} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

/** The steps as a flow chart: each phase a box in order, its numbered steps inside, an arrow to the next
 * phase; a step that waits on something shows what. Ends at finalisation. */
function Flowchart({ guide }: { guide: GuideV3 }) {
  const phases = PHASES.map((p) => ({ ...p, label: phaseLabel(guide, p.id), steps: guide.steps.filter((s) => s.phase === p.id) })).filter(
    (p) => p.steps.length,
  )
  const now = guide.steps.filter((s) => s.can_start_now).length
  return (
    <figure className={styles.flow} aria-label="Flow chart of the steps to finalisation">
      <figcaption className={styles.flowCaption}>
        <ListChecks size={14} aria-hidden="true" /> {guide.steps.length} steps in {phases.length} phase{phases.length === 1 ? '' : 's'}: {now} can start now,{' '}
        {guide.steps.length - now} wait on something
      </figcaption>
      <ol className={styles.flowList}>
        {phases.map((p, i) => (
          <li key={p.id} className={styles.flowItem}>
            <div className={styles.phase} data-phase={p.id}>
              <div className={styles.phaseHead}>
                <span className={styles.phaseNo}>{i + 1}</span> {p.label}
              </div>
              <ol className={styles.phaseSteps}>
                {p.steps.map((s) => (
                  <li key={`${s.n}-${s.step}`} data-now={s.can_start_now || undefined}>
                    <span className={styles.stepNo}>{s.n}</span>
                    <span>
                      {s.step}
                      {!s.can_start_now && s.depends_on && <span className={styles.waits}> — waits on {s.depends_on}</span>}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
            {i < phases.length - 1 && (
              <span className={styles.arrow} aria-hidden="true">
                <ArrowDown size={16} />
              </span>
            )}
          </li>
        ))}
      </ol>
    </figure>
  )
}

function StepStatus({ now }: { now: boolean }) {
  return now ? (
    <span className={styles.now}>
      <CheckCircle2 size={12} aria-hidden="true" /> Can start now
    </span>
  ) : (
    <span className={styles.waitsChip}>
      <Clock size={12} aria-hidden="true" /> Waits
    </span>
  )
}

/** The checklist's progress: done, open and not applicable, as one bar. */
function Progress({ checklist }: { checklist: GuideV3['checklist'] }) {
  if (!checklist.length) return null
  const n = (status: 'done' | 'open' | 'na') => checklist.filter((c) => c.status === status).length
  const total = checklist.length
  return (
    <div className={styles.progress}>
      <div className={styles.meter} role="img" aria-label={`Checklist: ${n('done')} done, ${n('open')} open, ${n('na')} not applicable`}>
        {(['done', 'open', 'na'] as const).map((st) =>
          n(st) ? (
            <span key={st} data-status={st} style={{ flex: n(st) }}>
              {n(st)} {CHECK_STATUS[st].toLowerCase()}
            </span>
          ) : null,
        )}
      </div>
      <span className={styles.muted}>
        <CircleDashed size={12} aria-hidden="true" /> {Math.round((n('done') / total) * 100)}% done
      </span>
    </div>
  )
}

function Section({ n, title, empty, children }: { n: number; title: string; empty?: string | false; children: ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <h3 className={styles.sectionTitle}>
        <span className={styles.sectionNo}>{n}</span> {title}
        {n === 5 && <Scale size={14} aria-hidden="true" />}
      </h3>
      {empty ? <p className={styles.muted}>{empty}</p> : children}
    </section>
  )
}

function Refs({ sources, evidence }: { sources?: SourceRef[]; evidence: Evidence }) {
  if (!sources?.length) return null
  return <DocIcons sources={sources} evidence={evidence} label="" variant="row" max={4} />
}

function Flags({ flags }: { flags?: string[] }) {
  const shown = (flags ?? []).filter((f) => f !== 'added_by_code')
  if (!shown.length) return null
  return (
    <>
      {shown.map((f) => (
        <span key={f} className={styles.flag}>
          <AlertTriangle size={11} aria-hidden="true" /> {FLAG_TEXT[f] ?? f}
        </span>
      ))}
    </>
  )
}
