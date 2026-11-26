import { Check, X } from 'lucide-react'

import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type ClientChange, money, useClientChange } from '@/api/localTax'
import { Button } from '@/design-system'

const KIND: Record<ClientChange['type'], string> = {
  field: 'Client info',
  journal: 'Journal',
  tax_adjustment: 'Tax adjustment',
  note: 'Note',
  policy: 'Policy',
  heading: 'Heading',
}

/** The changes Local_Tax_AI proposes for a client's request (AFIT, 26 Nov 2026), each shown with what it changes from and
 * to and applied - or dismissed - by the accountant one at a time. Every amount is code's: a journal's difference and its
 * balancing line are worked out from the current balances. */
export function ClientChanges({ taskKey, message, changes, dropped }: { taskKey: string; message: number; changes: ClientChange[]; dropped: string[] }) {
  const decide = useClientChange(taskKey)
  const busy = (n: number) => decide.isPending && decide.variables?.message === message && decide.variables?.n === n
  return (
    <div className={styles.changes} aria-label="Changes the client asked for">
      {changes.map((c) => (
        <section key={c.n} className={styles.change} data-status={c.status} aria-label={c.label}>
          <div className={styles.changeHead}>
            <strong>
              <span className={styles.chip}>{KIND[c.type]}</span> {c.label}
            </strong>
            {c.status !== 'proposed' && (
              <span className={styles.chip} data-status={c.status === 'applied' ? 'approved' : undefined}>
                {c.status === 'applied' ? 'Applied' : 'Dismissed'}
              </span>
            )}
          </div>
          {c.type === 'journal' && c.lines ? (
            <table className={styles.table} aria-label={`Journal: ${c.label}`}>
              <thead>
                <tr><th>Account</th><th className={styles.num}>Debit</th><th className={styles.num}>Credit</th></tr>
              </thead>
              <tbody>
                {c.lines.map((ln) => (
                  <tr key={ln.code}>
                    <td>
                      {ln.code} {ln.name}
                      {ln.sets !== undefined && <span className={styles.muted}> — balance {money(ln.was ?? '0')} → {money(ln.sets)}</span>}
                    </td>
                    <td className={styles.num}>{Number(ln.amount) > 0 ? money(ln.amount) : ''}</td>
                    <td className={styles.num}>{Number(ln.amount) < 0 ? money(String(-Number(ln.amount))) : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <dl className={styles.fromTo}>
              <dt>Now</dt>
              <dd>{(c.type === 'tax_adjustment' ? money(c.from) : c.from) || '—'}</dd>
              <dt>Change to</dt>
              <dd>{c.type === 'tax_adjustment' ? money(c.to) : c.to}</dd>
            </dl>
          )}
          <p className={styles.muted} style={{ margin: 0 }}>{c.reason}</p>
          {c.status === 'proposed' ? (
            <div className={styles.actions}>
              <Button size="sm" variant="primary" disabled={decide.isPending} aria-label={`Apply: ${c.label}`}
                onClick={() => decide.mutate({ message, n: c.n, decision: 'apply' })}>
                <Check size={13} /> {busy(c.n) ? 'Applying…' : c.type === 'journal' || c.type === 'tax_adjustment' ? 'Propose for approval' : 'Apply'}
              </Button>
              <Button size="sm" variant="subtle" disabled={decide.isPending} aria-label={`Dismiss: ${c.label}`}
                onClick={() => decide.mutate({ message, n: c.n, decision: 'dismiss' })}>
                <X size={13} /> Dismiss
              </Button>
            </div>
          ) : (
            c.result && <p style={{ margin: 0 }}>{c.result}{c.by ? ` — ${c.by}` : ''}</p>
          )}
          {decide.isError && decide.variables?.message === message && decide.variables?.n === c.n && (
            <p className={styles.error} role="alert" style={{ margin: 0 }}>{extractErrorMessage(decide.error)}</p>
          )}
        </section>
      ))}
      {dropped.length > 0 && (
        <p className={styles.muted} style={{ margin: 0 }}>
          Left out (TASKO can&apos;t make these from the chat): {dropped.join(' ')}
        </p>
      )}
    </div>
  )
}
