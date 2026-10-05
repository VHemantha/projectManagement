import { AlertTriangle, Check, ChevronDown, ExternalLink, GraduationCap, Mail, X } from 'lucide-react'
import { useState } from 'react'

import styles from './PrecheckResult.module.css'
import { extractErrorMessage } from '@/api/errors'
import {
  type LessonKind,
  type PrecheckItem,
  type PrecheckOutput,
  type SourceRef,
  useLessons,
  useSetLessonStatus,
  useTeachLesson,
} from '@/api/precheck'
import { Button, CopyButton } from '@/design-system'

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

function Source({ source, output }: { source: SourceRef; output: PrecheckOutput }) {
  const ev = source.evidence_id ? output.evidence[source.evidence_id] : undefined
  if (!ev) return <span className={styles.source}>{source.label}</span>
  return (
    <a className={styles.source} href={ev.drive_url} target="_blank" rel="noreferrer" title={`${ev.file_name} — ${ev.location}: ${ev.quote}`}>
      {source.label} <ExternalLink size={11} aria-hidden="true" />
    </a>
  )
}

function Sources({ sources, output }: { sources: SourceRef[]; output: PrecheckOutput }) {
  if (!sources.length) return null
  return (
    <span className={styles.sources}>
      {sources.map((s) => (
        <Source key={s.id} source={s} output={output} />
      ))}
    </span>
  )
}

/** Teach the pre-check from a correction. It applies to this client at once; for every client of
 * this business nature it waits for a lead or admin (unless one is teaching it). */
function TeachForm({
  jobKey,
  item,
  kind: initialKind,
  natureLabel,
  onDone,
}: {
  jobKey: string
  item: string
  kind: LessonKind
  natureLabel: string
  onDone: () => void
}) {
  const teach = useTeachLesson(jobKey)
  const [kind, setKind] = useState<LessonKind>(initialKind)
  const [itemText, setItemText] = useState(item)
  const [note, setNote] = useState('')
  const [firmWide, setFirmWide] = useState(false)
  return (
    <form
      className={styles.teach}
      onSubmit={(e) => {
        e.preventDefault()
        teach.mutate({ kind, item: itemText, note, firm_wide: firmWide }, { onSuccess: onDone })
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
      <label>
        <span>Item</span>
        <input value={itemText} onChange={(e) => setItemText(e.target.value)} placeholder="e.g. Home office details" />
      </label>
      <label>
        <span>What the pre-check should do instead, and why</span>
        <textarea
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. Not needed when every property is run by a property manager: no home office is claimed."
        />
      </label>
      <label className={styles.check}>
        <input type="checkbox" checked={firmWide} onChange={(e) => setFirmWide(e.target.checked)} />
        <span>Apply to all {natureLabel.toLowerCase()} clients (a lead or admin approves it first)</span>
      </label>
      {teach.isError && (
        <div role="alert" className={styles.error}>
          {extractErrorMessage(teach.error)}
        </div>
      )}
      <div className={styles.teachActions}>
        <Button type="submit" variant="primary" size="sm" disabled={teach.isPending || note.trim().length < 5}>
          {teach.isPending ? 'Saving…' : 'Save lesson'}
        </Button>
        <Button type="button" variant="subtle" size="sm" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function ItemRow({
  item,
  output,
  jobKey,
  natureLabel,
  teachAs,
}: {
  item: PrecheckItem
  output: PrecheckOutput
  jobKey: string
  natureLabel: string
  teachAs: LessonKind
}) {
  const [teaching, setTeaching] = useState(false)
  const [taught, setTaught] = useState(false)
  return (
    <li className={styles.item}>
      <div className={styles.itemHead}>
        <span className={styles.itemTitle}>{item.item}</span>
        {!teaching && (
          <button type="button" className={styles.teachButton} onClick={() => setTeaching(true)} aria-label={`Correct: ${item.item}`}>
            <GraduationCap size={13} aria-hidden="true" /> {taught ? 'Lesson saved' : 'Correct this'}
          </button>
        )}
      </div>
      <p className={styles.reason}>{item.reason}</p>
      {item.documents.length > 0 && (
        <div className={styles.provided}>
          Provided by: <Sources sources={item.documents} output={output} />
        </div>
      )}
      <Sources sources={item.sources} output={output} />
      {item.flags.map((f) => (
        <span key={f} className={styles.flag}>
          <AlertTriangle size={11} aria-hidden="true" /> {FLAG_TEXT[f] ?? f}
        </span>
      ))}
      {teaching && (
        <TeachForm
          jobKey={jobKey}
          item={item.item}
          kind={teachAs}
          natureLabel={natureLabel}
          onDone={() => {
            setTeaching(false)
            setTaught(true)
          }}
        />
      )}
    </li>
  )
}

function grouped(items: PrecheckItem[]): [string, PrecheckItem[]][] {
  const groups = new Map<string, PrecheckItem[]>()
  for (const i of items) groups.set(i.group, [...(groups.get(i.group) ?? []), i])
  return [...groups.entries()]
}

function ItemList(props: { items: PrecheckItem[]; output: PrecheckOutput; jobKey: string; natureLabel: string; teachAs: LessonKind }) {
  return (
    <>
      {grouped(props.items).map(([group, rows]) => (
        <div key={group} className={styles.group}>
          <h4 className={styles.groupTitle}>{group}</h4>
          <ul className={styles.items}>
            {rows.map((i) => (
              <ItemRow key={i.item} {...props} item={i} />
            ))}
          </ul>
        </div>
      ))}
    </>
  )
}

/** Lessons waiting for a lead or admin to apply them to every client. */
function PendingLessons({ jobKey }: { jobKey: string }) {
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
            <p className={styles.reason}>{l.note}</p>
            <div className={styles.teachActions}>
              <Button size="sm" variant="primary" onClick={() => setStatus.mutate({ id: l.id, status: 'active' })}>
                Apply to all clients
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

/** The pre-check's result: the decision and its reason, the key documents, the business nature,
 * every item still needed (with its reason and sources), and the email to send. */
export function PrecheckResult({ output, jobKey }: { output: PrecheckOutput; jobKey: string }) {
  const nature = output.business_nature
  const natureLabel = nature?.label ?? 'similar'
  const [missedOpen, setMissedOpen] = useState(false)
  return (
    <div className={styles.result}>
      <section aria-labelledby="pc-key">
        <h3 id="pc-key" className={styles.sectionTitle}>
          Key documents
        </h3>
        <ul className={styles.keyDocs}>
          {output.key_documents.map((k) => (
            <li key={k.role}>
              {k.found ? <Check size={14} className={styles.pass} aria-label="Found" /> : <X size={14} className={styles.fail} aria-label="Missing" />}
              <span className={styles.keyLabel}>{k.label}</span>
              {k.files.map((f) => (
                <Source key={f.name} source={{ id: f.name, label: f.name, evidence_id: f.evidence_id }} output={output} />
              ))}
              {!k.found && <span className={styles.muted}>{k.note || 'Not in the folder'}</span>}
            </li>
          ))}
        </ul>
      </section>

      {nature && (
        <section aria-labelledby="pc-nature" className={styles.nature}>
          <h3 id="pc-nature" className={styles.sectionTitle}>
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

      <section aria-labelledby="pc-requests">
        <div className={styles.sectionHead}>
          <h3 id="pc-requests" className={styles.sectionTitle}>
            Requests to send ({output.requests.length})
          </h3>
          {nature && (
            <button type="button" className={styles.teachButton} onClick={() => setMissedOpen((v) => !v)}>
              <GraduationCap size={13} aria-hidden="true" /> Something was missed
            </button>
          )}
        </div>
        {missedOpen && <TeachForm jobKey={jobKey} item="" kind="missed" natureLabel={natureLabel} onDone={() => setMissedOpen(false)} />}
        {output.requests.length === 0 ? (
          <p className={styles.muted}>Nothing to request.</p>
        ) : (
          <ItemList items={output.requests} output={output} jobKey={jobKey} natureLabel={natureLabel} teachAs="not_needed" />
        )}
      </section>

      {output.provided.length > 0 && (
        <details className={styles.collapsible}>
          <summary>
            <ChevronDown size={14} aria-hidden="true" /> Already provided ({output.provided.length})
          </summary>
          <ItemList items={output.provided} output={output} jobKey={jobKey} natureLabel={natureLabel} teachAs="wrong_reason" />
        </details>
      )}
      {output.not_needed.length > 0 && (
        <details className={styles.collapsible}>
          <summary>
            <ChevronDown size={14} aria-hidden="true" /> Not needed ({output.not_needed.length})
          </summary>
          <ItemList items={output.not_needed} output={output} jobKey={jobKey} natureLabel={natureLabel} teachAs="wrong_reason" />
        </details>
      )}

      {output.preparer_notes.length > 0 && (
        <section aria-labelledby="pc-notes">
          <h3 id="pc-notes" className={styles.sectionTitle}>
            Notes for the preparer
          </h3>
          <ul className={styles.facts}>
            {output.preparer_notes.map((n) => (
              <li key={n.text}>
                {n.text} <Sources sources={n.sources} output={output} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {output.email.body && (
        <section aria-labelledby="pc-email" className={styles.email}>
          <div className={styles.sectionHead}>
            <h3 id="pc-email" className={styles.sectionTitle}>
              <Mail size={13} aria-hidden="true" /> Email to the client (drafted, not sent)
            </h3>
            <CopyButton value={`${output.email.subject}\n\n${output.email.body}`} label="email" />
          </div>
          <div className={styles.subject}>{output.email.subject}</div>
          <pre className={styles.body}>{output.email.body}</pre>
        </section>
      )}

      {output.lessons_applied.length > 0 && (
        <p className={styles.muted}>
          Lessons applied: {output.lessons_applied.map((l) => l.text).join(' · ')}
        </p>
      )}
      <PendingLessons jobKey={jobKey} />
    </div>
  )
}
