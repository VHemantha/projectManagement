# Local Tax AI Workflow: technical plan

This module brings a Sri Lankan income tax engagement into TASKO: **Questionnaire → Financial
Statements → Tax Computation → Draft Tax Return**. It is the AFIT requirement of 21–22 Nov 2026.

## 1. Scope rule: only the Local clients' cards

The workflow applies **only** to cards (tasks) in **Team 3 → Local**. Every other card keeps the
pre-check, guide, WP Agent and review exactly as they are.

- `clients.Client.workflow` is a new field, `"local_tax"` or `""`. A data migration sets it on the
  sub-workspace named *Local* in the workspace *Team 3*.
- A card is a Local Tax card when `issue.project.client.workflow == "local_tax"`. The task API
  exposes this as `workflow`.
- The frontend shows the Local Tax workflow in place of the AI workspace **only** for those cards.
- Every Local Tax API checks the flag and refuses any other card (HTTP 404).

## 2. Who does what

| Concern | Where | Why |
|---|---|---|
| Data, permissions, audit trail, versions | Django app `backend/apps/localtax` | Reuses TASKO's auth, task records, documents and access control |
| **All figures**: financial statements, tax, reverse calculation, return fields | Deterministic engine `backend/apps/localtax/engine/` | Pure Python, unit tested, recalculated on every edit, never the AI |
| Tax rules per year of assessment | `backend/apps/localtax/rules/*.json` | Versioned and dated, each rule with its legal reference and a `validated` flag |
| AI: reading documents, TB mapping suggestions, tax analysis, reverse-tax questions, return mapping, chat | **Local_Tax_AI**, a separate LangGraph + LangChain service (`local-tax-ai/`) | Separate from the pre-check agent, as AFIT asked |

### The AI never sets a figure

The AI gives structured answers (validated by pydantic in the service, then again in the
backend). They can be any of these:

- extracted lines, each citing its source document and waiting for the accountant to confirm;
- suggested TB mappings;
- explanations;
- questions to the accountant.

The engine computes every amount. A suggestion changes nothing until a person accepts it.

## 3. Data model (`apps/localtax`)

- **TaxEngagement**: one per card (1:1 with Issue). It holds:
  - entity type, residency, year of assessment, financial year-end, tax type;
  - basic details: legal name, TIN, NIC/registration, address, activity;
  - reporting framework, engagement type (audited/unaudited);
  - expected tax and its basis (total liability or remaining payable);
  - the questionnaire sections as validated JSON: income lines (incl. foreign), expenses by
    source, assets, liabilities, tax payments;
  - each of the four stages' status: Not Started → In Progress → Ready for Review → Approved.
- **TbLine**: the trial balance, current year and comparative, each line mapped to an FS heading.
  The mapping records who set it: rule, AI or person.
- **Adjustment**: journals, reclassifications, tax adjustments and reverse-tax corrections. Each
  keeps:
  - the original amount, proposed amount and difference;
  - its scope: accounting (changes profit) or tax-only (computation only);
  - the reason, the evidence (a card attachment) and its status: proposed → approved/rejected;
  - who and when.

  **Only approved adjustments reach the figures.**
- **Extraction**: what the AI read from an uploaded document. It cites the document and waits for
  confirmation before use.
- **EngagementEvent**: the audit trail of every change (user or AI): field, old → new, reason, when.

Figures are kept in four separate layers: **original** (as entered/uploaded), **hypothetical**
(reverse-tax scenarios, never stored as figures), **proposed** (adjustments awaiting approval) and
**approved final**.

## 4. Engine

- `rules.py` loads the year's rules. A missing rule is returned as a **flag for professional
  review**, never guessed.
- `fs.py` builds:
  - for companies: profit or loss, financial position and changes in equity from the mapped TB plus
    approved accounting adjustments, with comparatives, the balance check and unusual balances;
  - for individuals: the statement of income and expenses by source.
- `tax.py` does the full computation:
  - **Individuals:** employment, business, investment and other income; exempt and
    final-withholding income shown apart; expenses, qualifying payments, reliefs, losses; the
    progressive bands; special-rate income (e.g. qualifying foreign service income, only when its
    statutory conditions are ticked); credits and instalments (final WHT never credited);
    payable or refundable.
  - **Companies:** from profit before tax, add-backs, deductions, accounting depreciation
    reversed, capital allowances, losses, qualifying payments, rate by income category, credits,
    payable.
- `reverse.py` (reverse tax):
  - Expected vs calculated tax, on the basis the client gave (total or remaining).
  - The taxable income needed is found by solving the **complete** tax function (bisection), never
    by dividing by one rate.
  - For each selectable account or computation line, the change that alone would explain the
    difference, or "cannot explain it" when it can't.
  - The effect of a proposed correction: revised profit, taxable income, tax and remaining
    variance.
- `returns.py` maps approved figures to the draft return's fields and schedules from the year's
  return layout, and lists missing mandatory fields. The IRD field codes are placeholders marked
  **requires validation against the year's RAMIS return**.

## 5. Local_Tax_AI service (`local-tax-ai/`)

- FastAPI on 127.0.0.1:8300. It reuses the pre-check agent's virtualenv on the server (the same
  libraries), but is its own code, own process and own systemd unit (`trackflow-local-tax`).
- LangGraph graphs, one per agent:
  - **document**: read, classify, extract lines with citations, list gaps;
  - **fs_mapping**: suggest an FS heading per TB account and flag inconsistencies;
  - **tax_analysis**: classify income, suggest adjustments and reliefs with reasons and references,
    flag uncertain treatment;
  - **reverse_tax**: from the engine's variance and the engagement's accounts, ask targeted
    questions and rank the accounts to review;
  - **return_prep**: check the mapping and list gaps;
  - **chat**: engagement-aware questions and answers. A "what if" answer is marked hypothetical,
    with its figures from the engine.
- Every answer is a pydantic schema, validated before it is returned. Demo/fake mode is used for
  tests.
- It is called by the backend with a shared service token, and never by the browser.

## 6. UI (as AFIT's screens)

The Local Tax card shows the engagement overview: the four stage cards with status, checklist,
documents and progress; the tax summary; reverse tax analysis; and the AI assistant. Each stage
opens full screen with:

- the stage stepper;
- the section list on the left;
- the form or table in the middle (editable);
- the AI assistant and summary on the right.

There are Save, Review, Approve and Download (PDF and Excel) controls throughout.

## 7. Phases

1. **Foundation**: the scope flag, models, rules for YA 2024/25 and 2025/26, the engine (FS, tax,
   reverse, return) with tests, the API, Local_Tax_AI with its graphs, and the four-stage UI with
   PDF/Excel exports.
2. **Documents** (built): Local_Tax_AI reads a trial balance, general ledger, prior return / computation,
   fixed asset register, income or tax payment evidence into lines citing the document; nothing is used
   until a person confirms it and chooses what it is used as. A general ledger is summed by account (by
   code) into the TB; a prior return gives the prior-year figures and its losses carried forward (by year);
   a register fills the fixed asset register. A TB file the importer cannot read can be read by the AI
   instead, and unmapped accounts get AI heading suggestions as soon as the TB is in.
3. **Depth** (built), all by code (`engine/depth.py`, `engine/schedules.py`):
   - statement of changes in equity, statement of cash flows (indirect, reconciled to the cash movement);
   - notes (one per heading with its accounts, the income tax reconciliation, the notes only the accountant
     can write) and accounting policies (standard wording for the framework, tailored by the accountant,
     with Local_Tax_AI's suggestions);
   - capital allowance schedule from the fixed asset register (balancing charges/allowances on disposal)
     and the loss schedule by year of origin (oldest used first);
   - the return's schedules (capital allowances, losses, special-rate income, tax credits);
   - the draft auditor's report template on SLAuS 700 (always labelled draft; never an opinion);
   - all in the PDF/Excel exports.
4. **Validation** (built - the workflow; the review itself is a professional's): a validator (staff or the
   "Local tax rule validators" group) validates or corrects each rule with the legal reference relied on,
   and records each return field's RAMIS reference (`RuleReview`, `ReturnFieldReview`, every review kept).
   The engine uses the reviewed values. Local_Tax_AI can read a law document for a rule and say whether it
   agrees (assistance only). Approving the computation or the return on unvalidated rules needs an explicit
   acknowledgement, recorded in the audit trail. Review page: `/local-tax/rules/<ya>`.

## 8. What needs professional validation

Every rate, band, threshold, relief, capital allowance rate and return field code ships with
`"validated": false` and its legal reference. The UI shows "requires professional validation" next
to anything computed from an unvalidated rule, until a Sri Lankan tax professional marks it
validated.

## 9. Client Info, supporting documents and the house-format statements (added)

- **Client Info** (formerly the Questionnaire) has a **Supporting Documents** step: the trial balance upload (moved here),
  other documents uploaded directly, or the client's **Google Drive folder** linked once shared (Viewer) with TASKO's
  service account; *Sync now* copies new or changed files to the card (read-only).
- **Local_Tax_AI pre-fills** the client info from the documents (bank statements, bank balance confirmations, TBs,
  ledgers, prior returns, certificates): each value is a suggestion with its source (document and place); nothing is
  used until the accountant confirms it, as it is or edited, and it then flows to the statements and computation.
- **Flags** for what is missing, unclear or inconsistent - across documents (two TINs; two balances for one account on
  one date; several TBs), with the client info, with the year end, or bank balances against the TB's bank accounts.
- **Financial statements required**: income statement only, or the full set (the statements, checks and PDF follow).
- **PDF in AFIT's house format** (`fs_report.py`): cover, contents, auditor's report (a labelled template, never an
  opinion), comprehensive income statement, financial position with the certificate and directors' approval, changes
  in equity, cash flows, accounting policies and numbered notes (PPE movement by class).
- The workflow opens in a **full-screen window** from the card; *Back to AI Workflow* returns to the four boxes; every
  step has *Back* beside *Next*.
