# precheck-agent

The AI assistant for AFIT Connect's accountants, on every task card, in three tabs:

- **Pre-check** — before the accounts are prepared: checks the three documents nothing can start
  without, decides the client's business nature, and lists what is still needed, each with its
  reason, plus a drafted email to the client.
- **Review** — once the preparer has drafted the financial statements: reviews them round after
  round against last year's signed statements, the documents received and the preparer's
  assumptions and judgements; the reviewer responds to every finding, and only the reviewer
  completes the review.
- **Ask** — any question about the task, answered only from the task's own knowledge, with the
  passages each answer rests on.

Every correction a person makes teaches it: the AI drafts the correction as a rule (a learned
skill) that applies from then on — to that client at once, more widely once a lead approves.
It never sends an email, never marks a task reviewed, never edits workpapers and never writes
to Drive.

## How it works

A separate service (FastAPI + LangGraph). The PM application calls `POST /precheck/runs` and
gets a run id at once; progress and the result come back as events.

`load_job -> sync_drive -> index -> run_rules -> key_documents -> [precheck] -> publish`

1. **Key documents, by code.** This year's client questionnaire, last year's financial
   statements and last year's workpapers (`keydocs.py`). If any is missing the run stops there:
   the result is Blocked, and code drafts the email asking for what is missing, with the reason.
   No model is called. Last year's questionnaire does not count as this year's.
   A person can say on the task card where each one is: a path inside the task folder (a file
   or a folder, zips included; folders above the task folder are ignored) or a Drive file or
   folder link, several separated by ";". That decides the document whatever its name or year.
   A place that holds nothing blocks the run as a mistake to correct on the card, and the
   client is not asked for it.
2. **The pre-check, one Opus call** (`precheck.py`, `PRECHECK_PRECHECK_MODEL`, structured
   output). Its input is built by code, every line with an id: the questionnaire (Q), last
   year's statements (F) and trial balance (T), the workpapers (W), the files received (D),
   this year's other documents (R), each bank export summarised by code (B, and B.n by payer and
   payee), the checks code can answer (C: opening balance against last year's closing, bank
   data covering the year, the rules), the Direction Note if there is one (N) and the lessons
   people taught (L). Its instructions are the skills: `precheck-method` plus the one for the
   business nature: `nz-residential-rental` (AFIT's rental rules: property manager or owner
   managed, property details, invoices for expenses and accruals (else the manager statement,
   else a request) and for body corporate, loans and refinancing, rent bond, short-term rental
   statements, a sold property's remaining assets to drawings (a preparer note), items over $1,000; NZ interest deductibility, bright-line, ring-fencing), `nz-general-business` or
   `nz-investment`. The model decides the type from the questionnaire and last year's accounts
   unless the task's setup fixes it.
3. **Code checks the answer.** Ids that do not exist are dropped; an item "already provided"
   without naming a file becomes a request; a reason with a figure not in the documents is
   flagged; duplicates are removed. The decision (Requests to send / Ready) and the email are
   made by code from the checked list. Every source links to its place in the document.

**Teaching it.** On the task card a person can correct an item (not needed, wrong reason) or
add one that was missed. The lesson applies to this client at once. "Apply to all clients of
this type" waits until a lead or admin approves it. Active lessons are given to the model on
every run (L lines) and the result lists the lessons it applied. Nothing is trained.

**The knowledge store (ChromaDB).** Everything the AI searches lives in ChromaDB, open source,
embedded in this service, with its data in a folder on the server (`PRECHECK_CHROMA_PATH`, in the
nightly backup): every document chunk, the preparer's assumptions, review findings, the
reviewer's feedback and the learned rules. Every entry is tagged with where the task card sits —
**team** (Workspace), **vendor** (Sub-workspace, the client), **project** and **task** — plus what it
is (source type, document class, this year / last year). A search filters on those tags first,
from the card's own place, and only then compares meaning among what is left; the filter is part
of the query, never of a prompt. Documents never leave their vendor (code refuses a wider
search); only learned rules may be shared across a team or the firm. Embeddings are made on the
server by a small local model (`fastembed`, BAAI/bge-small-en-v1.5, about 180 MB, loaded on first
use), so client text never leaves the server for indexing. Postgres in the PM application stays
the record for everything people decide (finding status, responses, approvals, the audit trail);
ChromaDB is kept in step with it on every run. A file counts as indexed only when its chunks are
really in ChromaDB, so a lost or restored store is rebuilt from the cached parse (no image is
read again).

**The review** (`review.py`, `mode: "review"`, one Opus call per round). The draft statements are
found in the folder (this year's financial statements) or where the task card says. The input:
the draft line by line with its comparatives (S), this year's trial balance (T), last year's
signed statements (F), the preparer's assumptions and judgements (A), passages from this year's
documents found in the knowledge store for each assumption, each open finding and the largest
lines (E), the questionnaire (Q), code checks (C — including each comparative against last year's
signed statements), the files (D), earlier findings with the reviewer's responses (R) and the
learned rules (L). Skills: `nz-fs-review` plus the business nature's. Code checks the answer:
real sources only, a finding the reviewer closed is never raised again, unknown refs become new
findings, figures not in the input or the skills are flagged. Findings keep one ref (R1, R2…)
across rounds in the PM application; responses are agree, fixed, not an issue or wrong reason
(the last two need a reason, which teaches the AI); a person can add something the AI missed.
Each assumption gets a verdict: supported, challenged or needs evidence.

**Ask** (`ask.py`, `POST /precheck/ask`, Sonnet). Retrieval: this task's tags first, narrowed by
what the question names (last year / this year, bank, questionnaire, invoice, trial balance…),
then meaning, then exact words — names, addresses, amounts and the words documents use (sold →
Sale / Settlement) in their usual capitalisations; exact matches are always kept. Assumptions,
findings, feedback and the learned rules that apply to the task are searched too. The answer
cites only the passages given; code keeps real citations, flags amounts not in them, and an
answer with nothing behind it is "partly answered", never "answered".

**Learned skills** (`learn.py`, `POST /precheck/learn`, Sonnet). A correction — the pre-check's
"Correct this", or in the review "not an issue", "wrong reason" or "something the AI missed" —
becomes a lesson; the AI drafts it as a rule (when / do / why) without widening what the person
said, and the note stays with it. Scope: this client (at once), this project, this workspace or
all clients of the type (a lead or admin approves). Active rules reach the pre-check and the
review as L lines and Ask through the knowledge store.

| Where | What |
|---|---|
| `precheck_agent/graph.py` | the nodes |
| `precheck_agent/keydocs.py` | the three key documents and the email asking for them |
| `precheck_agent/precheck.py` | the input, the call, the checks on the answer, the email |
| `precheck_agent/analysis.py` | what code works out from last year's accounts and this year's bank |
| `precheck_agent/rules.py` | checks that need no model |
| `precheck_agent/store.py` | manifest, parsed documents, exact-match caches (client and job are part of every key) |
| `precheck_agent/knowledge.py` | the knowledge store (ChromaDB): tags, tag-filtered search, boundaries |
| `precheck_agent/review.py` | the review: input, call, checks on the answer, knowledge kept in step |
| `precheck_agent/ask.py` | Ask: retrieval (tags, meaning, exact words), the answer and its checks |
| `precheck_agent/learn.py` | learned skills: corrections drafted as rules |
| `skills/` | the pre-check method, the review method and the three business natures, versioned with the code |
| `../backend/apps/precheck` | runs, assumptions, review findings and responses, questions, lessons, audit log |
| `../frontend/src/features/precheck` | the task card's AI assistant (Pre-check, Review, Ask tabs) |

**Drafting a Direction Note** stays available on request (`mode: "draft"` on
`POST /precheck/runs`): one call to the drafting model from this client's past tasks and what
is in the folder. The pre-check does not need a Direction Note.

**Zip archives.** A zip in the job folder is opened in memory and each file inside is read as
its own document ("Trial Balance.xlsx (in Documents.zip)"); a document's version is its CRC,
so re-uploading the zip with one file changed re-reads only that file. Limits: 100 MB per zip,
300 files, nesting up to three levels deep. Password-protected files and other archive types
(.rar, .7z) are reported as unreadable. Drive cannot link inside a zip, so "Open in Drive"
opens the zip itself.

**Emails.** `.eml` and Outlook `.msg` files are read by code, with no model call. The email is
a document (sender, date, subject, then the body, cited as "email line N") and each attachment
is a document of its own ("Invoice.pdf (attached to RE Year end.eml)"), including emails
inside zips and forwarded emails. Pictures embedded in the body under 20 KB are treated as
logos and left out. An email is always classed as correspondence, so "RE: Trial balance" never
satisfies a rule that looks for a trial balance. Emails are part of the documents the pre-check reads.

**Images and scans.** A photo, screenshot or scanned PDF has no text for a library to extract,
so the reader model (Haiku) looks at it once and writes out what it says; that transcript is
then chunked, searched and quoted like any other document, located as "image read by AI,
line N". Code does the rest: any
type Pillow opens (PNG, JPEG, GIF, WebP, BMP, TIFF, HEIC, ICO, AVIF) is turned upright, shrunk
to 1,568 px and sent as JPEG; a scanned PDF or multi-page TIFF is cut to its first 5 pages
(and says so). Each page is read in its own call, four at a time, so every quote's page is
exact. **A scanned questionnaire is read to the end** (up to 30 pages): one named like a
questionnaire ("Client Questionnaire…", or "QD--FY2026--…" as the client form sends it) is read
whole at once; any other scan whose first pages turn out to be a questionnaire has the rest
read too. On a form every tick box is written as `[X] label` or `[ ] label`, so the pre-check
sees which answer was chosen. A questionnaire states its year, and that year is this year
unless the task title says otherwise. Measured on a real 14-page image-only questionnaire (6 Oct
2026, Haiku 4.5): all 39 ticked answers right and on the right page, 26,000 tokens in, 6,200
out, $0.057, 36 s. The transcript is stored against the file's id and version, so an image is paid
for once. A run reads at most 10 images (`PRECHECK_BUDGET_IMAGE_CALLS`); the rest are reported as not read yet, the result is marked partial, and
the next run reads them. SVG and HTML files are text already and are read by code. Measured
(2 Oct 2026, Haiku 4.5): a one-page voucher photo was 1,755 tokens in, 155 out ($0.0025); a
two-page scanned PDF 3,367 in, 99 out ($0.0039); a dense screenshot 1,766 in, 654 out ($0.005).
So ten images add roughly $0.03-0.05 to a first run and nothing to later runs. A full run on a zip holding five documents, an email with a photographed board minute, a voucher photo and a two-page scan cost $0.046 and took 28 s; the re-run cost nothing. A quote from an
image is the model's reading of it, not text copied from the file: the location says so, and
the reviewer should open the image where a figure rests on it alone.

**Which year a document belongs to.** Code decides it (a folder named `2025`/`FY25`, a date
range in the file name, "for the year ended ..." inside it, a year in the name; years outside
2000 to next year are ignored). This year is the task's year, else the year after the latest
finished pack. The automatic checks run on this year's documents only.

**Size and budget.** Code shortens the pre-check's input to fit 90,000 tokens
(`PRECHECK_PRECHECK_MAX_INPUT_TOKENS`) before the call. Hard caps per run:
`PRECHECK_RUN_INPUT_TOKENS` 120,000 and `PRECHECK_RUN_OUTPUT_TOKENS` 24,000, plus 10 images.
These replace `PRECHECK_BUDGET_UNCACHED_INPUT_TOKENS` and `PRECHECK_BUDGET_OUTPUT_TOKENS`, whose
old values of 40,000 and 4,000 stopped real runs; the old names are now ignored.

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows; bin/ on Linux
cp .env.example .env            # set the API key, service token and Google key
.venv/Scripts/python -m uvicorn precheck_agent.api:app --port 8100
.venv/Scripts/pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest tests   # no key needed
```

In the PM application set `PRECHECK_AGENT_URL` and the same `PRECHECK_SERVICE_TOKEN`, and run
its migrations. Share each job's Drive folder (Viewer) with the service account's email.
**Demo mode** (`PRECHECK_LLM_MODE=fake`, `PRECHECK_DRIVE_MODE=local`) runs the whole pipeline
on `fixtures/` with scripted answers and labels every result as a demo.

## Tokens and cost per run

Measured with real Claude on 5 Oct 2026 on a real 57-document NZ company task (Opus 5.5,
effort medium): one call with about 55,000 input tokens (statements 23,000, this year's
documents 15,500, questionnaire 4,600, instructions 4,700), about $0.35-0.40. The answer had 17
requests, 3 already provided and 2 not needed, each with its sources. It caught the missing
month of bank data, unexplained transfers and income mentioned only in an email. A Blocked run
costs only the images read (about $0.04 on the same folder). An unchanged re-run costs nothing:
the answer is cached by an exact hash of the model, skills, lessons and input.

```bash
python -m precheck_agent.measure --folder <Drive folder id> --client <client id>
```

**Measured (12 Oct 2026).** A review round with Opus 5.5 on a small rental task with four
planted errors: all four found and both assumptions challenged, 8,400 tokens in, 3,900 out,
$0.11, 55 s; the next round resolved the fixed finding, kept the unfixed one under its ref and
applied the learned rule instead of re-raising a closed finding ($0.07, 34 s). Ask on the real
Landm folder (123 files, 887 chunks): $0.01–0.016 and 4–15 s per question; the sale price and
settlement date were found and cited. Drafting a rule: under $0.003. Indexing that folder with
the local search model: no model cost beyond the images read ($0.13 for its scans).

## Decisions

- **One professional call instead of many readers.** The earlier reader/judge/escalate design
  hit token limits before finishing and judged items one by one. Code now does the reading,
  summarising and checking; Opus sees the whole job once and decides like a preparer.
- **The key documents are a gate in code**, not a model decision.
- **Firm-wide lessons need a lead's approval**; client lessons apply at once.
- **Embeddings are local** (a hashing embedder by default, `fastembed` optional): Claude has no
  embeddings model, and client text stays inside the service.

## Verified, not verified, not built

- **Verified against Claude** (5 Oct 2026): the pre-check with Opus 5.5 on a real task folder
  (above), and the Blocked path on the same folder.
- **Verified against Claude** (2 Oct 2026): reading photos, scanned PDFs and TIFFs attached to a
  real Outlook `.msg`; an instruction written inside an image was copied out, not followed.
  Not verified: handwriting, HEIC photos, accuracy on poor scans.
- **Verified on Postgres 16 + pgvector 0.6**: the full test suite.
- **Not verified with real Claude: a rental folder.** The rental rules are tested with scripted
  answers only. Run one real rental task and read the list before relying on it.
- **Not built**: the Batch API path for bulk re-runs; AWS Secrets Manager (keys are in a
  root-owned file on the instance, like the app's other secrets).
