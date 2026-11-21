import {
  AlertTriangle,
  BookOpenCheck,
  Check,
  ChevronDown,
  ChevronUp,
  CircleCheck,
  ClipboardList,
  Eye,
  Info,
  Mail,
  MessageSquareText,
  MessagesSquare,
  Pencil,
  Plus,
  Save,
  Scale,
  Send,
  Sparkles,
  X,
} from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router-dom'

import { DocIcons } from './DocIcons'
import { GapChip, GapTracker } from './GapTracker'
import { JobSnapshot } from './JobSnapshot'
import { PolicyFeedbackForm } from './PoliciesPanel'
import styles from './PrecheckResult.module.css'
import { CHECK_TYPES, RULE_ENTITY_TYPES } from './ruleOptions'
import { NotesConsidered } from './SpecialNotes'
import { Sources as SharedSources } from './SourceLinks'
import { useAsk } from '@/api/ask'
import { extractErrorMessage } from '@/api/errors'
import {
  type AccountantAnswer,
  type Lesson,
  type LessonKind,
  type PrecheckItem,
  type PrecheckOutput,
  type SourceRef,
  useAccountantAnswers,
  useAnswerQuestion,
  useLessons,
  useRunPrecheck,
  useSetLessonStatus,
  useTeachLesson,
} from '@/api/precheck'
import { Button, CopyButton, Dialog, DialogContent, Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'

const FLAG_TEXT: Record<string, string> = {
  no_source: 'The AI gave no source for this',
  no_file_named: 'The AI said it was provided but named no file, so it is requested',
  figure_not_in_documents: 'The reason mentions a figure not found in the documents',
}

const KIND_LABEL: Record<LessonKind, string> = {
  not_needed: 'Not needed',
  wrong_reason: 'Wrong reason',
  missed: 'Missed item',
  other: 'Other',
}

const norm = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

function Sources({ sources, output }: { sources: SourceRef[]; output: PrecheckOutput }) {
  return <SharedSources sources={sources} evidence={output.evidence} />
}

/** The lesson someone saved for a point (a correction), if any: the latest for the same item. */
function lessonFor(lessons: Lesson[], item: string): Lesson | undefined {
  const key = norm(item)
  return lessons.filter((l) => l.status !== 'disabled' && norm(l.item) === key).at(-1)
}

// ---- correcting a point ------------------------------------------------------------------------

/** Teach the pre-check from a correction or something it missed. It applies to this client at once;
 * for every client it waits for a lead or admin (unless one is teaching it). The type of check (and
 * entity type) it is for decides which later pre-checks are given it (AFIT, 29 Oct 2026). "Save and
 * re-run" also runs the pre-check again, so the list and the client email follow the correction. */
function TeachForm({
  jobKey,
  item,
  kind: initialKind,
  natureType,
  onDone,
  onCancel,
}: {
  jobKey: string
  item: string
  kind: LessonKind
  /** The business nature this run worked to: the type of check offered first. */
  natureType: string
  onDone: (rerun: boolean) => void
  onCancel: () => void
}) {
  const teach = useTeachLesson(jobKey)
  const run = useRunPrecheck(jobKey)
  const [kind, setKind] = useState<LessonKind>(initialKind)
  const [itemText, setItemText] = useState(item)
  const [note, setNote] = useState('')
  const [firmWide, setFirmWide] = useState(false)
  const [checkType, setCheckType] = useState(CHECK_TYPES.some((t) => t.value === natureType) ? natureType : '')
  const [entity, setEntity] = useState('')
  const [more, setMore] = useState(false)
  const typeLabel = CHECK_TYPES.find((t) => t.value === checkType)?.label ?? 'Every type of check'
  const save = (rerun: boolean) =>
    teach.mutate(
      { kind, item: itemText, note, firm_wide: firmWide, precheck_type: checkType, entity_type: entity },
      {
        onSuccess: () => {
          if (rerun) run.mutate()
          onDone(rerun)
        },
      },
    )

  return (
    <form
      className={styles.teach}
      onSubmit={(e) => {
        e.preventDefault()
        save(false)
      }}
    >
      <label>
        <span>What was wrong</span>
        <select value={kind} onChange={(e) => setKind(e.target.value as LessonKind)}>
          {(Object.keys(KIND_LABEL) as LessonKind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
      </label>
      {(!item || more) && (
        <label>
          <span>Item</span>
          <input value={itemText} onChange={(e) => setItemText(e.target.value)} placeholder="e.g. Home office details" />
        </label>
      )}
      <label>
        <span>What the pre-check should do instead, and why</span>
        <textarea
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. This property was sold in February 2026, so no council rates are needed for the full year."
        />
      </label>
      <div className={styles.teachRow}>
        <label>
          <span>Type of check it is for</span>
          <select value={checkType} onChange={(e) => setCheckType(e.target.value)} aria-label="Type of check">
            {CHECK_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Entity type</span>
          <select value={entity} onChange={(e) => setEntity(e.target.value)} aria-label="Entity type">
            {RULE_ENTITY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className={styles.check}>
        <input type="checkbox" checked={firmWide} onChange={(e) => setFirmWide(e.target.checked)} />
        <span>
          Apply to every client: {checkType ? `each ${typeLabel.toLowerCase()} check` : 'every check'}
          {entity ? ` of a ${RULE_ENTITY_TYPES.find((t) => t.value === entity)?.label}` : ''} (a lead or admin approves it first)
        </span>
      </label>
      {item && !more && (
        <button type="button" className={styles.linkButton} onClick={() => setMore(true)}>
          Change the item&apos;s wording
        </button>
      )}
      {(teach.isError || run.isError) && (
        <div role="alert" className={styles.error}>
          {extractErrorMessage(teach.error ?? run.error)}
        </div>
      )}
      <div className={styles.teachActions}>
        <Button type="button" variant="primary" size="sm" disabled={teach.isPending || note.trim().length < 5} onClick={() => save(true)}>
          <Sparkles size={13} aria-hidden="true" /> Save and re-run
        </Button>
        <Button type="submit" variant="secondary" size="sm" disabled={teach.isPending || note.trim().length < 5}>
          {teach.isPending ? 'Saving…' : 'Save lesson'}
        </Button>
        <Button type="button" variant="subtle" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

/** What the agent does with a correction, said plainly: nothing changes in the accounts. */
function AiAction({ saved, rerun, lesson }: { saved: boolean; rerun: boolean; lesson?: Lesson }) {
  const done = saved || !!lesson
  const firm = lesson?.status === 'pending'
  const steps = [
    { text: firm ? 'Saved as a learning; a lead approves it for other clients.' : 'Saved as a learning for this client and similar cases.', done },
    {
      text: rerun ? 'Re-running the pre-check: the request list and the email update when it finishes.' : 'The next pre-check run removes or rewords this request and its email line.',
      done: rerun,
    },
  ]
  return (
    <div className={styles.aiAction}>
      <h5 className={styles.aiActionTitle}>
        <Sparkles size={13} aria-hidden="true" /> AI action (auto-update)
      </h5>
      {done ? (
        <ul>
          {steps.map((s) => (
            <li key={s.text} data-done={s.done || undefined}>
              {s.done ? <CircleCheck size={14} aria-hidden="true" /> : <span className={styles.pendingDot} aria-hidden="true" />} {s.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.muted}>
          Write what is wrong and save it. The pre-check keeps it as a lesson for this client, and the request list and the client email
          follow it on the next run.
        </p>
      )}
    </div>
  )
}

// ---- the points --------------------------------------------------------------------------------

/** What the policy check did to a point (AFIT, 20 Nov 2026), and feedback on the policy behind it. */
function PointPolicyNote({ item, jobKey }: { item: PrecheckItem; jobKey: string }) {
  const [feedbackFor, setFeedbackFor] = useState<number | null>(null)
  const policy = item.policy
  if (!policy || policy.policies.length === 0) return null
  return (
    <div className={styles.policyNote} data-changed={policy.changed || undefined}>
      <p className={styles.policyText}>
        <Scale size={13} aria-hidden="true" />{' '}
        {policy.added ? 'Added because a policy requires it' : policy.changed ? 'Changed to follow a policy' : 'Checked against a policy and kept'}
        {policy.note ? `: ${policy.note}` : '.'}
      </p>
      {policy.changed && policy.was && (
        <p className={styles.policyWas}>
          Before: {policy.was.label}
          {policy.was.reason ? ` — ${policy.was.reason}` : ''}
        </p>
      )}
      <div className={styles.policyChips}>
        {policy.policies.map((p) => (
          <span key={p.id} className={styles.policyChip}>
            {p.title} <span className={styles.muted}>· {p.scope_label}</span>
            <button
              type="button"
              className={styles.policyFeedbackButton}
              onClick={() => setFeedbackFor(feedbackFor === p.id ? null : p.id)}
              aria-label={`Feedback on the policy ${p.title}`}
            >
              Feedback
            </button>
          </span>
        ))}
      </div>
      {feedbackFor !== null && (
        <PolicyFeedbackForm policyId={feedbackFor} task={jobKey} context={`${item.item}: ${item.reason}`} onDone={() => setFeedbackFor(null)} />
      )}
    </div>
  )
}

/** Ask the Pre-Check Agent's chat about one point (AFIT, 20 Nov 2026): the question names the point, so the
 * chat answers from that point's result first; the answer appears in the chat. */
function AskAboutPoint({ item, jobKey }: { item: PrecheckItem; jobKey: string }) {
  const ask = useAsk(jobKey)
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('Why is this needed, and where does it come from?')
  const [asked, setAsked] = useState(false)
  if (!open) {
    return (
      <div>
        <button type="button" className={styles.linkButton} onClick={() => (setOpen(true), setAsked(false))}>
          <MessagesSquare size={13} aria-hidden="true" /> Ask the agent about this point
        </button>
        {asked && <span className={styles.muted}> Asked. The answer appears in the chat.</span>}
      </div>
    )
  }
  return (
    <form
      className={styles.askPoint}
      aria-label={`Ask about: ${item.item}`}
      onSubmit={(e) => {
        e.preventDefault()
        const q = question.trim()
        if (q.length < 3) return
        ask.mutate(`About the pre-check point "${item.item.replace(/"/g, "'")}": ${q}`, {
          onSuccess: () => {
            setAsked(true)
            setOpen(false)
            document.querySelector('[aria-label="Pre-Check Agent chat"]')?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
          },
        })
      }}
    >
      <label>
        <span>Your question about “{item.item}”</span>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1500} />
      </label>
      {ask.isError && <p className={styles.muted}>{extractErrorMessage(ask.error)}</p>}
      <div className={styles.askPointActions}>
        <Button type="button" size="sm" variant="subtle" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button type="submit" size="sm" variant="primary" disabled={ask.isPending || question.trim().length < 3}>
          <Send size={13} /> {ask.isPending ? 'Asking…' : 'Ask'}
        </Button>
      </div>
    </form>
  )
}

/** The run's check of every point against the firm's pre-check policies (AFIT, 20 Nov 2026). */
function PolicyCheckLine({ output }: { output: PrecheckOutput }) {
  const c = output.policy_check
  if (!c) return null
  const n = c.policies.length
  return (
    <div className={styles.policyCheck} role="note">
      <Scale size={14} aria-hidden="true" />
      <span>
        {c.error ? (
          c.error
        ) : (
          <>
            Every point was checked against {n} pre-check polic{n === 1 ? 'y' : 'ies'} for this task: <strong>{c.changed} changed</strong>,{' '}
            <strong>{c.added} added</strong>.
          </>
        )}{' '}
        <Link to="/ai-rules?tab=policies">See the policies</Link>
      </span>
    </div>
  )
}

function PointRow({
  n,
  item,
  output,
  jobKey,
  teachAs,
  lesson,
}: {
  n: number
  item: PrecheckItem
  output: PrecheckOutput
  jobKey: string
  teachAs: LessonKind
  lesson?: Lesson
}) {
  const [open, setOpen] = useState(false)
  const [teaching, setTeaching] = useState(false)
  const [saved, setSaved] = useState(false)
  const [rerun, setRerun] = useState(false)
  const corrected = saved || !!lesson
  const docs = [...item.documents, ...item.sources]
  const toggle = () => setOpen((v) => !v)
  return (
    <li className={styles.point} data-open={open || undefined} data-corrected={corrected || undefined}>
      <div className={styles.pointRow}>
        <span className={styles.pointNo} aria-hidden="true">
          {n}
        </span>
        <div className={styles.pointMain}>
          <button type="button" className={styles.pointTitle} onClick={toggle} aria-expanded={open}>
            {item.item}
          </button>
          <p className={styles.pointReason}>{item.reason}</p>
          {item.policy?.changed && (
            <span className={styles.policyBadge}>
              <Scale size={11} aria-hidden="true" /> {item.policy.added ? 'Added by a policy' : 'Changed by a policy'}
            </span>
          )}
          {!open && <DocIcons sources={docs} evidence={output.evidence} max={4} />}
        </div>
        <span className={styles.status} data-status={corrected ? 'corrected' : 'review'}>
          {corrected ? (
            <>
              Corrected <Check size={12} aria-hidden="true" />
            </>
          ) : (
            'To review'
          )}
        </span>
        {corrected ? (
          <button type="button" className={styles.rowButton} onClick={() => setOpen(true)}>
            <MessageSquareText size={13} aria-hidden="true" /> View comment
          </button>
        ) : (
          <button
            type="button"
            className={styles.rowButton}
            data-primary
            aria-label={`Correct: ${item.item}`}
            onClick={() => (setOpen(true), setTeaching(true))}
          >
            <Check size={13} aria-hidden="true" /> Correct
          </button>
        )}
        <button type="button" className={styles.chevron} onClick={toggle} aria-label={`${open ? 'Hide' : 'Show'} details: ${item.item}`} aria-expanded={open}>
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>
      {open && (
        <div className={styles.pointDetail}>
          <div className={styles.pointMeta}>
            {item.group && <span className={styles.groupTag}>{item.group}</span>}
            {item.priority === 'blocking' && item.decision === 'request' && <span className={styles.blocking}>Blocks preparation</span>}
            {item.gap && <GapChip status={item.gap.status} />}
            {item.flags.includes('key_document') && <span className={styles.muted}>Not in the folder: requested first.</span>}
            {item.flags
              .filter((f) => f !== 'key_document')
              .map((f) => (
                <span key={f} className={styles.flag}>
                  <AlertTriangle size={11} aria-hidden="true" /> {FLAG_TEXT[f] ?? f}
                </span>
              ))}
          </div>
          <PointPolicyNote item={item} jobKey={jobKey} />
          {item.documents.length > 0 && <DocIcons sources={item.documents} evidence={output.evidence} label="Provided by" max={8} />}
          <DocIcons sources={item.sources} evidence={output.evidence} max={8} />
          <AskAboutPoint item={item} jobKey={jobKey} />
          <div className={styles.correction}>
            <div className={styles.comment}>
              <h5 className={styles.commentTitle}>
                <MessageSquareText size={13} aria-hidden="true" /> Your comment / correction
              </h5>
              {teaching ? (
                <TeachForm
                  jobKey={jobKey}
                  item={item.item}
                  kind={teachAs}
                  natureType={output.business_nature?.type ?? ''}
                  onCancel={() => setTeaching(false)}
                  onDone={(again) => (setTeaching(false), setSaved(true), setRerun(again))}
                />
              ) : lesson ? (
                <blockquote className={styles.commentText}>
                  {lesson.note}
                  <footer>
                    {KIND_LABEL[lesson.kind]}
                    {lesson.created_by ? ` · ${lesson.created_by}` : ''}
                    {lesson.status === 'pending' ? ' · waiting for a lead to apply it to every client' : ''}
                  </footer>
                </blockquote>
              ) : saved ? (
                <p className={styles.commentText}>Lesson saved.</p>
              ) : (
                <button type="button" className={styles.addComment} onClick={() => setTeaching(true)} aria-label={`Correct: ${item.item}`}>
                  <Pencil size={13} aria-hidden="true" /> Add a comment or correction
                </button>
              )}
            </div>
            <AiAction saved={saved} rerun={rerun} lesson={lesson} />
          </div>
        </div>
      )}
    </li>
  )
}

function PointList({ items, output, jobKey, teachAs, lessons, start = 1 }: {
  items: PrecheckItem[]
  output: PrecheckOutput
  jobKey: string
  teachAs: LessonKind
  lessons: Lesson[]
  start?: number
}) {
  return (
    <ol className={styles.points}>
      {items.map((i, k) => (
        <PointRow key={`${i.group}-${i.item}`} n={start + k} item={i} output={output} jobKey={jobKey} teachAs={teachAs} lesson={lessonFor(lessons, i.item)} />
      ))}
    </ol>
  )
}

function PointsCard({ output, jobKey }: { output: PrecheckOutput; jobKey: string }) {
  const lessons = useLessons(jobKey).data?.lessons ?? []
  const [missedOpen, setMissedOpen] = useState(false)
  const corrected = output.requests.filter((r) => lessonFor(lessons, r.item)).length
  const nature = output.business_nature
  return (
    <section className={styles.card} aria-labelledby="pc-points">
      <div className={styles.cardHead}>
        <span className={styles.cardIcon} aria-hidden="true">
          <ClipboardList size={22} />
        </span>
        <div className={styles.cardHeadText}>
          <h3 id="pc-points" className={styles.cardTitle}>
            Pre-Check Results (Points)
          </h3>
          <p className={styles.cardLead}>
            Review each point and correct it if needed. The client request email is drafted from these points.
          </p>
        </div>
        <dl className={styles.tallies}>
          <div>
            <dt>Total points</dt>
            <dd>{output.requests.length}</dd>
          </div>
          <div data-tone="review">
            <dt>To review</dt>
            <dd>{output.requests.length - corrected}</dd>
          </div>
          <div data-tone="corrected">
            <dt>Corrected</dt>
            <dd>{corrected}</dd>
          </div>
        </dl>
      </div>
      <PolicyCheckLine output={output} />
      <h4 className={styles.srOnly}>Section A — Information required from the client ({output.requests.length})</h4>
      <div className={styles.tableHead} aria-hidden="true">
        <span>#</span>
        <span>Pre-check point</span>
        <span>Status</span>
      </div>
      {output.requests.length === 0 ? (
        <p className={styles.empty}>Nothing to request from the client.</p>
      ) : (
        <PointList items={output.requests} output={output} jobKey={jobKey} teachAs="not_needed" lessons={lessons} />
      )}
      {/* Whether the "not found" list is still provisional, after the points it is about. */}
      <div className={styles.gaps}>
        <GapTracker jobKey={jobKey} />
      </div>
      <div className={styles.cardFoot}>
        {nature && (
          <button type="button" className={styles.linkButton} onClick={() => setMissedOpen((v) => !v)}>
            <Plus size={13} aria-hidden="true" /> Something was missed
          </button>
        )}
      </div>
      {missedOpen && (
        <TeachForm
          jobKey={jobKey}
          item=""
          kind="missed"
          natureType={nature?.type ?? ''}
          onCancel={() => setMissedOpen(false)}
          onDone={() => setMissedOpen(false)}
        />
      )}
      {output.provided.length > 0 && (
        <details className={styles.collapsible}>
          <summary>
            <ChevronDown size={14} aria-hidden="true" /> Already provided ({output.provided.length})
          </summary>
          <PointList items={output.provided} output={output} jobKey={jobKey} teachAs="wrong_reason" lessons={lessons} />
        </details>
      )}
      {output.not_needed.length > 0 && (
        <details className={styles.collapsible}>
          <summary>
            <ChevronDown size={14} aria-hidden="true" /> Not needed ({output.not_needed.length})
          </summary>
          <PointList items={output.not_needed} output={output} jobKey={jobKey} teachAs="wrong_reason" lessons={lessons} />
        </details>
      )}
    </section>
  )
}

// ---- the client email ----------------------------------------------------------------------------

interface Draft {
  base: string
  subject: string
  body: string
}

const draftKey = (jobKey: string) => `tasko.precheck.email-draft.${jobKey}`

function readDraft(jobKey: string, base: string): Draft | null {
  try {
    const raw = window.localStorage.getItem(draftKey(jobKey))
    const d = raw ? (JSON.parse(raw) as Draft) : null
    return d && d.base === base ? d : null // a draft of an earlier run's email is not this one's
  } catch {
    return null
  }
}

/** The client request email, drafted by code from the points (never sent by the AI). The preparer can
 * edit it, keep the edit as a draft in this browser, preview it, copy it, or open it in their email app. */
function EmailCard({ output, jobKey }: { output: PrecheckOutput; jobKey: string }) {
  const base = `${output.email.subject}\n${output.email.body}`
  const [draft, setDraft] = useState<Draft | null>(() => readDraft(jobKey, base))
  const [editing, setEditing] = useState(false)
  const [preview, setPreview] = useState(false)
  const [savedNote, setSavedNote] = useState('')
  const [subject, setSubject] = useState(draft?.subject ?? output.email.subject)
  const [body, setBody] = useState(draft?.body ?? output.email.body)
  const edited = subject !== output.email.subject || body !== output.email.body

  const saveDraft = () => {
    const d = { base, subject, body }
    try {
      window.localStorage.setItem(draftKey(jobKey), JSON.stringify(d))
      setDraft(d)
      setSavedNote('Draft saved in this browser.')
    } catch {
      setSavedNote('The draft could not be saved in this browser.')
    }
    setEditing(false)
  }
  const discard = () => {
    try {
      window.localStorage.removeItem(draftKey(jobKey))
    } catch {
      /* nothing saved */
    }
    setDraft(null)
    setSubject(output.email.subject)
    setBody(output.email.body)
    setSavedNote('')
  }
  const mailto = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`

  return (
    <section className={styles.card} aria-label="Email to the client">
      <div className={styles.cardHead}>
        <span className={styles.cardIcon} aria-hidden="true">
          <Mail size={22} />
        </span>
        <div className={styles.cardHeadText}>
          <h3 className={styles.cardTitle}>Client Request Email (drafted, not sent)</h3>
          <p className={styles.cardLead}>Drafted from the points above. Review and edit it before you send it.</p>
        </div>
        <span className={styles.synced}>
          <Check size={13} aria-hidden="true" /> {draft || edited ? 'Edited by you' : 'Drafted from the points'}
        </span>
      </div>
      <div className={styles.emailGrid}>
        <div className={styles.emailBox}>
          {editing ? (
            <>
              <label className={styles.emailField}>
                <span>Subject</span>
                <input value={subject} onChange={(e) => setSubject(e.target.value)} />
              </label>
              <label className={styles.emailField}>
                <span>Message</span>
                <textarea rows={12} value={body} onChange={(e) => setBody(e.target.value)} />
              </label>
            </>
          ) : (
            <>
              <div className={styles.subject}>
                <span>Subject:</span> {subject}
              </div>
              <pre className={styles.body}>{body}</pre>
            </>
          )}
        </div>
        <div className={styles.emailActions}>
          <a className={styles.sendButton} href={mailto} title="Opens your email app with this email, ready to address and send">
            <Send size={14} aria-hidden="true" /> Send to client
          </a>
          {editing ? (
            <Button variant="secondary" size="sm" onClick={saveDraft}>
              <Save size={14} aria-hidden="true" /> Save as draft
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
              <Pencil size={14} aria-hidden="true" /> Edit
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={() => setPreview(true)}>
            <Eye size={14} aria-hidden="true" /> Preview
          </Button>
          <span className={styles.copyRow}>
            <CopyButton value={`${subject}\n\n${body}`} label="email" /> Copy email
          </span>
          {(draft || edited) && !editing && (
            <button type="button" className={styles.linkButton} onClick={discard}>
              Back to the drafted email
            </button>
          )}
          {savedNote && <span className={styles.muted}>{savedNote}</span>}
        </div>
      </div>
      <Dialog open={preview} onOpenChange={setPreview}>
        <DialogContent title="Email preview" maxWidth={640}>
          <div className={styles.subject}>
            <span>Subject:</span> {subject}
          </div>
          <pre className={styles.body}>{body}</pre>
        </DialogContent>
      </Dialog>
    </section>
  )
}

// ---- learning ------------------------------------------------------------------------------------

function LearningCard({ output, jobKey }: { output: PrecheckOutput; jobKey: string }) {
  const lessons = useLessons(jobKey).data?.lessons ?? []
  const active = lessons.filter((l) => l.status !== 'disabled')
  return (
    <section className={styles.card} aria-labelledby="pc-learning">
      <div className={styles.cardHead}>
        <span className={styles.cardIcon} aria-hidden="true">
          <BookOpenCheck size={20} />
        </span>
        <h3 id="pc-learning" className={styles.cardTitle}>
          Learning &amp; Continuous Improvement
        </h3>
        <span className={styles.infoIcon} title="Corrections are kept as lessons. The pre-check follows them on this client's later runs, and on every client's once a lead approves them.">
          <Info size={16} aria-label="How learning works" />
        </span>
      </div>
      <ul className={styles.learning}>
        <li>
          <CircleCheck size={15} aria-hidden="true" />{' '}
          {active.length
            ? `${active.length} correction${active.length === 1 ? ' is' : 's are'} kept as learning for this client.`
            : 'Corrections you save are kept as learning for this client.'}
        </li>
        <li>
          <CircleCheck size={15} aria-hidden="true" /> The agent considers them in similar future jobs.
        </li>
        {output.lessons_applied.map((l) => (
          <li key={l.id}>
            <CircleCheck size={15} aria-hidden="true" /> Applied in this run: {l.text}
          </li>
        ))}
      </ul>
      <NotesConsidered notes={output.special_notes} />
      <PendingLessons jobKey={jobKey} />
    </section>
  )
}

/** Lessons waiting for a lead or admin to apply them to every client. */
const APPROVE_LABEL: Record<string, string> = {
  firm: 'Apply to all clients',
  team: 'Approve for this workspace',
  project: 'Approve for this project',
  client: 'Approve',
}

/** Lessons a lead or admin must approve before they apply beyond the client they came from. */
export function PendingLessons({ jobKey }: { jobKey: string }) {
  const { data } = useLessons(jobKey)
  const setStatus = useSetLessonStatus(jobKey)
  if (!data?.can_approve || !data.pending_firm_wide.length) return null
  return (
    <div className={styles.pending}>
      <h3 className={styles.sectionTitle}>Lessons waiting for approval ({data.pending_firm_wide.length})</h3>
      <ul className={styles.items}>
        {data.pending_firm_wide.map((l) => (
          <li key={l.id} className={styles.item}>
            <div className={styles.itemHead}>
              <span className={styles.itemTitle}>
                {KIND_LABEL[l.kind]}: {l.item || 'general'}
              </span>
              <span className={styles.muted}>
                {l.created_by}, {l.task}
              </span>
            </div>
            {l.rule ? (
              <p className={styles.reason}>
                <strong>When:</strong> {l.rule.when} <strong>Do:</strong> {l.rule.do} <strong>Why:</strong> {l.rule.why}
              </p>
            ) : null}
            <p className={styles.reason}>{l.rule ? `Note: ${l.note}` : l.note}</p>
            <div className={styles.teachActions}>
              <Button size="sm" variant="primary" onClick={() => setStatus.mutate({ id: l.id, status: 'active' })}>
                {APPROVE_LABEL[l.scope] ?? 'Approve'}
              </Button>
              <Button size="sm" variant="subtle" onClick={() => setStatus.mutate({ id: l.id, status: 'disabled' })}>
                Reject
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---- your information ------------------------------------------------------------------------------

function Information({ output, extra }: { output: PrecheckOutput; extra?: ReactNode }) {
  const nature = output.business_nature
  return (
    <div className={styles.infoGrid}>
      <section className={styles.card} aria-labelledby="pc-key">
        <h3 id="pc-key" className={styles.cardTitle}>
          Key documents
        </h3>
        <ul className={styles.keyDocs}>
          {output.key_documents.map((k) => (
            <li key={k.role}>
              {k.found ? <Check size={15} className={styles.pass} aria-label="Found" /> : <X size={15} className={styles.fail} aria-label="Missing" />}
              <span className={styles.keyLabel}>{k.label}</span>
              {k.files.length > 0 && (
                <DocIcons sources={k.files.map((f) => ({ id: f.name, label: f.name, evidence_id: f.evidence_id }))} evidence={output.evidence} label="Files" />
              )}
              {!k.found && <span className={styles.muted}>{k.note || 'Not in the folder'}</span>}
            </li>
          ))}
        </ul>
      </section>
      {nature && (
        <section className={styles.card} aria-label="Business nature">
          <h3 className={styles.cardTitle}>
            Business nature: {nature.label}
            {nature.fixed && <span className={styles.muted}> (set on the task)</span>}
          </h3>
          {nature.summary && <p className={styles.summary}>{nature.summary}</p>}
          {nature.reasoning && <p className={styles.reason}>{nature.reasoning}</p>}
          <Sources sources={nature.sources} output={output} />
          {nature.facts.length > 0 && (
            <ul className={styles.facts}>
              {nature.facts.map((f) => (
                <li key={f.text}>
                  {f.text} <Sources sources={f.sources} output={output} />
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {extra && <section className={`${styles.card} ${styles.wide}`}>{extra}</section>}
    </div>
  )
}

// ---- AI to human questions ---------------------------------------------------------------------------

/** Questions the pre-check has for the accountant. An answer is kept with the task and given to
 * every later run, so the question is not asked again. */
function AccountantQuestions({ jobKey, questions, output }: { jobKey: string; questions: PrecheckItem[]; output: PrecheckOutput }) {
  const { data } = useAccountantAnswers(jobKey)
  const answers = data?.answers ?? []
  return (
    <>
      <h4 className={styles.subTitle}>Questions for the accountant ({questions.length})</h4>
      <ul className={styles.items}>
        {questions.map((q) => (
          <AccountantQuestion key={q.item} jobKey={jobKey} q={q} output={output} answer={answers.filter((a) => a.question === q.item).at(-1)} />
        ))}
      </ul>
    </>
  )
}

function AccountantQuestion({ jobKey, q, output, answer }: { jobKey: string; q: PrecheckItem; output: PrecheckOutput; answer?: AccountantAnswer }) {
  const save = useAnswerQuestion(jobKey)
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  return (
    <li className={styles.item}>
      <div className={styles.itemHead}>
        <span className={styles.itemTitle}>{q.item}</span>
        {q.priority === 'blocking' && <span className={styles.blocking}>Blocks preparation</span>}
        <span className={styles.muted}>{q.group}</span>
      </div>
      <p className={styles.reason}>{q.reason}</p>
      <DocIcons sources={q.sources} evidence={output.evidence} />
      {answer ? (
        <p className={styles.answer}>
          <strong>Answered by {answer.answered_by}:</strong> {answer.answer}
        </p>
      ) : open ? (
        <form
          className={styles.teach}
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate({ question: q.item, answer: text.trim() }, { onSuccess: () => setOpen(false) })
          }}
        >
          <label>
            <span>Your answer (the next pre-check will use it and not ask again)</span>
            <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
          <div className={styles.teachActions}>
            <Button type="submit" size="sm" variant="primary" disabled={text.trim().length < 2 || save.isPending}>
              Save answer
            </Button>
            <Button type="button" size="sm" variant="subtle" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <button type="button" className={styles.rowButton} data-primary onClick={() => setOpen(true)} aria-label={`Answer: ${q.item}`}>
          Answer
        </button>
      )}
    </li>
  )
}

function Questions({ output, jobKey }: { output: PrecheckOutput; jobKey: string }) {
  const questions = output.accountant_questions ?? []
  return (
    <section className={`${styles.card} ${styles.internal}`} aria-labelledby="pc-questions">
      <h3 id="pc-questions" className={styles.cardTitle}>
        Section B — Internal analysis and accountant questions
      </h3>
      <p className={styles.muted}>For the team only: never sent to the client.</p>
      {questions.length > 0 ? (
        <AccountantQuestions jobKey={jobKey} questions={questions} output={output} />
      ) : (
        <p className={styles.empty}>The pre-check has no questions for the team.</p>
      )}
      {output.preparer_notes.length > 0 && (
        <>
          <h4 className={styles.subTitle}>Notes for the preparer</h4>
          <ul className={styles.facts}>
            {output.preparer_notes.map((n) => (
              <li key={n.text}>
                {n.text} <Sources sources={n.sources} output={output} />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

// ---- the whole result ----------------------------------------------------------------------------

type Tab = 'points' | 'snapshot' | 'info' | 'questions'

/** The pre-check's result as the preparer works through it (AFIT wireframe, 19 Nov 2026): the points
 * to review and correct with their supporting documents as icons, the client email drafted from them,
 * the agent's chat and what it has learned; then the Job Snapshot, the information the run worked
 * from, and the questions the AI has for the team. Every action is the pre-check's own: a correction
 * is a lesson, an answer is kept for later runs; nothing is sent to the client by the AI. */
export function PrecheckResult({ output, jobKey, chat, information }: {
  output: PrecheckOutput
  jobKey: string
  /** The Pre-Check Agent's chat (the latest run only). */
  chat?: ReactNode
  /** More for "Your information": how the AI got here, the setup, the run's details. */
  information?: ReactNode
}) {
  const [tab, setTab] = useState<Tab>('points')
  const answers = useAccountantAnswers(jobKey).data?.answers ?? []
  const open = (output.accountant_questions ?? []).filter((q) => !answers.some((a) => a.question === q.item)).length
  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
      <div className={styles.tabs}>
        <TabsList aria-label="Pre-check views">
          <TabsTrigger value="points">Pre-Check Results (Points)</TabsTrigger>
          <TabsTrigger value="snapshot">Snapshot</TabsTrigger>
          <TabsTrigger value="info">Your Information</TabsTrigger>
          <TabsTrigger value="questions">
            AI to Human Questions
            {open > 0 && <span className={styles.openBadge}>{open} open</span>}
          </TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="points" className={styles.tabBody}>
        <div className={styles.layout}>
          <div className={styles.mainColumn}>
            <PointsCard output={output} jobKey={jobKey} />
            {/* Keyed by the email: a new run's email starts afresh (with its own saved draft, if any). */}
            {output.email.body && <EmailCard key={`${output.email.subject}|${output.email.body}`} output={output} jobKey={jobKey} />}
          </div>
          <aside className={styles.sideColumn}>
            {chat && <section className={styles.card}>{chat}</section>}
            <LearningCard output={output} jobKey={jobKey} />
          </aside>
        </div>
      </TabsContent>
      <TabsContent value="snapshot" className={styles.tabBody}>
        {output.snapshot ? (
          <JobSnapshot snapshot={output.snapshot} evidence={output.evidence} />
        ) : (
          <p className={styles.empty}>This run has no Job Snapshot. Run the pre-check again to get one.</p>
        )}
      </TabsContent>
      <TabsContent value="info" className={styles.tabBody}>
        <Information output={output} extra={information} />
      </TabsContent>
      <TabsContent value="questions" className={styles.tabBody}>
        <Questions output={output} jobKey={jobKey} />
      </TabsContent>
    </Tabs>
  )
}
