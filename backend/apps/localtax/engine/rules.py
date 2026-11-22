"""The Sri Lankan income tax rules for each year of assessment (AFIT, 22 Nov 2026), from versioned JSON files in
`apps/localtax/rules/` ("2024-25.json" for YA 2024/25). Every rule carries its legal reference and whether a tax
professional has validated it. A rule the year does not have, or has without a value, is reported as a flag for
review: it is never guessed."""
import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


class MissingRules(Exception):
    """No rules for the year of assessment: the computation can't run until they are added and validated."""


def file_for(year_of_assessment: str) -> Path:
    """"2024/25" -> rules/2024-25.json."""
    return RULES_DIR / (str(year_of_assessment).strip().replace("/", "-") + ".json")


def years() -> list[str]:
    return sorted(json.loads(p.read_text(encoding="utf-8"))["year_of_assessment"] for p in RULES_DIR.glob("*.json"))


@lru_cache
def load(year_of_assessment: str) -> dict:
    path = file_for(year_of_assessment)
    if not path.exists():
        raise MissingRules(f"There are no tax rules for YA {year_of_assessment} yet. Add rules/{path.name} and have it validated.")
    return json.loads(path.read_text(encoding="utf-8"))


class Rules:
    """One year's rules, read with the use of each recorded (so the result can say which rules it rests on and
    which of those are not yet validated)."""

    def __init__(self, year_of_assessment: str, reviews: dict | None = None):
        """`reviews`: a tax professional's review of rules, by path ("company.standard_rate"): {"status":
        "validated"|"corrected", "value", "ref", "by", "at"} (Phase 4, held in the database). A validated rule keeps
        the file's value; a corrected one uses the reviewer's value instead; both count as validated."""
        self.data = load(year_of_assessment)
        self.year = self.data["year_of_assessment"]
        self.reviews = reviews or {}
        self.used: dict[str, dict] = {}

    def fresh(self) -> "Rules":
        """The same year and reviews, with nothing recorded as used yet."""
        return Rules(self.year, self.reviews)

    def rule(self, *path: str) -> dict | None:
        node = self.data
        for p in path:
            if not isinstance(node, dict) or p not in node:
                return None
            node = node[p]
        if isinstance(node, dict) and "value" in node:
            key = ".".join(path)
            review = self.reviews.get(key)
            if review:
                node = {**node, "validated": True, "reviewed_by": review.get("by", ""), "reviewed_at": review.get("at", ""),
                        "ref": review.get("ref") or node.get("ref", "")}
                if review.get("status") == "corrected":
                    node["value"] = review.get("value")
            self.used[key] = {"ref": node.get("ref", ""), "validated": bool(node.get("validated")), "value": node.get("value"),
                              "reviewed_by": node.get("reviewed_by", "")}
        return node

    def value(self, *path: str):
        node = self.rule(*path)
        if node is None or node.get("value") is None:
            return None
        v = node["value"]
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        return v

    def special_rates(self, entity: str) -> dict:
        return (self.data.get(entity) or {}).get("special_rates") or {}

    def report(self) -> list[dict]:
        """The rules the computation used, each with its reference and validation state."""
        return [{"rule": k, **v} for k, v in sorted(self.used.items())]

    def all_rules(self) -> list[dict]:
        """Every rule of the year (path, label, value, ref, validated), with the reviews applied: the review register."""
        out = []

        def walk(node, path):
            if isinstance(node, dict) and "value" in node:
                n = self.rule(*path)
                out.append({"rule": ".".join(path), "label": n.get("label", ""), "value": n.get("value"), "ref": n.get("ref", ""),
                            "validated": bool(n.get("validated")), "reviewed_by": n.get("reviewed_by", ""), "reviewed_at": n.get("reviewed_at", ""),
                            "file_value": node.get("value"), "conditions": node.get("conditions") or []})
            elif isinstance(node, dict):
                for k, v in node.items():
                    walk(v, path + [k])

        for k, v in self.data.items():
            walk(v, [k])
        self.used = {}
        return out

    @property
    def unvalidated(self) -> bool:
        return any(not v["validated"] for v in self.used.values())
