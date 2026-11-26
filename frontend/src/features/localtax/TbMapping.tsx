import { GitBranch, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import styles from './LocalTax.module.css'
import { HEADINGS } from './headings'
import { extractErrorMessage } from '@/api/errors'
import { type Financials, money, useAiAgent, useMapLine, usePutTb } from '@/api/localTax'
import { Button } from '@/design-system'

/** The trial balance mapping, at the top right of the Financial Statements stage (AFIT, 26 Nov 2026): every account
 * with its heading (a person's choice kept across re-uploads), AI suggestions to accept one by one, and the trial
 * balance entered by hand. A line edited on the statements shows here until it is posted to the TB. */
export function TbMapping({ taskKey, fin }: { taskKey: string; fin: Financials | null }) {
  const map = useMapLine(taskKey)
  const put = usePutTb(taskKey)
  const suggest = useAiAgent<{ suggestions: { code: string; heading: string; reason: string }[]; notes: string[] }>(taskKey, 'map-tb')
  const [rows, setRows] = useState<{ code: string; name: string; amount: string; comparative: string }[]>([])
  const [filter, setFilter] = useState('')
  const tb = fin?.tb ?? []
  const unmapped = fin?.unmapped?.length ?? 0
  const asked = useRef(false)
  useEffect(() => {
    if (unmapped > 0 && !asked.current) {
      asked.current = true
      suggest.mutate(undefined)
    }
  }, [unmapped, suggest])
  const q = filter.trim().toLowerCase()
  const shown = q ? tb.filter((ln) => `${ln.code} ${ln.name}`.toLowerCase().includes(q)) : tb
  const total = tb.reduce((s, ln) => s + Number(ln.amount ?? 0), 0)
  return (
    <section className={styles.card} aria-label="TB Mapping">
      <h3 className={styles.cardTitle}><GitBranch size={18} aria-hidden="true" /> TB Mapping</h3>
      <p className={styles.muted} style={{ margin: 0 }}>
        {tb.length} accounts{unmapped ? ` — ${unmapped} not mapped` : ', all mapped'}; {Math.abs(total) < 0.005 ? 'balances' : `out by ${money(total)}`}.
      </p>
      <div className={styles.actions}>
        <input aria-label="Find an account" placeholder="Find an account…" value={filter} onChange={(ev) => setFilter(ev.target.value)} style={{ flex: 1, minWidth: 0 }} />
        <Button size="sm" variant="secondary" disabled={!tb.length || suggest.isPending} onClick={() => suggest.mutate(undefined)}>
          <Sparkles size={13} /> {suggest.isPending ? 'Checking…' : 'AI'}
        </Button>
      </div>
      {suggest.isError && <p className={styles.error}>{extractErrorMessage(suggest.error)}</p>}
      {suggest.data && suggest.data.suggestions.length > 0 && (
        <div aria-label="AI mapping suggestions">
          <strong>Local_Tax_AI suggests ({suggest.data.suggestions.length})</strong>
          {suggest.data.suggestions.map((s) => (
            <div key={s.code} className={styles.actions} style={{ justifyContent: 'space-between' }}>
              <span>{s.code} → {HEADINGS.find((h) => h[0] === s.heading)?.[1]} <span className={styles.muted}>{s.reason}</span></span>
              <Button size="sm" variant="subtle" onClick={() => map.mutate({ code: s.code, heading: s.heading })}>Accept</Button>
            </div>
          ))}
          {suggest.data.notes.map((n) => <p key={n} className={styles.muted}>{n}</p>)}
        </div>
      )}
      <ul className={styles.tbList} aria-label="Trial balance">
        {shown.map((ln) => (
          <li key={ln.code} data-missing={!ln.heading || undefined} data-edit={ln.edit || undefined}>
            <span className={styles.tbLine}>
              <span><b>{ln.code}</b> {ln.name}{ln.adjusted && !ln.edit ? ' (adjusted)' : ''}</span>
              <span className={styles.num}>{money(ln.amount)}</span>
            </span>
            {ln.edit ? (
              <span className={styles.hint}>Edited on the statements: not in the TB until posted.</span>
            ) : (
              <select aria-label={`Heading for ${ln.name}`} value={ln.heading} onChange={(ev) => map.mutate({ code: ln.code, heading: ev.target.value })}>
                <option value="">Not mapped</option>
                {HEADINGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            )}
          </li>
        ))}
      </ul>
      <details>
        <summary>Enter or replace the trial balance by hand</summary>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead><tr><th>Code</th><th>Account</th><th className={styles.num}>Current (Dr + / Cr −)</th><th className={styles.num}>Prior</th><th /></tr></thead>
            <tbody>
              {rows.map((r, i) => {
                const set = (p: Partial<typeof r>) => setRows(rows.map((x, n) => (n === i ? { ...x, ...p } : x)))
                return (
                  <tr key={i}>
                    <td className={styles.cell}><input aria-label="Code" value={r.code} onChange={(ev) => set({ code: ev.target.value })} /></td>
                    <td className={styles.cell}><input aria-label="Account" value={r.name} onChange={(ev) => set({ name: ev.target.value })} /></td>
                    <td className={styles.cell}><input aria-label="Current" inputMode="decimal" value={r.amount} onChange={(ev) => set({ amount: ev.target.value })} /></td>
                    <td className={styles.cell}><input aria-label="Prior" inputMode="decimal" value={r.comparative} onChange={(ev) => set({ comparative: ev.target.value })} /></td>
                    <td><Button size="sm" variant="subtle" iconOnly aria-label="Remove" onClick={() => setRows(rows.filter((_, n) => n !== i))}><Trash2 size={13} /></Button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className={styles.actions}>
          <Button size="sm" variant="subtle" onClick={() => setRows([...rows, { code: '', name: '', amount: '', comparative: '' }])}><Plus size={13} /> Add account</Button>
          <Button size="sm" variant="primary" disabled={!rows.length || put.isPending}
            onClick={() => put.mutate(rows.map((r) => ({ ...r, comparative: r.comparative || null })), { onSuccess: () => setRows([]) })}>
            Replace the trial balance
          </Button>
        </div>
        {put.isError && <p className={styles.error}>{extractErrorMessage(put.error)}</p>}
      </details>
    </section>
  )
}
