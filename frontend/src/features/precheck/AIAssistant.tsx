import { ArrowRight, ClipboardCheck, FileSpreadsheet, ListChecks, MessagesSquare, ScanSearch, Sparkles } from 'lucide-react'
import { type FormEvent, type ReactNode, useRef, useState } from 'react'

import styles from './AIWorkspace.module.css'
import { AskPanel } from './AskPanel'
import { GuidePanel } from './GuidePanel'
import { PrecheckPanel } from './PrecheckPanel'
import { ReviewPanel } from './ReviewPanel'
import { SpecialNotes } from './SpecialNotes'
import { WpAgentPanel } from './WpAgentPanel'
import { useAsk, useConversation } from '@/api/ask'
import { extractErrorMessage } from '@/api/errors'
import { useJobGuide } from '@/api/guide'
import { useJobPrecheck } from '@/api/precheck'
import { useJobReview } from '@/api/review'
import { useWpAgent } from '@/api/wpAgent'
import { Dialog, DialogContent } from '@/design-system'

type Tool = 'precheck' | 'guide' | 'wp' | 'ask' | 'review'

const ASK_PROMPTS = ['What is missing?', 'Explain this GST difference', 'Help with an adjustment']

const finished = (status: string | undefined) => status === 'complete' || status === 'partial'

/** The AI workspace on a task (AFIT, 12 Nov 2026 design): four tools as tiles — the pre-check before
 * the accounts are prepared, the guide to preparing them, the WP Agent's reconciliation workpapers
 * and the review of the draft statements — each opening in its own window, the next one to do marked
 * "Next step"; and Ask, a question box on the page whose answers open in their own window. */
export function AIAssistant({ jobKey }: { jobKey: string }) {
  const [open, setOpen] = useState<Tool | null>(null)
  const [question, setQuestion] = useState('')
  const questionRef = useRef<HTMLInputElement>(null)
  const ask = useAsk(jobKey)
  const precheck = useJobPrecheck(jobKey).data
  const review = useJobReview(jobKey).data
  const conversation = useConversation(jobKey).data
  const guide = useJobGuide(jobKey).data
  const wp = useWpAgent(jobKey).data

  const precheckStatus = precheck?.latest
    ? precheck.latest.status === 'running'
      ? 'Running…'
      : precheck.latest.status === 'failed'
        ? 'Last run failed'
        : (precheck.latest.readiness ?? 'Done')
    : precheck && !precheck.setup.ready
      ? 'Set up the Drive folder'
      : 'Not run yet'
  const openFindings = review?.findings.filter((f) => f.status === 'open') ?? []
  const openHigh = openFindings.filter((f) => f.severity === 'high').length
  const reviewStatus = !review
    ? ''
    : review.session.status === 'complete'
      ? 'Review complete'
      : review.latest?.status === 'running'
        ? 'Reviewing…'
        : review.rounds_done
          ? `${openFindings.length} open finding${openFindings.length === 1 ? '' : 's'}${openHigh ? ` (${openHigh} high)` : ''}`
          : 'Not run yet'
  const asked = conversation?.questions.length ?? 0
  const askStatus = conversation?.questions.some((q) => q.status === 'pending')
    ? 'Answering…'
    : asked
      ? `${asked} question${asked === 1 ? '' : 's'} asked`
      : ''

  const guideLatest = guide?.latest
  const guideBody = (guideLatest?.guide ?? {}) as { format?: number; steps?: unknown[]; events?: { status: string }[] }
  const guideSteps = guideBody.steps?.length ?? 0
  const guideEvents = guideBody.events ?? []
  const toConfirm = guideEvents.filter((e) => e.status === 'suspected').length
  const guideWritten =
    guideBody.format === 2
      ? `${guideEvents.length} event alert${guideEvents.length === 1 ? '' : 's'}${toConfirm ? `, ${toConfirm} to confirm` : ''}`
      : `${guideSteps} step${guideSteps === 1 ? '' : 's'}`
  const guideStatus = !guide
    ? ''
    : guideLatest?.status === 'running'
      ? 'Writing…'
      : guideLatest?.status === 'failed'
        ? 'Last run failed'
        : guideLatest
          ? guideWritten
          : guide.has_precheck
            ? 'Ready to write'
            : 'Best after the pre-check'

  // The WP Agent (AFIT, 8 Nov 2026): reconciliation workpapers (GST; wages and ICA from 10 Nov 2026).
  const wpLatest = wp?.latest
  const wpStatus = !wp
    ? ''
    : wpLatest?.status === 'running'
      ? 'Reconciling…'
      : wpLatest?.status === 'failed'
        ? 'Last run failed'
        : wpLatest?.gst?.status
          ? `GST: ${wpLatest.gst.status}`
          : 'Reconciliation workpapers'

  // The next tool to use, in the order the work is done: the pre-check, the guide, then the review.
  const reviewDone = (review?.rounds_done ?? 0) > 0
  const next: Tool | null = !finished(precheck?.latest?.status)
    ? 'precheck'
    : !finished(guideLatest?.status)
      ? 'guide'
      : !reviewDone
        ? 'review'
        : null

  const submitQuestion = (e: FormEvent) => {
    e.preventDefault()
    const text = question.trim()
    if (!text) return
    ask.mutate(text, { onSuccess: () => (setQuestion(''), setOpen('ask')) })
  }

  return (
    <section className={styles.workspace} aria-label="AI assistant">
      <div className={styles.heading}>
        <h2 className={styles.title}>
          <Sparkles size={20} aria-hidden="true" /> AI workspace
        </h2>
        <span className={styles.tagline}>Expert support at every stage</span>
      </div>
      <div className={styles.tiles}>
        <Tile icon={<ScanSearch size={20} />} name="Pre-check" purpose="Identify missing information" status={precheckStatus}
          action={precheck?.latest ? 'Open pre-check' : 'Start pre-check'} next={next === 'precheck'} onOpen={() => setOpen('precheck')} />
        <Tile icon={<ListChecks size={20} />} name="Preparation guide" purpose="A clear plan for this job" status={guideStatus}
          action={guideLatest ? 'Open guide' : 'Generate guide'} next={next === 'guide'} onOpen={() => setOpen('guide')} />
        <Tile icon={<FileSpreadsheet size={20} />} name="Workpaper agent" purpose="GST, wages & imputation" status={wpStatus}
          action="Open workpapers" onOpen={() => setOpen('wp')} />
        <Tile icon={<ClipboardCheck size={20} />} name="Review" purpose="Check draft financial statements" status={reviewStatus}
          action={reviewDone ? 'Open review' : 'Start review'} next={next === 'review'} onOpen={() => setOpen('review')} />
      </div>
      <SpecialNotes jobKey={jobKey} />

      <div className={styles.ask}>
        <div className={styles.askHead}>
          <span className={styles.askIcon} aria-hidden="true">
            <MessagesSquare size={24} />
          </span>
          <div className={styles.askText}>
            <h3 className={styles.askTitle}>Ask Assistant</h3>
            <p className={styles.askPurpose}>Answers grounded in this job and its documents</p>
          </div>
          {askStatus && (
            <button type="button" className={styles.askHistory} onClick={() => setOpen('ask')}>
              {askStatus}
            </button>
          )}
        </div>
        <form className={styles.askForm} onSubmit={submitQuestion}>
          <input
            ref={questionRef}
            aria-label="Ask anything about this job"
            placeholder="Ask anything about this job…"
            value={question}
            maxLength={2000}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button type="submit" className={styles.askSend} aria-label="Ask" disabled={!question.trim() || ask.isPending}>
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        </form>
        <div className={styles.prompts} role="group" aria-label="Suggested questions">
          {ASK_PROMPTS.map((p) => (
            <button key={p} type="button" className={styles.prompt} onClick={() => (setQuestion(p), questionRef.current?.focus())}>
              {p}
            </button>
          ))}
        </div>
        {ask.isError && <p className={styles.error}>{extractErrorMessage(ask.error)}</p>}
      </div>

      <Dialog open={open === 'precheck'} onOpenChange={(o) => !o && setOpen(null)}>
        {/* The pre-check panel has its own title row (with earlier runs), so the window's title is for screen readers. */}
        <DialogContent title="AI pre-check" maxWidth={1040} hideTitle>
          <PrecheckPanel jobKey={jobKey} />
        </DialogContent>
      </Dialog>
      <Dialog open={open === 'guide'} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent title="Preparation guide" maxWidth={1040}>
          <GuidePanel jobKey={jobKey} />
        </DialogContent>
      </Dialog>
      <Dialog open={open === 'wp'} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent title="WP Agent — reconciliations" maxWidth={1040}>
          <WpAgentPanel jobKey={jobKey} />
        </DialogContent>
      </Dialog>
      <Dialog open={open === 'review'} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent title="AI review of the draft financial statements" maxWidth={1040}>
          <ReviewPanel jobKey={jobKey} />
        </DialogContent>
      </Dialog>
      <Dialog open={open === 'ask'} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent title="Ask the AI about this task" maxWidth={820}>
          <AskPanel jobKey={jobKey} />
        </DialogContent>
      </Dialog>
    </section>
  )
}

function Tile({
  icon,
  name,
  purpose,
  status,
  action,
  next,
  onOpen,
}: {
  icon: ReactNode
  name: string
  purpose: string
  status: string
  action: string
  next?: boolean
  onOpen: () => void
}) {
  return (
    <div className={styles.tile} data-next={next || undefined} role="group" aria-label={name}>
      <span className={styles.tileIcon} aria-hidden="true">
        {icon}
      </span>
      <div className={styles.tileText}>
        <div className={styles.tileHead}>
          <h3 className={styles.tileName}>{name}</h3>
          {next && <span className={styles.nextStep}>Next step</span>}
        </div>
        <p className={styles.tilePurpose}>{purpose}</p>
        {status && <p className={styles.tileStatus}>{status}</p>}
        <button type="button" className={next ? styles.tileActionPrimary : styles.tileAction} onClick={onOpen} aria-haspopup="dialog">
          {action} <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
