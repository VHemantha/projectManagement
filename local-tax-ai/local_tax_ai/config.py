"""Local_Tax_AI's settings (AFIT, 22 Nov 2026), from LOCAL_TAX_AI_* environment variables or .env. The Claude key
falls back to the pre-check agent's (PRECHECK_ANTHROPIC_API_KEY) or ANTHROPIC_API_KEY, so one key serves both."""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOCAL_TAX_AI_", env_file=".env", extra="ignore")

    service_token: str = "dev-precheck-token"  # shared with the PM application (LOCAL_TAX_AI_TOKEN there)
    llm_mode: str = "anthropic"  # "anthropic" | "fake" (tests, demo)
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-5-5"  # explanations, mapping, questions, chat
    reader_model: str = "claude-sonnet-5-5"  # reading documents (PDFs and images are sent as they are)
    max_tokens: int = 4000
    reader_max_tokens: int = 12000
    timeout_s: int = 180
    # Answers that grow with the trial balance (a dummy TB from a story, mapping every account, classifying the
    # assets): 4000 tokens cut the dummy TB short, so every "create from a story" failed (25 Nov 2026).
    long_max_tokens: int = 16000
    long_timeout_s: int = 230  # inside the PM application's 240 s wait
    # Google Drive (read-only), for a Local client's supporting documents folder
    drive_mode: str = "google"  # "google" | "local" (tests, demo: a directory stands in for a folder)
    local_drive_root: str = "demo_drive"
    google_service_account_json: str = ""
    google_service_account_file: str = ""
    drive_timeout_s: int = 60
    max_files_per_folder: int = 200
    max_file_bytes: int = 25 * 1024 * 1024

    @property
    def api_key(self) -> str:
        return self.anthropic_api_key or os.environ.get("PRECHECK_ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
