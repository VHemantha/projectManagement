"""Claude for the coordination agent: replies in a person's conversation (Sonnet) and the CEO's
briefing. Every call is costed and counted against the CEO's daily cap; past the cap, or without a
key, the agent falls back to plain messages written by code.

The key is the one the pre-check agent already uses (from the secret manager, in the shared
precheck.env), so it is not copied into a second place.
"""
import json
import logging
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-5-5"
# US$ per million tokens (input, output), from Anthropic's price list.
PRICES = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}


class Unavailable(Exception):
    """No key, over the daily cap, or the API failed: the caller uses its code-written fallback."""


def api_key() -> str:
    key = getattr(settings, "COORDINATOR_ANTHROPIC_API_KEY", "")
    if key:
        return key
    path = Path(getattr(settings, "PRECHECK_ENV_FILE", "") or "")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("PRECHECK_ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


@lru_cache
def _client(key: str):
    import anthropic

    return anthropic.Anthropic(api_key=key, timeout=60, max_retries=1)


def spent_today() -> float:
    from .facts import local_now
    from .models import AgentAction

    start = local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    return float(AgentAction.objects.filter(created_at__gte=start).aggregate(t=Sum("cost_usd"))["t"] or 0)


def cost(model: str, usage) -> float:
    pin, pout = PRICES.get(model, PRICES[CHAT_MODEL])
    return round((usage.input_tokens * pin + usage.output_tokens * pout) / 1_000_000, 6)


def structured(system: str, messages: list[dict], schema: dict, *, model: str = CHAT_MODEL, max_tokens: int = 1500) -> tuple[dict, float]:
    """One call with a fixed answer shape. Returns (answer, cost in US$)."""
    from .models import CoordinatorSettings

    key = api_key()
    if not key:
        raise Unavailable("no API key")
    if spent_today() >= CoordinatorSettings.get().daily_cost_cap_usd:
        raise Unavailable("the daily AI spending cap is reached")
    kwargs = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages,
              "output_config": {"format": {"type": "json_schema", "schema": schema}, "effort": "low"}}
    if model == CHAT_MODEL:
        kwargs["thinking"] = {"type": "between_tools"}  # a short reply needs no extended thinking
    try:
        response = _client(key).messages.create(**kwargs)
    except Exception as exc:  # network, rate limit, server: fall back, never break the chat
        logger.warning("Coordinator model call failed: %s", exc)
        raise Unavailable(str(exc)) from exc
    spent = cost(model, response.usage)
    if response.stop_reason in ("refusal", "max_tokens"):
        raise Unavailable(f"stopped early ({response.stop_reason})")
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    try:
        return json.loads(text), spent
    except json.JSONDecodeError as exc:
        raise Unavailable("the answer was not valid JSON") from exc


def stamp() -> str:
    return timezone.now().isoformat()
