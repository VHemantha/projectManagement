import { AlertTriangle, ExternalLink, Globe2, Loader2, Send } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import styles from './AskPanel.module.css'
import { type AnswerBasis, type AnswerPoint, type AnswerSource, type AssistantQuestion, useAsk, useConversation, useStopQuestion } from '@/api/ask'
import { extractErrorMessage } from '@/api/errors'
import { Button, Skeleton } from '@/design-system'

const STATUS_LABEL: Record<string, string> = {
  answered: 'Answered from the documents',
  partial: 'Partly answered',
  not_found: 'Not found in the documents',
}
const NEW_STATUS_LABEL: Record<string, string> = {
  answered: 'Answered',
  partial: 'Partly answered',
  not_found: 'Could not be answered',
}
const BASIS_LABEL: Record<AnswerBasis, string> = {
  task_documents: "From this task's documents",
  nz_standards_law: 'NZ standards / law',
  general_knowledge: 'General knowledge — beyond NZ standards',
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
  'How is GST treated on the sale of a residential rental?',
]

/** Ask the AI about this task or the accounting and tax around it. Answers draw first on this
 * task's documents, then NZ standards and law, then general knowledge — and each point says which,
 * so the accountant can see where the AI went beyond the folder and NZ sources. */
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
        Ask about this task, or a general accounting or tax question. The AI answers from this task&apos;s documents first, then
        NZ standards, IRD law and company law, and general knowledge last — each point says which.
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
            <Exchange key={q.id} q={q} jobKey={jobKey} />
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

function Exchange({ q, jobKey }: { q: AssistantQuestion; jobKey: string }) {
  const stop = useStopQuestion(jobKey)
  return (
    <li className={styles.exchange}>
      <p className={styles.question}>
        <span className={styles.who}>{q.asked_by || 'You'}</span> {q.question}
      </p>
      {q.status === 'pending' ? (
        <p className={styles.answer} aria-busy="true">
          <Loader2 size={14} className={styles.spin} aria-hidden="true" /> Looking…{' '}
          <button type="button" className={styles.stop} disabled={stop.isPending} onClick={() => stop.mutate(q.id)}>
            {stop.isPending ? 'Stopping…' : 'Stop'}
          </button>
        </p>
      ) : q.status === 'failed' ? (
        <p className={styles.error}>{q.failure_reason || 'The AI could not answer.'}</p>
      ) : (
        <div className={styles.answer}>
          <span className={styles.status} data-status={q.answer_status}>
            {(q.points?.length ? NEW_STATUS_LABEL : STATUS_LABEL)[q.answer_status] ?? q.answer_status}
          </span>
          {q.outside_job && <span className={styles.outside}>Outside this job</span>}
          <p className={styles.text}>{q.answer}</p>
          {q.beyond_nz && (
            <p className={styles.beyond} role="note">
              <Globe2 size={13} aria-hidden="true" /> Part of this answer goes beyond NZ standards and law — those points are
              marked below with where the advice comes from.
            </p>
          )}
          {q.points && q.points.length > 0 && (
            <ol className={styles.points} aria-label="Points of the answer">
              {q.points.map((pt, i) => (
                <Point key={i} p={pt} />
              ))}
            </ol>
          )}
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

function Point({ p }: { p: AnswerPoint }) {
  return (
    <li className={styles.point} data-basis={p.basis}>
      <span className={styles.basis} data-basis={p.basis}>
        {BASIS_LABEL[p.basis] ?? p.basis}
      </span>
      <p className={styles.text}>{p.text}</p>
      {p.reference && <p className={styles.reference}>Source: {p.reference}</p>}
      {p.sources.length > 0 && (
        <ul className={styles.sources} aria-label="Sources">
          {p.sources.map((s) => (
            <Source key={s.id} s={s} />
          ))}
        </ul>
      )}
      {p.flags.map((f) => (
        <p key={f} className={styles.flag}>
          <AlertTriangle size={12} aria-hidden="true" /> {FLAG_TEXT[f] ?? f}
        </p>
      ))}
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
