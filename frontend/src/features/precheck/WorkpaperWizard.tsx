import { ArrowLeft, ArrowRight, Check, FileSpreadsheet, X } from 'lucide-react'
import { useState } from 'react'

import styles from './WorkpaperWizard.module.css'
import { Button, Dialog, DialogContent } from '@/design-system'

export interface WorkpaperType {
  key: string
  title: string
  purpose: string
}

/** The electronic workpapers the agent can prepare, with what each one is for (L1 GST is the GST
 * reconciliation agent). */
export const EWP_WORKPAPERS: WorkpaperType[] = [
  { key: 'B1', title: 'Review summary', purpose: 'General ledger balances by workpaper, against the workpapers and last year' },
  { key: 'F1.1', title: 'Bank reconciliation', purpose: 'One reconciliation per bank account, from the statements and bank reconciliations' },
  { key: 'M1', title: 'Accounts payable', purpose: 'Creditors at balance date, against the ledger' },
  { key: 'Q1', title: 'Taxation due', purpose: 'Income tax payable or refundable, from IRD and the tax computation' },
  { key: 'Q3a', title: 'Imputation credit account', purpose: 'Credits and debits to the ICA for the year' },
  { key: 'S2', title: 'Income reconciliation', purpose: 'Sales and other income, against the GST returns' },
  { key: 'T2', title: 'Investment income', purpose: 'Interest and dividends received, gross, with tax deducted' },
  { key: 'V1', title: 'Expenses', purpose: 'Expense accounts reviewed for capital items, private use and non-deductibles' },
  { key: 'V2', title: 'Use of home as office', purpose: 'The home office claim and its apportionment' },
  { key: 'V5', title: 'Accounting fees', purpose: "The year's accounting fees, against the ledger" },
  { key: 'D1', title: 'Journals', purpose: 'Proposed journals from the other workpapers (not posted)' },
]

/** Choosing the workpapers to prepare (AFIT, 21 Nov 2026): one workpaper at a time - include it or leave it
 * out, then Next - until every workpaper has been seen; the last page lists the choice, ready to prepare. */
export function WorkpaperWizard({ open, onOpenChange, value, onDone, workpapers = EWP_WORKPAPERS }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  value: string[]
  /** The workpapers chosen; `prepare`: the person pressed "Prepare" on the last page. */
  onDone: (chosen: string[], prepare: boolean) => void
  workpapers?: WorkpaperType[]
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Choose the workpapers to prepare" maxWidth={560}>
        {/* Keyed by opening, so each time it starts at the first workpaper with the current choice. */}
        {open && <Steps workpapers={workpapers} initial={value} onDone={onDone} />}
      </DialogContent>
    </Dialog>
  )
}

function Steps({ workpapers, initial, onDone }: { workpapers: WorkpaperType[]; initial: string[]; onDone: (chosen: string[], prepare: boolean) => void }) {
  const [step, setStep] = useState(0)
  const [chosen, setChosen] = useState<Set<string>>(() => new Set(initial))
  const last = step === workpapers.length
  const current = workpapers[step]
  const picked = workpapers.filter((w) => chosen.has(w.key))
  const set = (key: string, on: boolean) =>
    setChosen((c) => {
      const next = new Set(c)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })
  const choose = (on: boolean) => {
    set(current.key, on)
    setStep((s) => s + 1)
  }

  return (
    <div className={styles.wizard}>
      <ol className={styles.progress} aria-label="Workpapers">
        {workpapers.map((w, i) => (
          <li key={w.key} data-state={i === step ? 'current' : chosen.has(w.key) ? 'in' : 'out'}>
            <button type="button" onClick={() => setStep(i)} aria-label={`${w.key} ${w.title}: ${chosen.has(w.key) ? 'included' : 'left out'}`}>
              {w.key}
            </button>
          </li>
        ))}
        <li data-state={last ? 'current' : 'out'}>
          <button type="button" onClick={() => setStep(workpapers.length)} aria-label="Summary">
            <Check size={12} aria-hidden="true" />
          </button>
        </li>
      </ol>

      {!last ? (
        <section className={styles.card} aria-label={`${current.key} ${current.title}`}>
          <p className={styles.count}>
            Workpaper {step + 1} of {workpapers.length}
          </p>
          <h3 className={styles.title}>
            <FileSpreadsheet size={18} aria-hidden="true" /> {current.key} — {current.title}
          </h3>
          <p className={styles.purpose}>{current.purpose}</p>
          <div className={styles.choice} role="radiogroup" aria-label={`Prepare ${current.key}?`}>
            <label data-on={chosen.has(current.key) || undefined}>
              <input type="radio" name={`wp-${current.key}`} checked={chosen.has(current.key)} onChange={() => set(current.key, true)} />
              <Check size={14} aria-hidden="true" /> Include
            </label>
            <label data-on={!chosen.has(current.key) || undefined}>
              <input type="radio" name={`wp-${current.key}`} checked={!chosen.has(current.key)} onChange={() => set(current.key, false)} />
              <X size={14} aria-hidden="true" /> Leave out
            </label>
          </div>
          <div className={styles.actions}>
            <Button type="button" variant="subtle" size="sm" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
              <ArrowLeft size={14} aria-hidden="true" /> Back
            </Button>
            <span className={styles.spacer} />
            <Button type="button" variant="subtle" size="sm" onClick={() => choose(false)}>
              Leave out and next
            </Button>
            <Button type="button" variant="primary" size="sm" onClick={() => setStep((s) => s + 1)}>
              Next <ArrowRight size={14} aria-hidden="true" />
            </Button>
          </div>
        </section>
      ) : (
        <section className={styles.card} aria-label="Summary">
          <h3 className={styles.title}>
            <Check size={18} aria-hidden="true" /> {picked.length} of {workpapers.length} workpapers to prepare
          </h3>
          {picked.length ? (
            <ul className={styles.summary}>
              {picked.map((w) => (
                <li key={w.key}>
                  <strong>{w.key}</strong> {w.title}
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.purpose}>None chosen: go back and include at least one.</p>
          )}
          <div className={styles.actions}>
            <Button type="button" variant="subtle" size="sm" onClick={() => setStep((s) => s - 1)}>
              <ArrowLeft size={14} aria-hidden="true" /> Back
            </Button>
            <span className={styles.spacer} />
            <Button type="button" variant="subtle" size="sm" disabled={!picked.length} onClick={() => onDone(picked.map((w) => w.key), false)}>
              Save the choice
            </Button>
            <Button type="button" variant="primary" size="sm" disabled={!picked.length} onClick={() => onDone(picked.map((w) => w.key), true)}>
              Prepare {picked.length} workpaper{picked.length === 1 ? '' : 's'}
            </Button>
          </div>
        </section>
      )}
    </div>
  )
}
