import { AlertTriangle, Check, ExternalLink, Loader2, Plus, RotateCcw, Sparkles, X } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import styles from './ReviewPanel.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type LessonScope, type SourceRef, useLessons, useSetLessonStatus } from '@/api/precheck'
import {
  type Assumption,
  type AssumptionInput,
  type AssumptionVerdict,
  type ReviewFindingRecord,
  type ReviewOutput,
  type ReviewResponseKind,
  type ReviewState,
  useAddMissed,
  useCompleteReview,
  useJobReview,
  useRespondToFinding,
  useRunReview,
  useSaveAssumption,
} from '@/api/review'
import { PendingLessons } from './PrecheckResult'
import { Button, Skeleton } from '@/design-system'

const RESPONSE_LABEL: Record<ReviewResponseKind, string> = {
  agree: 'Agree',
  fixed: 'Fixed',
  not_an_issue: 'Not an issue',
  wrong_reason: 'Wrong reason',
}
const NEEDS_NOTE: ReviewResponseKind[] = ['not_an_issue', 'wrong_reason']
const VERDICT_LABEL: Record<AssumptionVerdict, string> = {
  supported: 'Supported',
  challenged: 'Challenged',
  needs_evidence: 'Needs evidence',
}
const FLAG_TEXT: Record<string, string> = {
  no_source: 'The AI gave no source for this',
  figure_not_in_documents: 'It mentions a figure not found in the documents',
}
type Filter = 'open' | 'resolved' | 'closed'

/** The review of this task's draft financial statements: rounds of AI review, the reviewer's
 * response to every finding, the preparer's assumptions, and a review only a person completes. */
export function ReviewPanel({ jobKey }: { jobKey: string }) {
  const { data, isLoading, isError } = useJobReview(jobKey)
  if (isLoading) {
    return (
      <div aria-busy="true">
        <Skeleton height={64} />
      </div>
    )
  }
  if (isError || !data) return <p className={styles.muted}>The review could not be loaded. Refresh the page to try again.</p>
  return <ReviewBody jobKey={jobKey} data={data} />
}

function ReviewBody({ jobKey, data }: { jobKey: string; data: ReviewState }) {
  const start = useRunReview(jobKey)
  const [filter, setFilter] = useState<Filter>('open')
  const latest = data.latest
  const output = latest && 'decision' in (latest.review ?? {}) ? (latest.review as ReviewOutput) : null
  const running = latest?.status === 'running'
  const complete = data.session.status === 'complete'
  const counts = {
    open: data.findings.filter((f) => f.status === 'open').length,
    resolved: data.findings.filter((f) => f.status === 'resolved').length,
    closed: data.findings.filter((f) => f.status === 'closed').length,
  }
  const shown = data.findings.filter((f) => f.status === filter)
  const verdicts = Object.fromEntries((output?.assumption_reviews ?? []).map((r) => [r.assumption, r]))

  return (
    <div className={styles.review}>
      <div className={styles.head}>
        <p className={styles.lead}>
          The AI reviews this year&apos;s draft financial statements against last year&apos;s, the documents received and the
          preparer&apos;s assumptions. Respond to each finding and run another round until you complete the review.
        </p>
        <div className={styles.actions}>
          {complete ? (
            <span className={styles.chip} data-tone="success">
              <Check size={13} aria-hidden="true" /> Review complete{data.session.completed_by && ` — ${data.session.completed_by}`}
            </span>
          ) : (
            <Button variant="primary" size="sm" disabled={running || start.isPending} onClick={() => start.mutate()}>
              {running || start.isPending ? (
                <Loader2 size={14} className={styles.spin} aria-hidden="true" />
              ) : data.rounds_done ? (
                <RotateCcw size={14} aria-hidden="true" />
              ) : (
                <Sparkles size={14} aria-hidden="true" />
              )}
              {running ? 'Reviewing…' : start.isPending ? 'Starting…' : data.rounds_done ? `Run round ${data.rounds_done + 1}` : 'Run AI review'}
            </Button>
          )}
        </div>
      </div>
      {start.isError && (
        <div role="alert" className={styles.notice} data-tone="danger">
          {extractErrorMessage(start.error, 'The review could not be started.')}
        </div>
      )}
      {running && latest?.progress?.length ? <p className={styles.muted}>{latest.progress[latest.progress.length - 1].label}</p> : null}
      {latest?.status === 'failed' && (
        <div role="alert" className={styles.notice} data-tone="danger">
          {latest.failure_reason || 'The review stopped.'}
        </div>
      )}
      {output && <RoundSummary output={output} round={data.rounds_done} />}

      <section aria-labelledby="rv-findings">
        <div className={styles.sectionHead}>
          <h3 id="rv-findings" className={styles.sectionTitle}>
            Findings
          </h3>
          <div className={styles.filters} role="group" aria-label="Show findings">
            {(['open', 'resolved', 'closed'] as Filter[]).map((f) => (
              <button key={f} type="button" className={styles.filter} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f[0].toUpperCase() + f.slice(1)} ({counts[f]})
              </button>
            ))}
          </div>
        </div>
        {shown.length ? (
          <ul className={styles.findings}>
            {shown.map((f) => (
              <FindingCard key={f.id} jobKey={jobKey} finding={f} output={output} locked={complete} />
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>{filter === 'open' ? (data.rounds_done ? 'Nothing open.' : 'Run the AI review to see findings.') : 'None.'}</p>
        )}
        {!complete && <MissedForm jobKey={jobKey} />}
      </section>

      <Assumptions jobKey={jobKey} data={data} verdicts={verdicts} output={output} locked={complete} />

      <LearnedRules jobKey={jobKey} />

      {output && output.checks.length > 0 && (
        <details className={styles.details}>
          <summary>
            Checks by code ({output.checks.filter((c) => !c.passed).length} failed of {output.checks.length})
          </summary>
          <ul className={styles.checks}>
            {output.checks.map((c) => (
              <li key={c.label}>
                {c.passed ? <Check size={13} className={styles.pass} aria-label="Passed" /> : <X size={13} className={styles.fail} aria-label="Failed" />}
                <span>{c.label}</span>
                {!c.passed && <span className={styles.muted}>{c.detail}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {data.can_complete && <CompleteReview jobKey={jobKey} data={data} />}
    </div>
  )
}

function RoundSummary({ output, round }: { output: ReviewOutput; round: number }) {
  const tone = output.decision.state === 'blocked' ? 'danger' : output.decision.state === 'findings' ? 'warning' : 'success'
  return (
    <div className={styles.banner} data-tone={tone}>
      <div className={styles.bannerTitle}>
        {output.decision.state === 'clear' ? <Check size={15} aria-hidden="true" /> : <AlertTriangle size={15} aria-hidden="true" />}
        {output.decision.label}
        {round > 0 && <span className={styles.muted}> · round {round}</span>}
      </div>
      <p className={styles.bannerText}>{output.summary || output.decision.reason}</p>
      {output.draft_fs.length > 0 && (
        <p className={styles.muted}>
          Reviewed: {output.draft_fs.map((d) => d.name).join(', ')}
          {output.draft_found_by === 'task card' ? ' (set on the task card)' : ''}
        </p>
      )}
      {output.lessons_applied.length > 0 && (
        <p className={styles.muted}>Lessons applied: {output.lessons_applied.map((l) => l.text).join('; ')}</p>
      )}
    </div>
  )
}

function Sources({ sources, output }: { sources: SourceRef[]; output: ReviewOutput | null }) {
  if (!sources.length) return null
  return (
    <span className={styles.sources}>
      {sources.map((s) => {
        const ev = s.evidence_id && output ? output.evidence[s.evidence_id] : undefined
        return ev ? (
          <a key={s.id} className={styles.source} href={ev.drive_url} target="_blank" rel="noreferrer" title={`${ev.file_name} — ${ev.location}: ${ev.quote}`}>
            {s.label} <ExternalLink size={11} aria-hidden="true" />
          </a>
        ) : (
          <span key={s.id} className={styles.source}>
            {s.label}
          </span>
        )
      })}
    </span>
  )
}

function FindingCard({
  jobKey,
  finding: f,
  output,
  locked,
}: {
  jobKey: string
  finding: ReviewFindingRecord
  output: ReviewOutput | null
  locked: boolean
}) {
  const respond = useRespondToFinding(jobKey)
  const [choosing, setChoosing] = useState<ReviewResponseKind | null>(null)
  const [note, setNote] = useState('')
  const [scope, setScope] = useState<LessonScope>('client')
  const needsNote = choosing !== null && NEEDS_NOTE.includes(choosing)
  const send = (response: ReviewResponseKind, text = '') =>
    respond.mutate(
      { id: f.id, response, note: text, ...(NEEDS_NOTE.includes(response) ? { scope } : {}) },
      { onSuccess: () => (setChoosing(null), setNote('')) },
    )

  return (
    <li className={styles.finding} data-severity={f.severity}>
      <div className={styles.findingHead}>
        <span className={styles.ref}>{f.ref}</span>
        <span className={styles.severity} data-severity={f.severity}>
          {f.severity}
        </span>
        <span className={styles.where}>
          {f.area}
          {f.fs_line && ` · ${f.fs_line}`}
        </span>
        {f.origin === 'person' && <span className={styles.chip}>Raised by {f.created_by || 'a person'}</span>}
      </div>
      <h4 className={styles.issue}>{f.issue}</h4>
      {f.why && <p className={styles.why}>{f.why}</p>}
      {f.action && (
        <p className={styles.action}>
          <strong>Action:</strong> {f.action}
        </p>
      )}
      {f.assumptions.length > 0 && <p className={styles.muted}>Concerns {f.assumptions.join(', ')}</p>}
      <Sources sources={f.sources} output={output} />
      {f.flags.map((flag) => (
        <p key={flag} className={styles.flag}>
          <AlertTriangle size={12} aria-hidden="true" /> {FLAG_TEXT[flag] ?? flag}
        </p>
      ))}
      {f.status === 'resolved' && <p className={styles.muted}>Resolved: {f.resolved_reason}</p>}
      {f.response && (
        <p className={styles.response}>
          {RESPONSE_LABEL[f.response]} — {f.responded_by}
          {f.note && `: ${f.note}`}
        </p>
      )}
      {!locked && f.status !== 'resolved' && (
        <div className={styles.respond} role="group" aria-label={`Respond to ${f.ref}`}>
          {(Object.keys(RESPONSE_LABEL) as ReviewResponseKind[]).map((r) => (
            <button
              key={r}
              type="button"
              className={styles.respondButton}
              aria-pressed={f.response === r}
              disabled={respond.isPending}
              onClick={() => (NEEDS_NOTE.includes(r) ? setChoosing(r) : send(r))}
            >
              {RESPONSE_LABEL[r]}
            </button>
          ))}
        </div>
      )}
      {needsNote && (
        <form
          className={styles.noteForm}
          onSubmit={(e) => {
            e.preventDefault()
            send(choosing!, note.trim())
          }}
        >
          <label className={styles.field}>
            <span>{choosing === 'not_an_issue' ? 'Why is it not an issue?' : 'What is the right reason?'} The AI learns from this.</span>
            <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <ScopeChoice value={scope} onChange={setScope} />
          <div className={styles.row}>
            <Button type="submit" variant="primary" size="sm" disabled={note.trim().length < 5 || respond.isPending}>
              Save
            </Button>
            <Button type="button" variant="subtle" size="sm" onClick={() => setChoosing(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {respond.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(respond.error)}
        </p>
      )}
      {f.responses.length > 1 && (
        <details className={styles.history}>
          <summary>History ({f.responses.length})</summary>
          <ul>
            {f.responses.map((r, i) => (
              <li key={i}>
                {RESPONSE_LABEL[r.response]} — {r.by}
                {r.note && `: ${r.note}`}
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  )
}

function MissedForm({ jobKey }: { jobKey: string }) {
  const add = useAddMissed(jobKey)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ area: '', fs_line: '', issue: '', note: '' })
  const [scope, setScope] = useState<LessonScope>('client')
  if (!open) {
    return (
      <button type="button" className={styles.link} onClick={() => setOpen(true)}>
        <Plus size={13} aria-hidden="true" /> Something the AI missed
      </button>
    )
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    add.mutate({ ...form, scope }, { onSuccess: () => (setOpen(false), setForm({ area: '', fs_line: '', issue: '', note: '' })) })
  }
  return (
    <form className={styles.card} onSubmit={submit} aria-label="Something the AI missed">
      <div className={styles.grid2}>
        <label className={styles.field}>
          <span>Area</span>
          <input value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value })} placeholder="GST" />
        </label>
        <label className={styles.field}>
          <span>Statement line</span>
          <input value={form.fs_line} onChange={(e) => setForm({ ...form, fs_line: e.target.value })} placeholder="GST payable" />
        </label>
      </div>
      <label className={styles.field}>
        <span>What was missed</span>
        <textarea rows={2} value={form.issue} onChange={(e) => setForm({ ...form, issue: e.target.value })} />
      </label>
      <label className={styles.field}>
        <span>Why it matters (optional)</span>
        <textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      </label>
      <ScopeChoice value={scope} onChange={setScope} />
      {add.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(add.error)}
        </p>
      )}
      <div className={styles.row}>
        <Button type="submit" variant="primary" size="sm" disabled={form.issue.trim().length < 5 || add.isPending}>
          Add finding
        </Button>
        <Button type="button" variant="subtle" size="sm" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function Assumptions({
  jobKey,
  data,
  verdicts,
  output,
  locked,
}: {
  jobKey: string
  data: ReviewState
  verdicts: Record<string, ReviewOutput['assumption_reviews'][number]>
  output: ReviewOutput | null
  locked: boolean
}) {
  const save = useSaveAssumption(jobKey)
  const [editing, setEditing] = useState<Assumption | 'new' | null>(null)
  const active = data.assumptions.filter((a) => a.status === 'active')
  const withdrawn = data.assumptions.length - active.length
  return (
    <section aria-labelledby="rv-assumptions">
      <div className={styles.sectionHead}>
        <h3 id="rv-assumptions" className={styles.sectionTitle}>
          Assumptions and judgements ({active.length})
        </h3>
        {!locked && editing === null && (
          <Button variant="secondary" size="sm" onClick={() => setEditing('new')}>
            <Plus size={14} aria-hidden="true" /> Add
          </Button>
        )}
      </div>
      <p className={styles.muted}>
        What the preparer decided and why. The AI tests each one against the evidence in every round.
      </p>
      {editing === 'new' && <AssumptionForm areas={data.areas} onDone={() => setEditing(null)} save={save} />}
      <ul className={styles.assumptions}>
        {active.map((a) =>
          editing !== 'new' && editing?.id === a.id ? (
            <li key={a.id}>
              <AssumptionForm areas={data.areas} initial={a} onDone={() => setEditing(null)} save={save} />
            </li>
          ) : (
            <li key={a.id} className={styles.assumption}>
              <div className={styles.findingHead}>
                <span className={styles.ref}>{a.ref}</span>
                <span className={styles.where}>
                  {a.area_label}
                  {a.fs_line && ` · ${a.fs_line}`}
                  {a.amount && ` · $${Number(a.amount).toLocaleString('en-NZ', { minimumFractionDigits: 2 })}`}
                </span>
                {verdicts[a.ref] && (
                  <span className={styles.verdict} data-verdict={verdicts[a.ref].verdict}>
                    {VERDICT_LABEL[verdicts[a.ref].verdict]}
                  </span>
                )}
              </div>
              <p className={styles.judgement}>{a.judgement}</p>
              {a.basis && <p className={styles.why}>Basis: {a.basis}</p>}
              {a.evidence && <p className={styles.muted}>Evidence: {a.evidence}</p>}
              {verdicts[a.ref]?.reason && (
                <p className={styles.aiSays}>
                  AI: {verdicts[a.ref].reason} <Sources sources={verdicts[a.ref].sources} output={output} />
                </p>
              )}
              {!locked && (
                <div className={styles.row}>
                  <button type="button" className={styles.link} onClick={() => setEditing(a)}>
                    Edit
                  </button>
                  <button type="button" className={styles.link} onClick={() => save.mutate({ id: a.id, body: { status: 'withdrawn' } })}>
                    Withdraw
                  </button>
                  {a.history.length > 0 && <span className={styles.muted}>Edited {a.history.length}×</span>}
                </div>
              )}
            </li>
          ),
        )}
      </ul>
      {!active.length && editing === null && <p className={styles.muted}>None recorded yet.</p>}
      {withdrawn > 0 && <p className={styles.muted}>{withdrawn} withdrawn (kept in the record).</p>}
    </section>
  )
}

function AssumptionForm({
  areas,
  initial,
  onDone,
  save,
}: {
  areas: ReviewState['areas']
  initial?: Assumption
  onDone: () => void
  save: ReturnType<typeof useSaveAssumption>
}) {
  const [form, setForm] = useState<AssumptionInput>({
    area: initial?.area ?? 'other',
    fs_line: initial?.fs_line ?? '',
    amount: initial?.amount ?? '',
    judgement: initial?.judgement ?? '',
    basis: initial?.basis ?? '',
    evidence: initial?.evidence ?? '',
  })
  const set = (k: keyof AssumptionInput) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ id: initial?.id, body: form }, { onSuccess: onDone })
  }
  return (
    <form className={styles.card} onSubmit={submit} aria-label={initial ? `Edit ${initial.ref}` : 'New assumption'}>
      <div className={styles.grid3}>
        <label className={styles.field}>
          <span>Area</span>
          <select value={form.area} onChange={set('area')}>
            {areas.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span>Statement line</span>
          <input value={form.fs_line} onChange={set('fs_line')} placeholder="Repairs and maintenance" />
        </label>
        <label className={styles.field}>
          <span>Amount (optional)</span>
          <input value={form.amount} onChange={set('amount')} inputMode="decimal" placeholder="9,850.00" />
        </label>
      </div>
      <label className={styles.field}>
        <span>Assumption or judgement</span>
        <textarea rows={2} value={form.judgement} onChange={set('judgement')} placeholder="Hot water cylinder replacement treated as a repair, not capital." />
      </label>
      <label className={styles.field}>
        <span>Basis — why</span>
        <textarea rows={2} value={form.basis} onChange={set('basis')} placeholder="Like-for-like replacement of a worn part of the property." />
      </label>
      <label className={styles.field}>
        <span>Evidence (document name, path or link)</span>
        <input value={form.evidence} onChange={set('evidence')} placeholder="Kauri Plumbing invoice 14 Nov 2025" />
      </label>
      {save.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(save.error)}
        </p>
      )}
      <div className={styles.row}>
        <Button type="submit" variant="primary" size="sm" disabled={!form.judgement?.trim() || save.isPending}>
          {initial ? 'Save changes' : 'Add assumption'}
        </Button>
        <Button type="button" variant="subtle" size="sm" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function CompleteReview({ jobKey, data }: { jobKey: string; data: ReviewState }) {
  const complete = useCompleteReview(jobKey)
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  if (data.session.status === 'complete') {
    return (
      <div className={styles.complete}>
        <p className={styles.muted}>
          Completed by {data.session.completed_by}
          {data.session.note && `: ${data.session.note}`}
        </p>
        <Button variant="subtle" size="sm" onClick={() => complete.mutate({ reopen: true })}>
          Reopen review
        </Button>
      </div>
    )
  }
  if (!open) {
    return (
      <div className={styles.complete}>
        <Button variant="secondary" size="sm" disabled={!data.rounds_done} onClick={() => setOpen(true)}>
          <Check size={14} aria-hidden="true" /> Complete review
        </Button>
      </div>
    )
  }
  return (
    <form
      className={styles.card}
      onSubmit={(e) => {
        e.preventDefault()
        complete.mutate({ note: note.trim() }, { onSuccess: () => setOpen(false) })
      }}
    >
      {data.open_high > 0 && (
        <p className={styles.flag}>
          <AlertTriangle size={12} aria-hidden="true" /> {data.open_high} high finding{data.open_high === 1 ? ' is' : 's are'} still open. Say why the
          review can be completed anyway.
        </p>
      )}
      <label className={styles.field}>
        <span>Completion note{data.open_high > 0 ? '' : ' (optional)'}</span>
        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {complete.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(complete.error)}
        </p>
      )}
      <div className={styles.row}>
        <Button type="submit" variant="primary" size="sm" disabled={(data.open_high > 0 && note.trim().length < 5) || complete.isPending}>
          Complete review
        </Button>
        <Button type="button" variant="subtle" size="sm" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  )
}


const SCOPE_LABEL: Record<LessonScope, string> = {
  client: 'This client (applies at once)',
  project: 'This project (a lead approves)',
  team: 'This workspace (a lead approves)',
  firm: 'All clients of this type (a lead approves)',
}

/** How widely a correction should teach the AI. */
function ScopeChoice({ value, onChange }: { value: LessonScope; onChange: (s: LessonScope) => void }) {
  return (
    <label className={styles.field}>
      <span>Teach this to</span>
      <select value={value} onChange={(e) => onChange(e.target.value as LessonScope)}>
        {(Object.keys(SCOPE_LABEL) as LessonScope[]).map((s) => (
          <option key={s} value={s}>
            {SCOPE_LABEL[s]}
          </option>
        ))}
      </select>
    </label>
  )
}

/** What the AI has learned that applies to this task: each correction as the rule the AI drafted
 * from it (when / do / why), how widely it applies, and whether it is waiting for approval. */
function LearnedRules({ jobKey }: { jobKey: string }) {
  const { data } = useLessons(jobKey)
  const setStatus = useSetLessonStatus(jobKey)
  const rules = data?.lessons ?? []
  return (
    <section aria-labelledby="rv-learned">
      <div className={styles.sectionHead}>
        <h3 id="rv-learned" className={styles.sectionTitle}>
          Learned rules ({rules.length})
        </h3>
      </div>
      <p className={styles.muted}>
        Corrections from the team, drafted by the AI as rules it applies to this task from now on.
      </p>
      {rules.length > 0 && (
        <ul className={styles.assumptions}>
          {rules.map((l) => (
            <li key={l.id} className={styles.assumption}>
              <div className={styles.findingHead}>
                <span className={styles.where}>{l.rule?.title || l.item || 'Correction'}</span>
                <span className={styles.chip}>{l.scope_label ?? l.scope}</span>
                {l.status === 'pending' && <span className={styles.verdict} data-verdict="needs_evidence">Waiting for approval</span>}
              </div>
              {l.rule ? (
                <p className={styles.why}>
                  <strong>When:</strong> {l.rule.when} <strong>Do:</strong> {l.rule.do} <strong>Why:</strong> {l.rule.why}
                </p>
              ) : (
                <p className={styles.why}>{l.note}</p>
              )}
              {l.drafting === 'drafting' && <p className={styles.muted}>The AI is drafting this as a rule; the note applies meanwhile.</p>}
              <div className={styles.row}>
                <span className={styles.muted}>
                  {l.rule ? `Note from ${l.created_by}: ${l.note}` : `From ${l.created_by}`}
                  {l.task && ` · ${l.task}`}
                </span>
                <button type="button" className={styles.link} onClick={() => setStatus.mutate({ id: l.id, status: 'disabled' })}>
                  Switch off
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <PendingLessons jobKey={jobKey} />
    </section>
  )
}

