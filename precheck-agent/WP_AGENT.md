# WP Agent — GST reconciliation

The first workpaper agent on the task card, next to the Guide. It implements AFIT's *GST
reconciliation agent — process and functional specification* (working draft 1.0, 7 Nov 2026)
with the amendments of 8 Nov 2026 (ageing-report GST, GL fallback, import GST check, the GST
column pre-check and the journal / late-claim duplicate check). It reconciles GST outstanding
per returns and IRD records at the balance date to the GST control balance in the financial
statements, and produces an editable Excel workpaper laid out as the firm's CCH *L1 GST
reconciliation* sheet, with the supporting schedules behind it.

It prepares workpapers and proposed journals only. It never posts a journal, files a return,
writes to Drive or marks anything reviewed.

## 1. How a person uses it

1. On the task card, **AI assistant → WP Agent**.
2. Paste the **Google Drive link** of the folder holding the documents (or several links,
   separated by `;`). Optional: separate links for the year-end **AR and AP ageing reports**.
3. Check the **job settings**: entity, IRD number, financial year start and balance date, GST
   basis, filing frequency, software, currency, GL version, GST control account(s), first-year
   entity. Values detected from the documents are shown beside them; the accountant's values win.
4. **Run reconciliation.** Progress is shown step by step. The result: status, the A–F bridge,
   exceptions with the next evidence needed, proposed corrections, and **Download workpaper (Excel)**.
5. If an ageing report has no GST column, that side **pauses** with AFIT's message and two
   actions: *Upload revised report* (a new link, run again) or *GST-inclusive report unavailable —
   continue with GL analysis* (recorded, and the GL fallback is used for that side only).

## 2. Where it runs

| Part | Where | What |
|---|---|---|
| Panel, launcher, download | `frontend/src/features/precheck/WpAgentPanel.tsx` | Inputs, progress, result, workbook download |
| Run record and workbook | backend `AIPrecheck` (kind `gst`), fields `options`, `gst`, `workbook` | Every run kept; workbook stored with its run |
| API | `GET/POST /api/precheck/jobs/<key>/wp-agent/`, `GET /api/precheck/runs/<id>/workpaper.xlsx` | Same permission as the task |
| Agent | `precheck_agent/gst/` in this service, mode `gst` | Reads Drive (read-only), extracts, reconciles, writes the workbook |
| Skills | `skills/nz-gst-reconciliation`, `skills/gst-document-reading` | Method rules and reading rules given to the model where it is used |

## 3. The run (one pass, deterministic where it counts)

`gather → classify → extract → check uploads → returns & settlements (A) → receivables / payables GST
(B, C) → journals, late claims, import GST (D) → payment matching and corrections (F) → period analysis
→ bridge, status → workbook`

* **AI is used for** reading documents (classifying a file whose name and headings don't say what
  it is; mapping unusual column headings; reading PDFs — IRD return summaries, IRD statements,
  prior-year workpapers, late-claim detail), telling import GST apart from duty or freight, and
  writing the plain-language summary. Every AI-read value keeps its source (file, page/sheet, row).
* **Code does** every sum, sign, date filter, allocation, match, duplicate check and the bridge,
  with `Decimal` arithmetic. Item ids are derived from their sources, so an unchanged rerun gives
  the same totals and the same ids.

Sign convention throughout: GST payable positive, receivable negative; original debit/credit kept.

### Component A — GST principal outstanding at balance date
* One row per return period (current year and older unsettled periods), latest version used,
  original kept. Net GST checked as output + Box 9 − input − Box 13 (a source giving only
  Box 10/14 totals is flagged, so adjustments aren't added twice).
* IRD statement lines allocated to periods by IRD's own period reference — never because amounts
  agree. Principal kept apart from penalties and use-of-money interest. Settlements effective on or
  before the balance date reduce the period; later ones are shown in a separate column.
* The return for the period ending at the balance date is included even when filed later. A
  missing return is an exception, never zero; a nil return is distinguished from a missing one.
* Due dates (28th of the next month; 7 May for March; 15 January for November) separate overdue
  from not yet due.

### Components B and C — receivables and payables GST
* **Primary source: the Xero AR/AP ageing reports with the GST column.** The reported GST is used
  as is (no 3/23 recalculation), each customer/supplier kept with its source row. The ageing
  totals are agreed to the GL control accounts; differences are exceptions.
* **GST column pre-check**, each report on its own: no GST column → that side pauses with AFIT's
  message; a column of zeros is valid and is not a missing column.
* **GL fallback** (only when the preparer chooses it): the AR/AP control account in the full GL is
  traced invoice by invoice — invoices, receipts/payments and credit notes by reference, with the
  GST and tax codes posted with each — and every balance is put in one of: *contains GST*,
  *zero-rated / exempt / no GST*, *mixed*, *unresolved*. Wages, PAYE, KiwiSaver, ESCT, income tax and
  GST itself are excluded. 3/23 (15/115) is used only as a labelled estimate for a supported,
  standard-rated, GST-inclusive balance with no GST amount; never on an unknown or mixed total.
* Basis rules: payments — add receivables GST, deduct payables GST; invoice — no automatic
  adjustment; hybrid — payables only. Items already returned or claimed are excluded.

### Component D — journals, late claims and import GST
* Journals with an effective date at or before the balance date that change GST and were
  created after the affected return was finalised (actual filed date; the due date only as a
  flagged fallback) are candidates, not proof.
* Late claims in later returns for transactions of the year: one adjustment per underlying
  difference. A late claim and a journal are matched on reference, GST amount, contact,
  description, period and direction — an equal amount alone is never enough. A match links the
  late claim as evidence (no second amount); a part match adds only the unmatched part; an
  uncertain match is flagged. Order of processing does not change the result. Ordinary later
  settlement of an unpaid invoice is not a correction. Prior-year late claims are evidence only.
* **Import GST check**: GL lines described or coded as import GST / GST on imports / Customs GST
  are each checked (import GST and not duty or freight; in the GL GST account; in the return;
  timing). Classified as matched, GL-only (reconciling item or return correction), return-only
  (accounting correction), documented but absent from both (review), or evidence insufficient
  (request Customs / broker documents). Shown on its own schedule; counted once if it is also a
  payable or late-claim item. Nothing is assumed when no import GST is found.

### Component F — the GL, payment coding and corrections
* Reported GST control balance from the trial balance (several GST accounts consolidated).
* IRD payments and refunds matched to the full GL. A GST payment found in income tax, an income
  tax payment or penalty/interest found in GST, become **proposed corrections** (debit/credit,
  accounts, amount, evidence, *proposed — not posted*). A payment missing from the books asks for
  bank evidence instead of proposing an entry. Adjusted balance = reported + correction effects;
  both are shown.

### Bridge and status
`E = A + B − C + D`, `unexplained = F − E`, tolerance 0 unless configured. Statuses:
**Reconciled**, **Reconciled subject to corrections**, **Unreconciled**, **Incomplete evidence**
(missing or contradictory support, a paused side, a missing return — even when amounts net to
zero). The stop rule applies: an unexplained residual is reported with the next evidence needed;
nothing is offset or manufactured.

## 4. The workpaper (Excel)

1. **L1 GST reconciliation** — the CCH layout of the firm's template: header (firm, client,
   prep date, balance date, prepared/reviewed by), accounting basis and period, *GST return
   information* by period (total outputs, output tax, prior-year adjustments, Box 9, total inputs,
   input tax, prior-year adjustments, Box 13, (payment)/refund, paid/received at balance date),
   totals, GL output/input tax and variance, *GST ledger information*, *Timing differences*
   (returns outstanding at balance date L1.1, prior-year periods, accounts receivable G1, accounts
   payable M1, unprocessed payments/receipts, GST since last return, cash on hand, income in
   advance) and *Adjustments required* (income not declared / declared in error, expenses not
   claimed / claimed in error, private use, other adjustments incl. entertainment V1, FBT T1, use
   of home V2, capital adjustments, return variance), total adjustments, total, ledger totals and
   variance. Totals are Excel formulas, so the sheet stays editable.
2. **Summary** — the A–F bridge, reported and adjusted GL, status, open exceptions, outstanding
   returns, source coverage, preparation cut-off, run id and versions.
3. **L1.1 Returns & settlements**, **Opening items**, **G1 Receivables GST**, **M1 Payables GST**,
   **Import GST**, **Journals & late claims**, **Payment matching**, **Proposed corrections**,
   **Period analysis**, **Exceptions & evidence**, **Sources**.

## 5. Acceptance scenarios (tests)

March return paid in May · prior-year arrears partly settled · return assessed after year-end ·
GST payment coded to income tax · one correction in a journal and a late claim (one $150, not
$300) · part-paid and zero-rated debtors/creditors · invoice and hybrid basis · missing GST column
(pause; zeros are not missing) · import GST found only in the GL · missing return (incomplete
evidence) · several GST accounts · an unchanged rerun gives the same totals and item ids.

## 6. Decisions for AFIT review

Supported bases in release 1 (all three are implemented; special transactions, registration and
basis changes are routed to review); rounding tolerance (0 by default, shown); who may approve
corrections (proposed only in release 1); the representative job set for speed and accuracy;
carrying a structured closing reconciliation forward to next year (the result is stored in a
form that allows it).

## 7. Ask knows the WP Agent's work (10 Nov 2026)

Every finished reconciliation is kept in the knowledge store (ChromaDB) as entries of its own kind,
`wp_gst`, tagged with the task card's place — the same technique as the review's record — beside the
pre-check's result (`precheck_result`) and the preparation guide (`guide`), each kept apart
(`precheck_agent/memory.py`). One entry per fact: the status and summary, each bridge component, each
return period, each receivable and payable line, each exception, proposed correction, adjustment and
import GST item, and each document read. A new run replaces the task's entries; an unchanged result
isn't stored again; the PM application also sends the latest results with each question, so runs from
before this, or a restored store, are brought in step.

Ask first puts a question in its area — the WP Agent's GST reconciliation, the pre-check, the guide,
the review, or the documents (`ask.areas_of`) — searches that area's entries first (by meaning and by
the question's own words), tells the model which area it is answering, and labels each passage with
the agent it came from. The tags keep one client's results away from another's.


## 8. Wages (PAYE) and imputation (ICA) reconciliation agents (10 Nov 2026)

The WP Agent panel has a radio button for the reconciliation agent: **GST reconciliation**, **Wages
(PAYE) reconciliation** or **Imputation (ICA) reconciliation**. Each has its own settings, runs,
workpaper and latest result (backend kinds `gst`, `wages`, `ica`; `GET/POST .../wp-agent/?agent=`).
They share the GST agent's Drive reading, AI document classification and workbook styling
(`precheck_agent/wp/base.py`, `wp/sheets.py`); the figures are computed in code.

| Agent | Code / skill | Documents | Workpaper |
| --- | --- | --- | --- |
| Wages | `wp/wages.py`, `skills/nz-wages-reconciliation` (rules `wages-1.0`) | IRD payroll (employment information) summary, myIR EMP transaction summary (month-first dates), TB, GL, journals, payroll register, prior-year workpaper | Summary (two conclusions), IRD monthly totals, GL mapping, IRD settlements, liability roll-forward, accruals & prior year, monthly differences, proposed journals, exceptions, sources |
| ICA | `wp/ica.py`, `skills/nz-imputation-reconciliation` (rules `ica-1.0`) | Prior ICA return/workpaper, IRD income tax transactions, income summary / dividends, tax computation, statements, TB, GL | "Imputation Credits" and "Reconcile ICA to RE" in the firm's layout, then movements, tax payments & balances, dividends & income, historical rates, exceptions, sources |

- **Wages:** expense baseline = gross (less schedular payments) + net employer KiwiSaver + ESCT,
  bridged for accruals; liabilities = opening + current-year charges − payments to the balance date.
  Payments charged to wages, income tax or suspense are proposed journals (not posted). No opening
  balance and no prior-year evidence → liabilities "Incomplete evidence", never nil.
- **ICA:** opening + credits (income tax paid, RWT, imputation credits received) − debits (refunds,
  credits attached to dividends paid) = closing; UOMI and penalties are excluded. The closing balance
  with terminal and Prov 3 tax is grossed up at exactly 72/28 (shown as 0.3889) and compared with
  tax-paid retained profit; missing credits = difference × 28/72. Because the exact ratio is used,
  figures can differ by cents from a workpaper that multiplies by a rounded 0.3889 (e.g. 2,837.65
  vs 2,837.57 on the sample).
- Ask stores each result as its own kind (`wp_wages`, `wp_ica`) and routes payroll/PAYE questions
  and imputation/retained-earnings questions to them.
