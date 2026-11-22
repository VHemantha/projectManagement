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

    @property
    def api_key(self) -> str:
        return self.anthropic_api_key or os.environ.get("PRECHECK_ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
