import { History, Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'

import styles from './AiRulesPage.module.css'
import { extractErrorMessage } from '@/api/errors'
import {
  type PolicyInput,
  type PolicyLibrary,
  type PolicyScope,
  type PrecheckPolicy,
  useDeletePolicy,
  usePolicies,
  usePolicy,
  usePolicyFeedback,
  useSavePolicy,
} from '@/api/precheck'
import { Button, Skeleton } from '@/design-system'

const SCOPE_HINT: Record<PolicyScope, string> = {
  client: 'Every task of one client (a sub-workspace, e.g. RWCA).',
  group: "Every task in one client group (the task's group, e.g. Lummis group).",
  location: "Every task whose pre-check settings give this location (e.g. Auckland).",
  all: 'Every task.',
}

/** Write or edit a pre-check policy: who it is for, the type of check, and what the pre-check should do. */
export function PolicyForm({ library, policy, onDone }: { library: PolicyLibrary; policy?: PrecheckPolicy; onDone: () => void }) {
  const save = useSavePolicy()
  const [scope, setScope] = useState<PolicyScope>(policy?.scope ?? 'client')
  const [clientId, setClientId] = useState<string>(policy?.client ? String(policy.client.id) : '')
  const [group, setGroup] = useState(policy?.group ?? '')
  const [location, setLocation] = useState(policy?.location ?? '')
  const [checkType, setCheckType] = useState(policy?.precheck_type ?? '')
  const [title, setTitle] = useState(policy?.title ?? '')
  const [text, setText] = useState(policy?.text ?? '')
  const target = scope === 'client' ? clientId : scope === 'group' ? group.trim() : scope === 'location' ? location.trim() : 'all'
  const payload: PolicyInput = {
    scope,
    client_id: scope === 'client' && clientId ? Number(clientId) : null,
    group: scope === 'group' ? group.trim() : '',
    location: scope === 'location' ? location.trim() : '',
    precheck_type: checkType,
    title: title.trim(),
    text: text.trim(),
  }
  return (
    <form
      className={styles.form}
      aria-label={policy ? `Edit ${policy.title}` : 'New policy'}
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate({ ...payload, id: policy?.id }, { onSuccess: onDone })
      }}
    >
      <div className={styles.row}>
        <label>
          <span>Applies to</span>
          <select value={scope} onChange={(e) => setScope(e.target.value as PolicyScope)}>
            {library.scopes.map((s) => (
              <option key={s.value} value={s.value}>
                {s.value === 'all' ? 'Every task' : `One ${s.label.toLowerCase()}`}
              </option>
            ))}
          </select>
        </label>
        {scope === 'client' && (
          <label>
            <span>Client</span>
            <select value={clientId} onChange={(e) => setClientId(e.target.value)}>
              <option value="">Choose…</option>
              {library.clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {scope === 'group' && (
          <label>
            <span>Group</span>
            <input value={group} onChange={(e) => setGroup(e.target.value)} list="policy-groups" maxLength={100} placeholder="e.g. Lummis group" />
            <datalist id="policy-groups">
              {library.groups.map((g) => (
                <option key={g} value={g} />
              ))}
            </datalist>
          </label>
        )}
        {scope === 'location' && (
          <label>
            <span>Location</span>
            <input value={location} onChange={(e) => setLocation(e.target.value)} list="policy-locations" maxLength={100} placeholder="e.g. Auckland" />
            <datalist id="policy-locations">
              {library.locations.map((l) => (
                <option key={l} value={l} />
              ))}
            </datalist>
          </label>
        )}
        <label>
          <span>Type of check</span>
          <select value={checkType} onChange={(e) => setCheckType(e.target.value)}>
            <option value="">Every type of check</option>
            {library.precheck_types.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className={styles.hint}>{SCOPE_HINT[scope]}</p>
      <label>
        <span>Title</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={150} placeholder="e.g. Sold rentals: settlement statement only" />
      </label>
      <label>
        <span>What the pre-check should do</span>
        <textarea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={2000}
          placeholder="e.g. When a rental property was sold during the year, do not ask for the full year's council rates: ask only for the settlement statement, which shows the rates apportionment."
        />
      </label>
      <p className={styles.hint}>
        After each pre-check, the AI checks every point against the policies that apply to the task and changes the result to follow them. Each
        change says which policy made it.
      </p>
      {save.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(save.error)}
        </p>
      )}
      <div className={styles.actions}>
        <Button type="button" variant="subtle" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={save.isPending || !target || !payload.title || !payload.text}>
          {save.isPending ? 'Saving…' : policy ? 'Save changes' : 'Save policy'}
        </Button>
      </div>
    </form>
  )
}

/** Feedback on a policy: the AI rewrites the policy from it, keeping the old wording in the history. */
export function PolicyFeedbackForm({ policyId, task, context, onDone }: { policyId: number; task?: string; context?: string; onDone?: () => void }) {
  const send = usePolicyFeedback()
  const [text, setText] = useState('')
  const sent = send.data
  return (
    <form
      className={styles.feedback}
      aria-label="Feedback on the policy"
      onSubmit={(e) => {
        e.preventDefault()
        send.mutate({ id: policyId, text: text.trim(), task, context }, { onSuccess: () => setText('') })
      }}
    >
      <label>
        <span>What should change in this policy?</span>
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000}
          placeholder="e.g. This should not apply when the property was sold during the year." />
      </label>
      {send.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(send.error)}
        </p>
      )}
      {sent && (
        <p role="status" className={styles.hint}>
          {sent.status === 'failed' ? sent.summary : 'Thank you. The AI is revising the policy; the next pre-check uses the new wording.'}
        </p>
      )}
      <div className={styles.actions}>
        {onDone && (
          <Button type="button" variant="subtle" size="sm" onClick={onDone}>
            Close
          </Button>
        )}
        <Button type="submit" variant="primary" size="sm" disabled={send.isPending || text.trim().length < 3}>
          <Sparkles size={13} /> {send.isPending ? 'Sending…' : 'Revise the policy'}
        </Button>
      </div>
    </form>
  )
}

function PolicyCard({ policy, library }: { policy: PrecheckPolicy; library: PolicyLibrary }) {
  const [mode, setMode] = useState<'view' | 'edit' | 'feedback' | 'history'>('view')
  const save = useSavePolicy()
  const remove = useDeletePolicy()
  const [confirming, setConfirming] = useState(false)
  // The full record (history, feedback) only once it is opened.
  const { data: full } = usePolicy(mode === 'history' || mode === 'feedback' ? policy.id : null)
  if (mode === 'edit') return <PolicyForm library={library} policy={policy} onDone={() => setMode('view')} />
  return (
    <li className={styles.rule} data-status={policy.active ? 'active' : 'disabled'}>
      <div className={styles.ruleHead}>
        <span className={styles.ruleTitle}>{policy.title}</span>
        <span className={styles.status}>{policy.active ? 'Active' : 'Switched off'}</span>
      </div>
      <div className={styles.tags}>
        <span className={styles.tag}>{policy.scope_label}</span>
        <span className={styles.tag}>{policy.precheck_type_label}</span>
        {policy.version > 1 && <span className={styles.tag}>Version {policy.version}</span>}
      </div>
      <p className={styles.note}>{policy.text}</p>
      <p className={styles.muted}>
        {policy.created_by || 'Someone'}
        {policy.updated_by && policy.updated_by !== policy.created_by ? ` · last changed by ${policy.updated_by}` : ''} ·{' '}
        {new Date(policy.updated_at).toLocaleDateString()}
      </p>
      {mode === 'feedback' && (
        <>
          {full?.feedback?.[0] && (
            <p className={styles.hint} role="status">
              Latest feedback ({full.feedback[0].by}): “{full.feedback[0].text}” —{' '}
              {full.feedback[0].status === 'revising' ? 'the AI is revising the policy…' : full.feedback[0].summary}
            </p>
          )}
          <PolicyFeedbackForm policyId={policy.id} onDone={() => setMode('view')} />
        </>
      )}
      {mode === 'history' && (
        <div className={styles.history} aria-label="Earlier wordings">
          {!full ? (
            <Skeleton height={40} />
          ) : full.history.length === 0 ? (
            <p className={styles.hint}>No earlier wordings.</p>
          ) : (
            <ol>
              {[...full.history].reverse().map((h) => (
                <li key={h.version}>
                  <strong>Version {h.version}</strong> · {h.changed_by} · {new Date(h.changed_at).toLocaleDateString()} — {h.why}
                  <div className={styles.muted}>{h.text}</div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => setMode(mode === 'history' ? 'view' : 'history')}>
          <History size={13} /> History
        </Button>
        <Button size="sm" variant="subtle" onClick={() => setMode(mode === 'feedback' ? 'view' : 'feedback')}>
          <Sparkles size={13} /> Feedback
        </Button>
        {policy.can_change && (
          <>
            <Button size="sm" variant="subtle" onClick={() => setMode('edit')}>
              Edit
            </Button>
            <Button size="sm" variant="subtle" disabled={save.isPending} onClick={() => save.mutate({ id: policy.id, active: !policy.active })}>
              {policy.active ? 'Switch off' : 'Switch on'}
            </Button>
            {confirming ? (
              <Button size="sm" variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(policy.id)}>
                Delete for good?
              </Button>
            ) : (
              <Button size="sm" variant="subtle" onClick={() => setConfirming(true)}>
                Delete
              </Button>
            )}
          </>
        )}
      </div>
    </li>
  )
}

/** The firm's pre-check policies (AFIT, 20 Nov 2026): the accountants' standards for what a pre-check asks
 * for, for a client, a client group, a location or every task. */
export function PoliciesPanel() {
  const [q, setQ] = useState('')
  const [scope, setScope] = useState('')
  const [adding, setAdding] = useState(false)
  const { data, isLoading, isError } = usePolicies({ q: q || undefined, scope: scope || undefined })
  return (
    <>
      <div className={styles.header}>
        <p className={styles.lead}>
          The firm&apos;s standards for what a pre-check asks for. After each pre-check, the AI checks every point against the policies for that
          task&apos;s client, group and location, and changes the result to follow them.
        </p>
        {!adding && data && (
          <Button variant="primary" onClick={() => setAdding(true)}>
            <Plus size={14} /> New policy
          </Button>
        )}
      </div>
      {adding && data && <PolicyForm library={data} onDone={() => setAdding(false)} />}
      <div className={styles.filters}>
        <input type="search" placeholder="Search policies…" aria-label="Search policies" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Applies to" value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="">Any client, group or location</option>
          <option value="client">Client policies</option>
          <option value="group">Group policies</option>
          <option value="location">Location policies</option>
          <option value="all">Policies for every task</option>
        </select>
      </div>
      {isLoading ? (
        <Skeleton height={120} />
      ) : isError || !data ? (
        <p className={styles.error}>The policies could not be loaded.</p>
      ) : data.policies.length === 0 ? (
        <p className={styles.muted}>No policies yet. Write one and every later pre-check it applies to will follow it.</p>
      ) : (
        <ul className={styles.list} aria-label="Policies">
          {data.policies.map((p) => (
            <PolicyCard key={p.id} policy={p} library={data} />
          ))}
        </ul>
      )}
    </>
  )
}
