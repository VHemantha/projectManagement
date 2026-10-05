# precheck-agent

The AI pre-check for AFIT Connect: a quality gate that runs before human internal review. A user
presses **Run pre-check** on a job card; the agent reads the job's Direction Note and the
documents in its Google Drive folder and answers three questions: was each Direction Note item
addressed (with evidence), what exceptions remain, and is the job ready for review. It never
marks a job reviewed, never edits workpapers and never writes to Drive.

## How it works

A separate service (FastAPI + LangGraph). The PM application calls `POST /precheck/runs` and
gets a run id at once; progress and the result come back as events.

`load_job → sync_drive → index → run_rules → plan → read (parallel) → judge → [escalate] → publish`

Only `read` (Haiku), `judge` (Sonnet) and `escalate` (Opus, rare) call a model. Everything else
is code: listing and hashing the folder, parsing, the deterministic checks, retrieval, turning
citations into evidence, the verdict and the coverage figure.

| Where | What |
|---|---|
| `precheck_agent/graph.py` | the nine nodes |
| `precheck_agent/readers.py`, `judge.py` | the four reader agents; judge, escalation and the code that checks them |
| `precheck_agent/rules.py` | checks that need no model |
| `precheck_agent/store.py` | manifest, chunks + vectors, exact-match caches (client and job are part of every query and key) |
| `skills/` | seven skills in Agent Skills format, versioned with the code |
| `../backend/apps/precheck` | run history, findings, evidence, audit log and feedback in the PM application |
| `../frontend/src/features/precheck` | the job card panel |

**Drafting the Direction Note.** A job with no Direction Note gets one drafted before it is
verified (`draft_directions`, between `run_rules` and `plan`; one call to the judge model,
structured output, cached by exact match). The draft uses this client's past jobs — the items
used before, earlier findings and what people decided about them, sent by the PM application
with the job — and what is in the folder now (document names and kinds, and what the rules
flagged; never document text). Nothing is trained: the history is shown to the model on each
draft. Findings a person marked rejected or not applicable are removed in code whatever the
model returns, and if the model cannot be used the draft falls back to a standard list built
by code from the kinds of document present. `mode: "draft"` on `POST /precheck/runs` drafts
without verifying. Measured on the demo job with a three-finding history: the draft call was
2,058 tokens in, 443 out (about $0.009); draft plus full verification of six items cost $0.066.

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
satisfies a rule that looks for a trial balance, and every reader may be shown emails.

**Images and scans.** A photo, screenshot or scanned PDF has no text for a library to extract,
so the reader model (Haiku) looks at it once and writes out what it says; that transcript is
then chunked, searched and quoted like any other document, located as "image read by AI,
line N". This is the one model call outside read, judge and escalate. Code does the rest: any
type Pillow opens (PNG, JPEG, GIF, WebP, BMP, TIFF, HEIC, ICO, AVIF) is turned upright, shrunk
to 1,568 px and sent as JPEG; a scanned PDF or multi-page TIFF is cut to its first 5 pages
(and says so). The transcript is stored against the file's id and version, so an image is paid
for once. A run reads at most 10 images (`PRECHECK_BUDGET_IMAGE_CALLS`), counted apart from
the reader budget; the rest are reported as not read yet, the result is marked partial, and
the next run reads them. SVG and HTML files are text already and are read by code. Measured
(2 Oct 2026, Haiku 4.5): a one-page voucher photo was 1,755 tokens in, 155 out ($0.0025); a
two-page scanned PDF 3,367 in, 99 out ($0.0039); a dense screenshot 1,766 in, 654 out ($0.005).
So ten images add roughly $0.03-0.05 to a first run and nothing to later runs. A full run on a zip holding five documents, an email with a photographed board minute, a voucher photo and a two-page scan cost $0.046 and took 28 s; the re-run cost nothing. A quote from an
image is the model's reading of it, not text copied from the file: the location says so, and
the reviewer should open the image where a figure rests on it alone.

**This year against last year.** A task folder often holds last year's finished pack next to
what the client has sent for this year. Code decides each document's year (a folder named
`2025`/`FY25`, a date range in the file name, "for the year ended …" inside it, a year in the
name) and when both years are present:
- the automatic checks run on this year's documents only (last year's finished workpapers are
  the baseline, not something to check again);
- `analyse` takes last year's lines from its final trial balance (or signed statements), this
  year's figures from a current trial balance if there is one, and summarises each bank export
  of this year (period, opening and closing balance, money in and out, totals by payer/payee);
- two checks have a right answer and are done by code: this year's opening bank balance equals
  last year's closing balance, and the bank data covers the whole year;
- one judge-model call reads only those compact lists and says, line by line, whether this
  year's material covers each line of last year's accounts (covered, partly, not received yet,
  prepared at year end, not expected, unclear) with a short note and question. Code keeps only
  references that exist and drops any sentence with a figure code did not produce.
The task card shows it under "Compared with last year". The largest "not received yet" lines
and failed checks also become findings. Measured on a real 57-document NZ task (2 Oct 2026):
the analysis call was 4,282 tokens in and 2,589 out (about $0.035).

**Budget.** A run grows its budget with the work it finds (about 6,500 input tokens per reader
task, measured), up to hard caps (40 reader calls, 240,000 input and 20,000 output tokens). The
analysis, drafting, the judge and second looks have a reserve of their own (30,000 input,
12,000 output) that readers cannot use, so a large Direction Note no longer stops the run
before its findings are weighed. A pasted Direction Note is put back together first (wrapped
lines joined, headings put in front of their bullets). On the real 57-document task with a
17-line Direction Note: all 15 items read, findings weighed, about $0.25 for the first run
(including 7 images read) and nothing for an unchanged re-run.

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows; bin/ on Linux
cp .env.example .env            # set the API key, service token and Google key
.venv/Scripts/python -m uvicorn precheck_agent.api:app --port 8100
.venv/Scripts/pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest tests   # 58 tests, no key needed
```

In the PM application set `PRECHECK_AGENT_URL` and the same `PRECHECK_SERVICE_TOKEN`, and run
its migrations. Share each job's Drive folder (Viewer) with the service account's email.
**Demo mode** (`PRECHECK_LLM_MODE=fake`, `PRECHECK_DRIVE_MODE=local`) runs the whole pipeline
on `fixtures/` with scripted answers and labels every result as a demo.

## Tokens and cost per run

Measured against Claude on 2 Oct 2026 with the demo fixture (`fixtures/demo-acme-fy25`: 5
documents, 3 Direction Note items, 1 rule flag), list prices, SQLite storage:

| Run | Reader calls | Model calls | Input (uncached) | Cache write / read | Output | Cost | Time |
|---|---|---|---|---|---|---|---|
| First run | 4 | 5 | 14,563 | 0 / 0 | 1,475 | $0.030 | 19 s |
| Re-run, nothing changed | 0 | 0 | 0 | 0 / 0 | 0 | $0.000 | under 1 s |
| One escalation (Opus), measured separately | – | 1 | 713 | 0 / 0 | 87 | $0.005 | – |
| Worst case allowed by the budget | 12 | – | 40,000 | – | 4,000 | under $0.10 | – |

A reader call is about 2,700–3,200 input tokens (system prompt with its skill, two tool
definitions, up to 6 chunks) and 50–290 output tokens; the judge was 3,101 in, 1,147 out.
Nothing is served from the prompt cache: every prefix is below its model's cache minimum (see
below), so the saving comes from not calling the model at all on unchanged work. One synthetic
job is not a benchmark: measure 20 real jobs before fixing the budget.

```bash
python -m precheck_agent.measure --folder <Drive folder id> --client <client id> --items items.txt
```

prints this table for any job folder and reports whether citations and the structured judge
output worked.

Why the cost is predictable: unchanged files are never re-read (keyed by file id + checksum +
parser version); a reader sees at most 6 chunks / 3,000 tokens; reader answers are cached by an
exact hash of model, skill versions, question and chunk hashes; outputs are one line per
finding with `max_tokens` on every call; and a per-run budget (12 reader calls, 40,000 uncached
input tokens, 4,000 output tokens) is enforced in code — on breach the run stops and reports
what it skipped.

## Decisions that differ from the brief

- **A reader's own skill and the finding format are preloaded by code**, not fetched through
  `load_skill`. Both are needed on every call, and fetching them would make each reader two
  model calls instead of one. `load_skill` stays available for the other skills.
- **No prompt-cache marker on reader calls with Haiku**: the stable prefix is roughly 2,000-2,500 tokens,
  below Haiku 4.5's 4,096-token cache minimum, and it is not padded. The code adds the marker
  (and sends one reader per type first) automatically if the prefix ever becomes cacheable.
- **The plan node never calls a model**: an item code cannot map by its wording goes to the
  reader for the kind of document that best matches it.
- **Embeddings are local** (a hashing embedder by default, `fastembed` optional): Claude has no
  embeddings model, and client text stays inside the service.
- **Refusal fallbacks are off by default** (`PRECHECK_REFUSAL_FALLBACKS`) so a run never
  silently moves to another model; a refusal becomes an "unclear" finding.
- **The Direction Note and the Drive folder link are minimal stand-ins** entered on the job
  card, until the Direction Note generator exists. Approved knowledge is not read (none exists).

## Verified, not verified, not built

- **Verified against Claude** (2 Oct 2026): reader citations on custom-content documents through
  `create_agent` (every AI finding came back tied to a passage), the judge's
  `output_config.format` with thinking set to `between_tools` on Sonnet 5.5, and Opus
  escalation at low effort.
- **Verified against Claude** (2 Oct 2026): reading a rotated BMP photo, a two-page scanned
  PDF and a TIFF attached to a real Outlook `.msg`; an instruction written inside the image was
  copied out as text and not followed. Real `.msg` files open with their attachments. Not
  verified: handwriting, HEIC photos from a phone, and accuracy on poor scans.
- **Verified on Postgres 16 + pgvector 0.6**: the full test suite, including the leakage test
  and the Postgres checkpointer (`PRECHECK_TEST_DATABASE_URL=... pytest`).
- **Partly verified: Google Drive.** Sign-in with the service account and the "folder not
  shared" message work against the real API; no folder had been shared with the account, so
  listing, download and export of real files have not run. Links open at the cited cells only for Google Sheets (first-sheet ranges are
  reliable; other sheets depend on Drive honouring the sheet name); Docs and PDFs open at the
  file.
- **Not verified: the AWS deploy scripts** (`deploy/ec2/precheck_deploy.sh`,
  `deploy/scripts/set_precheck_secrets.sh`). They are syntax-checked and their logic was
  exercised locally, but they have not run on the server. See DEPLOYMENT.md §16.
- **Not built**: the Batch API path for scheduled or bulk re-runs; the fenced semantic cache
  (exact-match caches only); the 1-hour cache for an AFIT-wide knowledge prefix (no knowledge
  yet); prior-year comparatives as a rule; AWS Secrets Manager (keys are in a root-owned file
  on the instance, like the app's other secrets).
- **Rules are heuristics** tested on one synthetic job. Expect to tune them, and the budget,
  on 20 real jobs.
