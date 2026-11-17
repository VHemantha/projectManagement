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
- F1.1: the bank's own statement balance at balance date; the software's reconciliation report is a
  fallback flagged for review. Unprocessed items are entered as positive amounts.
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
