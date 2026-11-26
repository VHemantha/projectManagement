import { CheckCircle2, Download, Sparkles, Upload } from 'lucide-react'
import { useRef, useState } from 'react'

import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import { useUploadAttachment } from '@/api/issues'
import { type Extraction, money, useDecideExtraction, useExtract, useUploadTb } from '@/api/localTax'
import { Button } from '@/design-system'

const TEMPLATE = 'Code,Account,Debit,Credit,Prior year\n4000,Sales,,50000000,-46200000\n5000,Cost of sales,32500000,,29800000\n1000,Bank,23900000,,0\n'

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([TEMPLATE], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = 'trial-balance-template.csv'
  a.click()
  URL.revokeObjectURL(url)
}

/** Upload the trial balance of a Local client's card (Excel or CSV), read by code into the financial statements.
 * A file whose columns the importer can't recognise (a PDF, a scan, an unusual layout) is attached to the task and
 * read by Local_Tax_AI instead - shown here to confirm before it replaces the trial balance. Uploading again
 * replaces the trial balance; a heading a person chose is kept for the same account code. */
export function TbUpload({ taskKey, accounts = 0, compact = false, variant = 'bar' }: {
  taskKey: string; accounts?: number; compact?: boolean
  /** "drop": the Supporting docs design - a drop zone with Choose file. */
  variant?: 'bar' | 'drop'
}) {
  const tb = useUploadTb(taskKey)
  const attach = useUploadAttachment(taskKey)
  const extract = useExtract(taskKey)
  const decide = useDecideExtraction(taskKey)
  const input = useRef<HTMLInputElement>(null)
  const [failed, setFailed] = useState<File | null>(null)
  const [read, setRead] = useState<Extraction | null>(null)

  const send = (file: File) => {
    setRead(null)
    if (!/\.(xlsx|xlsm|xls|csv|tsv|txt)$/i.test(file.name)) {
      setFailed(file)  // not a spreadsheet: only the AI can read it
      return
    }
    tb.mutate(file, { onError: () => setFailed(file), onSuccess: () => setFailed(null) })
  }
  const readWithAi = async (file: File) => {
    const att = await attach.mutateAsync(file)
    extract.mutate({ attachmentId: att.id, kind: 'trial_balance' }, { onSuccess: (d) => { setRead(d.extraction); setFailed(null) } })
  }
  const busy = tb.isPending || attach.isPending || extract.isPending || decide.isPending
  const [over, setOver] = useState(false)
  const picker = (
    <input ref={input} type="file" hidden aria-label="Trial balance file" accept=".xlsx,.xlsm,.xls,.csv,.tsv,.txt,.pdf,.png,.jpg,.jpeg"
      onChange={(ev) => { const f = ev.target.files?.[0]; if (f) send(f); ev.target.value = '' }} />
  )
  const results = (
    <>
      {tb.isSuccess && (
        <p className={styles.muted} role="status" style={{ margin: 0 }}>
          <CheckCircle2 size={13} aria-hidden="true" /> Trial balance read: {tb.data.financials?.tb?.length ?? 0} accounts.
          {(tb.data.financials?.unmapped?.length ?? 0) > 0 && ` ${tb.data.financials?.unmapped?.length} need a heading (TB Mapping).`}
        </p>
      )}
      {(tb.isError || failed) && (
        <div className={styles.actions}>
          {tb.isError && <span className={styles.error}>{extractErrorMessage(tb.error)}</span>}
          {failed && (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void readWithAi(failed)}>
              <Sparkles size={13} /> {extract.isPending ? 'Local_Tax_AI is reading…' : `Read ${failed.name} with Local_Tax_AI`}
            </Button>
          )}
        </div>
      )}
      {(attach.isError || extract.isError) && <p className={styles.error}>{extractErrorMessage(attach.error ?? extract.error)}</p>}
    </>
  )

  if (variant === 'drop') {
    return (
      <section className={styles.dropzone} data-over={over || undefined} aria-label="Upload the trial balance"
        onDragOver={(ev) => { ev.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
        onDrop={(ev) => { ev.preventDefault(); setOver(false); const f = ev.dataTransfer.files?.[0]; if (f) send(f) }}>
        {picker}
        <Upload size={22} className={styles.dropIcon} aria-hidden="true" />
        <strong>{accounts ? `${accounts} accounts loaded` : 'Upload a trial balance'}</strong>
        <span className={styles.muted}>{accounts ? 'Drop a new file to replace it. XLSX, CSV or PDF.' : 'Drag a file here. XLSX, CSV or PDF.'}</span>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => input.current?.click()}>
          {tb.isPending ? 'Reading…' : accounts ? 'Replace file' : 'Choose file'}
        </Button>
        <button type="button" className={styles.linkButton} onClick={downloadTemplate}><Download size={12} aria-hidden="true" /> Template (CSV)</button>
        {results}
        {read && <ReadByAi read={read} busy={busy} onConfirm={() => decide.mutate({ id: read.id, decision: 'confirm', use_as: 'trial_balance' }, { onSuccess: () => setRead(null) })}
          onReject={() => decide.mutate({ id: read.id, decision: 'reject' }, { onSuccess: () => setRead(null) })} error={decide.isError ? extractErrorMessage(decide.error) : ''} />}
      </section>
    )
  }

  return (
    <section className={styles.card} aria-label="Upload the trial balance">
      <div className={styles.actions}>
        <strong><Upload size={15} aria-hidden="true" /> Trial balance</strong>
        <span className={styles.muted}>{accounts ? `${accounts} accounts loaded — uploading again replaces them` : 'Not uploaded yet'}</span>
        <span className={styles.spacer} />
        {picker}
        <Button size="sm" variant="primary" disabled={busy} onClick={() => input.current?.click()}>
          <Upload size={13} /> {tb.isPending ? 'Reading…' : accounts ? 'Replace TB' : 'Upload TB'}
        </Button>
        {!compact && <Button size="sm" variant="subtle" onClick={downloadTemplate}><Download size={13} /> Template (CSV)</Button>}
      </div>
      {!compact && (
        <p className={styles.hint} style={{ margin: 0 }}>
          Excel (.xlsx or .xls) or CSV with the account (Code and Account / Account Name / Ledger) and its figures — Debit and Credit columns, one Amount or Balance column (credits negative, in brackets or marked Cr), or a column per year — and optionally Prior year. Read by code — the figures never pass through the AI.
          A PDF or scanned TB is read by Local_Tax_AI and shown for you to confirm.
        </p>
      )}
      {results}
      {read && <ReadByAi read={read} busy={busy} onConfirm={() => decide.mutate({ id: read.id, decision: 'confirm', use_as: 'trial_balance' }, { onSuccess: () => setRead(null) })}
        onReject={() => decide.mutate({ id: read.id, decision: 'reject' }, { onSuccess: () => setRead(null) })} error={decide.isError ? extractErrorMessage(decide.error) : ''} />}
    </section>
  )
}

/** A trial balance Local_Tax_AI read from a PDF or scan: shown to confirm before it replaces the trial balance. */
function ReadByAi({ read, busy, onConfirm, onReject, error }: { read: Extraction; busy: boolean; onConfirm: () => void; onReject: () => void; error: string }) {
  return (
        <div aria-label="Trial balance read by AI" style={{ alignSelf: 'stretch', textAlign: 'left' }}>
          <strong>Local_Tax_AI read {read.data.lines.length} accounts from {read.document} — confirm before use</strong>
          {read.data.gaps.length > 0 && <p className={styles.muted}>Gaps: {read.data.gaps.join('; ')}</p>}
          <div className={styles.tableWrap} style={{ maxHeight: 240 }}>
            <table className={styles.table}>
              <thead><tr><th>Code</th><th>Account</th><th className={styles.num}>Current</th><th className={styles.num}>Prior</th><th>Where</th></tr></thead>
              <tbody>
                {read.data.lines.map((ln, n) => (
                  <tr key={n}><td>{ln.code}</td><td>{ln.description}</td><td className={styles.num}>{money(ln.amount)}</td>
                    <td className={styles.num}>{ln.comparative ? money(ln.comparative) : ''}</td><td>{ln.cite}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className={styles.actions}>
            <Button size="sm" variant="primary" disabled={busy || !read.data.lines.length} onClick={onConfirm}>
              Confirm and use as the trial balance
            </Button>
            <Button size="sm" variant="subtle" disabled={busy} onClick={onReject}>Reject</Button>
          </div>
          {error && <p className={styles.error}>{error}</p>}
        </div>
  )
}
