---
name: nz-wages-reconciliation
description: AFIT's method for the year-end New Zealand wages (PAYE) reconciliation (WP Agent) - payroll expense from IRD employment information (gross earnings, net employer KiwiSaver, ESCT) bridged to the accrual P&L, and payroll liabilities from the IRD EMP account rolled forward to the balance date against the GL controls, concluded separately.
metadata:
  version: "1.0"
  source: "AFIT wages reconciliation agent specification, working draft 1.0 (7 Nov 2026)"
---

# Year-end wages reconciliation (New Zealand)

Two separate conclusions: payroll expense, and payroll liabilities. Code computes every figure; you
read documents and explain results.

## Reading IRD payroll documents
- The IRD payroll (employment information) summary has one row per month ending: gross earnings
  and/or schedular payments, not liable for ACC earners' levy, PAYE (incl. tax on schedular payments),
  child support, student loan, KiwiSaver deductions, net KiwiSaver employer contributions, ESCT, ESS,
  prior-period adjustments and total deductions. myIR writes dates month first (4/30/2025). Columns
  can continue on a later page in the same row order. A blank isn't automatically zero.
- The myIR transaction summary for the EMP account: period ending, account type (Payroll), date,
  transaction (PAYE deductions, KiwiSaver employee deductions, KiwiSaver employer contributions,
  superannuation contribution tax (ESCT), student loan, child support, payment) and amount (payments
  in brackets, i.e. negative).

## Payroll expense
- Baseline = employee gross earnings (schedular payments taken out) + net employer KiwiSaver + ESCT.
  If the employer field is already gross of ESCT, ESCT is not added again.
- PAYE, employee KiwiSaver, student loan and child support are deductions from gross: never extra expense.
- Bridge to the accrual P&L: add closing and deduct opening wage accruals; the leave provision
  movement only as far as it is charged to the selected expense.
- Expected expense against the mapped GL wages expense: reported, proposed corrections, adjusted.

## Payroll liabilities
- Opening payable + current-year charges - payments and credits to the balance date = IRD principal
  payable at the balance date. Later payments are settlement evidence only. Penalties and interest
  are kept apart. Missing history is not a nil opening balance.
- One EMP payment can settle several components: never allocate it to PAYE alone or twice.
- A payment charged to wages, income tax or suspense is a proposed journal (debit the payroll
  liability), not a timing item. Net wages payable is tested separately.

## Summary
Plain New Zealand English for the reviewing accountant: each conclusion's status and residual, what
drives it, proposed journals (not posted), and the evidence still needed. Use only the figures given.
