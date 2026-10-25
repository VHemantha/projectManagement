import { type FormEvent, useState } from 'react'

import styles from './Coordinator.module.css'
import { leaveDays } from './leaveText'
import { type LeaveKind, type LeaveRow, useLeave, useRequestLeave, useWithdrawLeave } from '@/api/coordinator'
import { extractErrorMessage } from '@/api/errors'
import { Button, Skeleton } from '@/design-system'

const KINDS: { value: LeaveKind; label: string }[] = [
  { value: 'annual', label: 'Annual leave' },
  { value: 'sick', label: 'Sick leave' },
  { value: 'training', label: 'Training' },
  { value: 'other', label: 'Other' },
]
const TONE: Record<LeaveRow['status'], string> = { pending: 'warning', approved: 'success', rejected: 'danger' }

/** Leave: request it here; the CEO approves it. Approved leave is taken into account by the
 * coordination agent, so nobody is asked about timesheets or deadlines for days they are away. */
export function LeavePage() {
  const { data, isLoading } = useLeave()
  const request = useRequestLeave()
  const withdraw = useWithdrawLeave()
  const [form, setForm] = useState({ start_date: '', end_date: '', kind: 'annual' as LeaveKind, hours_per_day: '', note: '' })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    request.mutate(
      { ...form, end_date: form.end_date || form.start_date, hours_per_day: form.hours_per_day ? Number(form.hours_per_day) : null },
      { onSuccess: () => setForm({ start_date: '', end_date: '', kind: 'annual', hours_per_day: '', note: '' }) },
    )
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Leave</h1>
      <p className={styles.lead}>
        Request leave here. Once the CEO approves it, the Loca Coordinator will not ask you about timesheets or deadlines for those
        days.
      </p>
      <section className={styles.card} aria-label="Request leave">
        <h2 className={styles.cardTitle}>Request leave</h2>
        <form className={styles.form} onSubmit={submit}>
          <label>
            First day
            <input type="date" required value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
          </label>
          <label>
            Last day
            <input type="date" value={form.end_date} min={form.start_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
          </label>
          <label>
            Kind
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as LeaveKind })}>
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Hours a day (part day)
            <input type="number" min={0.5} max={24} step={0.5} placeholder="Whole day" value={form.hours_per_day}
              onChange={(e) => setForm({ ...form, hours_per_day: e.target.value })} />
          </label>
          <label className={styles.grow}>
            Note (optional)
            <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </label>
          <Button type="submit" variant="primary" size="sm" disabled={request.isPending || !form.start_date}>
            Request
          </Button>
        </form>
        {request.isError && <p className={styles.error}>{extractErrorMessage(request.error)}</p>}
      </section>
      <section className={styles.card} aria-label="Your leave">
        <h2 className={styles.cardTitle}>Your leave</h2>
        {isLoading ? (
          <Skeleton height={48} />
        ) : !data?.leave.length ? (
          <p className={styles.muted}>No leave requested yet.</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Days</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Status</th>
                  <th scope="col" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {data.leave.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {leaveDays(r)}
                      {r.hours_per_day != null && <small>{r.hours_per_day} hours a day</small>}
                      {r.note && <small>{r.note}</small>}
                    </td>
                    <td>{r.kind_label}</td>
                    <td>
                      <span className={styles.chip} data-tone={TONE[r.status]}>
                        {r.status_label}
                      </span>
                      {r.decided_by && <small>by {r.decided_by.display_name}</small>}
                    </td>
                    <td>
                      {r.status === 'pending' && (
                        <Button size="sm" variant="secondary" disabled={withdraw.isPending} onClick={() => withdraw.mutate(r.id)}>
                          Withdraw
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
