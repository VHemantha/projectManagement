import { useState } from 'react'

import { useCompleteSprint } from '@/api/sprints'
import type { Sprint } from '@/api/types'
import { Button, Dialog, DialogContent } from '@/design-system'

interface CompleteSprintDialogProps {
  sprint: Sprint | null
  otherOpenSprints: Sprint[]
  onClose: () => void
}

export function CompleteSprintDialog({ sprint, otherOpenSprints, onClose }: CompleteSprintDialogProps) {
  const completeSprint = useCompleteSprint(sprint?.project_key ?? '')
  const [moveTo, setMoveTo] = useState<string>('backlog')

  const handleComplete = () => {
    if (!sprint) return
    completeSprint.mutate(
      { id: sprint.id, moveTo: moveTo === 'backlog' ? 'backlog' : Number(moveTo) },
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog open={!!sprint} onOpenChange={(next) => !next && onClose()}>
      {sprint && (
        <DialogContent title={`Complete ${sprint.name}`} maxWidth={440}>
          <p style={{ fontSize: 14, color: 'var(--tf-text-secondary)', marginBottom: 16 }}>
            Move incomplete issues to:
          </p>
          <select
            style={{
              width: '100%',
              height: 36,
              borderRadius: 4,
              border: '2px solid var(--tf-border)',
              padding: '0 12px',
              marginBottom: 20,
            }}
            value={moveTo}
            onChange={(e) => setMoveTo(e.target.value)}
          >
            <option value="backlog">Backlog</option>
            {otherOpenSprints.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button variant="subtle" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleComplete} disabled={completeSprint.isPending}>
              {completeSprint.isPending ? 'Completing…' : 'Complete sprint'}
            </Button>
          </div>
        </DialogContent>
      )}
    </Dialog>
  )
}
