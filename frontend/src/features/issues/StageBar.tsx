import { format, formatDistanceToNow, parseISO } from 'date-fns'
import { CalendarDays, Check, MessageSquare, Sparkles } from 'lucide-react'
import { useState } from 'react'

import styles from './StageBar.module.css'
import { extractErrorMessage } from '@/api/errors'
import {
  type StageKey,
  type TaskStage,
  textToDoc,
  useAddStageComment,
  useDraftStageNote,
  useStageComments,
  useTaskStages,
} from '@/api/stages'
import type { Comment } from '@/api/types'
import { Avatar, Button, RichTextEditor, Skeleton } from '@/design-system'

function when(stage: TaskStage): string {
  if (stage.done_on) return `Done ${format(parseISO(stage.done_on), 'd MMM')}`
  if (stage.state === 'active') return stage.due_date ? `Active · due ${format(parseISO(stage.due_date), 'd MMM')}` : 'Active'
  return stage.due_date ? `Due ${format(parseISO(stage.due_date), 'd MMM')}` : 'Not scheduled'
}

/** The first line of a comment the AI posted ("AI pre-check — posted automatically on …"). */
function isAiResult(comment: Comment): boolean {
  const first = (comment.body as { content?: { content?: { text?: string }[] }[] }).content?.[0]?.content?.[0]?.text ?? ''
  return / — posted automatically on /.test(first)
}

/** The task's five stages as a progress bar (AFIT, 12 Nov 2026). Clicking a stage shows its
 * history under the bar: the AI's posted results for it and everyone's comments, newest first, and a
 * box to record its completion, drafted by the AI from the stage's latest results. */
export function StageBar({ issueKey }: { issueKey: string }) {
  const { data: stages, isLoading } = useTaskStages(issueKey)
  const [open, setOpen] = useState<StageKey | null>(null)
  const current = stages?.find((s) => s.key === open) ?? null

  return (
    <section className={styles.section} aria-label="Milestones">
      <h2 className={styles.title}>
        <CalendarDays size={18} aria-hidden="true" /> Milestones
      </h2>
      {isLoading || !stages ? (
        <Skeleton height={48} />
      ) : (
        <ol className={styles.bar}>
          {stages.map((s) => (
            <li key={s.key} className={styles.step} data-state={s.state}>
              <button
                type="button"
                className={styles.stepButton}
                aria-pressed={open === s.key}
                aria-label={`${s.label}: ${when(s)}${s.comments ? `, ${s.comments} comment${s.comments === 1 ? '' : 's'}` : ''}. Show its history`}
                onClick={() => setOpen(open === s.key ? null : s.key)}
              >
                <span className={styles.dot} aria-hidden="true">
                  {s.state === 'done' && <Check size={12} strokeWidth={3} />}
                </span>
                <span className={styles.stepLabel}>{s.label}</span>
                <span className={styles.stepWhen}>{when(s)}</span>
                {s.comments > 0 && (
                  <span className={styles.count} aria-hidden="true">
                    <MessageSquare size={10} /> {s.comments}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ol>
      )}
      {current && <StageHistory key={current.key} issueKey={issueKey} stage={current} />}
    </section>
  )
}

function StageHistory({ issueKey, stage }: { issueKey: string; stage: TaskStage }) {
  const { data: comments, isLoading } = useStageComments(issueKey, stage.key)
  const draft = useDraftStageNote(issueKey)
  const add = useAddStageComment(issueKey)
  const [text, setText] = useState('')
  const [drafted, setDrafted] = useState<'ai' | 'code' | null>(null)
  const name = stage.label.toLowerCase()

  const draftWithAi = () =>
    draft.mutate(stage.key, {
      onSuccess: (note) => {
        setText(note.text)
        setDrafted(note.ai ? 'ai' : 'code')
      },
    })
  const post = () => {
    if (!text.trim()) return
    add.mutate({ stage: stage.key, body: textToDoc(text) }, { onSuccess: () => (setText(''), setDrafted(null)) })
  }

  return (
    <div className={styles.history} role="region" aria-label={`${stage.label} history`}>
      <div className={styles.historyHead}>
        <h3>{stage.label} history</h3>
        <span className={styles.muted}>{when(stage)}</span>
      </div>

      <div className={styles.composer}>
        <textarea
          aria-label={`Comment on the ${name}`}
          placeholder={`Record the ${name}'s completion and its results, or add a comment…`}
          value={text}
          rows={text ? Math.min(10, text.split('\n').length + 1) : 2}
          onChange={(e) => setText(e.target.value)}
        />
        {drafted && (
          <p className={styles.draftNote}>
            <Sparkles size={12} aria-hidden="true" />
            {drafted === 'ai'
              ? `Drafted by the AI from the ${name}'s latest results. Check it before you post.`
              : "Written from the task's records (the AI isn't available just now). Check it before you post."}
          </p>
        )}
        <div className={styles.composerActions}>
          <Button variant="secondary" size="sm" onClick={draftWithAi} disabled={draft.isPending}>
            <Sparkles size={14} aria-hidden="true" /> {draft.isPending ? 'Drafting…' : 'Draft with AI'}
          </Button>
          <Button variant="primary" size="sm" onClick={post} disabled={!text.trim() || add.isPending}>
            Post comment
          </Button>
        </div>
        {(draft.isError || add.isError) && <p className={styles.error}>{extractErrorMessage(draft.error ?? add.error)}</p>}
      </div>

      {isLoading ? (
        <Skeleton height={40} />
      ) : comments && comments.length > 0 ? (
        <ol className={styles.comments} aria-label={`${stage.label} comments`}>
          {comments.map((c) => (
            <li key={c.id} className={styles.comment}>
              <Avatar name={c.author.display_name} src={c.author.avatar} size={28} />
              <div className={styles.commentBody}>
                <div className={styles.commentMeta}>
                  <span className={styles.author}>{c.author.display_name}</span>
                  {isAiResult(c) && (
                    <span className={styles.aiBadge}>
                      <Sparkles size={10} aria-hidden="true" /> AI result
                    </span>
                  )}
                  <span className={styles.muted}>{formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}</span>
                </div>
                <RichTextEditor content={c.body} editable={false} showToolbar={false} />
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className={styles.muted}>No comments on the {name} yet. The AI's results appear here when it finishes.</p>
      )}
    </div>
  )
}
