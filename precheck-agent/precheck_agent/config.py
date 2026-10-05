"""All settings come from the environment (prefix PRECHECK_). Nothing here is hard-coded in
the graph: models, budgets and prices are changed by config, not by editing code."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PRECHECK_", env_file=".env", extra="ignore")

    # --- storage -------------------------------------------------------------------------
    # Postgres + pgvector in production ("postgresql+psycopg://..."); SQLite for dev and tests.
    database_url: str = "sqlite:///./precheck.db"

    # --- PM application ------------------------------------------------------------------
    pm_base_url: str = "http://127.0.0.1:8000"
    service_token: str = "dev-precheck-token"  # shared secret, both directions; set in secrets

    # --- models (Claude only; never hard-coded elsewhere) ----------------------------------
    llm_mode: str = "anthropic"  # "anthropic" | "fake" (tests and the labelled demo mode)
    reader_model: str = "claude-haiku-4-5-20251001"
    judge_model: str = "claude-sonnet-5-5"
    escalate_model: str = "claude-opus-5-5"
    anthropic_api_key: str = ""  # from the secret manager; falls back to ANTHROPIC_API_KEY
    # Sonnet 5.5 thinks by default and thinking is billed as output. "between_tools" turns it
    # off for the judge (allowed at effort high or below); "" leaves the model default.
    judge_thinking: str = "between_tools"
    judge_effort: str = "low"
    escalate_effort: str = "low"  # Opus 5.5 cannot disable thinking; low effort keeps it small
    # Off by default so cost per run stays predictable: a refusal becomes an "unclear" finding.
    refusal_fallbacks: bool = False

    # --- Drive -----------------------------------------------------------------------------
    drive_mode: str = "google"  # "google" | "local" (a directory per folder id; tests, demo)
    google_service_account_file: str = ""  # path to the key file mounted from the secret manager
    google_service_account_json: str = ""  # or the key itself, injected as a secret env var
    local_drive_root: str = "./fixtures"
    max_files_per_folder: int = 400
    max_file_bytes: int = 25_000_000
    # Zip archives in a job folder are opened and each file inside is read as its own document.
    max_zip_bytes: int = 100_000_000
    max_zip_members: int = 300
    # Emails: a picture embedded in the body that is smaller than this is a logo, not evidence.
    min_inline_image_bytes: int = 20_000

    # --- images and scans (read by the reader model, once per file version) ------------------
    vision_model: str = ""  # empty: the reader model
    budget_image_calls: int = 10  # images read per run; the rest wait for the next run
    image_max_tokens: int = 2000  # output cap for one transcript
    image_max_edge: int = 1568  # longest side sent to the model, in pixels
    max_scan_pages: int = 5  # pages read from one scanned PDF or multi-page TIFF

    # --- indexing --------------------------------------------------------------------------
    embedder: str = "hash"  # "hash" (built in, no download) | "fastembed" (local ONNX model)
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    parser_version: str = "p2"  # p2: emails, images and scans are read
    chunk_tokens: int = 450

    # --- retrieval / readers ------------------------------------------------------------------
    top_k: int = 6
    listing_files: int = 12  # file names shown to a reader next to its passages
    reader_context_tokens: int = 3000
    reader_max_tokens: int = 400
    reader_max_steps: int = 3  # model calls inside one reader (answer, or one tool then answer)
    judge_max_tokens: int = 2500  # grows with the number of findings to weigh, up to the cap
    judge_max_tokens_cap: int = 8000
    escalate_max_tokens: int = 700
    # Smallest prefix each model will cache. Below it a cache marker does nothing, so we do not
    # add one and we never pad a prompt to reach it.
    cache_min_tokens: dict[str, int] = Field(
        default_factory=lambda: {"haiku": 4096, "sonnet": 2048, "opus": 2048}
    )

    # --- budget per run ------------------------------------------------------------------------
    # The minimums below suit a small task. A run grows its budget with the work it finds (per
    # Direction Note item and flagged rule) up to the hard caps, so a task with 17 items is
    # read in full instead of stopping half way. Measured on a real 57-document task: a reader
    # call is 4,800-5,800 input tokens.
    budget_reader_calls: int = 12
    budget_uncached_input_tokens: int = 40_000
    budget_output_tokens: int = 4_000
    budget_input_per_task: int = 6_500
    budget_output_per_task: int = 300
    budget_max_reader_calls: int = 40
    budget_max_uncached_input_tokens: int = 240_000
    budget_max_output_tokens: int = 20_000
    # A pool of its own for the steps that pull everything together (the year-on-year analysis,
    # a drafted Direction Note, the judge, second looks): readers can never starve them.
    budget_reserve_tokens: int = 30_000
    budget_reserve_output_tokens: int = 12_000
    budget_wider_slices: int = 4  # reader calls that may ask for one wider slice (a second call)

    # --- year-on-year analysis ----------------------------------------------------------------------
    analysis_min_amount: float = 250.0  # last year's lines smaller than this are not listed
    analysis_max_tokens: int = 6_000
    analysis_max_findings: int = 6  # "nothing yet for …" findings; the full list is in the analysis

    # --- rules -------------------------------------------------------------------------------
    variance_pct: float = 25.0
    variance_min_amount: float = 5_000.0
    balance_tolerance: float = 1.0
    required_classes: list[str] = Field(default_factory=lambda: ["trial_balance"])

    # --- prices, USD per million tokens (checked 2 Oct 2026; update with the pricing page) -------
    prices: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "haiku": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.10},
            "sonnet": {"input": 2.0, "output": 10.0, "cache_write": 2.5, "cache_read": 0.20},
            "opus": {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": 0.20},
        }
    )

    skills_dir: str = str(REPO_SKILLS_DIR)
    prompt_version: str = "2026-10-04.1"


def family(model_id: str) -> str:
    """'haiku' | 'sonnet' | 'opus' from a model id, for prices and cache minimums."""
    for name in ("haiku", "sonnet", "opus"):
        if name in model_id:
            return name
    return "sonnet"


@lru_cache
def get_settings() -> Settings:
    return Settings()
