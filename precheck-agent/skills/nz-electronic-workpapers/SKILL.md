---
name: nz-electronic-workpapers
description: AFIT's method for preparing the firm's CCH-style "Electronic Workpapers Static 2026" workbook (WP Agent) - B1 review summary, D1 journals, F1.1 bank, M1 accounts payable, Q1 taxation due, Q3a imputation credit account, S2 income, T2 investment income, V1 expenses, V2 use of home and V5 accounting fees - from the entity's own documents, evidence first, never forced to balance.
metadata:
  version: "1.0"
  source: "AFIT AI agent instructions - Electronic Workpapers Reconciliation 2026 (16 Nov 2026)"
---

# Electronic workpapers (New Zealand, CCH layout)

You read documents into fixed records and explain results; code computes every figure, writes only the
workbook's input cells and never a formula. GST (L1) is the separate GST reconciliation agent.

## Reading documents
- A document is used only if it names the entity (or its IRD number). Folders often hold other
  clients' or the owners' personal documents: set them aside, never mix them in.
- Read amounts exactly as printed, with their sign; dates as YYYY-MM-DD. Keep each figure's place
  (page, sheet and row). Gross, net, RWT and imputation credits are kept apart - never confuse gross
  interest, net interest and withholding tax.
- IRD's income summary is IRD's record of interest and dividends; a payer's statement agreeing with it
  confirms it. myIR shows an ICA credit balance as a negative figure.
- A dividend the company paid (minutes, its own dividend statement) is not a dividend received.
- An accountant's statement counts only when addressed to the entity.

## Preparing
- B1 takes each account's closing balance from the ledger (debit +) and last year's closing as the
  prior-year figure. An account that fits no workpaper is shown for review, never guessed.
- F1: one sheet per bank account (AFIT, 18 Nov 2026). Every bank reconciliation in the task folder and
  its subfolders is matched to its ledger bank account (by account number, else the ledger code or
  name); the number of bank accounts goes in the Workbench's bank quantity (M40) and each gets its own
  sheet, F1.1, F1.2 ..., in the order of B1's bank rows (bank # 1 is F1.1). A reconciliation for an
  account the ledger doesn't have still gets a sheet, flagged.
- Each F1 sheet: the bank's own statement balance at balance date; the software's reconciliation report
  is a fallback flagged for review. Unprocessed items, from that account's reconciliation, are entered
  as positive amounts. B1 takes each bank account's balance in the accounts on its own row.
- T2: interest and dividends gross, with RWT and imputation credits; if the ledger holds them net,
  propose a gross-up journal - never post it.
- Q1/Q3a: IRD's transactions decide what was paid and when; a ledger payment IRD doesn't show is
  flagged, not entered. The opening ICA is last year's closing from IRD or last year's return.
- V1: expenses by category from the ledger, flagging entertainment (50%), possible capital items,
  private items and vehicle use without a logbook.
- Missing evidence is missing: say what is needed. A difference stays a difference, with its reason.

## Summary
Plain New Zealand English for the reviewing accountant: each workpaper's status, the differences with
the ledger and what drives them, proposed journals (not posted), documents set aside, and the evidence
still needed. Use only the figures given.
