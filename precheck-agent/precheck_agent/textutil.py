import hashlib
import math
import re


def est_tokens(text: str) -> int:
    """Cheap, deliberately pessimistic token estimate (no API call): used only for budgets and
    chunk sizing, never for billing. Billing uses the usage each response reports. Calibrated
    against real runs (2 Oct 2026): numbers and table rows tokenise at about 2.5 characters per
    token, so the budget reserves enough before parallel readers start."""
    return math.ceil(len(text) / 2.5) if text else 0


def sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8", "replace"))
        h.update(b"\x1f")
    return h.hexdigest()


def clip_words(text: str, limit: int) -> str:
    words = text.split()
    return text.strip() if len(words) <= limit else " ".join(words[:limit]).rstrip(",;:") + "…"


_NUM = re.compile(r"^\(?-?[£$€]?\s?[\d,]+(\.\d+)?\)?$")


def to_number(value) -> float | None:
    """Accounting-style numbers: 1,234.50, (1,234.50), -£1,234."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or not _NUM.match(s):
        return None
    negative = s.startswith("(") or s.startswith("-")
    digits = re.sub(r"[^\d.]", "", s)
    if not digits:
        return None
    return -float(digits) if negative else float(digits)
