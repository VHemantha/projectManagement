import { format, parseISO } from 'date-fns'
import { RefreshCw, SearchCheck } from 'lucide-react'

import styles from './GapTracker.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type GapStatus, useGapAction, useJobGaps } from '@/api/precheck'
import { Button } from '@/design-system'

const GAP_LABEL: Record<GapStatus, string> = {
  OPEN: 'Not found yet — still checking',
  PARTIALLY_RESOLVED: 'Partly found',
  RESOLVED: 'Found by searching every document',
  CONFLICTING: 'Documents disagree',
  CONFIRMED_MISSING: 'Confirmed missing',
}

/** A pre-check item's gap status, beside its title. */
export function GapChip({ status }: { status: GapStatus }) {
  return (
    <span className={styles.chip} data-status={status}>
      {GAP_LABEL[status]}
    </span>
  )
}

/** Whether the pre-check's "not found" list is still provisional (AFIT, 12 Nov 2026): the AI keeps
 * checking every document of the task, new ones as they arrive, until each item is found or the
 * folder has settled and it is confirmed missing. A person can check again now, or settle it now. */
export function GapTracker({ jobKey }: { jobKey: string }) {
  const { data } = useJobGaps(jobKey)
  const action = useGapAction(jobKey)
  if (!data || data.gaps.length === 0) return null
  const count = (s: GapStatus) => data.counts[s] ?? 0
  const still = count('OPEN') + count('PARTIALLY_RESOLVED') + count('CONFLICTING')

  return (
    <section className={styles.tracker} data-final={!data.provisional || undefined} aria-label="Items the AI keeps checking">
      <div className={styles.head}>
        <SearchCheck size={18} aria-hidden="true" />
        <p className={styles.text}>
          {data.provisional ? (
            <>
              <strong>Provisional.</strong> The AI keeps checking every document, and new ones as they arrive, against{' '}
              {still} item{still === 1 ? '' : 's'} until each is found or confirmed missing.
            </>
          ) : (
            <>
              <strong>Settled{data.finalized_at ? ` on ${format(parseISO(data.finalized_at), 'd MMM yyyy')}` : ''}.</strong> Every document was
              checked.
            </>
          )}
        </p>
      </div>
      <ul className={styles.counts}>
        {(['RESOLVED', 'PARTIALLY_RESOLVED', 'CONFLICTING', 'OPEN', 'CONFIRMED_MISSING'] as GapStatus[])
          .filter((s) => count(s) > 0)
          .map((s) => (
            <li key={s} data-status={s}>
              <span className={styles.number}>{count(s)}</span> {s === 'RESOLVED' ? 'found' : GAP_LABEL[s].toLowerCase().split(' — ')[0]}
            </li>
          ))}
      </ul>
      {data.provisional && (
        <div className={styles.actions}>
          <Button size="sm" variant="secondary" onClick={() => action.mutate('recheck')} disabled={action.isPending}>
            <RefreshCw size={13} aria-hidden="true" /> Check again now
          </Button>
          <Button
            size="sm"
            variant="subtle"
            onClick={() => action.mutate('finalize')}
            disabled={action.isPending}
            title="Every document has arrived: one last check, then anything still not found is confirmed missing"
          >
            Confirm what's still not found
          </Button>
          {action.isSuccess && <span className={styles.muted}>Checking… the list updates when it is done.</span>}
        </div>
      )}
      {action.isError && <p className={styles.error}>{extractErrorMessage(action.error)}</p>}
    </section>
  )
}
