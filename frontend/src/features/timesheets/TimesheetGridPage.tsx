import { addDays, addWeeks, format, startOfWeek, subWeeks } from 'date-fns'
import { BarChart3, ChevronLeft, ChevronRight, ClipboardCheck, Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './TimesheetGridPage.module.css'
import { LogTimeModal } from './LogTimeModal'
import { useGetOrCreateTimesheet, useSubmitTimesheet, useTimeEntries } from '@/api/timesheets'
import type { TimeEntry, Timesheet } from '@/api/types'
import { Button, IssueKey, Skeleton } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

const STATUS_CLASS: Record<string, string> = {
  draft: styles.statusDraft,
  submitted: styles.statusSubmitted,
  approved: styles.statusApproved,
  rejected: styles.statusRejected,
}

interface RowGroup {
  key: string
  label: string
  issueId: number | null
  entriesByDate: Map<string, TimeEntry[]>
}

export function TimesheetGridPage() {
  const currentUser = useAuthStore((s) => s.user)
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }))
  const [timesheet, setTimesheet] = useState<Timesheet | null>(null)
  const [modalState, setModalState] = useState<{ date: string; issueId: number | null; entry: TimeEntry | null } | null>(null)

  const weekEnd = addDays(weekStart, 6)
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
  const periodStart = format(weekStart, 'yyyy-MM-dd')
  const periodEnd = format(weekEnd, 'yyyy-MM-dd')

  const getOrCreateTimesheet = useGetOrCreateTimesheet()
  const submitTimesheet = useSubmitTimesheet()

  useEffect(() => {
    setTimesheet(null)
    getOrCreateTimesheet.mutate(
      { period_start: periodStart, period_end: periodEnd },
      { onSuccess: setTimesheet },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodStart, periodEnd])

  const { data: entries, isLoading: entriesLoading } = useTimeEntries(
    { user: currentUser?.id, date_from: periodStart, date_to: periodEnd, page_size: 500 },
    !!currentUser,
  )

  const rows = useMemo<RowGroup[]>(() => {
    const groups = new Map<string, RowGroup>()
    for (const entry of entries ?? []) {
      const key = entry.issue ? `issue-${entry.issue.id}` : 'general'
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          label: entry.issue ? `${entry.issue.key} ${entry.issue.summary}` : 'General (no task)',
          issueId: entry.issue?.id ?? null,
          entriesByDate: new Map(),
        })
      }
      const group = groups.get(key)!
      const list = group.entriesByDate.get(entry.work_date) ?? []
      list.push(entry)
      group.entriesByDate.set(entry.work_date, list)
    }
    return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label))
  }, [entries])

  const hoursFor = (list: TimeEntry[] | undefined) =>
    !list ? 0 : list.reduce((sum, e) => sum + e.duration_seconds, 0) / 3600

  const dayTotal = (date: string) =>
    rows.reduce((sum, row) => sum + hoursFor(row.entriesByDate.get(date)), 0)

  const rowTotal = (row: RowGroup) =>
    weekDays.reduce((sum, d) => sum + hoursFor(row.entriesByDate.get(format(d, 'yyyy-MM-dd'))), 0)

  const grandTotal = rows.reduce((sum, row) => sum + rowTotal(row), 0)
  const isLocked = timesheet?.status === 'submitted' || timesheet?.status === 'approved'

  const openCell = (dateStr: string, issueId: number | null, list: TimeEntry[] | undefined) => {
    if (isLocked) return
    setModalState({ date: dateStr, issueId, entry: list?.[0] ?? null })
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Timesheet</h1>
        <div className={styles.weekNav}>
          <Button variant="subtle" size="sm" iconOnly onClick={() => setWeekStart((d) => subWeeks(d, 1))}>
            <ChevronLeft size={14} />
          </Button>
          <span className={styles.weekLabel}>
            {format(weekStart, 'MMM d')} – {format(weekEnd, 'MMM d, yyyy')}
          </span>
          <Button variant="subtle" size="sm" iconOnly onClick={() => setWeekStart((d) => addWeeks(d, 1))}>
            <ChevronRight size={14} />
          </Button>
        </div>
        {timesheet && (
          <span className={`${styles.statusBadge} ${STATUS_CLASS[timesheet.status]}`}>{timesheet.status}</span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Link to="/timesheets/reports">
            <Button variant="secondary" size="sm">
              <BarChart3 size={14} /> Time reports
            </Button>
          </Link>
          <Link to="/timesheets/review">
            <Button variant="secondary" size="sm">
              <ClipboardCheck size={14} /> Review inbox
            </Button>
          </Link>
          <Button
            variant="primary"
            size="sm"
            disabled={isLocked || rows.length === 0 || submitTimesheet.isPending}
            onClick={() => timesheet && submitTimesheet.mutate(timesheet.id, { onSuccess: setTimesheet })}
          >
            {isLocked ? 'Submitted' : 'Submit for approval'}
          </Button>
        </div>
      </div>

      {timesheet?.status === 'rejected' && timesheet.reviewer_note && (
        <div className={styles.reviewerNote}>Rejected: {timesheet.reviewer_note}</div>
      )}

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Task</th>
            {weekDays.map((d) => (
              <th key={d.toISOString()}>
                {format(d, 'EEE')}
                <br />
                {format(d, 'MMM d')}
              </th>
            ))}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {entriesLoading && (
            <tr>
              <td colSpan={9} style={{ padding: '10px 12px' }}>
                <Skeleton height={12} width="60%" />
              </td>
            </tr>
          )}
          {!entriesLoading && rows.length === 0 && (
            <tr>
              <td colSpan={9} className={styles.empty}>
                No time logged this week yet.
              </td>
            </tr>
          )}
          {rows.map((row) => (
            <tr key={row.key}>
              <td>
                <div className={styles.rowLabel}>
                  {row.issueId ? <IssueKey value={row.label.split(' ')[0]} /> : null}
                  <span>{row.issueId ? row.label.slice(row.label.indexOf(' ') + 1) : row.label}</span>
                </div>
              </td>
              {weekDays.map((d) => {
                const dateStr = format(d, 'yyyy-MM-dd')
                const list = row.entriesByDate.get(dateStr)
                const hours = hoursFor(list)
                return (
                  <td key={dateStr}>
                    <div
                      className={`${styles.cell} ${!hours ? styles.empty : ''} ${isLocked ? styles.locked : ''}`}
                      onClick={() => openCell(dateStr, row.issueId, list)}
                    >
                      {hours ? hours.toFixed(2) : '–'}
                    </div>
                  </td>
                )
              })}
              <td className={styles.totalCell}>{rowTotal(row).toFixed(2)}</td>
            </tr>
          ))}
          <tr className={styles.totalsRow}>
            <td>Total</td>
            {weekDays.map((d) => (
              <td key={d.toISOString()}>{dayTotal(format(d, 'yyyy-MM-dd')).toFixed(2)}</td>
            ))}
            <td>{grandTotal.toFixed(2)}</td>
          </tr>
        </tbody>
      </table>

      {!isLocked && (
        <div style={{ marginTop: 16 }}>
          <Button variant="secondary" size="sm" onClick={() => openCell(format(new Date(), 'yyyy-MM-dd'), null, undefined)}>
            <Plus size={14} /> Log time
          </Button>
        </div>
      )}

      {modalState && (
        <LogTimeModal
          open={!!modalState}
          onOpenChange={(open) => !open && setModalState(null)}
          defaultDate={modalState.date}
          defaultIssueId={modalState.issueId}
          existingEntry={modalState.entry}
        />
      )}
    </div>
  )
}
