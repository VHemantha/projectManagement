# precheck-agent

The AI pre-check for AFIT Connect. A user presses **Run pre-check** on a task card; the agent
reads the task's Google Drive folder and acts like the preparer starting the job: it checks the
three documents nothing can start without, decides the client's business nature, and lists what
is still needed to prepare this year's accounts, each item with its decision and the reason,
plus a drafted email to the client. It never sends the email, never marks a task reviewed,
never edits workpapers and never writes to Drive.

## How it works

A separate service (FastAPI + LangGraph). The PM application calls `POST /precheck/runs` and
gets a run id at once; progress and the result come back as events.

`load_job -> sync_drive -> index -> run_rules -> key_documents -> [precheck] -> publish`

1. **Key documents, by code.** This year's client questionnaire, last year's financial
   statements and last year's workpapers (`keydocs.py`). If any is missing the run stops there:
   the result is Blocked, and code drafts the email asking for what is missing, with the reason.
   No model is called. Last year's questionnaire does not count as this year's.
2. **The pre-check, one Opus call** (`precheck.py`, `PRECHECK_PRECHECK_MODEL`, structured
   output). Its input is built by code, every line with an id: the questionnaire (Q), last
   year's statements (F) and trial balance (T), the workpapers (W), the files received (D),
   this year's other documents (R), each bank export summarised by code (B, and B.n by payer and
   payee), the checks code can answer (C: opening balance against last year's closing, bank
   data covering the year, the rules), the Direction Note if there is one (N) and the lessons
   people taught (L). Its instructions are the skills: `precheck-method` plus the one for the
   business nature: `nz-residential-rental` (AFIT's rental rules: property manager or owner
   managed, property details, invoices for expenses not paid through the bank and for body
   corporate, loans and refinancing, rent bond, short-term rental statements, items over
   $1,000; NZ interest deductibility, bright-line, ring-fencing), `nz-general-business` or
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

| Where | What |
|---|---|
| `precheck_agent/graph.py` | the nodes |
| `precheck_agent/keydocs.py` | the three key documents and the email asking for them |
| `precheck_agent/precheck.py` | the input, the call, the checks on the answer, the email |
| `precheck_agent/analysis.py` | what code works out from last year's accounts and this year's bank |
| `precheck_agent/rules.py` | checks that need no model |
| `precheck_agent/store.py` | manifest, chunks, exact-match caches (client and job are part of every key) |
| `skills/` | the method and the three business natures, versioned with the code |
| `../backend/apps/precheck` | run history, lessons, audit log in the PM application |
| `../frontend/src/features/precheck` | the task card panel |

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
(and says so). The transcript is stored against the file's id and version, so an image is paid
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
