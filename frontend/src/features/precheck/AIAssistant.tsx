import { ClipboardCheck, ListChecks, MessageCircleQuestion, Sparkles } from 'lucide-react'
import { type ReactNode, useState } from 'react'

import styles from './AIAssistant.module.css'
import { AskPanel } from './AskPanel'
import { GuidePanel } from './GuidePanel'
import { Milestones } from './Milestones'
import { PrecheckPanel } from './PrecheckPanel'
import { ReviewPanel } from './ReviewPanel'
import { useConversation } from '@/api/ask'
import { useJobGuide } from '@/api/guide'
import { useJobPrecheck } from '@/api/precheck'
import { useJobReview } from '@/api/review'
import { Dialog, DialogContent } from '@/design-system'

type Tool = 'precheck' | 'guide' | 'ask' | 'review'

/** The AI assistant on a task card: four buttons, each opening its tool in a window — the
 * pre-check before the accounts are prepared, the guide to preparing them, questions at any time,
 * and the review of the draft statements. Each button shows where things stand; below, the
 * dates of each stage of the task. */
export function AIAssistant({ jobKey }: { jobKey: string }) {
  const [open, setOpen] = useState<Tool | null>(null)
  const precheck = useJobPrecheck(jobKey).data
  const review = useJobReview(jobKey).data
  const conversation = useConversation(jobKey).data
  const guide = useJobGuide(jobKey).data

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
      : 'Ask anything about this task'

  const guideLatest = guide?.latest
  const guideSteps = guideLatest && 'steps' in (guideLatest.guide ?? {}) ? (guideLatest.guide as { steps: unknown[] }).steps.length : 0
  const guideStatus = !guide
    ? ''
    : guideLatest?.status === 'running'
      ? 'Writing…'
      : guideLatest?.status === 'failed'
        ? 'Last run failed'
        : guideLatest
          ? `${guideSteps} step${guideSteps === 1 ? '' : 's'}`
          : guide.has_precheck
            ? 'Ready to write'
            : 'Best after the pre-check'

  return (
    <section className={styles.assistant} aria-label="AI assistant">
      <h2 className={styles.title}>
        <Sparkles size={15} aria-hidden="true" /> AI assistant
      </h2>
      <div className={styles.launchers}>
        <Launcher icon={<Sparkles size={18} />} name="Pre-check" purpose="What is still needed before preparing the accounts"
          status={precheckStatus} onOpen={() => setOpen('precheck')} />
        <Launcher icon={<ListChecks size={18} />} name="Guide" purpose="Step-by-step guide to preparing the statements"
          status={guideStatus} onOpen={() => setOpen('guide')} />
        <Launcher icon={<MessageCircleQuestion size={18} />} name="Ask" purpose="Questions on this task, NZ standards and law"
          status={askStatus} onOpen={() => setOpen('ask')} />
        <Launcher icon={<ClipboardCheck size={18} />} name="Review" purpose="Review the draft financial statements"
          status={reviewStatus} onOpen={() => setOpen('review')} />
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
      <Milestones jobKey={jobKey} />
    </section>
  )
}

function Launcher({ icon, name, purpose, status, onOpen }: { icon: ReactNode; name: string; purpose: string; status: string; onOpen: () => void }) {
  return (
    <button type="button" className={styles.launcher} onClick={onOpen} aria-haspopup="dialog">
      <span className={styles.icon} aria-hidden="true">
        {icon}
      </span>
      <span className={styles.text}>
        <span className={styles.name}>{name}</span>
        <span className={styles.purpose}>{purpose}</span>
        {status && <span className={styles.status}>{status}</span>}
      </span>
    </button>
  )
}
