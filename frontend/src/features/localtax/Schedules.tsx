import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import styles from './LocalTax.module.css'
import { type CaSchedule, type Computation, type FixedAsset, type LossYear, money } from '@/api/localTax'
import { Button } from '@/design-system'

/** Phase 3 of the Local Tax workflow (AFIT): the fixed asset register the capital allowance schedule is worked out
 * from (allowance at the class's rate for the year, balancing charge or allowance on a disposal), and the tax
 * losses by year of origin, used oldest first. The figures are the engine's; only the register is typed here. */

const ASSET_CLASSES: [string, string][] = [['plant_machinery', 'Plant, machinery and fixtures'], ['buildings', 'Buildings'],
  ['computers_software', 'Computer hardware and software'], ['motor_vehicles', 'Motor vehicles'], ['intangibles', 'Intangible assets']]

export function FixedAssetRegister({ rows, schedule, onSave, busy }: { rows: FixedAsset[]; schedule?: CaSchedule | null; onSave: (rows: FixedAsset[]) => void; busy: boolean }) {
  const [draft, setDraft] = useState<FixedAsset[]>(rows)
  const set = (i: number, p: Partial<FixedAsset>) => setDraft(draft.map((r, n) => (n === i ? { ...r, ...p } : r)))
  const byId = new Map((schedule?.rows ?? []).map((r) => [r.id, r]))
  return (
    <>
      <h3 className={styles.cardTitle}>Fixed asset register</h3>
      <p className={styles.hint}>
        The capital allowance schedule is worked out from the register: the year&apos;s rate for the class on cost, never more than the cost not yet claimed;
        a disposal gives a balancing charge or allowance against the tax written-down value. Read a register with Local_Tax_AI under Questionnaire &gt; Upload Documents.
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Fixed asset register">
          <thead>
            <tr>
              <th>Asset</th><th>Class</th><th>Acquired</th><th className={styles.num}>Cost</th><th className={styles.num}>Claimed before</th>
              <th className={styles.num}>Allowance (blank: by rate)</th><th>Disposed</th><th className={styles.num}>Proceeds</th><th /></tr>
          </thead>
          <tbody>
            {draft.map((r, i) => (
              <tr key={r.id ?? i}>
                <td className={styles.cell}><input aria-label="Asset" value={r.description} onChange={(ev) => set(i, { description: ev.target.value })} /></td>
                <td className={styles.cell}>
                  <select aria-label="Asset class" value={r.asset_class} onChange={(ev) => set(i, { asset_class: ev.target.value })}>
                    <option value="">Choose…</option>
                    {ASSET_CLASSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </td>
                <td className={styles.cell}><input type="date" aria-label="Acquired" value={r.acquired ?? ''} onChange={(ev) => set(i, { acquired: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Cost" inputMode="decimal" value={r.cost} onChange={(ev) => set(i, { cost: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Claimed before" inputMode="decimal" value={r.ca_claimed_bf ?? ''} onChange={(ev) => set(i, { ca_claimed_bf: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Allowance" inputMode="decimal" value={r.allowance ?? ''} onChange={(ev) => set(i, { allowance: ev.target.value })} /></td>
                <td className={styles.cell}><input type="date" aria-label="Disposed" value={r.disposed ?? ''} onChange={(ev) => set(i, { disposed: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Proceeds" inputMode="decimal" value={r.proceeds ?? ''} disabled={!r.disposed} onChange={(ev) => set(i, { proceeds: ev.target.value })} /></td>
                <td><Button size="sm" variant="subtle" iconOnly aria-label="Remove" onClick={() => setDraft(draft.filter((_, n) => n !== i))}><Trash2 size={13} /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => setDraft([...draft, { description: '', asset_class: 'plant_machinery', cost: '' }])}><Plus size={13} /> Add asset</Button>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onSave(draft)}>Save and recalculate</Button>
      </div>
      {schedule && schedule.rows.length > 0 && (
        <>
          <h3 className={styles.cardTitle}>Capital allowance schedule</h3>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Capital allowance schedule">
              <thead>
                <tr><th>Asset</th><th className={styles.num}>Rate</th><th className={styles.num}>Tax WDV b/f</th><th className={styles.num}>Allowance</th>
                  <th className={styles.num}>Balancing charge / (allowance)</th><th className={styles.num}>Tax WDV c/f</th></tr>
              </thead>
              <tbody>
                {schedule.rows.map((r) => (
                  <tr key={r.id} title={r.ref}>
                    <th scope="row">{r.description} <span className={styles.muted}>{r.label}{r.manual ? ' · entered' : ''}{r.disposed ? ` · disposed ${r.disposed}` : ''}</span></th>
                    <td className={styles.num}>{r.rate === null ? '—' : `${Number(r.rate) * 100}%`}</td>
                    <td className={styles.num}>{money(r.wdv_bf)}</td><td className={styles.num}>{money(r.allowance)}</td>
                    <td className={styles.num}>{r.disposed ? money(Number(r.balancing_charge) - Number(r.balancing_allowance)) : ''}</td>
                    <td className={styles.num}>{money(r.wdv_cf)}</td>
                  </tr>
                ))}
                <tr data-kind="subtotal">
                  <th scope="row">Total</th><td /><td /><td className={styles.num}>{money(schedule.totals.allowance)}</td>
                  <td className={styles.num}>{money(Number(schedule.totals.balancing_charge) - Number(schedule.totals.balancing_allowance))}</td>
                  <td className={styles.num}>{money(schedule.totals.wdv_cf)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {byId.size > 0 && schedule.flags.map((f) => <p key={f.text} className={styles.error}>{f.text}</p>)}
        </>
      )}
    </>
  )
}

export function LossHistory({ rows, comp, onSave, busy }: { rows: LossYear[]; comp: Computation | null; onSave: (rows: LossYear[]) => void; busy: boolean }) {
  const [draft, setDraft] = useState<LossYear[]>(rows)
  const set = (i: number, p: Partial<LossYear>) => setDraft(draft.map((r, n) => (n === i ? { ...r, ...p } : r)))
  const sched = comp?.loss_schedule
  return (
    <>
      <h3 className={styles.cardTitle}>Tax losses by year of origin</h3>
      <p className={styles.hint}>When given, these replace the single “losses brought forward” figure; the oldest loss is used first. A prior return read with Local_Tax_AI adds its losses carried forward here.</p>
      <table className={styles.table} aria-label="Tax losses brought forward">
        <thead><tr><th>Year of assessment</th><th className={styles.num}>Unused loss brought forward</th><th>Source</th><th /></tr></thead>
        <tbody>
          {draft.map((r, i) => (
            <tr key={r.id ?? i}>
              <td className={styles.cell}><input aria-label="Year of assessment" placeholder="2022/23" value={r.ya} onChange={(ev) => set(i, { ya: ev.target.value })} /></td>
              <td className={styles.cell}><input aria-label="Loss" inputMode="decimal" value={r.amount} onChange={(ev) => set(i, { amount: ev.target.value })} /></td>
              <td className={styles.muted}>{r.source}</td>
              <td><Button size="sm" variant="subtle" iconOnly aria-label="Remove" onClick={() => setDraft(draft.filter((_, n) => n !== i))}><Trash2 size={13} /></Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => setDraft([...draft, { ya: '', amount: '' }])}><Plus size={13} /> Add year</Button>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onSave(draft)}>Save and recalculate</Button>
      </div>
      {sched && sched.rows.length > 0 && (
        <table className={styles.table} aria-label="Tax loss schedule">
          <thead><tr><th>Year of assessment</th><th className={styles.num}>Brought forward</th><th className={styles.num}>Utilised</th><th className={styles.num}>Carried forward</th></tr></thead>
          <tbody>
            {sched.rows.map((r) => (
              <tr key={r.ya}><th scope="row">{r.ya}{r.current ? ' (this year’s loss)' : ''}</th><td className={styles.num}>{money(r.bf)}</td>
                <td className={styles.num}>{money(r.utilised)}</td><td className={styles.num}>{money(r.cf)}</td></tr>
            ))}
            <tr data-kind="subtotal"><th scope="row">Total</th><td className={styles.num}>{money(sched.totals.bf)}</td>
              <td className={styles.num}>{money(sched.totals.utilised)}</td><td className={styles.num}>{money(sched.totals.cf)}</td></tr>
          </tbody>
        </table>
      )}
    </>
  )
}
