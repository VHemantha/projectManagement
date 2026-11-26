import { RefreshCw } from 'lucide-react'
import { useState } from 'react'

import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type StageKey, type UpdateChange, money, useUpdateWorkflow } from '@/api/localTax'
import { Button } from '@/design-system'

const COUNT = new Set(['blocking'])

/** Update (AFIT, 26 Nov 2026), on every stage: the workflow worked out again from everything entered - the statements,
 * depreciation, the computation and the return - and what changed since the last update said beside it. `before` runs
 * first (e.g. saving what is typed on Client Info). */
export function UpdateButton({ taskKey, stage, label = 'Update', before }: {
  taskKey: string; stage: StageKey; label?: string; before?: () => Promise<unknown>
}) {
  const update = useUpdateWorkflow(taskKey)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try {
      if (before) await before()
      await update.mutateAsync(stage)
    } catch {
      // the error is shown below
    } finally {
      setBusy(false)
    }
  }
  const out = update.data
  const fmt = (c: UpdateChange, v: string | null) => (v === null ? '—' : COUNT.has(c.key) ? v : money(v))
  return (
    <span className={styles.update}>
      <Button variant="secondary" onClick={run} disabled={busy || update.isPending} title="Work everything out again from what is entered">
        <RefreshCw size={15} className={busy ? styles.spin : undefined} /> {busy ? 'Updating…' : label}
      </Button>
      {out && !busy && (
        <span className={styles.updateResult} role="status">
          {out.first ? 'Updated.' : out.changes.length === 0 ? 'Updated: nothing changed since the last update.' : (
            <>
              Updated — changed since the last update:
              <ul>
                {out.changes.map((c) => <li key={c.key}>{c.label}: {fmt(c, c.from)} → {fmt(c, c.to)}</li>)}
              </ul>
            </>
          )}
        </span>
      )}
      {update.isError && <span className={styles.error} role="alert">{extractErrorMessage(update.error)}</span>}
    </span>
  )
}
