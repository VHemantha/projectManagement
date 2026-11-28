import { BookOpenText, Link2, Sparkles, Upload } from 'lucide-react'
import { useRef, useState } from 'react'

import styles from './LocalTax.module.css'
import { HEADINGS } from './headings'
import { extractErrorMessage } from '@/api/errors'
import { useUploadAttachment } from '@/api/issues'
import {
  type Extraction,
  type LocalTaxState,
  type PriorProposal,
  type StoryTb,
  money,
  useApplyComparatives,
  useDecideExtraction,
  usePriorFs,
  useTbStory,
  useUseStoryTb,
} from '@/api/localTax'
import { Button } from '@/design-system'
import { withSpoken } from '@/api/coordinator'
import { VoiceButton } from '@/features/chat/VoiceButton'

const headingLabel = (h: string) => HEADINGS.find(([k]) => k === h)?.[1] ?? h

/** No trial balance yet (training, a demonstration, a quick illustration)? The accountant tells the business's story and
 * Local_Tax_AI makes up a dummy trial balance from it: previewed first, balanced by code, and labelled DUMMY DATA wherever
 * it is used - the statements are then prepared from it like any other trial balance. */
export function StoryTrialBalance({ taskKey, state }: { taskKey: string; state: LocalTaxState }) {
  const make = useTbStory(taskKey)
  const use = useUseStoryTb(taskKey)
  const [story, setStory] = useState(state.engagement.data.tb_source?.story ?? '')
  const [preview, setPreview] = useState<StoryTb | null>(null)
  const isDummy = state.engagement.data.tb_source?.kind === 'story'
  return (
    <details className={styles.card} open={isDummy}>
      <summary>
        <BookOpenText size={15} aria-hidden="true" /> <strong>Create a dummy trial balance from a story</strong>{' '}
        <span className={styles.muted}>{isDummy ? '— the trial balance in use is dummy data' : 'for training or a demonstration'}</span>
      </summary>
      <p className={styles.hint} style={{ margin: 0 }}>
        Describe the business: what it does, its size (e.g. sales of about LKR 30 million), how the year went, its assets, loans and staff. Local_Tax_AI makes up
        realistic figures for this year and last year. They are illustrative only — every statement made from them says DUMMY DATA. The year's depreciation is
        left to the PPE & Depreciation schedule.
      </p>
      <label className={`${styles.field} ${styles.wide}`}>
        <span>The story</span>
        <textarea rows={4} value={story} maxLength={4000} onChange={(ev) => setStory(ev.target.value)}
          placeholder="e.g. A family bakery in Kandy, two outlets, sales of about LKR 30 million (up 15%), bought a delivery van in July, a bank loan of LKR 5 million…" />
      </label>
      <div className={styles.actions}>
        <VoiceButton language="en-IN" label="Speak the story"
          title="Tell the story aloud (Amazon Transcribe): the words appear in the box to check before the trial balance is made"
          onText={(t) => setStory((s) => withSpoken(s, t).slice(0, 4000))} />
        <Button size="sm" variant="primary" disabled={story.trim().length < 20 || make.isPending} onClick={() => make.mutate(story, { onSuccess: setPreview })}>
          <Sparkles size={13} /> {make.isPending ? 'Making the trial balance…' : 'Make the trial balance'}
        </Button>
        {make.isError && <span className={styles.error}>{extractErrorMessage(make.error)}</span>}
      </div>
      {preview && (
        <div aria-label="Dummy trial balance preview">
          <strong>{preview.rows.length} accounts — DUMMY DATA, check before use</strong>
          {[...preview.assumptions, ...preview.notes].map((n, i) => <p key={i} className={styles.muted} style={{ margin: 0 }}>{n}</p>)}
          <div className={styles.tableWrap} style={{ maxHeight: 280 }}>
            <table className={styles.table}>
              <thead><tr><th>Code</th><th>Account</th><th>Heading</th><th className={styles.num}>This year</th><th className={styles.num}>Last year</th></tr></thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.code}><td>{r.code}</td><td>{r.name}</td><td>{headingLabel(r.heading)}</td><td className={styles.num}>{money(r.amount)}</td>
                    <td className={styles.num}>{money(r.comparative)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className={styles.actions}>
            <Button size="sm" variant="primary" disabled={use.isPending}
              onClick={() => use.mutate({ rows: preview.rows, story: preview.story }, { onSuccess: () => setPreview(null) })}>
              {state.financials?.tb?.length ? 'Replace the trial balance with this dummy one' : 'Use as the trial balance (dummy data)'}
            </Button>
            <Button size="sm" variant="subtle" onClick={() => setPreview(null)}>Discard</Button>
          </div>
          {use.isError && <p className={styles.error}>{extractErrorMessage(use.error)}</p>}
        </div>
      )}
    </details>
  )
}

/** Last year's financial statements as this year's comparatives: a Google Drive link (shared with TASKO's service account)
 * or a document uploaded. Local_Tax_AI reads each figure; code proposes the trial balance account for each; the accountant
 * confirms the matches before they become the prior-year column (and the PPE note's figures the opening balances). */
export function PriorYearComparatives({ taskKey, state }: { taskKey: string; state: LocalTaxState }) {
  const read = usePriorFs(taskKey)
  const apply = useApplyComparatives(taskKey)
  const reject = useDecideExtraction(taskKey)
  const upload = useUploadAttachment(taskKey)
  const input = useRef<HTMLInputElement>(null)
  const [link, setLink] = useState('')
  const [ex, setEx] = useState<Extraction | null>(null)
  const [map, setMap] = useState<PriorProposal[]>([])
  const tb = state.financials?.tb ?? []
  const done = state.engagement.data.comparatives_source
  const got = (d: { extraction: Extraction }) => (setEx(d.extraction), setMap(d.extraction.data.proposals ?? []))
  const busy = read.isPending || apply.isPending || upload.isPending
  const set = (i: number, p: Partial<PriorProposal>) => setMap(map.map((m) => (m.index === i ? { ...m, ...p } : m)))
  return (
    <section className={styles.card} aria-label="Comparatives from last year's financial statements">
      <div className={styles.actions}>
        <Link2 size={15} aria-hidden="true" /> <strong>Comparatives from last year's financial statements</strong>
        {done && <span className={styles.muted}>— {done.accounts} accounts from {done.document} ({done.by})</span>}
      </div>
      {!tb.length ? <p className={styles.muted} style={{ margin: 0 }}>Load this year's trial balance first: last year's figures are matched to its accounts.</p> : (
        <div className={styles.actions}>
          <input aria-label="Google Drive link to last year's financial statements" style={{ flex: 1, minWidth: 260 }} value={link} onChange={(ev) => setLink(ev.target.value)}
            placeholder="https://drive.google.com/file/d/… (shared with TASKO)" />
          <Button size="sm" variant="primary" disabled={!link.trim() || busy} onClick={() => read.mutate({ link }, { onSuccess: got })}>
            <Sparkles size={13} /> {read.isPending ? 'Reading…' : 'Read from the link'}
          </Button>
          <input ref={input} type="file" hidden aria-label="Last year's financial statements" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.docx"
            onChange={async (ev) => { const f = ev.target.files?.[0]; ev.target.value = ''; if (f) read.mutate({ attachment_id: (await upload.mutateAsync(f)).id }, { onSuccess: got }) }} />
          <Button size="sm" variant="subtle" disabled={busy} onClick={() => input.current?.click()}><Upload size={13} /> Upload instead</Button>
        </div>
      )}
      {(read.isError || upload.isError) && <p className={styles.error}>{extractErrorMessage(read.error ?? upload.error)}</p>}
      {ex && (
        <>
          <p className={styles.muted} style={{ margin: 0 }}>{ex.data.summary} — check each match; nothing changes until you apply them.</p>
          <div className={styles.tableWrap} style={{ maxHeight: 340 }}>
            <table className={styles.table} aria-label="Last year's figures and their accounts">
              <thead><tr><th>Line in last year's statements</th><th className={styles.num}>Amount</th><th>Use as</th><th>Account / heading</th></tr></thead>
              <tbody>
                {ex.data.lines.map((ln, i) => {
                  const m = map.find((x) => x.index === i) ?? { index: i, action: 'ignore' as const, code: '', heading: '' }
                  return (
                    <tr key={i}>
                      <td>{ln.description}<div className={styles.muted}>{ln.cite}{m.why ? ` · ${m.why}` : ''}</div></td>
                      <td className={styles.num}>{money(ln.amount)}</td>
                      <td className={styles.cell}>
                        <select aria-label={`Use of ${ln.description}`} value={m.action} onChange={(ev) => set(i, { action: ev.target.value as PriorProposal['action'] })}>
                          <option value="match">An account of this year's TB</option>
                          <option value="new">A new account</option>
                          <option value="ppe">PPE note (opening balances)</option>
                          <option value="cash_flow">Cash flow comparative</option>
                          <option value="ignore">Ignore</option>
                        </select>
                      </td>
                      <td className={styles.cell}>
                        {m.action === 'match' ? (
                          <select aria-label={`Account for ${ln.description}`} value={m.code} onChange={(ev) => set(i, { code: ev.target.value })}>
                            <option value="">Choose…</option>
                            {tb.map((t) => <option key={t.code} value={t.code}>{t.code} {t.name}</option>)}
                          </select>
                        ) : m.action === 'new' ? (
                          <select aria-label={`Heading for ${ln.description}`} value={m.heading} onChange={(ev) => set(i, { heading: ev.target.value })}>
                            <option value="">Heading…</option>
                            {HEADINGS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
                          </select>
                        ) : m.action === 'ppe' || m.action === 'cash_flow' ? <span className={styles.muted}>{ln.description}</span> : null}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className={styles.actions}>
            <Button size="sm" variant="primary" disabled={busy || map.some((m) => m.action === 'match' && !m.code)}
              onClick={() => apply.mutate({ id: ex.id, mapping: map }, { onSuccess: () => setEx(null) })}>Apply as this year's comparatives</Button>
            <Button size="sm" variant="subtle" disabled={busy} onClick={() => reject.mutate({ id: ex.id, decision: 'reject' }, { onSuccess: () => setEx(null) })}>Discard</Button>
          </div>
          {apply.isError && <p className={styles.error}>{extractErrorMessage(apply.error)}</p>}
        </>
      )}
      {done?.notes?.length ? done.notes.map((n, i) => <p key={i} className={styles.hint} style={{ margin: 0 }}>{n}</p>) : null}
    </section>
  )
}
