import { AlertTriangle, CheckCircle2, Plus, Save, Sparkles, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'

import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import { useAttachments, useUploadAttachment } from '@/api/issues'
import {
  type Extraction,
  type LocalTaxState,
  type PolicyRow,
  type PpeAddition,
  type PpeClassify,
  type PpeDisposal,
  type PpeState,
  money,
  useApproveDepreciation,
  useDecideExtraction,
  useExtract,
  usePpeClassify,
  useSaveLocalTax,
  useSavePolicy,
} from '@/api/localTax'
import { Button } from '@/design-system'

const pct = (v: string) => `${Number((Number(v) * 100).toFixed(4))}`
const STATUS = {
  approved: ['Approved', 'The depreciation journal (JE-DEP) is posted to the trial balance.'],
  changed: ['Changed since approval', 'The policy, the assets or the trial balance changed: approve again to update the depreciation journal.'],
  not_approved: ['Not approved', 'Review the schedule and approve it to post the depreciation journal.'],
} as const

/** PPE & Depreciation (AFIT, 24 Nov 2026), following AFIT's eight steps:
 * 1. Opening balances from the trial balance or last year's statements.
 * 2. The client's depreciation policy.
 * 3. Additions and disposals, read by AI from invoices or a register.
 * 4. Monthly depreciation.
 * 5. Review and approval.
 * 6-7. The depreciation journal posted to the trial balance.
 * 8. The PPE note.
 * Every figure is worked out by code; AI only suggests categories and reads documents for a person to confirm. */
export function PpeSection({ taskKey, state }: { taskKey: string; state: LocalTaxState }) {
  const ppe = state.ppe
  if (!ppe) {
    return (
      <p className={styles.muted}>
        No property, plant and equipment yet: map the trial balance's PPE accounts (TB Mapping) or add this year's assets below once the trial balance is loaded.
      </p>
    )
  }
  const totals = ppe.schedule.totals
  return (
    <>
      <ApprovalBar taskKey={taskKey} state={state} ppe={ppe} />
      {ppe.schedule.flags.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {ppe.schedule.flags.map((f, i) => (
            <li key={i} className={f.severity === 'blocking' ? styles.error : styles.muted}>{f.severity === 'blocking' ? <AlertTriangle size={12} /> : null} {f.text}</li>
          ))}
        </ul>
      )}
      <Policy taskKey={taskKey} ppe={ppe} />
      <Accounts taskKey={taskKey} state={state} ppe={ppe} />
      <Opening taskKey={taskKey} ppe={ppe} />
      <Movements taskKey={taskKey} state={state} ppe={ppe} />
      <Schedule ppe={ppe} />
      {totals && <JournalPreview ppe={ppe} />}
    </>
  )
}

function ApprovalBar({ taskKey, state, ppe }: { taskKey: string; state: LocalTaxState; ppe: PpeState }) {
  const approve = useApproveDepreciation(taskKey)
  const [label, text] = STATUS[ppe.status]
  return (
    <div className={styles.card} style={{ background: 'var(--tf-surface-sunken)' }}>
      <div className={styles.actions}>
        {ppe.status === 'approved' ? <CheckCircle2 size={16} aria-hidden="true" /> : <AlertTriangle size={16} aria-hidden="true" />}
        <strong>Depreciation: {label}</strong>
        <span className={styles.muted}>{text}{ppe.approved.by ? ` Last approved by ${ppe.approved.by}.` : ''}</span>
        <span className={styles.spacer} />
        <span>Charge for the year: <strong>LKR {money(ppe.schedule.totals?.charge ?? 0)}</strong></span>
        {state.engagement.can_approve && (
          <Button size="sm" variant="primary" disabled={approve.isPending || ppe.blocking.length > 0 || ppe.status === 'approved'} onClick={() => approve.mutate()}>
            {ppe.status === 'changed' ? 'Approve again and update the journal' : 'Approve and post the journal'}
          </Button>
        )}
      </div>
      {!state.engagement.can_approve && ppe.status !== 'approved' && <p className={styles.hint} style={{ margin: 0 }}>A reviewer, lead or admin approves the depreciation.</p>}
      {approve.isError && <p className={styles.error}>{extractErrorMessage(approve.error)}</p>}
      {ppe.reconciliation.length > 0 && (
        <p className={styles.muted} style={{ margin: 0 }}>
          PPE note against the trial balance: {ppe.reconciliation.every((r) => r.agrees) ? 'agrees for every category.' :
            ppe.reconciliation.filter((r) => !r.agrees).map((r) => `${r.label} differs`).join('; ')}
        </p>
      )}
    </div>
  )
}

function Policy({ taskKey, ppe }: { taskKey: string; ppe: PpeState }) {
  const save = useSavePolicy(taskKey)
  const [rows, setRows] = useState<PolicyRow[]>(ppe.policy)
  const [dirty, setDirty] = useState(false)
  const set = (i: number, p: Partial<PolicyRow>) => (setRows(rows.map((r, n) => (n === i ? { ...r, ...p } : r))), setDirty(true))
  return (
    <details open={!ppe.policy_about.saved}>
      <summary>
        <strong>1. Depreciation policy</strong>{' '}
        <span className={styles.muted}>{ppe.policy_about.saved ? `kept with ${ppe.policy_about.client} for every year` : 'illustrative rates - save the client\'s own'}</span>
      </summary>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Depreciation policy">
          <thead><tr><th>Asset category</th><th>Method</th><th className={styles.num}>Annual rate %</th><th className={styles.num}>Residual value %</th><th /></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.key || i}>
                <td className={styles.cell}><input aria-label="Category" value={r.label} onChange={(ev) => set(i, { label: ev.target.value })} /></td>
                <td className={styles.cell}>
                  <select aria-label="Method" value={r.method} onChange={(ev) => set(i, { method: ev.target.value as PolicyRow['method'] })}>
                    {Object.entries(ppe.methods).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </td>
                <td className={styles.cell}><input aria-label="Annual rate %" inputMode="decimal" value={pct(r.rate)} onChange={(ev) => set(i, { rate: String(Number(ev.target.value) / 100) })} /></td>
                <td className={styles.cell}><input aria-label="Residual value %" inputMode="decimal" value={pct(r.residual)} onChange={(ev) => set(i, { residual: String(Number(ev.target.value) / 100) })} /></td>
                <td><Button size="sm" variant="subtle" aria-label={`Remove ${r.label}`} onClick={() => (setRows(rows.filter((_, n) => n !== i)), setDirty(true))}><Trash2 size={13} /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => (setRows([...rows, { key: '', label: '', method: 'straight_line', rate: '0', residual: '0' }]), setDirty(true))}><Plus size={13} /> Category</Button>
        <span className={styles.spacer} />
        <Button size="sm" variant="primary" disabled={!dirty || save.isPending}
          onClick={() => save.mutate(rows.map((r) => ({ ...r, rate: String(Number(r.rate) * 100), residual: String(Number(r.residual) * 100) })), { onSuccess: () => setDirty(false) })}>
          <Save size={13} /> Save for {ppe.policy_about.client || 'the client'}
        </Button>
      </div>
      {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
    </details>
  )
}

function Accounts({ taskKey, state, ppe }: { taskKey: string; state: LocalTaxState; ppe: PpeState }) {
  const save = useSaveLocalTax(taskKey)
  const classify = usePpeClassify(taskKey)
  const [ai, setAi] = useState<PpeClassify | null>(null)
  const overrides = state.engagement.data.ppe?.accounts ?? {}
  const setAccount = (patch: Record<string, { category: string; role: 'cost' | 'accumulated'; by: 'person' | 'ai' }>) =>
    save.mutate({ data: { ppe: { accounts: { ...overrides, ...patch } } }, stage: 'fs' })
  if (!ppe.accounts.length) return null
  return (
    <details open={ppe.accounts.some((a) => !a.category)}>
      <summary><strong>PPE accounts and their categories</strong> <span className={styles.muted}>{ppe.accounts.length} accounts</span></summary>
      <div className={styles.actions}>
        <Button size="sm" variant="secondary" disabled={classify.isPending} onClick={() => classify.mutate(undefined, { onSuccess: setAi })}>
          <Sparkles size={13} /> {classify.isPending ? 'Identifying…' : 'Identify categories with AI'}
        </Button>
        {ai && ai.suggestions.length > 0 && (
          <Button size="sm" variant="primary" onClick={() => (setAccount(Object.fromEntries(ai.suggestions.filter((s) => s.category).map((s) => [s.code, { category: s.category, role: s.role, by: 'ai' as const }]))), setAi(null))}>
            Accept all suggestions
          </Button>
        )}
        {classify.isError && <span className={styles.error}>{extractErrorMessage(classify.error)}</span>}
      </div>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="PPE accounts">
          <thead><tr><th>Code</th><th>Account</th><th className={styles.num}>This year</th><th className={styles.num}>Last year</th><th>Category</th><th>Holds</th></tr></thead>
          <tbody>
            {ppe.accounts.map((a) => {
              const s = ai?.suggestions.find((x) => x.code === a.code)
              return (
                <tr key={a.code}>
                  <td>{a.code}</td>
                  <td>{a.name}{s && <div className={styles.muted}><Sparkles size={11} /> {ppe.policy.find((p) => p.key === s.category)?.label ?? 'no category'} - {s.reason}</div>}</td>
                  <td className={styles.num}>{money(a.amount)}</td>
                  <td className={styles.num}>{money(a.comparative)}</td>
                  <td className={styles.cell}>
                    <select aria-label={`Category of ${a.code}`} value={a.category} onChange={(ev) => setAccount({ [a.code]: { category: ev.target.value, role: a.role, by: 'person' } })}>
                      <option value="">Choose…</option>
                      {ppe.policy.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                    </select>
                  </td>
                  <td className={styles.cell}>
                    <select aria-label={`Role of ${a.code}`} value={a.role} onChange={(ev) => setAccount({ [a.code]: { category: a.category, role: ev.target.value as 'cost' | 'accumulated', by: 'person' } })}>
                      <option value="cost">Cost</option><option value="accumulated">Accumulated depreciation</option>
                    </select>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function Opening({ taskKey, ppe }: { taskKey: string; ppe: PpeState }) {
  const save = useSaveLocalTax(taskKey)
  const [draft, setDraft] = useState<Record<string, { cost: string; accumulated: string }>>({})
  const cats = ppe.policy.filter((p) => Number(ppe.opening[p.key]?.cost) || Number(ppe.opening[p.key]?.accumulated) || ppe.accounts.some((a) => a.category === p.key))
  return (
    <details>
      <summary><strong>2. Opening balances</strong> <span className={styles.muted}>from the trial balance's prior-year column or last year's statements - edit if needed</span></summary>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Opening balances">
          <thead><tr><th>Category</th><th className={styles.num}>Cost</th><th className={styles.num}>Accumulated depreciation</th><th className={styles.num}>Net book value</th><th>Source</th></tr></thead>
          <tbody>
            {cats.map((p) => {
              const o = ppe.opening[p.key] ?? { cost: '0', accumulated: '0', source: '' }
              const d = draft[p.key] ?? { cost: String(o.cost ?? ''), accumulated: String(o.accumulated ?? '') }
              const set = (v: Partial<typeof d>) => setDraft({ ...draft, [p.key]: { ...d, ...v } })
              return (
                <tr key={p.key}>
                  <td>{p.label}</td>
                  <td className={styles.cell}><input aria-label={`Opening cost ${p.label}`} inputMode="decimal" value={d.cost} onChange={(ev) => set({ cost: ev.target.value })} /></td>
                  <td className={styles.cell}><input aria-label={`Opening accumulated depreciation ${p.label}`} inputMode="decimal" value={d.accumulated} onChange={(ev) => set({ accumulated: ev.target.value })} /></td>
                  <td className={styles.num}>{money(Number(d.cost || 0) - Number(d.accumulated || 0))}</td>
                  <td className={styles.muted}>{o.source || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className={styles.actions}>
        <span className={styles.spacer} />
        <Button size="sm" variant="primary" disabled={!Object.keys(draft).length || save.isPending}
          onClick={() => save.mutate({ data: { ppe: { opening: { ...(Object.fromEntries(Object.entries(ppe.opening).filter(([, v]) => v.source && !v.source.startsWith('Trial balance')).map(([k, v]) => [k, { cost: String(v.cost), accumulated: String(v.accumulated), source: v.source }]))),
            ...Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, { ...v, source: 'Entered by the accountant' }])) } } }, stage: 'fs' }, { onSuccess: () => setDraft({}) })}>
          <Save size={13} /> Save opening balances
        </Button>
      </div>
      {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
    </details>
  )
}

function Movements({ taskKey, state, ppe }: { taskKey: string; state: LocalTaxState; ppe: PpeState }) {
  const save = useSaveLocalTax(taskKey)
  const [adds, setAdds] = useState<PpeAddition[]>(ppe.additions)
  const [disps, setDisps] = useState<PpeDisposal[]>(ppe.disposals)
  const [dirty, setDirty] = useState(false)
  const tb = state.financials?.tb ?? []
  const options = (
    <>
      <option value="">Choose…</option>
      {ppe.policy.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
    </>
  )
  const setA = (i: number, p: Partial<PpeAddition>) => (setAdds(adds.map((r, n) => (n === i ? { ...r, ...p } : r))), setDirty(true))
  const setD = (i: number, p: Partial<PpeDisposal>) => (setDisps(disps.map((r, n) => (n === i ? { ...r, ...p } : r))), setDirty(true))
  const proceedsCode = state.engagement.data.ppe?.options?.proceeds_code ?? ''
  return (
    <details open>
      <summary><strong>3. This year's additions and disposals</strong> <span className={styles.muted}>{adds.length} additions · {disps.length} disposals</span></summary>
      <ReadAssets taskKey={taskKey} />
      <h4 style={{ margin: '8px 0 4px' }}>Additions</h4>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Additions">
          <thead><tr><th>Asset</th><th>Category</th><th>Purchased</th><th>Available for use</th><th className={styles.num}>Cost</th><th>Source</th><th>Confirmed</th><th /></tr></thead>
          <tbody>
            {adds.map((a, i) => (
              <tr key={a.id ?? i}>
                <td className={styles.cell}><input aria-label="Asset" value={a.description} onChange={(ev) => setA(i, { description: ev.target.value })} /></td>
                <td className={styles.cell}><select aria-label="Addition category" value={a.category} onChange={(ev) => setA(i, { category: ev.target.value })}>{options}</select></td>
                <td className={styles.cell}><input type="date" aria-label="Purchase date" value={a.purchase_date} onChange={(ev) => setA(i, { purchase_date: ev.target.value })} /></td>
                <td className={styles.cell}><input type="date" aria-label="Available for use" value={a.available_date} onChange={(ev) => setA(i, { available_date: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Cost" inputMode="decimal" value={a.cost} onChange={(ev) => setA(i, { cost: ev.target.value })} /></td>
                <td className={styles.muted}>{a.source || 'Entered'}</td>
                <td><input type="checkbox" aria-label="Confirmed" checked={!!a.confirmed} onChange={(ev) => setA(i, { confirmed: ev.target.checked })} /></td>
                <td><Button size="sm" variant="subtle" aria-label="Remove addition" onClick={() => (setAdds(adds.filter((_, n) => n !== i)), setDirty(true))}><Trash2 size={13} /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button size="sm" variant="subtle" onClick={() => (setAdds([...adds, { description: '', category: '', purchase_date: '', available_date: '', cost: '', confirmed: true }]), setDirty(true))}><Plus size={13} /> Addition</Button>
      <h4 style={{ margin: '8px 0 4px' }}>Disposals</h4>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Disposals">
          <thead><tr><th>Asset</th><th>Category</th><th>Disposed</th><th className={styles.num}>Cost</th><th className={styles.num}>Acc. dep. at start of year</th><th className={styles.num}>Proceeds</th><th /></tr></thead>
          <tbody>
            {disps.map((x, i) => (
              <tr key={x.id ?? i}>
                <td className={styles.cell}><input aria-label="Disposed asset" value={x.description} onChange={(ev) => setD(i, { description: ev.target.value })} /></td>
                <td className={styles.cell}><select aria-label="Disposal category" value={x.category} onChange={(ev) => setD(i, { category: ev.target.value })}>{options}</select></td>
                <td className={styles.cell}><input type="date" aria-label="Disposal date" value={x.date} onChange={(ev) => setD(i, { date: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Disposal cost" inputMode="decimal" value={x.cost} onChange={(ev) => setD(i, { cost: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Accumulated depreciation at the start of the year" inputMode="decimal" value={x.accumulated_bf} onChange={(ev) => setD(i, { accumulated_bf: ev.target.value })} /></td>
                <td className={styles.cell}><input aria-label="Proceeds" inputMode="decimal" value={x.proceeds} onChange={(ev) => setD(i, { proceeds: ev.target.value })} /></td>
                <td><Button size="sm" variant="subtle" aria-label="Remove disposal" onClick={() => (setDisps(disps.filter((_, n) => n !== i)), setDirty(true))}><Trash2 size={13} /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.actions}>
        <Button size="sm" variant="subtle" onClick={() => (setDisps([...disps, { description: '', category: '', date: '', cost: '', accumulated_bf: '', proceeds: '' }]), setDirty(true))}><Plus size={13} /> Disposal</Button>
        {disps.length > 0 && (
          <label className={styles.field} style={{ minWidth: 260 }}>
            <span>The proceeds were posted to (if any)</span>
            <select value={proceedsCode} onChange={(ev) => save.mutate({ data: { ppe: { options: { proceeds_code: ev.target.value } } }, stage: 'fs' })}>
              <option value="">Not in the trial balance</option>
              {tb.map((t) => <option key={t.code} value={t.code}>{t.code} {t.name}</option>)}
            </select>
          </label>
        )}
        <span className={styles.spacer} />
        <Button size="sm" variant="primary" disabled={!dirty || save.isPending}
          onClick={() => save.mutate({ data: { ppe: { additions: adds, disposals: disps } }, stage: 'fs' }, { onSuccess: () => setDirty(false) })}>
          <Save size={13} /> Save additions and disposals
        </Button>
      </div>
      <p className={styles.hint} style={{ margin: 0 }}>{ppe.schedule.convention}</p>
      {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
    </details>
  )
}

/** Purchase invoices or a fixed asset register read by Local_Tax_AI into additions (or disposals) to confirm. */
function ReadAssets({ taskKey }: { taskKey: string }) {
  const { data: attachments = [] } = useAttachments(taskKey)
  const upload = useUploadAttachment(taskKey)
  const extract = useExtract(taskKey)
  const decide = useDecideExtraction(taskKey)
  const [pick, setPick] = useState('')
  const [read, setRead] = useState<Extraction | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const go = (id: number) => extract.mutate({ attachmentId: id, kind: 'fixed_assets' }, { onSuccess: (d) => setRead(d.extraction) })
  const busy = upload.isPending || extract.isPending || decide.isPending
  return (
    <div className={styles.card} style={{ background: 'var(--tf-surface-sunken)' }}>
      <div className={styles.actions}>
        <Sparkles size={14} aria-hidden="true" /> <strong>Read invoices or a fixed asset register with AI</strong>
        <select aria-label="Document to read" value={pick} onChange={(ev) => setPick(ev.target.value)}>
          <option value="">Choose a document of this card…</option>
          {attachments.map((a) => <option key={a.id} value={a.id}>{a.filename}</option>)}
        </select>
        <Button size="sm" variant="secondary" disabled={!pick || busy} onClick={() => go(Number(pick))}>{extract.isPending ? 'Reading…' : 'Read'}</Button>
        <input ref={input} type="file" hidden aria-label="Asset document" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.csv"
          onChange={async (ev) => { const f = ev.target.files?.[0]; ev.target.value = ''; if (f) go((await upload.mutateAsync(f)).id) }} />
        <Button size="sm" variant="subtle" disabled={busy} onClick={() => input.current?.click()}><Upload size={13} /> Upload and read</Button>
      </div>
      {(extract.isError || upload.isError) && <p className={styles.error}>{extractErrorMessage(extract.error ?? upload.error)}</p>}
      {read && (
        <>
          <p className={styles.muted} style={{ margin: 0 }}>{read.data.summary} — confirm before use; set each asset's available-for-use date after.</p>
          <div className={styles.tableWrap} style={{ maxHeight: 220 }}>
            <table className={styles.table}>
              <thead><tr><th>Asset</th><th>Date</th><th className={styles.num}>Amount</th><th>Where</th></tr></thead>
              <tbody>{read.data.lines.map((l, n) => <tr key={n}><td>{l.description}</td><td>{l.date}</td><td className={styles.num}>{money(l.amount)}</td><td>{l.cite}</td></tr>)}</tbody>
            </table>
          </div>
          <div className={styles.actions}>
            <Button size="sm" variant="primary" disabled={busy || !read.data.lines.length} onClick={() => decide.mutate({ id: read.id, decision: 'confirm', use_as: 'ppe_additions' }, { onSuccess: () => setRead(null) })}>Add as additions</Button>
            <Button size="sm" variant="secondary" disabled={busy || !read.data.lines.length} onClick={() => decide.mutate({ id: read.id, decision: 'confirm', use_as: 'ppe_disposals' }, { onSuccess: () => setRead(null) })}>Add as disposals</Button>
            <Button size="sm" variant="subtle" disabled={busy} onClick={() => decide.mutate({ id: read.id, decision: 'reject' }, { onSuccess: () => setRead(null) })}>Reject</Button>
          </div>
        </>
      )}
    </div>
  )
}

function Schedule({ ppe }: { ppe: PpeState }) {
  const s = ppe.schedule
  if (!s.available) return <p className={styles.muted}>{s.reason}</p>
  const t = s.totals
  return (
    <details open>
      <summary><strong>4. Depreciation schedule and PPE note</strong> <span className={styles.muted}>{s.start} to {s.end}</span></summary>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Depreciation schedule">
          <thead>
            <tr><th>Category</th><th className={styles.num}>Cost b/f</th><th className={styles.num}>Additions</th><th className={styles.num}>Disposals</th><th className={styles.num}>Cost c/f</th>
              <th className={styles.num}>Acc. dep. b/f</th><th className={styles.num}>Charge</th><th className={styles.num}>On disposals</th><th className={styles.num}>Acc. dep. c/f</th>
              <th className={styles.num}>NBV this year</th><th className={styles.num}>NBV last year</th></tr>
          </thead>
          <tbody>
            {s.categories.map((c) => (
              <tr key={c.key}>
                <th scope="row">{c.label}<div className={styles.muted}>{ppe.methods[c.method]} {pct(c.rate)}%{c.fully_depreciated ? ' · fully depreciated' : ''}</div></th>
                <td className={styles.num}>{money(c.cost.opening)}</td><td className={styles.num}>{money(c.cost.additions)}</td><td className={styles.num}>{money(-Number(c.cost.disposals))}</td>
                <td className={styles.num}>{money(c.cost.closing)}</td><td className={styles.num}>{money(c.accumulated.opening)}</td><td className={styles.num}><strong>{money(c.accumulated.charge)}</strong></td>
                <td className={styles.num}>{money(-Number(c.accumulated.disposals))}</td><td className={styles.num}>{money(c.accumulated.closing)}</td>
                <td className={styles.num}>{money(c.nbv.closing)}</td><td className={styles.num}>{money(c.nbv.opening)}</td>
              </tr>
            ))}
            {t && (
              <tr data-kind="total">
                <th scope="row">Total</th><td className={styles.num}>{money(t.cost_open)}</td><td className={styles.num}>{money(t.additions)}</td><td className={styles.num}>{money(-Number(t.disposals_cost))}</td>
                <td className={styles.num}>{money(t.cost_close)}</td><td className={styles.num}>{money(t.acc_open)}</td><td className={styles.num}><strong>{money(t.charge)}</strong></td>
                <td className={styles.num}>{money(-Number(t.acc_disposals))}</td><td className={styles.num}>{money(t.acc_close)}</td>
                <td className={styles.num}>{money(Number(t.cost_close) - Number(t.acc_close))}</td><td className={styles.num}>{money(Number(t.cost_open) - Number(t.acc_open))}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Month by month</summary>
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="Monthly depreciation">
            <thead><tr><th>Category</th>{s.months?.map((m) => <th key={m} className={styles.num}>{m}</th>)}</tr></thead>
            <tbody>
              {s.categories.map((c) => <tr key={c.key}><th scope="row">{c.label}</th>{c.monthly.map((v, i) => <td key={i} className={styles.num}>{money(v)}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      </details>
    </details>
  )
}

function JournalPreview({ ppe }: { ppe: PpeState }) {
  const j = ppe.journal
  return (
    <details open={ppe.status !== 'approved'}>
      <summary><strong>5-7. The depreciation journal</strong> <span className={styles.muted}>{ppe.status === 'approved' ? `posted as ${ppe.journal_ref || 'JE-DEP'}` : 'posted on approval'}</span></summary>
      {j.lines.length === 0 ? <p className={styles.muted}>Nothing to post: the trial balance already agrees with the schedule.</p> : (
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="Depreciation journal">
            <thead><tr><th>Account</th><th className={styles.num}>Debit</th><th className={styles.num}>Credit</th></tr></thead>
            <tbody>
              {j.lines.map((l) => {
                const a = Number(l.amount)
                return <tr key={l.code}><td style={{ paddingLeft: a < 0 ? 24 : 4 }}>{l.code} {l.name}</td><td className={styles.num}>{a > 0 ? money(a) : ''}</td><td className={styles.num}>{a < 0 ? money(-a) : ''}</td></tr>
              })}
            </tbody>
          </table>
        </div>
      )}
      {j.explain.map((x, i) => <p key={i} className={styles.hint} style={{ margin: 0 }}>{x}</p>)}
    </details>
  )
}
