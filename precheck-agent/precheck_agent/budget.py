"""The per-run budget (token rule 11), enforced in code so cost per job is predictable.

Starting values: 12 reader calls, 40,000 uncached input tokens, 4,000 output tokens. When a
limit is reached the run stops asking the model, finishes with what it has, and reports what
was skipped (the result is marked "partial"). Tune the values after measuring 20 real jobs.
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
    """Two pools inside one cap. Readers spend the first; the steps that pull everything
    together (year-on-year analysis, drafting, the judge, second looks) spend a reserve that
    readers cannot touch — so however much the readers use, the run still finishes properly."""

    reader_calls: int
    uncached_input: int  # the whole run's cap, both pools
    output: int  # the whole run's output cap, both pools
    used_calls: int = 0
    reader_input: int = 0
    reader_output: int = 0
    final_input: int = 0
    final_output: int = 0
    image_calls: int = 0  # images read this run; counted apart from the reader budget
    used_images: int = 0
    reserve: int = 0  # input tokens kept for the steps that pull everything together
    reserve_output: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def used_input(self) -> int:
        return self.reader_input + self.final_input

    @property
    def used_output(self) -> int:
        return self.reader_output + self.final_output

    def try_reader_call(self, estimated_input: int) -> str | None:
        """Reserve one reader call. Returns None when allowed, else the reason it is not."""
        with self._lock:
            if self.used_calls >= self.reader_calls:
                return "reader call limit reached"
            if self.reader_input + estimated_input > self.uncached_input - self.reserve:
                return "input token limit reached"
            if self.reader_output >= self.output - self.reserve_output:
                return "output token limit reached"
            self.used_calls += 1
            self.reader_input += estimated_input  # replaced by the real figure in settle()
            return None

    def settle(self, estimated_input: int, usage: dict, extra_calls: int = 0) -> None:
        with self._lock:
            self.reader_input += usage["input"] - estimated_input
            self.reader_output += usage["output"]
            self.used_calls += extra_calls

    def try_image_call(self) -> str | None:
        """Reserve one image read. Images have their own count, so a folder of photos cannot
        use up the budget the readers and the judge need."""
        with self._lock:
            if self.used_images >= self.image_calls:
                return f"the limit of {self.image_calls} images for one run was reached"
            self.used_images += 1
            return None

    def can_call(self, estimated_input: int) -> str | None:
        """For the analysis, drafting, the judge and second looks: their own reserve."""
        with self._lock:
            if self.final_input + estimated_input > self.reserve:
                return "input token limit reached"
            if self.final_output >= self.reserve_output:
                return "output token limit reached"
            return None

    def add(self, usage: dict) -> None:
        with self._lock:
            self.final_input += usage["input"]
            self.final_output += usage["output"]

    def spare_calls(self, planned: int) -> int:
        return max(self.reader_calls - planned, 0)

    def fit(self, tasks: int, estimated_input: int, settings: Settings) -> None:
        """Grow the readers' pool to the work found: every planned reader call (at least the
        measured cost of one), room for a few wider slices (each re-sends the conversation),
        plus the reserve. Never beyond the hard caps, never below the minimums — so cost per
        task stays bounded and predictable."""
        with self._lock:
            self.reader_calls = min(settings.budget_max_reader_calls, max(self.reader_calls, tasks + settings.budget_wider_slices))
            per_task = settings.budget_input_per_task
            readers = max(estimated_input, tasks * per_task) + settings.budget_wider_slices * 2 * per_task
            self.uncached_input = min(settings.budget_max_uncached_input_tokens,
                                      max(self.uncached_input, self.reader_input + readers + self.reserve))
            wanted_out = self.reader_output + tasks * settings.budget_output_per_task + self.reserve_output
            self.output = min(settings.budget_max_output_tokens, max(self.output, wanted_out))


_budgets: dict[str, RunBudget] = {}
_registry_lock = threading.Lock()


def budget_for(run_id: str) -> RunBudget:
    with _registry_lock:
        if run_id not in _budgets:
            s = get_settings()
            # The minimums always cover the reserve, so a small task still has room for its readers.
            _budgets[run_id] = RunBudget(
                s.budget_reader_calls, s.budget_uncached_input_tokens + s.budget_reserve_tokens,
                s.budget_output_tokens + s.budget_reserve_output_tokens, image_calls=s.budget_image_calls,
                reserve=s.budget_reserve_tokens, reserve_output=s.budget_reserve_output_tokens)
        return _budgets[run_id]


def release(run_id: str) -> None:
    with _registry_lock:
        _budgets.pop(run_id, None)
