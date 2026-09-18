import { addMonths, differenceInCalendarDays, format, startOfMonth } from 'date-fns'
import { useEffect, useMemo, useRef, useState } from 'react'

import styles from './TimelinePage.module.css'
import { usePatchIssueField, useIssues } from '@/api/issues'
import type { IssueListItem } from '@/api/types'
import { useProjectContext } from '@/features/projects/useProjectContext'
import { useUiStore } from '@/store/uiStore'

function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    if (!ref.current) return
    const observer = new ResizeObserver((entries) => setWidth(entries[0].contentRect.width))
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])

  return [ref, width] as const
}

interface DragState {
  epic: IssueListItem
  mode: 'move' | 'resize-start' | 'resize-end'
  startX: number
  originalStart: Date
  originalEnd: Date
}

export function TimelinePage() {
  const { project } = useProjectContext()
  const { data: epicsPage, isLoading } = useIssues({ project: project.key, issue_type: 'Epic', page_size: 100 })
  const patchIssue = usePatchIssueField()
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const [trackRef, chartWidth] = useElementWidth<HTMLDivElement>()
  const [drag, setDrag] = useState<DragState | null>(null)
  const [previewDates, setPreviewDates] = useState<{ start: Date; end: Date } | null>(null)

  const epics = (epicsPage?.results ?? []).filter((e) => e.start_date && e.due_date)

  const { rangeStart, rangeEnd, months } = useMemo(() => {
    const now = new Date()
    let minDate = startOfMonth(now)
    let maxDate = addMonths(now, 3)
    for (const e of epics) {
      if (e.start_date && new Date(e.start_date) < minDate) minDate = startOfMonth(new Date(e.start_date))
      if (e.due_date && new Date(e.due_date) > maxDate) maxDate = new Date(e.due_date)
    }
    const monthList: Date[] = []
    let cursor = minDate
    while (cursor <= maxDate) {
      monthList.push(cursor)
      cursor = addMonths(cursor, 1)
    }
    return { rangeStart: minDate, rangeEnd: addMonths(maxDate, 1), months: monthList }
  }, [epics])

  const totalDays = Math.max(differenceInCalendarDays(rangeEnd, rangeStart), 1)
  const pxPerDay = chartWidth / totalDays

  const dateToX = (d: Date) => differenceInCalendarDays(d, rangeStart) * pxPerDay
  const xToDays = (px: number) => Math.round(px / pxPerDay)

  useEffect(() => {
    if (!drag) return
    const handleMove = (e: MouseEvent) => {
      const deltaDays = xToDays(e.clientX - drag.startX)
      let newStart = drag.originalStart
      let newEnd = drag.originalEnd
      if (drag.mode === 'move') {
        newStart = addDays(drag.originalStart, deltaDays)
        newEnd = addDays(drag.originalEnd, deltaDays)
      } else if (drag.mode === 'resize-start') {
        newStart = addDays(drag.originalStart, deltaDays)
        if (newStart >= newEnd) newStart = addDays(newEnd, -1)
      } else {
        newEnd = addDays(drag.originalEnd, deltaDays)
        if (newEnd <= newStart) newEnd = addDays(newStart, 1)
      }
      setPreviewDates({ start: newStart, end: newEnd })
    }
    const handleUp = () => {
      setPreviewDates((preview) => {
        if (preview && drag) {
          patchIssue.mutate({
            key: drag.epic.key,
            patch: {
              start_date: format(preview.start, 'yyyy-MM-dd'),
              due_date: format(preview.end, 'yyyy-MM-dd'),
            },
          })
        }
        return null
      })
      setDrag(null)
    }
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    return () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag])

  if (isLoading) return <div className={styles.page}>Loading…</div>

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Timeline</h1>
      {epics.length === 0 ? (
        <div className={styles.empty}>No epics with start/due dates yet. Set dates on an epic to see it here.</div>
      ) : (
        <div className={styles.chart}>
          <div className={styles.monthHeader}>
            {months.map((m) => (
              <div key={m.toISOString()} className={styles.monthCell}>
                {format(m, 'MMM yyyy')}
              </div>
            ))}
          </div>
          {epics.map((epic) => {
            const isDragging = drag?.epic.id === epic.id
            const start = isDragging && previewDates ? previewDates.start : new Date(epic.start_date!)
            const end = isDragging && previewDates ? previewDates.end : new Date(epic.due_date!)
            const left = dateToX(start)
            const width = Math.max(dateToX(end) - left, 12)

            return (
              <div className={styles.row} key={epic.id}>
                <div className={styles.rowLabel} onClick={() => openIssueModal(epic.key)}>
                  <span
                    style={{ width: 8, height: 8, borderRadius: '50%', background: epic.epic?.epic_color ?? '#8777D9', flexShrink: 0 }}
                  />
                  {epic.summary}
                </div>
                <div className={styles.track} ref={epic === epics[0] ? trackRef : undefined}>
                  <div
                    className={styles.bar}
                    style={{ left, width, background: epic.epic?.epic_color ?? '#8777D9' }}
                    onMouseDown={(e) => {
                      setDrag({
                        epic,
                        mode: 'move',
                        startX: e.clientX,
                        originalStart: new Date(epic.start_date!),
                        originalEnd: new Date(epic.due_date!),
                      })
                    }}
                  >
                    {epic.key}
                    <span
                      className={`${styles.handle} ${styles.handleLeft}`}
                      onMouseDown={(e) => {
                        e.stopPropagation()
                        setDrag({
                          epic,
                          mode: 'resize-start',
                          startX: e.clientX,
                          originalStart: new Date(epic.start_date!),
                          originalEnd: new Date(epic.due_date!),
                        })
                      }}
                    />
                    <span
                      className={`${styles.handle} ${styles.handleRight}`}
                      onMouseDown={(e) => {
                        e.stopPropagation()
                        setDrag({
                          epic,
                          mode: 'resize-end',
                          startX: e.clientX,
                          originalStart: new Date(epic.start_date!),
                          originalEnd: new Date(epic.due_date!),
                        })
                      }}
                    />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function addDays(d: Date, days: number) {
  const copy = new Date(d)
  copy.setDate(copy.getDate() + days)
  return copy
}
