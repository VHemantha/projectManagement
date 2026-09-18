import { Clock, Square } from 'lucide-react'

import { useRunningTimer, useStartTimer, useStopTimer } from '@/api/timesheets'
import { Button } from '@/design-system'

interface TimerButtonProps {
  issueId: number
  size?: 'sm' | 'md'
  iconOnly?: boolean
}

/** Starts/stops a timer for one issue. Used identically in the issue detail header,
 * board card hover, and table row hover — one control, one API call, one place the
 * global nav widget reads from. */
export function TimerButton({ issueId, size = 'sm', iconOnly = true }: TimerButtonProps) {
  const { data: running } = useRunningTimer()
  const startTimer = useStartTimer()
  const stopTimer = useStopTimer()

  const isRunningHere = running?.issue?.id === issueId

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isRunningHere) {
      stopTimer.mutate(running!.id)
    } else {
      startTimer.mutate(issueId)
    }
  }

  return (
    <Button
      variant={isRunningHere ? 'primary' : 'subtle'}
      size={size}
      iconOnly={iconOnly}
      onClick={handleClick}
      aria-label={isRunningHere ? 'Stop timer' : 'Start timer'}
      title={isRunningHere ? 'Stop timer' : 'Start timer'}
    >
      {isRunningHere ? <Square size={13} /> : <Clock size={13} />}
      {!iconOnly && <span>{isRunningHere ? 'Stop timer' : 'Start timer'}</span>}
    </Button>
  )
}
