import { AlertTriangle, ExternalLink, Loader2, Send } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import styles from './AskPanel.module.css'
import { type AnswerSource, type AssistantQuestion, useAsk, useConversation } from '@/api/ask'
import { extractErrorMessage } from '@/api/errors'
import { Button, Skeleton } from '@/design-system'

const STATUS_LABEL: Record<string, string> = {
  answered: 'Answered from the documents',
  partial: 'Partly answered',
  not_found: 'Not found in the documents',
}
const FLAG_TEXT: Record<string, string> = {
  no_source: 'No source was given for this answer',
  figure_not_in_documents: 'It mentions a figure not found in the passages — check it',
}
const SUGGESTIONS = [
  'What changed this year according to the questionnaire?',
  'Which bank accounts and loans are there, and what are the closing balances?',
  'What evidence supports the repairs and maintenance expense?',
  'Which review findings are still open, and why?',
]

/** Ask the AI about this task. Answers come only from this task's documents, assumptions, review
 * findings and feedback, each with the passages it rests on. */
export function AskPanel({ jobKey }: { jobKey: string }) {
  const { data, isLoading, isError } = useConversation(jobKey)
  const ask = useAsk(jobKey)
  const [question, setQuestion] = useState('')
  const pending = data?.questions.some((q) => q.status === 'pending')

  const submit = (text: string) => {
    const q = text.trim()
    if (q.length < 3) return
    ask.mutate(q, { onSuccess: () => setQuestion('') })
  }

  if (isLoading) return <Skeleton height={64} />
  if (isError || !data) return <p className={styles.muted}>The conversation could not be loaded. Refresh the page to try again.</p>

  return (
    <div className={styles.ask}>
      <p className={styles.lead}>
        Ask about this task. The AI answers only from this task&apos;s documents, the preparer&apos;s assumptions and the review,
        and shows where each answer comes from.
      </p>
      {data.questions.length === 0 ? (
        <div className={styles.suggestions} role="group" aria-label="Suggested questions">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className={styles.suggestion} disabled={ask.isPending} onClick={() => submit(s)}>
              {s}
            </button>
          ))}
        </div>
      ) : (
        <ol className={styles.conversation} aria-label="Questions and answers">
          {data.questions.map((q) => (
            <Exchange key={q.id} q={q} />
          ))}
        </ol>
      )}
      <form
        className={styles.form}
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          submit(question)
        }}
      >
        <label className={styles.srOnly} htmlFor={`ask-${jobKey}`}>
          Your question
        </label>
        <textarea
          id={`ask-${jobKey}`}
          rows={2}
          value={question}
          placeholder="e.g. How much was the property sold for, and when did it settle?"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit(question)
            }
          }}
        />
        <Button type="submit" variant="primary" size="sm" disabled={question.trim().length < 3 || ask.isPending}>
          {ask.isPending ? <Loader2 size={14} className={styles.spin} aria-hidden="true" /> : <Send size={14} aria-hidden="true" />}
          Ask
        </Button>
      </form>
      {pending && <p className={styles.muted}>The AI is looking through the task&apos;s documents…</p>}
      {ask.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(ask.error, 'The question could not be sent.')}
        </p>
      )}
    </div>
  )
}

function Exchange({ q }: { q: AssistantQuestion }) {
  return (
    <li className={styles.exchange}>
      <p className={styles.question}>
        <span className={styles.who}>{q.asked_by || 'You'}</span> {q.question}
      </p>
      {q.status === 'pending' ? (
        <p className={styles.answer} aria-busy="true">
          <Loader2 size={14} className={styles.spin} aria-hidden="true" /> Looking…
        </p>
      ) : q.status === 'failed' ? (
        <p className={styles.error}>{q.failure_reason || 'The AI could not answer.'}</p>
      ) : (
        <div className={styles.answer}>
          <span className={styles.status} data-status={q.answer_status}>
            {STATUS_LABEL[q.answer_status] ?? q.answer_status}
          </span>
          <p className={styles.text}>{q.answer}</p>
          {q.flags.map((f) => (
            <p key={f} className={styles.flag}>
              <AlertTriangle size={12} aria-hidden="true" /> {FLAG_TEXT[f] ?? f}
            </p>
          ))}
          {q.sources.length > 0 && (
            <ul className={styles.sources} aria-label="Sources">
              {q.sources.map((s) => (
                <Source key={s.id} s={s} />
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  )
}

function Source({ s }: { s: AnswerSource }) {
  const title = s.evidence?.quote ? `${s.evidence.location ? `${s.evidence.location}: ` : ''}${s.evidence.quote}` : undefined
  const exact = s.how.startsWith('words')
  return (
    <li>
      {s.evidence?.drive_url ? (
        <a className={styles.source} href={s.evidence.drive_url} target="_blank" rel="noreferrer" title={title}>
          {s.label} <ExternalLink size={11} aria-hidden="true" />
        </a>
      ) : (
        <span className={styles.source} title={title}>
          {s.label}
        </span>
      )}
      {exact && <span className={styles.how}>exact match</span>}
    </li>
  )
}
