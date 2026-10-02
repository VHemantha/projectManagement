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
| `skills/` | six skills in Agent Skills format, versioned with the code |
| `../backend/apps/precheck` | run history, findings, evidence, audit log and feedback in the PM application |
| `../frontend/src/features/precheck` | the job card panel |

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows; bin/ on Linux
cp .env.example .env            # set the API key, service token and Google key
.venv/Scripts/python -m uvicorn precheck_agent.api:app --port 8100
.venv/Scripts/pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest tests   # 29 tests, no key needed
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
