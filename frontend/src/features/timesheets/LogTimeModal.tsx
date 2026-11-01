import { useEffect, useState } from 'react'

import { extractErrorMessage } from '@/api/errors'
import { useCreateTimeEntry, useOnBehalfPeople, useUpdateTimeEntry } from '@/api/timesheets'
import { useIssues } from '@/api/issues'
import type { TimeEntry } from '@/api/types'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

interface LogTimeModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultDate: string
  defaultIssueId?: number | null
  existingEntry?: TimeEntry | null
  projectKey?: string
}

export function LogTimeModal({
  open,
  onOpenChange,
  defaultDate,
  defaultIssueId,
  existingEntry,
  projectKey,
}: LogTimeModalProps) {
  const [workDate, setWorkDate] = useState(defaultDate)
  const [hours, setHours] = useState('')
  const [description, setDescription] = useState('')
  const [billable, setBillable] = useState(true)
  const [issueSearch, setIssueSearch] = useState('')
  const [issueId, setIssueId] = useState<number | null>(defaultIssueId ?? null)
  // Logging for someone else, e.g. a team lead entering the time of a person who is away
  // (AFIT, 1 Nov 2026). Offered only to those who lead someone.
  const [onBehalf, setOnBehalf] = useState(false)
  const [personId, setPersonId] = useState('')
  const { data: people } = useOnBehalfPeople(open && !existingEntry)
  const { data: issueResults } = useIssues({ project: projectKey, search: issueSearch, page_size: 6 }, issueSearch.length >= 2)
  const createEntry = useCreateTimeEntry()
  const updateEntry = useUpdateTimeEntry()

  useEffect(() => {
    if (open) {
      setWorkDate(existingEntry?.work_date ?? defaultDate)
      setHours(existingEntry ? String(existingEntry.duration_seconds / 3600) : '')
      setDescription(existingEntry?.description ?? '')
      setBillable(existingEntry?.is_billable ?? true)
      setIssueId(existingEntry?.issue?.id ?? defaultIssueId ?? null)
      setIssueSearch('')
      setOnBehalf(false)
      setPersonId('')
    }
  }, [open, existingEntry, defaultDate, defaultIssueId])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const hoursNum = Number(hours)
    if (!hoursNum || hoursNum <= 0) return
    if (onBehalf && !personId) return

    if (existingEntry) {
      updateEntry.mutate(
        { id: existingEntry.id, hours: hoursNum, description, is_billable: billable, work_date: workDate },
        { onSuccess: () => onOpenChange(false) },
      )
    } else {
      createEntry.mutate(
        {
          issue_id: issueId,
          hours: hoursNum,
          description,
          is_billable: billable,
          work_date: workDate,
          ...(onBehalf && personId ? { user_id: Number(personId) } : {}),
        },
        { onSuccess: () => onOpenChange(false) },
      )
    }
  }

  const isPending = createEntry.isPending || updateEntry.isPending
  const error = createEntry.error ?? updateEntry.error
  const canLogForOthers = !existingEntry && (people?.length ?? 0) > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={existingEntry ? 'Edit time entry' : 'Log time'} maxWidth={420}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {canLogForOthers && (
            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <input type="checkbox" checked={onBehalf} onChange={(e) => setOnBehalf(e.target.checked)} />
                Log for someone else (e.g. someone who is away)
              </label>
              {onBehalf && (
                <select
                  aria-label="Person"
                  required
                  value={personId}
                  onChange={(e) => setPersonId(e.target.value)}
                  style={{ width: '100%', height: 36, borderRadius: 4, border: '2px solid var(--tf-border)', padding: '0 8px', marginTop: 6 }}
                >
                  <option value="">Choose the person…</option>
                  {people?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.display_name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {!existingEntry && (
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Task (optional)</label>
              {issueId ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                  Selected issue #{issueId}
                  <Button type="button" variant="subtle" size="sm" onClick={() => setIssueId(null)}>
                    Clear
                  </Button>
                </div>
              ) : (
                <>
                  <input
                    placeholder="Search by key or summary…"
                    value={issueSearch}
                    onChange={(e) => setIssueSearch(e.target.value)}
                    style={{ width: '100%', height: 36, borderRadius: 4, border: '2px solid var(--tf-border)', padding: '0 10px' }}
                  />
                  {issueResults && issueResults.results.length > 0 && (
                    <div style={{ border: '1px solid var(--tf-border)', borderRadius: 4, marginTop: 4 }}>
                      {issueResults.results.map((r) => (
                        <div
                          key={r.id}
                          style={{ padding: '6px 8px', cursor: 'pointer', fontSize: 13 }}
                          onClick={() => {
                            setIssueId(r.id)
                            setIssueSearch('')
                          }}
                        >
                          {r.key} — {r.summary}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          <div style={{ display: 'flex', gap: 12 }}>
            <Input id="lt-date" label="Date" type="date" value={workDate} onChange={(e) => setWorkDate(e.target.value)} />
            <Input
              id="lt-hours"
              label="Hours"
              type="number"
              step="0.25"
              min="0.25"
              required
              value={hours}
              onChange={(e) => setHours(e.target.value)}
            />
          </div>

          <Input id="lt-description" label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <input type="checkbox" checked={billable} onChange={(e) => setBillable(e.target.checked)} />
            Billable
          </label>

          {error && (
            <p role="alert" style={{ margin: 0, fontSize: 12, color: 'var(--tf-danger)' }}>
              {extractErrorMessage(error, 'The time could not be saved.')}
            </p>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!hours || isPending || (onBehalf && !personId)}>
              {isPending ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
