import { GraduationCap, Plus } from 'lucide-react'
import { useState } from 'react'

import styles from './AiRulesPage.module.css'
import { CHECK_TYPES, KIND_LABELS, RULE_ENTITY_TYPES } from './ruleOptions'
import { extractErrorMessage } from '@/api/errors'
import { type Lesson, type LessonKind, useAddRule, useRuleLibrary, useSetRuleStatus } from '@/api/precheck'
import { Button, Skeleton } from '@/design-system'

const STATUS_LABEL: Record<Lesson['status'], string> = { active: 'Active', pending: 'Waiting for approval', disabled: 'Switched off' }

/** Give the AI something it missed, as a rule for a type of check: every later pre-check of that
 * type (and entity type) is given it, and applies it where it fits (AFIT, 29 Oct 2026). */
function AddRuleForm({ canApprove, onDone }: { canApprove: boolean; onDone: () => void }) {
  const add = useAddRule()
  const [kind, setKind] = useState<LessonKind>('missed')
  const [item, setItem] = useState('')
  const [note, setNote] = useState('')
  const [checkType, setCheckType] = useState('')
  const [entity, setEntity] = useState('')
  return (
    <form
      className={styles.form}
      aria-label="New AI rule"
      onSubmit={(e) => {
        e.preventDefault()
        add.mutate({ kind, item: item.trim(), note: note.trim(), precheck_type: checkType, entity_type: entity }, { onSuccess: onDone })
      }}
    >
      <div className={styles.row}>
        <label>
          <span>What it is</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as LessonKind)}>
            {(Object.keys(KIND_LABELS) as LessonKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Type of check</span>
          <select value={checkType} onChange={(e) => setCheckType(e.target.value)}>
            {CHECK_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Entity type</span>
          <select value={entity} onChange={(e) => setEntity(e.target.value)}>
            {RULE_ENTITY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        <span>Item (optional)</span>
        <input value={item} onChange={(e) => setItem(e.target.value)} placeholder="e.g. Landlord insurance" maxLength={300} />
      </label>
      <label>
        <span>What the AI should check or do, and why</span>
        <textarea
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={1000}
          placeholder="e.g. For every rental property ask for the landlord insurance schedule: the premium is deductible and often left out of the questionnaire."
        />
      </label>
      <p className={styles.hint}>
        The AI writes it up as a rule (when it applies, what to do, why). Each later pre-check of this type is given it and applies it
        where the job fits.{canApprove ? '' : ' A lead or an admin approves it before it applies.'}
      </p>
      {add.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(add.error)}
        </p>
      )}
      <div className={styles.actions}>
        <Button type="button" variant="subtle" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={add.isPending || note.trim().length < 5}>
          {add.isPending ? 'Saving…' : canApprove ? 'Save rule' : 'Propose rule'}
        </Button>
      </div>
    </form>
  )
}

function RuleCard({ lesson, canApprove }: { lesson: Lesson; canApprove: boolean }) {
  const setStatus = useSetRuleStatus()
  const rule = lesson.rule
  return (
    <li className={styles.rule} data-status={lesson.status}>
      <div className={styles.ruleHead}>
        <span className={styles.ruleTitle}>{rule?.title || lesson.item || KIND_LABELS[lesson.kind]}</span>
        <span className={styles.status}>{STATUS_LABEL[lesson.status]}</span>
      </div>
      <div className={styles.tags}>
        <span className={styles.tag}>{lesson.precheck_type_label ?? 'Every type of check'}</span>
        {lesson.entity_type && <span className={styles.tag}>{lesson.entity_label}</span>}
        <span className={styles.tag}>{lesson.scope_label ?? lesson.scope}</span>
        <span className={styles.tag}>{KIND_LABELS[lesson.kind]}</span>
      </div>
      {rule?.do ? (
        <dl className={styles.ruleBody}>
          <dt>When</dt>
          <dd>{rule.when}</dd>
          <dt>Do</dt>
          <dd>{rule.do}</dd>
          <dt>Why</dt>
          <dd>{rule.why}</dd>
        </dl>
      ) : (
        <p className={styles.note}>
          {lesson.note}
          {lesson.drafting === 'drafting' && <span className={styles.muted}> · The AI is writing it up as a rule…</span>}
        </p>
      )}
      {rule?.do && <p className={styles.muted}>In their words: {lesson.note}</p>}
      <p className={styles.muted}>
        {lesson.created_by || 'Someone'}
        {lesson.task ? ` from ${lesson.task}` : ''} · {new Date(lesson.created_at).toLocaleDateString()}
      </p>
      {canApprove && (
        <div className={styles.actions}>
          {lesson.status !== 'active' && (
            <Button size="sm" variant="primary" disabled={setStatus.isPending} onClick={() => setStatus.mutate({ id: lesson.id, status: 'active' })}>
              {lesson.status === 'pending' ? 'Approve' : 'Switch on'}
            </Button>
          )}
          {lesson.status !== 'disabled' && (
            <Button size="sm" variant="subtle" disabled={setStatus.isPending} onClick={() => setStatus.mutate({ id: lesson.id, status: 'disabled' })}>
              Switch off
            </Button>
          )}
        </div>
      )}
    </li>
  )
}

/** The AI rules: what the pre-check agent has been taught, and a place to teach it more. */
export function AiRulesPage() {
  const [q, setQ] = useState('')
  const [type, setType] = useState('all')
  const [status, setStatus] = useState('')
  const [adding, setAdding] = useState(false)
  const { data, isLoading, isError } = useRuleLibrary({ q: q || undefined, type, status: status || undefined })

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>
            <GraduationCap size={20} aria-hidden="true" /> AI rules
          </h1>
          <p className={styles.lead}>
            What the pre-check agent has been taught. Give it anything it missed: each later pre-check of that type of check is given the
            rules that fit the job and applies them.
          </p>
        </div>
        {!adding && (
          <Button variant="primary" onClick={() => setAdding(true)}>
            <Plus size={14} /> Teach the AI
          </Button>
        )}
      </header>

      {adding && <AddRuleForm canApprove={!!data?.can_approve} onDone={() => setAdding(false)} />}

      <div className={styles.filters}>
        <input type="search" placeholder="Search rules…" aria-label="Search rules" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Type of check" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="all">All types of check</option>
          {CHECK_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.value ? t.label : 'Every type (general rules)'}
            </option>
          ))}
        </select>
        <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="pending">Waiting for approval</option>
          <option value="disabled">Switched off</option>
        </select>
      </div>

      {isLoading ? (
        <Skeleton height={120} />
      ) : isError || !data ? (
        <p className={styles.error}>The rules could not be loaded.</p>
      ) : data.lessons.length === 0 ? (
        <p className={styles.muted}>No rules yet. Teach the AI something it missed and it will apply it from the next pre-check.</p>
      ) : (
        <ul className={styles.list} aria-label="Rules">
          {data.lessons.map((lesson) => (
            <RuleCard key={lesson.id} lesson={lesson} canApprove={data.can_approve} />
          ))}
        </ul>
      )}
    </div>
  )
}
