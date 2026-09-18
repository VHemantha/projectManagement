import { addDays, format } from 'date-fns'
import { type FormEvent, useState } from 'react'

import { extractErrorMessage } from '@/api/errors'
import { useStartSprint } from '@/api/sprints'
import type { Sprint } from '@/api/types'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

interface StartSprintDialogProps {
  sprint: Sprint | null
  onClose: () => void
}

export function StartSprintDialog({ sprint, onClose }: StartSprintDialogProps) {
  const startSprint = useStartSprint(sprint?.project_key ?? '')
  const today = format(new Date(), 'yyyy-MM-dd')
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(format(addDays(new Date(), 14), 'yyyy-MM-dd'))
  const [goal, setGoal] = useState(sprint?.goal ?? '')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!sprint) return
    startSprint.mutate(
      { id: sprint.id, start_date: startDate, end_date: endDate, goal },
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog open={!!sprint} onOpenChange={(next) => !next && onClose()}>
      {sprint && (
        <DialogContent title={`Start ${sprint.name}`} maxWidth={440}>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {startSprint.isError && (
              <div style={{ color: 'var(--tf-danger)', fontSize: 13 }}>{extractErrorMessage(startSprint.error)}</div>
            )}
            <div style={{ display: 'flex', gap: 12 }}>
              <Input
                id="ss-start"
                label="Start date"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
              <Input
                id="ss-end"
                label="End date"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
            <Input id="ss-goal" label="Sprint goal" value={goal} onChange={(e) => setGoal(e.target.value)} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button type="button" variant="subtle" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={startSprint.isPending}>
                {startSprint.isPending ? 'Starting…' : 'Start'}
              </Button>
            </div>
          </form>
        </DialogContent>
      )}
    </Dialog>
  )
}
