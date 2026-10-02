import * as RadixDialog from '@radix-ui/react-dialog'
import { format } from 'date-fns'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ExternalLink,
  FileSearch,
  FileText,
  FolderOpen,
  Gauge,
  ListChecks,
  Loader2,
  RotateCcw,
  Scale,
  ShieldCheck,
  Sparkles,
  Undo2,
  X,
} from 'lucide-react'
import { type FormEvent, useState } from 'react'

import styles from './PrecheckPanel.module.css'
import {
  BASIS_LABELS,
  costChip,
  DISPOSITION_ACTIONS,
  DISPOSITION_LABELS,
  duration,
  KIND_LABELS,
  openFindings,
  SEVERITY_LABELS,
  STATUS_LABELS,
  TRAIL,
  trailStep,
  VERDICT_WORDS,
} from './precheckText'
import { extractErrorMessage } from '@/api/errors'
import {
  type DirectionItem,
  type Finding,
  type JobPrecheck,
  type PrecheckSetup,
  type Run,
  type Severity,
  type TrailStage,
  useDraftDirections,
  useJobPrecheck,
  usePrecheckRun,
  useRunPrecheck,
  useSavePrecheckSetup,
  useSetDisposition,
} from '@/api/precheck'
import { Button, Skeleton } from '@/design-system'

const STAGE_ICONS: Record<TrailStage, typeof FileSearch> = {
  read: FileSearch,
  checked: ListChecks,
  compared: Scale,
  judged: Gauge,
  verified: ShieldCheck,
}

/** The AI pre-check on a job card: verdict, how the AI got there, findings with their proof,
 * and a person's decision on each. A quality gate before human review — never a review. */
export function PrecheckPanel({ jobKey }: { jobKey: string }) {
  const { data, isLoading, isError } = useJobPrecheck(jobKey)
  const start = useRunPrecheck(jobKey)
  const [editingSetup, setEditingSetup] = useState(false)
  const [viewing, setViewing] = useState<string | null>(null)
  const older = usePrecheckRun(viewing && viewing !== data?.latest?.run_id ? viewing : null)

  if (isLoading) {
    return (
      <section className={styles.panel} aria-label="AI pre-check" aria-busy="true">
        <Skeleton width={160} height={14} style={{ marginBottom: 16 }} />
        <Skeleton height={64} />
      </section>
    )
  }
  if (isError || !data) {
    return (
      <section className={styles.panel} aria-label="AI pre-check">
        <PanelTitle />
        <p className={styles.muted}>The pre-check could not be loaded. Refresh the page to try again.</p>
      </section>
    )
  }

  const run = older.data ?? data.latest
  const drafting = data.draft?.status === 'running'
  const running = data.latest?.status === 'running' || drafting
  const noItems = data.setup.direction_items.length === 0
  const runButton = (label: string, primary = true) => (
    <Button
      variant={primary ? 'primary' : 'secondary'}
      size="sm"
      disabled={!data.setup.ready || start.isPending || running}
      onClick={() => {
        setViewing(null)
        start.mutate()
      }}
    >
      {primary ? <Sparkles size={14} aria-hidden="true" /> : <RotateCcw size={14} aria-hidden="true" />}
      {start.isPending ? 'Starting…' : label}
    </Button>
  )

  return (
    <section className={styles.panel} aria-label="AI pre-check">
      <div className={styles.titleRow}>
        <PanelTitle />
        {data.history.length > 1 && (
          <label className={styles.history}>
            <span className={styles.srOnly}>Earlier runs</span>
            <select value={run?.run_id ?? ''} onChange={(e) => setViewing(e.target.value)}>
              {data.history.map((h, i) => (
                <option key={h.run_id} value={h.run_id}>
                  {format(new Date(h.created_at), 'd MMM, HH:mm')}
                  {i === 0 ? ' (latest)' : ''}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {start.isError && (
        <div role="alert" className={styles.notice} data-tone="danger">
          {extractErrorMessage(start.error, 'The pre-check could not be started.')}
        </div>
      )}

      {editingSetup || !data.setup.ready ? (
        <SetupForm
          // Remounts when the saved items change (for example when an AI draft arrives).
          key={data.setup.direction_items.map((i) => i.id + i.text).join('|')}
          jobKey={jobKey}
          setup={data.setup}
          drafting={drafting}
          draftFailure={data.draft?.status === 'failed' ? data.draft.failure_reason : ''}
          onDone={data.setup.ready ? () => setEditingSetup(false) : undefined}
        />
      ) : !run ? (
        <NeverRun
          setup={data.setup}
          button={runButton(noItems ? 'Draft the Direction Note and run' : 'Run pre-check')}
          onEdit={() => setEditingSetup(true)}
        />
      ) : (
        <RunView
          jobKey={jobKey}
          run={run}
          isLatest={run.run_id === data.latest?.run_id}
          button={runButton(run.status === 'failed' ? 'Try again' : 'Run again', run.status === 'failed')}
          onEdit={() => setEditingSetup(true)}
          setup={data.setup}
        />
      )}
    </section>
  )
}

function PanelTitle() {
  return (
    <h2 className={styles.title}>
      <span className={styles.titleIcon} aria-hidden="true">
        <Sparkles size={15} />
      </span>
      AI pre-check
    </h2>
  )
}

// ---- setup -----------------------------------------------------------------------------------

function SetupForm({
  jobKey,
  setup,
  drafting,
  draftFailure,
  onDone,
}: {
  jobKey: string
  setup: PrecheckSetup
  drafting: boolean
  draftFailure: string
  onDone?: () => void
}) {
  const save = useSavePrecheckSetup(jobKey)
  const draft = useDraftDirections(jobKey)
  const aiItems = setup.direction_items.filter((i) => i.origin === 'ai')
  const [folder, setFolder] = useState(setup.drive_folder_url)
  const [items, setItems] = useState(setup.direction_items.map((i) => i.text).join('\n'))
  const lines = items.split('\n').map((l) => l.trim()).filter(Boolean)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ drive_folder_url: folder.trim(), direction_items: lines }, { onSuccess: () => onDone?.() })
  }

  return (
    <form className={styles.setup} onSubmit={submit}>
      {!setup.ready && (
        <p className={styles.lead}>
          Before the pre-check can run, this job needs its Google Drive folder. The pre-check reads the folder and
          checks each Direction Note item against it. You can write the Direction Note yourself, or leave it empty and
          the AI will draft one from this client&apos;s past jobs and the folder.
        </p>
      )}
      <label className={styles.field}>
        <span>
          <FolderOpen size={14} aria-hidden="true" /> Google Drive folder link
        </span>
        <input
          type="text"
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
          placeholder="https://drive.google.com/drive/folders/…"
        />
        <small>Share the folder (Viewer) with the pre-check service account. The pre-check only reads it.</small>
      </label>
      <label className={styles.field}>
        <span>
          <ListChecks size={14} aria-hidden="true" /> Direction Note items, one per line
        </span>
        <textarea
          rows={Math.min(Math.max(lines.length + 1, 4), 12)}
          value={items}
          onChange={(e) => setItems(e.target.value)}
          placeholder={'Agree the bank reconciliation to the ledger\nConfirm the accruals workpaper is complete'}
        />
        <small>
          {lines.length} item{lines.length === 1 ? '' : 's'}. Each one is checked and reported as addressed or not.
          {lines.length === 0 && ' Leave it empty to have the AI draft it when the pre-check runs.'}
        </small>
      </label>
      {setup.ready && (
        <div className={styles.draftRow}>
          <Button type="button" variant="secondary" size="sm" disabled={drafting || draft.isPending} onClick={() => draft.mutate()}>
            {drafting || draft.isPending ? <Loader2 size={14} className={styles.spin} aria-hidden="true" /> : <Sparkles size={14} aria-hidden="true" />}
            {drafting || draft.isPending ? 'Drafting…' : 'Draft with AI'}
          </Button>
          <span className={styles.muted}>
            Suggests items from this client&apos;s past jobs, what reviewers decided before, and what is in the folder now.
            You can edit them.
          </span>
        </div>
      )}
      {(draft.isError || draftFailure) && (
        <div role="alert" className={styles.notice} data-tone="danger">
          {draft.isError ? extractErrorMessage(draft.error, 'The draft could not be started.') : draftFailure}
        </div>
      )}
      {aiItems.length > 0 && <DraftedList items={aiItems} />}
      {save.isError && (
        <div role="alert" className={styles.notice} data-tone="danger">
          {extractErrorMessage(save.error)}
        </div>
      )}
      <div className={styles.actionsRow}>
        <Button type="submit" variant="primary" size="sm" disabled={save.isPending || !folder.trim()}>
          {save.isPending ? 'Saving…' : 'Save'}
        </Button>
        {onDone && (
          <Button type="button" variant="subtle" size="sm" onClick={onDone}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  )
}

/** Why each AI-drafted item is there. */
function DraftedList({ items }: { items: DirectionItem[] }) {
  return (
    <div className={styles.drafted}>
      <div className={styles.sectionTitle}>Drafted by AI: why each item is here</div>
      <ul className={styles.detailList}>
        {items.map((i) => (
          <li key={i.id} className={styles.detailBlock}>
            <div>
              <span className={styles.ref}>{i.id}</span> <span className={styles.detailMain}>{i.text}</span>
            </div>
            <div className={styles.muted}>
              {i.basis && BASIS_LABELS[i.basis] ? `${BASIS_LABELS[i.basis]}: ` : ''}
              {i.reason}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function SetupLine({ setup, onEdit }: { setup: PrecheckSetup; onEdit: () => void }) {
  if (setup.direction_items.length === 0) {
    return (
      <p className={styles.setupLine}>
        No Direction Note yet: the AI will draft one from this client&apos;s past jobs and the folder, then check each
        item.{' '}
        <button type="button" className={styles.link} onClick={onEdit}>
          Write it yourself or edit the folder
        </button>
      </p>
    )
  }
  return (
    <p className={styles.setupLine}>
      Checks {setup.direction_items.length} Direction Note item{setup.direction_items.length === 1 ? '' : 's'} against the
      job&apos;s Drive folder.{' '}
      <button type="button" className={styles.link} onClick={onEdit}>
        Edit folder and items
      </button>
    </p>
  )
}

function NeverRun({ setup, button, onEdit }: { setup: PrecheckSetup; button: React.ReactNode; onEdit: () => void }) {
  return (
    <div className={styles.empty}>
      <p className={styles.lead}>
        Not run yet. The pre-check reads the job folder, runs the automatic checks and compares each Direction Note
        item with the evidence, so a reviewer starts with the open points in front of them.
        {setup.direction_items.length === 0 &&
          ' This job has no Direction Note, so the AI will draft one first and then verify it.'}
      </p>
      <div className={styles.actionsRow}>{button}</div>
      <SetupLine setup={setup} onEdit={onEdit} />
    </div>
  )
}

// ---- a run -----------------------------------------------------------------------------------

function RunView({
  jobKey,
  run,
  isLatest,
  button,
  setup,
  onEdit,
}: {
  jobKey: string
  run: Run
  isLatest: boolean
  button: React.ReactNode
  setup: JobPrecheck['setup']
  onEdit: () => void
}) {
  const [openFinding, setOpenFinding] = useState<Finding | null>(null)
  const finished = run.status === 'complete' || run.status === 'partial'
  const open = openFindings(run.findings)
  const addressed = run.findings.filter((f) => f.status === 'addressed')

  return (
    <>
      {run.status === 'running' && (
        <div className={styles.verdict} data-verdict="running" role="status">
          <Loader2 size={28} className={styles.spin} aria-hidden="true" />
          <div className={styles.verdictText}>
            <div className={styles.verdictWords}>Checking the job…</div>
            <p className={styles.summary}>This usually takes under a minute. You can leave this page; the result will be here.</p>
          </div>
        </div>
      )}

      {run.status === 'failed' && (
        <div className={styles.verdict} data-verdict="failed" role="alert">
          <AlertTriangle size={28} aria-hidden="true" />
          <div className={styles.verdictText}>
            <div className={styles.verdictWords}>The pre-check did not finish</div>
            <p className={styles.summary}>{run.failure_reason || 'Something went wrong. Nothing was changed.'}</p>
          </div>
          {isLatest && <div className={styles.verdictAction}>{button}</div>}
        </div>
      )}

      {finished && <VerdictHeader run={run} action={isLatest ? button : null} />}

      {run.status === 'partial' && (
        <div className={styles.notice} data-tone="warning" role="status">
          <strong>Stopped at the budget for one run.</strong> {run.skipped.length} step{run.skipped.length === 1 ? ' was' : 's were'} not
          checked and {run.skipped.length === 1 ? 'is' : 'are'} shown as not addressed:
          <ul>
            {run.skipped.map((s) => (
              <li key={s.task_id}>
                {s.what} <span className={styles.muted}>({s.reason})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {run.status !== 'failed' && <Trail run={run} />}

      {finished && run.direction_items.length > 0 && <DirectionChecklist run={run} />}

      {finished && (
        <>
          {open.length === 0 ? (
            <div className={styles.allClear}>
              <Check size={18} aria-hidden="true" />
              <div>
                <strong>Nothing found that needs attention.</strong>
                <div className={styles.muted}>
                  Every Direction Note item has evidence behind it and the automatic checks passed. A human review is still
                  needed.
                </div>
              </div>
            </div>
          ) : (
            (['high', 'medium', 'low'] as Severity[]).map((severity) => {
              const group = open.filter((f) => f.severity === severity)
              if (!group.length) return null
              return (
                <div key={severity} className={styles.group}>
                  <h3 className={styles.groupTitle} data-severity={severity}>
                    {SEVERITY_LABELS[severity]} <span>{group.length}</span>
                  </h3>
                  {group.map((f) => (
                    <FindingCard key={f.id} jobKey={jobKey} finding={f} run={run} onOpen={() => setOpenFinding(f)} />
                  ))}
                </div>
              )
            })
          )}
          {addressed.length > 0 && (
            <details className={styles.addressed}>
              <summary>
                <ChevronDown size={14} aria-hidden="true" /> Addressed <span>{addressed.length}</span>
              </summary>
              {addressed.map((f) => (
                <FindingCard key={f.id} jobKey={jobKey} finding={f} run={run} onOpen={() => setOpenFinding(f)} />
              ))}
            </details>
          )}
        </>
      )}

      <Footer run={run} />
      {isLatest && run.status !== 'running' && <SetupLine setup={setup} onEdit={onEdit} />}
      <EvidenceDrawer finding={openFinding} run={run} onClose={() => setOpenFinding(null)} />
    </>
  )
}

/** The Direction Note as verified in this run: each item addressed or not, and which ones the
 * AI drafted (with its reason). */
function DirectionChecklist({ run }: { run: Run }) {
  const drafted = run.direction_items.filter((i) => i.origin === 'ai').length
  return (
    <div>
      <h3 className={styles.sectionTitle}>
        Direction Note{drafted > 0 && ` (${drafted} of ${run.direction_items.length} drafted by AI)`}
      </h3>
      <ul className={styles.checklist}>
        {run.direction_items.map((i) => (
          <li key={i.id} data-addressed={i.addressed}>
            {i.addressed ? (
              <Check size={14} className={styles.pass} aria-label="Addressed" />
            ) : (
              <X size={14} className={styles.fail} aria-label="Not addressed" />
            )}
            <span className={styles.ref}>{i.id}</span>
            <span className={styles.detailMain}>{i.text}</span>
            {i.origin === 'ai' && (
              <span className={styles.tag} data-kind="ai_suggestion" title={i.reason}>
                AI-drafted
              </span>
            )}
            {i.origin === 'ai' && i.reason && <span className={styles.checkReason}>{i.reason}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function VerdictHeader({ run, action }: { run: Run; action: React.ReactNode }) {
  const { addressed, total } = run.coverage
  const share = total ? addressed / total : 0
  const circumference = 2 * Math.PI * 26
  const verdict = run.verdict || 'ready_with_exceptions'
  return (
    <div className={styles.verdict} data-verdict={verdict}>
      <div
        className={styles.ring}
        role="img"
        aria-label={`${addressed} of ${total} Direction Note items addressed`}
        title="Direction Note coverage"
      >
        <svg viewBox="0 0 64 64" width="64" height="64" aria-hidden="true">
          <circle cx="32" cy="32" r="26" className={styles.ringTrack} />
          <circle
            cx="32"
            cy="32"
            r="26"
            className={styles.ringValue}
            strokeDasharray={`${circumference * share} ${circumference}`}
            transform="rotate(-90 32 32)"
          />
        </svg>
        <span className={styles.ringText}>
          {addressed}/{total}
        </span>
      </div>
      <div className={styles.verdictText}>
        <div className={styles.verdictWords}>{VERDICT_WORDS[verdict]}</div>
        <p className={styles.summary}>{run.summary}</p>
        <div className={styles.counts} aria-label="Open findings by severity">
          {(['high', 'medium', 'low'] as Severity[]).map((s) => (
            <span key={s} className={styles.count} data-severity={s} data-zero={!run.counts[s]}>
              <strong>{run.counts[s] ?? 0}</strong> {SEVERITY_LABELS[s].toLowerCase()}
            </span>
          ))}
        </div>
      </div>
      {action && <div className={styles.verdictAction}>{action}</div>}
    </div>
  )
}

// ---- "How the AI got here" ---------------------------------------------------------------------

function Trail({ run }: { run: Run }) {
  const [open, setOpen] = useState<TrailStage | null>(null)
  return (
    <div className={styles.trailWrap}>
      <h3 className={styles.sectionTitle}>How the AI got here</h3>
      <ol className={styles.trail}>
        {TRAIL.map(({ stage, name }) => {
          const step = trailStep(run, stage)
          const Icon = STAGE_ICONS[stage]
          const hasDetail = !!run.trail?.[stage]
          return (
            <li key={stage} className={styles.step} data-state={step.state} data-open={open === stage}>
              <button
                type="button"
                className={styles.stepButton}
                aria-expanded={open === stage}
                aria-controls={`trail-${stage}`}
                disabled={!hasDetail}
                onClick={() => setOpen(open === stage ? null : stage)}
              >
                <span className={styles.stepIcon} aria-hidden="true">
                  {step.state === 'running' ? <Loader2 size={15} className={styles.spin} /> : <Icon size={15} />}
                </span>
                <span className={styles.stepName}>{name}</span>
                <span className={styles.stepLabel}>{step.label}</span>
              </button>
            </li>
          )
        })}
      </ol>
      {open && run.trail?.[open] && (
        <div id={`trail-${open}`} className={styles.trailDetail}>
          <TrailDetail stage={open} run={run} />
        </div>
      )}
    </div>
  )
}

interface ComparedRow {
  ref: string
  what: string
  reader: string
  outcome: string
  passages: { file: string; location: string }[]
}

function TrailDetail({ stage, run }: { stage: TrailStage; run: Run }) {
  const step = run.trail[stage]!
  if (stage === 'read') {
    return (
      <ul className={styles.detailList}>
        {(step.detail as unknown as { name: string; kind: string; changed: boolean; problem: string; note?: string }[]).map((d) => (
          <li key={d.name}>
            <FileText size={13} aria-hidden="true" /> <span className={styles.detailMain}>{d.name}</span>
            <span className={styles.muted}>{d.kind}</span>
            {d.changed && <span className={styles.tag}>new or changed</span>}
            {d.note && <span className={styles.tag}>{d.note}</span>}
            {d.problem && <span className={styles.tag} data-tone="warning">{d.problem}</span>}
          </li>
        ))}
      </ul>
    )
  }
  if (stage === 'checked') {
    return (
      <ul className={styles.detailList}>
        {(step.detail as unknown as { label: string; passed: boolean; flagged?: boolean; note: string }[]).map((d, i) => (
          <li key={i}>
            {d.passed ? (
              <Check size={13} className={styles.pass} aria-label="Passed" />
            ) : d.flagged ? (
              <AlertTriangle size={13} className={styles.flag} aria-label="Flagged for a closer look" />
            ) : (
              <X size={13} className={styles.fail} aria-label="Failed" />
            )}
            <span className={styles.detailMain}>{d.label}</span>
            {!d.passed && <span className={styles.muted}>{d.note}</span>}
          </li>
        ))}
      </ul>
    )
  }
  if (stage === 'compared') {
    return (
      <ul className={styles.detailList}>
        {(step.detail as unknown as ComparedRow[]).map((d, i) => (
          <li key={i} className={styles.detailBlock}>
            <div>
              {d.ref !== 'none' && <span className={styles.ref}>{d.ref}</span>} <span className={styles.detailMain}>{d.what}</span>
            </div>
            <div className={styles.muted}>
              {d.outcome === 'nothing to read'
                ? 'No document in the folder relates to this.'
                : `${d.reader}, ${d.outcome}: ${d.passages.map((p) => `${p.file} (${p.location})`).join('; ')}`}
            </div>
          </li>
        ))}
      </ul>
    )
  }
  if (stage === 'judged') {
    const how = { model: 'by the judge model', cache: 'reused from an identical earlier run', code: 'nothing needed judging', passthrough: 'not consolidated (see the notice above)' }[
      String(step.how)
    ]
    return (
      <p className={styles.detailText}>
        {String(step.findings_in)} findings from the readers and the automatic checks were weighed and {String(step.findings_out)} kept
        after removing duplicates, {how}. {Number(step.escalated) > 0 ? `${step.escalated} high-severity, low-confidence finding(s) were given a second look by the larger model.` : 'None needed a second look by the larger model.'}
      </p>
    )
  }
  return (
    <p className={styles.detailText}>
      {String(step.evidence)} source passages are linked to the findings. Code checked every finding:{' '}
      {Number(step.rejected_no_evidence)} rejected for having no evidence, {Number(step.rules_restored)} automatic-check
      finding(s) restored unchanged, {Number(step.items_filled)} Direction Note item(s) with no evidence reported as questions.
      Verdict and coverage are computed by code, not by the model.
    </p>
  )
}

// ---- findings ----------------------------------------------------------------------------------

function Confidence({ level }: { level: Severity }) {
  const filled = { high: 3, medium: 2, low: 1 }[level]
  return (
    <span className={styles.confidence} title={`Confidence: ${level}`} aria-label={`Confidence: ${level}`}>
      {[1, 2, 3].map((n) => (
        <span key={n} data-on={n <= filled} />
      ))}
    </span>
  )
}

function FindingCard({ jobKey, finding, run, onOpen }: { jobKey: string; finding: Finding; run: Run; onOpen: () => void }) {
  const setDisposition = useSetDisposition(jobKey)
  const item = run.direction_items.find((i) => i.id === finding.direction_ref)
  const decided = finding.disposition
  return (
    <article className={styles.card} data-severity={finding.status === 'addressed' ? 'done' : finding.severity} data-decided={!!decided}>
      <button type="button" className={styles.cardMain} onClick={onOpen} aria-label={`Show the evidence for: ${finding.title}`}>
        <span className={styles.cardTitle}>{finding.title}</span>
        <span className={styles.cardWhy}>{finding.why}</span>
        <span className={styles.cardMeta}>
          <span className={styles.tag} data-kind={finding.kind}>{KIND_LABELS[finding.kind]}</span>
          <span className={styles.tag}>{STATUS_LABELS[finding.status]}</span>
          <Confidence level={finding.confidence} />
          {item && (
            <span className={styles.ref} title={item.text}>
              {item.id} <span className={styles.refText}>{item.text}</span>
            </span>
          )}
          <span className={styles.proof}>
            {finding.evidence.length ? `${finding.evidence.length} source${finding.evidence.length === 1 ? '' : 's'}` : 'No source: a question for a person'}
          </span>
        </span>
      </button>
      <div className={styles.cardActions}>
        {decided ? (
          <>
            <span className={styles.decided} data-disposition={decided.disposition}>
              {DISPOSITION_LABELS[decided.disposition]}
              {decided.by ? ` by ${decided.by}` : ''}
            </span>
            <button
              type="button"
              className={styles.link}
              disabled={setDisposition.isPending}
              onClick={() => setDisposition.mutate({ findingId: finding.id, disposition: 'cleared' })}
            >
              <Undo2 size={12} aria-hidden="true" /> Undo
            </button>
          </>
        ) : (
          DISPOSITION_ACTIONS.map((a) => (
            <button
              key={a.value}
              type="button"
              className={styles.action}
              disabled={setDisposition.isPending}
              onClick={() => setDisposition.mutate({ findingId: finding.id, disposition: a.value })}
            >
              {a.label}
            </button>
          ))
        )}
      </div>
    </article>
  )
}

/** Claim on the left, proof on the right. */
function EvidenceDrawer({ finding, run, onClose }: { finding: Finding | null; run: Run; onClose: () => void }) {
  const item = finding ? run.direction_items.find((i) => i.id === finding.direction_ref) : null
  return (
    <RadixDialog.Root open={!!finding} onOpenChange={(open) => !open && onClose()}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className={styles.drawerOverlay} />
        <RadixDialog.Content className={styles.drawer} aria-describedby={undefined}>
          {finding && (
            <>
              <div className={styles.drawerHeader}>
                <RadixDialog.Title className={styles.drawerTitle}>Evidence</RadixDialog.Title>
                <RadixDialog.Close className={styles.iconButton} aria-label="Close">
                  <X size={18} />
                </RadixDialog.Close>
              </div>
              <div className={styles.drawerBody}>
                <div className={styles.claim}>
                  <div className={styles.columnLabel}>The claim</div>
                  <div className={styles.claimTitle}>{finding.title}</div>
                  <p className={styles.claimWhy}>{finding.why}</p>
                  <dl className={styles.facts}>
                    <dt>Status</dt>
                    <dd>{STATUS_LABELS[finding.status]}</dd>
                    <dt>Severity</dt>
                    <dd>{SEVERITY_LABELS[finding.severity]}</dd>
                    <dt>Kind</dt>
                    <dd>{KIND_LABELS[finding.kind]}</dd>
                    <dt>Found by</dt>
                    <dd>{finding.source === 'rule' ? 'An automatic check (no AI)' : 'An AI reader'}</dd>
                    <dt>Confidence</dt>
                    <dd>{SEVERITY_LABELS[finding.confidence]}</dd>
                    {finding.area && (
                      <>
                        <dt>Area</dt>
                        <dd>{finding.area}</dd>
                      </>
                    )}
                    {item && (
                      <>
                        <dt>Direction Note</dt>
                        <dd>
                          {item.id}: {item.text}
                        </dd>
                      </>
                    )}
                  </dl>
                </div>
                <div className={styles.proofColumn}>
                  <div className={styles.columnLabel}>The proof</div>
                  {finding.evidence.length === 0 ? (
                    <p className={styles.muted}>
                      There is no source passage for this. The AI did not find evidence, so it is asking the question rather
                      than drawing a conclusion.
                    </p>
                  ) : (
                    finding.evidence.map((e) => (
                      <figure key={e.id} className={styles.source}>
                        <figcaption>
                          <FileText size={14} aria-hidden="true" />
                          <span className={styles.sourceFile}>{e.file_name}</span>
                          <span className={styles.muted}>{e.location}</span>
                        </figcaption>
                        <blockquote>
                          <mark>{e.quote}</mark>
                        </blockquote>
                        {/^https?:\/\//.test(e.drive_url) ? (
                          <a href={e.drive_url} target="_blank" rel="noreferrer" className={styles.link}>
                            <ExternalLink size={12} aria-hidden="true" /> Open in Drive
                          </a>
                        ) : (
                          <span className={styles.muted}>Demo file: no Drive link</span>
                        )}
                      </figure>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  )
}

function Footer({ run }: { run: Run }) {
  const chip = costChip(run)
  const models = [run.models?.reader, run.models?.judge].filter(Boolean).join(' · ')
  return (
    <footer className={styles.footer}>
      <span className={styles.notReview}>AI pre-check, not a human review</span>
      {run.demo && <span className={styles.tag} data-tone="warning">Demo mode: scripted answers, not Claude</span>}
      <span>
        {format(new Date(run.created_at), 'd MMM yyyy, HH:mm')}
        {run.requested_by ? ` · ${run.requested_by}` : ''}
        {run.duration_s != null ? ` · ${duration(run.duration_s)}` : ''}
      </span>
      {models && <span>{models}</span>}
      {chip && (
        <span className={styles.chip} title="Tokens used by this run and the share of input served from the prompt cache">
          {chip}
        </span>
      )}
    </footer>
  )
}
