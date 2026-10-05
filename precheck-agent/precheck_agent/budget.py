"""The per-run budget, enforced in code so the cost of a run is bounded.

A run makes at most: one image read per new picture or scan (capped per run; the rest are read by
the next run), one Direction Note draft when asked, and one pre-check call whose input code has
already shortened to fit. The caps below stop anything beyond that; usage is reported per call.
"""
import threading
from dataclasses import dataclass, field

from .config import Settings, family, get_settings


def empty_usage() -> dict:
    return {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}


def usage_from_message(message) -> dict:
    """Token counts from one model response. LangChain reports input_tokens including cached
    tokens; `input` here is the uncached part only, which is what the budget counts."""
    meta = getattr(message, "usage_metadata", None) or {}
    details = meta.get("input_token_details") or {}
    cache_read = int(details.get("cache_read", 0) or 0)
    cache_write = int(details.get("cache_creation", 0) or 0)
    total_in = int(meta.get("input_tokens", 0) or 0)
    return {
        "input": max(total_in - cache_read - cache_write, 0),
        "output": int(meta.get("output_tokens", 0) or 0),
        "cache_write": cache_write,
        "cache_read": cache_read,
    }


def cost_usd(model: str, usage: dict, settings: Settings | None = None) -> float:
    prices = (settings or get_settings()).prices[family(model)]
    return (
        usage["input"] * prices["input"]
        + usage["output"] * prices["output"]
        + usage["cache_write"] * prices["cache_write"]
        + usage["cache_read"] * prices["cache_read"]
    ) / 1_000_000


@dataclass
class RunBudget:
    uncached_input: int
    output: int
    image_calls: int = 0
    used_input: int = 0
    used_output: int = 0
    used_images: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def try_image_call(self) -> str | None:
        """Reserve one image read. Images have their own count."""
        with self._lock:
            if self.used_images >= self.image_calls:
                return f"the limit of {self.image_calls} images for one run was reached"
            self.used_images += 1
            return None

    def can_call(self, estimated_input: int) -> str | None:
        with self._lock:
            if self.used_input + estimated_input > self.uncached_input:
                return "input token limit reached"
            if self.used_output >= self.output:
                return "output token limit reached"
            return None

    def add(self, usage: dict) -> None:
        with self._lock:
            self.used_input += usage["input"]
            self.used_output += usage["output"]


_budgets: dict[str, RunBudget] = {}
_registry_lock = threading.Lock()


def budget_for(run_id: str) -> RunBudget:
    with _registry_lock:
        if run_id not in _budgets:
            s = get_settings()
            _budgets[run_id] = RunBudget(s.run_input_tokens, s.run_output_tokens, image_calls=s.budget_image_calls)
        return _budgets[run_id]


def release(run_id: str) -> None:
    with _registry_lock:
        _budgets.pop(run_id, None)
