import { Link2, Sparkles, Upload } from 'lucide-react'
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

/** Or generate one from instructions (AFIT, 26 Nov 2026): the accountant gives the account balances, opening balances or
 * adjustments - or tells the business's story - and Local_Tax_AI drafts the trial balance. The figures given are used as
 * given; the draft is previewed and added only when the accountant says so. A draft with figures the AI made up (a story)
 * is labelled DUMMY DATA wherever it is used. */
export function TbInstructions({ taskKey, state, onDraft }: { taskKey: string; state: LocalTaxState; onDraft: (draft: StoryTb) => void }) {
  const make = useTbStory(taskKey)
  const [text, setText] = useState(state.engagement.data.tb_source?.story ?? '')
  return (
    <div className={styles.genBox}>
      <strong>Or generate one from instructions</strong>
      <textarea rows={4} value={text} maxLength={4000} aria-label="Instructions for the trial balance" onChange={(ev) => setText(ev.target.value)}
        placeholder="Enter account balances, opening balances or adjustments..." />
      <div className={styles.genFoot}>
        <span className={styles.muted}>You will review the draft before it is added.</span>
        <VoiceButton language="en-IN" label="Speak the instructions"
          title="Say the balances or the story (Amazon Transcribe): the words appear in the box to check before the draft is made"
          onText={(t) => setText((s) => withSpoken(s, t).slice(0, 4000))} />
        <Button size="sm" variant="primary" className={styles.darkButton} disabled={text.trim().length < 20 || make.isPending} onClick={() => make.mutate(text, { onSuccess: onDraft })}>
          {make.isPending ? <><Sparkles size={13} /> Drafting…</> : 'Generate draft'}
        </Button>
      </div>
      {make.isError && <p className={styles.error}>{extractErrorMessage(make.error)}</p>}
    </div>
  )
}

/** The draft Local_Tax_AI made from the instructions, for the accountant to check and add (or discard). */
export function TbDraftPreview({ taskKey, state, preview, onDone }: { taskKey: string; state: LocalTaxState; preview: StoryTb; onDone: () => void }) {
  const use = useUseStoryTb(taskKey)
  const dummy = preview.made_up !== false
  return (
    <div aria-label="Draft trial balance preview" className={styles.genPreview}>
      <strong>{preview.rows.length} accounts — {dummy ? 'DUMMY DATA (figures made up by Local_Tax_AI), check before use' : 'drafted from your instructions, check before use'}</strong>
      {[...preview.assumptions, ...preview.notes].map((n) => <p key={n} className={styles.muted} style={{ margin: 0 }}>{n}</p>)}
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
          onClick={() => use.mutate({ rows: preview.rows, story: preview.story, made_up: dummy }, { onSuccess: onDone })}>
          {state.financials?.tb?.length ? 'Replace the trial balance with this draft' : 'Add as the trial balance'}{dummy ? ' (dummy data)' : ''}
        </Button>
        <Button size="sm" variant="subtle" onClick={onDone}>Discard</Button>
      </div>
      {use.isError && <p className={styles.error}>{extractErrorMessage(use.error)}</p>}
    </div>
  )
}

/** Last year's financial statements as this year's comparatives: a Google Drive link (shared with TASKO's service account)
 * or a document uploaded. Local_Tax_AI reads each figure; code proposes the trial balance account for each; the accountant
 * confirms the matches before they become the prior-year column (and the PPE note's figures the opening balances). */
export function PriorYearComparatives({ taskKey, state, bare = false }: { taskKey: string; state: LocalTaxState; bare?: boolean }) {
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
    <section className={bare ? styles.side : styles.card} style={bare ? { gap: 8 } : undefined} aria-label="Comparatives from last year's financial statements">
      {!bare && (
        <div className={styles.actions}>
          <Link2 size={15} aria-hidden="true" /> <strong>Comparatives from last year's financial statements</strong>
          {done && <span className={styles.muted}>— {done.accounts} accounts from {done.document} ({done.by})</span>}
        </div>
      )}
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
                        ) : m.action === 'ppe' ? <span className={styles.muted}>{ln.description}</span> : null}
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
