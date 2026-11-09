---
name: nz-gst-reconciliation
description: AFIT's method for the year-end New Zealand GST reconciliation (WP Agent) - reconcile GST outstanding per returns and IRD records to the GST control balance, with receivables/payables GST by basis, journals and late claims counted once, the import GST check, payment-coding corrections and the stop rule.
metadata:
  version: "1.0"
  source: "AFIT GST reconciliation agent specification, working draft 1.0 (7 Nov 2026) and amendments (8 Nov 2026)"
---

# Year-end GST reconciliation (New Zealand)

The reconciliation explains the difference between GST principal outstanding with Inland Revenue at
the balance date and the GST control balance in the financial statements. Every item has an
amount, a reason, a source and one treatment. Code computes every figure; you interpret documents
and explain results.

## The bridge
- Sign convention: GST payable positive, receivable negative.
- A: GST principal outstanding at the balance date, from returns, opening arrears and IRD
  settlements effective on or before the balance date. Penalties and use-of-money interest are not
  GST principal. A March liability paid in May is still outstanding at 31 March.
- B: GST on unpaid receivables recognised in the GL but not yet returned (added).
- C: GST on unpaid payables recognised in the GL but not yet claimed (deducted).
- D: other supported return and timing differences, at their incremental GST effect.
- E = A + B - C + D is the expected GST control balance; F is the reported GL balance plus approved
  correction effects; F - E is unexplained and should be zero.
- Never create a balancing figure, infer GST only from an account name, or treat a zero net
  difference as proof that every item is right.

## Receivables and payables
- The Xero ageing report with its GST column is the primary source: use the GST it reports.
  Without that column, pause the side and ask for the report again; the general ledger is the
  fallback only when the preparer says the report is unavailable.
- Basis: payments - add receivables GST and deduct payables GST; invoice - no automatic
  adjustment; hybrid (invoice for sales, payments for purchases) - payables only.
- Exclude non-GST balances (wages, PAYE, KiwiSaver, ESCT, income tax, GST itself) and zero-rated or
  exempt items. 3/23 (15/115) is an estimate only for a supported standard-rated GST-inclusive
  balance; never for an unknown or mixed total.

## Journals, late claims and import GST
- A journal created after the affected return was finalised is a candidate, not proof.
- One adjustment per underlying difference: a journal and a later late claim for the same
  transaction are one adjustment with two pieces of evidence. Equal amounts alone never prove a match.
- A late claim after year-end shows a year-end difference was later cleared; it does not erase it.
- Import GST: tell import GST apart from customs duty, freight, brokerage and other charges on the
  same invoice. Check it is in the GL GST account and in the return; never assume it is missing
  because it isn't in the ordinary purchases total.

## Payment coding
- IRD statements are the primary evidence of which period a payment settled.
- A GST payment debited to income tax, an income tax payment or a penalty debited to GST, is a
  financial statement correction (a proposed reclassification), not a timing item.

## Stop rule
If a residual remains unexplained, report it and the next evidence needed. Never offset unrelated
output and input errors. Escalate unsupported tax treatments to the accountant.

## Writing the summary
Plain New Zealand English, short, for the reviewing accountant: the status, what drives the bridge,
what is conditional on unposted corrections, and the evidence still needed. Use only the figures
given; do not compute new ones; do not say the reconciliation is clean when the status is not
Reconciled.
