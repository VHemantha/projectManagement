import { format } from 'date-fns'
import { ArrowLeft, Check, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './TimesheetApprovalInboxPage.module.css'
import { useApproveTimesheet, useRejectTimesheet, useTimesheets } from '@/api/timesheets'
import type { Timesheet } from '@/api/types'
import { Avatar, Button, Dialog, DialogContent, Input, Skeleton } from '@/design-system'

function RejectDialog({ timesheet, onOpenChange }: { timesheet: Timesheet | null; onOpenChange: (v: boolean) => void }) {
  const [note, setNote] = useState('')
  const rejectTimesheet = useRejectTimesheet()

  return (
    <Dialog open={!!timesheet} onOpenChange={onOpenChange}>
      {timesheet && (
        <DialogContent title={`Reject ${timesheet.user.display_name}'s timesheet`} maxWidth={420}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Input
              id="reject-note"
              label="Reason (required)"
              required
              autoFocus
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button variant="subtle" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={!note.trim() || rejectTimesheet.isPending}
                onClick={() =>
                  rejectTimesheet.mutate(
                    { id: timesheet.id, note: note.trim() },
                    { onSuccess: () => onOpenChange(false) },
                  )
                }
              >
                Reject
              </Button>
            </div>
          </div>
        </DialogContent>
      )}
    </Dialog>
  )
}

export function TimesheetApprovalInboxPage() {
  const { data: timesheets, isLoading } = useTimesheets(true)
  const approveTimesheet = useApproveTimesheet()
  const [rejecting, setRejecting] = useState<Timesheet | null>(null)

  return (
    <div className={styles.page}>
      <Link to="/timesheets" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, marginBottom: 12 }}>
        <ArrowLeft size={13} /> My timesheet
      </Link>
      <h1 className={styles.title}>Timesheets to review</h1>
      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[0, 1, 2].map((row) => (
            <div key={row} className={styles.row}>
              <Skeleton width={32} height={32} style={{ borderRadius: '50%' }} />
              <div style={{ flex: 1 }}>
                <Skeleton width={140} height={13} style={{ marginBottom: 6 }} />
                <Skeleton width={100} height={11} />
              </div>
              <Skeleton width={40} height={13} />
            </div>
          ))}
        </div>
      ) : !timesheets || timesheets.length === 0 ? (
        <div className={styles.empty}>Nothing waiting for your approval.</div>
      ) : (
        timesheets.map((t) => (
          <div key={t.id} className={styles.row}>
            <Avatar name={t.user.display_name} src={t.user.avatar} size={32} />
            <div>
              <div className={styles.name}>{t.user.display_name}</div>
              <div className={styles.period}>
                {format(new Date(t.period_start), 'MMM d')} – {format(new Date(t.period_end), 'MMM d, yyyy')}
              </div>
            </div>
            <span className={styles.hours}>{t.total_hours}h</span>
            <div className={styles.actions}>
              <Button variant="subtle" size="sm" iconOnly aria-label="Reject" onClick={() => setRejecting(t)}>
                <X size={14} />
              </Button>
              <Button
                variant="primary"
                size="sm"
                iconOnly
                aria-label="Approve"
                onClick={() => approveTimesheet.mutate(t.id)}
              >
                <Check size={14} />
              </Button>
            </div>
          </div>
        ))
      )}
      <RejectDialog timesheet={rejecting} onOpenChange={(v) => !v && setRejecting(null)} />
    </div>
  )
}
