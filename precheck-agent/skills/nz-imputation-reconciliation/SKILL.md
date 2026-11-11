---
name: nz-imputation-reconciliation
description: AFIT's method for the New Zealand imputation credit account (ICA) reconciliation (WP Agent) - the ICA movement statement (opening + credits - debits) and the reconciliation of the closing ICA, with net current tax, grossed up at 72/28, to retained earnings with permanent and timing differences and historical-rate differentials.
metadata:
  version: "1.0"
  source: "AFIT imputation reconciliation agent specification, working draft 1.0 (7 Nov 2026); AFIT's ICA workpaper layout (10 Nov 2026)"
---

# Imputation (ICA) reconciliation (New Zealand)

The ICA is a tax memorandum account, not an asset or retained earnings. Its balance need not equal
28/72 of retained earnings; the conversion is a starting point. Never force agreement or invent a
balancing journal. Code computes every figure; you read documents and explain results.

## A — the ICA movement statement
- Opening (last year's closing ICA return) + credits - debits = closing. A debit balance is shown as
  negative and needs review (further income tax and an imputation penalty may follow).
- Credits: New Zealand income tax paid (principal only - use-of-money interest and penalties never
  count), RWT deducted from interest or dividends received by the company, imputation credits on
  dividends received. FDP is legacy (repealed): flag it, never treat it as routine.
- Debits: income tax refunded, imputation credits attached to dividends paid.
- RWT the company withholds and pays for others is not its own credit. Australian franking credits
  aren't NZ imputation credits. A tax assessment alone isn't a payment.

## B — closing ICA to retained earnings
- Balance = closing ICA + end-of-year terminal tax still to pay (a refund as negative) + Prov 3 tax
  still to pay (only if not already in the net tax payable) + other adjustments.
- Grossed up at exactly 72/28 (the ratio shows as 0.3889). Compare with tax-paid retained profit =
  retained profit + cumulative permanent differences (non-deductible expenses +, non-taxable income -)
  + cumulative timing differences + the 33% and 30% retained-earnings differentials. Difference =
  grossed up - tax-paid retained profit; missing credits = difference x 28/72.
- Historical rates: 33% to 2007-08, 30% 2008-09 to 2010-11, 28% from 2011-12. Use substantiated
  remaining credits only; never reconstruct pools from the closing ICA.

## Summary
Plain New Zealand English: the closing ICA, the difference and missing credits, what drives them,
and the evidence still needed. Use only the figures given.
