import { Square } from 'lucide-react'
import { useEffect, useState } from 'react'

import styles from './GlobalTimerWidget.module.css'
import { useRunningTimer, useStopTimer } from '@/api/timesheets'
import { useUiStore } from '@/store/uiStore'

function formatElapsed(totalSeconds: number) {
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export function GlobalTimerWidget() {
  const { data: running } = useRunningTimer()
  const stopTimer = useStopTimer()
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    if (!running) return undefined
    const interval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [running])

  if (!running || !running.started_at) return null

  const elapsed = Math.floor((now - new Date(running.started_at).getTime()) / 1000)

  return (
    <div className={styles.widget} onClick={() => running.issue && openIssueModal(running.issue.key)}>
      <span className={styles.dot} />
      <span>{formatElapsed(Math.max(elapsed, 0))}</span>
      {running.issue && <span className={styles.issueKey}>{running.issue.key}</span>}
      <button
        className={styles.stopBtn}
        onClick={(e) => {
          e.stopPropagation()
          stopTimer.mutate(running.id)
        }}
        aria-label="Stop timer"
      >
        <Square size={10} fill="white" />
      </button>
    </div>
  )
}
