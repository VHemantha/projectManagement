import { format, parseISO } from 'date-fns'
import { type FormEvent, useState } from 'react'

import styles from './Coordinator.module.css'
import { leaveDays } from './leaveText'
import {
  type RuleInfo,
  useAddHoliday,
  useAgentActions,
  useAudit,
  useCases,
  useCoordinatorSettings,
  useDecideLeave,
  useHolidays,
  useLeave,
  usePolicies,
  useRemoveHoliday,
  useSchedules,
  useSetPolicy,
  useSetSchedule,
  useUpdateCoordinatorSettings,
} from '@/api/coordinator'
import { extractErrorMessage } from '@/api/errors'
import { Button, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const when = (iso: string) => format(parseISO(iso), 'd MMM yyyy, HH:mm')

/** The CEO's console for the AI project coordinator: master switches, rules, leave, working hours,
 * holidays, and the logs of what the agent did and who changed what. CEO only. */
export function CoordinatorConsolePage() {
  const role = useAuthStore((s) => s.user?.role)
  if (role !== 'ceo') {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Coordinator console</h1>
        <p className={styles.lead}>Only the CEO can open the coordinator console. You can chat with the Loca Coordinator in Messages.</p>
      </div>
    )
  }
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Coordinator console</h1>
      <p className={styles.lead}>
        The Loca Coordinator follows up jobs, hours and timesheets with the team in Messages and reports to you. Here you set its rules
        and controls; every change is logged.
      </p>
      <Tabs defaultValue="controls">
        <TabsList aria-label="Coordinator console">
          <TabsTrigger value="controls">Controls</TabsTrigger>
          <TabsTrigger value="cases">Follow-ups</TabsTrigger>
          <TabsTrigger value="rules">Rules</TabsTrigger>
          <TabsTrigger value="leave">Leave</TabsTrigger>
          <TabsTrigger value="hours">Working hours</TabsTrigger>
          <TabsTrigger value="holidays">Holidays</TabsTrigger>
          <TabsTrigger value="actions">Agent actions</TabsTrigger>
          <TabsTrigger value="audit">Audit log</TabsTrigger>
        </TabsList>
        <TabsContent value="controls"><Controls /></TabsContent>
        <TabsContent value="cases"><FollowUps /></TabsContent>
        <TabsContent value="rules"><Rules /></TabsContent>
        <TabsContent value="leave"><LeaveApprovals /></TabsContent>
        <TabsContent value="hours"><WorkingHours /></TabsContent>
        <TabsContent value="holidays"><Holidays /></TabsContent>
        <TabsContent value="actions"><Actions /></TabsContent>
        <TabsContent value="audit"><Audit /></TabsContent>
      </Tabs>
    </div>
  )
}

function Controls() {
  const { data } = useCoordinatorSettings()
  const update = useUpdateCoordinatorSettings()
  const [cap, setCap] = useState<string | null>(null)
  if (!data) return <Skeleton height={80} />
  return (
    <section className={styles.card} aria-label="Controls">
      {data.paused && (
        <p className={styles.banner} data-tone="danger" role="status">
          The coordinator is paused: it runs no checks and sends no messages.
        </p>
      )}
      {!data.paused && data.shadow_mode && (
        <p className={styles.banner} role="status">
          Shadow mode: every message the coordinator would send to the team comes to you instead, for review.
        </p>
      )}
      <div className={styles.toggles}>
        <label className={styles.toggle}>
          <input type="checkbox" checked={data.paused} disabled={update.isPending} onChange={(e) => update.mutate({ paused: e.target.checked })} />
          <span>
            Emergency pause
            <small>Stops all checks and messages at once.</small>
          </span>
        </label>
        <label className={styles.toggle}>
          <input type="checkbox" checked={data.shadow_mode} disabled={update.isPending} onChange={(e) => update.mutate({ shadow_mode: e.target.checked })} />
          <span>
            Shadow mode
            <small>Messages to the team come to you first. Turn off when you are happy with what it says.</small>
          </span>
        </label>
      </div>
      <form
        className={styles.form}
        style={{ marginTop: 12 }}
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          if (cap !== null) update.mutate({ daily_cost_cap_usd: Number(cap) }, { onSuccess: () => setCap(null) })
        }}
      >
        <label>
          Daily AI spending cap (US$)
          <input type="number" min={0} max={500} step={0.5} value={cap ?? data.daily_cost_cap_usd} onChange={(e) => setCap(e.target.value)} />
        </label>
        <label>
          Time zone
          <input value={data.timezone} readOnly />
        </label>
        <Button type="submit" size="sm" variant="secondary" disabled={cap === null || update.isPending}>
          Save
        </Button>
      </form>
      {update.isError && <p className={styles.error}>{extractErrorMessage(update.error)}</p>}
      {data.updated_by && <p className={styles.muted} style={{ marginTop: 8 }}>Last changed by {data.updated_by.display_name}, {when(data.updated_at)}.</p>}
    </section>
  )
}

const STATE_TONE: Record<string, string> = { asked: 'warning', answered: 'success', escalated: 'danger', resolved: '' }

function FollowUps() {
  const { data } = useCases()
  if (!data) return <Skeleton height={80} />
  return (
    <section className={styles.card} aria-label="Follow-ups">
      {data.cases.length === 0 ? (
        <p className={styles.muted}>Nothing is being followed up right now.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Job</th>
                <th scope="col">Person</th>
                <th scope="col">Matter</th>
                <th scope="col">Dates</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {data.cases.map((c) => (
                <tr key={c.id}>
                  <td>
                    {c.issue}
                    <small>{c.title}</small>
                  </td>
                  <td>{c.person.display_name}</td>
                  <td>
                    {c.kind_label}
                    {c.commitment && (
                      <small>
                        Said: {c.commitment.remaining_hours != null ? `${c.commitment.remaining_hours}h to go, ` : ''}
                        {c.commitment.eta_date ? `finish ${format(parseISO(c.commitment.eta_date), 'd MMM')}` : 'no date'}
                        {c.commitment.cause !== 'None given' ? ` — ${c.commitment.cause}` : ''}
                      </small>
                    )}
                  </td>
                  <td>
                    {c.due_date && `Due ${format(parseISO(c.due_date), 'd MMM')}`}
                    {c.revised_due && <small>Revised {format(parseISO(c.revised_due), 'd MMM')}</small>}
                  </td>
                  <td>
                    <span className={styles.chip} data-tone={STATE_TONE[c.state]}>
                      {c.state_label}
                    </span>
                    <small>
                      {c.asked} message{c.asked === 1 ? '' : 's'}
                      {c.escalated_to && `, escalated to ${c.escalated_to.display_name}`}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Rules() {
  const { data } = usePolicies()
  if (!data) return <Skeleton height={120} />
  const scoped = data.policies.filter((p) => p.active && p.scope !== 'company')
  return (
    <section className={styles.card} aria-label="Rules">
      <p className={styles.muted} style={{ marginBottom: 8 }}>
        The defaults come from AFIT&apos;s specification. A change takes effect at once and is kept as a new version; the old one stays
        on record.
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Rule</th>
              <th scope="col">Company-wide</th>
              <th scope="col" aria-label="Change" />
            </tr>
          </thead>
          <tbody>
            {data.rules.map((r) => (
              <RuleRow key={r.key} rule={r} history={data.policies.filter((p) => p.key === r.key && p.scope === 'company').length} />
            ))}
          </tbody>
        </table>
      </div>
      {scoped.length > 0 && (
        <>
          <h3 className={styles.cardTitle} style={{ marginTop: 16 }}>Overrides for a team, client, person or job</h3>
          <ul className={styles.muted}>
            {scoped.map((p) => (
              <li key={p.id}>
                {data.rules.find((r) => r.key === p.key)?.label ?? p.key}: {String(p.value)} — {p.scope} {p.scope_id}
                {p.expires_at && `, until ${when(p.expires_at)}`}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function RuleRow({ rule, history }: { rule: RuleInfo; history: number }) {
  const set = useSetPolicy()
  const [value, setValue] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const editing = value !== null
  const save = () =>
    set.mutate(
      { key: rule.key, value: rule.kind === 'number' ? Number(value) : (value as string), note },
      { onSuccess: () => (setValue(null), setNote('')) },
    )
  return (
    <tr>
      <td>
        {rule.label}
        <small>{rule.help}</small>
        {set.isError && <p className={styles.error}>{extractErrorMessage(set.error)}</p>}
      </td>
      <td>
        {editing ? (
          <span className={styles.form}>
            {rule.kind === 'choice' ? (
              <select aria-label={rule.label} value={value} onChange={(e) => setValue(e.target.value)}>
                {rule.choices.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            ) : (
              <input aria-label={rule.label} type={rule.kind === 'time' ? 'time' : 'number'} step="any" value={value}
                min={rule.minimum ?? undefined} max={rule.maximum ?? undefined} onChange={(e) => setValue(e.target.value)} />
            )}
            <input aria-label="Why" placeholder="Why (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          </span>
        ) : (
          <>
            <strong>{String(rule.current)}</strong>
            <small>{String(rule.current) === String(rule.default) ? 'default' : `default ${String(rule.default)}`}{history ? ` · ${history} version${history === 1 ? '' : 's'}` : ''}</small>
          </>
        )}
      </td>
      <td>
        {editing ? (
          <span className={styles.actions}>
            <Button size="sm" variant="primary" disabled={set.isPending} onClick={save}>
              Save
            </Button>
            <Button size="sm" variant="subtle" onClick={() => setValue(null)}>
              Cancel
            </Button>
          </span>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => setValue(String(rule.current))}>
            Change
          </Button>
        )}
      </td>
    </tr>
  )
}

function LeaveApprovals() {
  const { data } = useLeave()
  const decide = useDecideLeave()
  if (!data) return <Skeleton height={80} />
  const pending = data.leave.filter((r) => r.status === 'pending')
  const decided = data.leave.filter((r) => r.status !== 'pending').slice(0, 30)
  return (
    <section className={styles.card} aria-label="Leave approvals">
      <h3 className={styles.cardTitle}>Waiting for approval ({pending.length})</h3>
      {pending.length === 0 ? (
        <p className={styles.muted}>Nothing waiting.</p>
      ) : (
        <table className={styles.table}>
          <tbody>
            {pending.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.user.display_name}</strong>
                  <small>{r.kind_label}{r.note && ` — ${r.note}`}</small>
                </td>
                <td>
                  {leaveDays(r)}
                  {r.hours_per_day != null && <small>{r.hours_per_day} hours a day</small>}
                </td>
                <td>
                  <span className={styles.actions}>
                    <Button size="sm" variant="primary" disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, status: 'approved' })}>
                      Approve
                    </Button>
                    <Button size="sm" variant="secondary" disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, status: 'rejected' })}>
                      Reject
                    </Button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {decided.length > 0 && (
        <>
          <h3 className={styles.cardTitle} style={{ marginTop: 16 }}>Decided</h3>
          <table className={styles.table}>
            <tbody>
              {decided.map((r) => (
                <tr key={r.id}>
                  <td>{r.user.display_name}</td>
                  <td>{leaveDays(r)}</td>
                  <td>{r.kind_label}</td>
                  <td>
                    <span className={styles.chip} data-tone={r.status === 'approved' ? 'success' : 'danger'}>
                      {r.status_label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

function WorkingHours() {
  const { data } = useSchedules()
  if (!data) return <Skeleton height={80} />
  return (
    <section className={styles.card} aria-label="Working hours">
      <p className={styles.muted} style={{ marginBottom: 8 }}>
        Normal hours each weekday. The timesheet check expects these, less approved leave and public holidays (e.g. set part-time
        staff here).
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Person</th>
              {WEEKDAYS.map((d) => (
                <th key={d} scope="col">
                  {d}
                </th>
              ))}
              <th scope="col">Note</th>
              <th scope="col" aria-label="Save" />
            </tr>
          </thead>
          <tbody>
            {data.schedules.map((s) => (
              <ScheduleRowEdit key={s.user.id} userId={s.user.id} name={s.user.display_name} hours={s.hours} note={s.note} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ScheduleRowEdit({ userId, name, hours, note }: { userId: number; name: string; hours: number[]; note: string }) {
  const set = useSetSchedule()
  const [draft, setDraft] = useState(hours.map(String))
  const [text, setText] = useState(note)
  const changed = draft.some((h, i) => Number(h) !== hours[i]) || text !== note
  return (
    <tr>
      <td>{name}</td>
      {draft.map((h, i) => (
        <td key={i}>
          <input className={styles.hours} aria-label={`${name} ${WEEKDAYS[i]}`} type="number" min={0} max={24} step={0.5} value={h}
            onChange={(e) => setDraft(draft.map((x, j) => (j === i ? e.target.value : x)))} />
        </td>
      ))}
      <td>
        <input aria-label={`${name} note`} value={text} onChange={(e) => setText(e.target.value)} />
      </td>
      <td>
        <Button size="sm" variant="secondary" disabled={!changed || set.isPending}
          onClick={() => set.mutate({ userId, hours: draft.map(Number), note: text })}>
          Save
        </Button>
      </td>
    </tr>
  )
}

function Holidays() {
  const { data } = useHolidays()
  const add = useAddHoliday()
  const remove = useRemoveHoliday()
  const [form, setForm] = useState({ date: '', name: '' })
  if (!data) return <Skeleton height={80} />
  return (
    <section className={styles.card} aria-label="Holidays">
      <p className={styles.muted} style={{ marginBottom: 8 }}>
        New Zealand&apos;s national public holidays are loaded. Add your region&apos;s anniversary day and any office closures.
      </p>
      <form className={styles.form} onSubmit={(e) => (e.preventDefault(), add.mutate(form, { onSuccess: () => setForm({ date: '', name: '' }) }))}>
        <label>
          Date
          <input type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </label>
        <label className={styles.grow}>
          Name
          <input required value={form.name} placeholder="e.g. Auckland Anniversary Day" onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <Button type="submit" size="sm" variant="primary" disabled={add.isPending}>
          Add
        </Button>
      </form>
      <table className={styles.table} style={{ marginTop: 8 }}>
        <tbody>
          {data.holidays.map((h) => (
            <tr key={h.date}>
              <td>{format(parseISO(h.date), 'EEE d MMM yyyy')}</td>
              <td>{h.name}</td>
              <td>
                <Button size="sm" variant="subtle" disabled={remove.isPending} onClick={() => remove.mutate(h.date)}>
                  Remove
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Actions() {
  const { data } = useAgentActions()
  if (!data) return <Skeleton height={80} />
  return (
    <section className={styles.card} aria-label="Agent actions">
      {data.actions.length === 0 ? (
        <p className={styles.muted}>The coordinator has not done anything yet.</p>
      ) : (
        <table className={styles.table}>
          <tbody>
            {data.actions.map((a) => (
              <tr key={a.id}>
                <td>{when(a.created_at)}</td>
                <td>
                  {a.reason || a.trigger}
                  {a.issue && <small>{a.issue}</small>}
                </td>
                <td>{a.target?.display_name}</td>
                <td>{a.shadow && <span className={styles.chip} data-tone="warning">Shadow</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function Audit() {
  const { data } = useAudit()
  if (!data) return <Skeleton height={80} />
  return (
    <section className={styles.card} aria-label="Audit log">
      {data.entries.length === 0 ? (
        <p className={styles.muted}>No changes yet.</p>
      ) : (
        <table className={styles.table}>
          <tbody>
            {data.entries.map((e) => (
              <tr key={e.id}>
                <td>{when(e.created_at)}</td>
                <td>{e.actor?.display_name ?? 'System'}</td>
                <td>
                  {e.action}
                  {e.target && <small>{e.target}</small>}
                </td>
                <td>
                  <span className={styles.chip} data-tone={e.allowed ? 'success' : 'danger'}>
                    {e.allowed ? 'Done' : 'Refused'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
