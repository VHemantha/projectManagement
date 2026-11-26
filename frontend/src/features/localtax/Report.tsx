import { Check, FileDown, FileText, PenLine, RotateCcw } from 'lucide-react'
import { useState } from 'react'

import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type LocalTaxState, downloadLocalTax, useSaveLocalTax } from '@/api/localTax'
import { Button } from '@/design-system'

/** The practitioner's report (AFIT, 26 Nov 2026): the independent auditor's report or the compilation report - chosen in
 * Client Info - in the firm's own format, every paragraph editable, and downloaded as Word or PDF, apart from the
 * financial statements. */
export function ReportView({ taskKey, state }: { taskKey: string; state: LocalTaxState }) {
  const rep = state.report
  const save = useSaveLocalTax(taskKey)
  const [editing, setEditing] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  if (!rep) return <p className={styles.muted}>The report is prepared once the trial balance is in.</p>
  const edited = state.engagement.data.report_text?.[rep.kind] ?? {}
  const store = (key: string, value: string, done?: () => void) =>
    save.mutate({ data: { report_text: { ...(state.engagement.data.report_text ?? {}), [rep.kind]: { ...edited, [key]: value } } }, stage: 'fs' },
      { onSuccess: () => done?.() })
  const download = (fmt: 'docx' | 'pdf') => {
    setError('')
    downloadLocalTax(taskKey, 'report', fmt).catch((e) => setError(extractErrorMessage(e, 'The report could not be downloaded.')))
  }
  return (
    <>
      <div className={styles.actions} style={{ justifyContent: 'space-between' }}>
        <h3 className={styles.cardTitle} style={{ margin: 0 }}><FileText size={18} aria-hidden="true" /> {rep.label}</h3>
        <span className={styles.actions}>
          <Button size="sm" variant="secondary" onClick={() => download('docx')}><FileDown size={13} /> Word</Button>
          <Button size="sm" variant="secondary" onClick={() => download('pdf')}><FileDown size={13} /> PDF</Button>
        </span>
      </div>
      <p className={styles.hint} style={{ margin: 0 }}>
        In the firm&apos;s {rep.kind === 'audit' ? 'audit report' : 'compilation report'} format, issued apart from the financial statements. {rep.draft_note}{' '}
        Change the report type with the client details.
      </p>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <article className={styles.report} aria-label={rep.label}>
        {rep.sections.map((s) => (
          <section key={s.key} data-kind={s.kind} aria-label={`Report: ${s.key}`}>
            {editing === s.key ? (
              <div className={styles.field}>
                <textarea rows={s.kind === 'para' ? 5 : 2} value={text} aria-label={`Wording: ${s.key}`} onChange={(ev) => setText(ev.target.value)} />
                <div className={styles.actions}>
                  <Button size="sm" variant="primary" disabled={save.isPending || !text.trim()} onClick={() => store(s.key, text, () => setEditing(null))}>
                    <Check size={12} /> Save
                  </Button>
                  <Button size="sm" variant="subtle" onClick={() => setEditing(null)}>Cancel</Button>
                </div>
              </div>
            ) : (
              <div className={styles.reportPara}>
                {s.kind === 'heading' ? <h4>{s.text}</h4> : s.kind === 'title' ? <h3>{s.text}</h3> : <p>{s.text}</p>}
                <span className={styles.reportTools}>
                  {s.edited && <span className={styles.chip} data-status="approved">Edited</span>}
                  <Button size="sm" variant="subtle" iconOnly aria-label={`Edit: ${s.key}`} onClick={() => (setEditing(s.key), setText(s.text))}>
                    <PenLine size={12} />
                  </Button>
                  {s.edited && (
                    <Button size="sm" variant="subtle" iconOnly aria-label={`Use the format's wording: ${s.key}`} onClick={() => store(s.key, '')}>
                      <RotateCcw size={12} />
                    </Button>
                  )}
                </span>
              </div>
            )}
          </section>
        ))}
        <div className={styles.reportSign}>
          {rep.signature.map((l) => <strong key={l}>{l}</strong>)}
          <label className={styles.field} style={{ maxWidth: 220 }}>
            <span>Report date</span>
            <input type="date" value={state.engagement.data.report_date || rep.date}
              onChange={(ev) => save.mutate({ data: { report_date: ev.target.value }, stage: 'fs' })} />
          </label>
        </div>
      </article>
      {save.isError && <p className={styles.error}>{extractErrorMessage(save.error)}</p>}
    </>
  )
}
