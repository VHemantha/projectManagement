import { Square } from 'lucide-react'

import { useStopRun } from '@/api/precheck'
import { extractErrorMessage } from '@/api/errors'
import { Button } from '@/design-system'

/** Stops a running pre-check, guide, review or Direction Note draft. The run is marked stopped at
 * once and the task is free to run again; anything the AI sends afterwards is ignored. */
export function StopRun({ jobKey, runId, label = 'Stop' }: { jobKey: string; runId: string | undefined; label?: string }) {
  const stop = useStopRun(jobKey)
  if (!runId) return null
  return (
    <>
      <Button type="button" variant="secondary" size="sm" disabled={stop.isPending} onClick={() => stop.mutate(runId)}>
        <Square size={12} aria-hidden="true" />
        {stop.isPending ? 'Stopping…' : label}
      </Button>
      {stop.isError && (
        <span role="alert" style={{ color: 'var(--tf-danger)', fontSize: 'var(--tf-font-size-sm)' }}>
          {extractErrorMessage(stop.error, 'It could not be stopped. Refresh the page and try again.')}
        </span>
      )}
    </>
  )
}
