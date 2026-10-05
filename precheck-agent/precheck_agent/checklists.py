"""Standard checklists by pre-check type, kept as data next to their skill.

A task's pre-check type picks its checklist: "general" has none (the Direction Note is the
to-do list); "residential_rental" adds AFIT's rental checks (skills/residential-rental-precheck/
checks.json, from the firm's instructions v1.1). Each check is verified exactly like a
Direction Note item — one reader task, findings with evidence, a status in the checklist — and
the Direction Note's own items are checked as well.
"""
import json
from functools import lru_cache
from pathlib import Path

from .config import get_settings

FILES = {"residential_rental": "residential-rental-precheck/checks.json"}
SKILL = {"residential_rental": "residential-rental-precheck"}
GENERAL_READINESS = {"ready": "Ready for review", "ready_with_exceptions": "Ready with exceptions", "not_ready": "Not ready"}


@lru_cache
def load(precheck_type: str) -> dict | None:
    name = FILES.get(precheck_type or "general")
    if not name:
        return None
    return json.loads((Path(get_settings().skills_dir) / name).read_text(encoding="utf-8"))


def items(precheck_type: str) -> list[dict]:
    """The checklist as items alongside the Direction Note's: id is the check's id (BS01 …)."""
    checklist = load(precheck_type)
    if not checklist:
        return []
    return [{"id": c["id"], "text": c["title"], "origin": "checklist", "reason": c["points"], "basis": checklist["label"],
             "area": c["area"], "search": f"{c['title']} {c['search']}"} for c in checklist["checks"]]


def question(item: dict, precheck_type: str) -> str:
    """What a reader is asked for one check: the check, what to look for, and the ground rules."""
    checklist = load(precheck_type) or {}
    rules = " ".join(f"({n}) {r}" for n, r in enumerate(checklist.get("ground_rules", []), start=1))
    return (f"{checklist.get('label', 'Checklist')} check {item['id']} ({item['area']}): {item['text']}. "
            f"What to look for: {item['reason']} "
            f"Report what is complete, partial, missing or needs clarification, per property, account or loan where it applies. "
            f"Use missing only when something in the documents shows the item exists this year but its evidence has not been supplied. "
            f"If nothing shows it applies this year (no purchase or sale, no body corporate, no vehicle use), answer unclear and ask whether it applies. "
            f"When you rely on a figure, write it as it appears in the passage. "
            f"Ground rules: {rules}")


def readiness(precheck_type: str) -> dict:
    checklist = load(precheck_type)
    return (checklist or {}).get("readiness") or GENERAL_READINESS


TYPES = {"general": "General", "residential_rental": "Residential rental"}
