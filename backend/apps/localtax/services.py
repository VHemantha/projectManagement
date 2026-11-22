"""The Local Tax workflow (AFIT, 22 Nov 2026): who may do what, the engine's inputs from the records, and the
engagement's whole state - questionnaire, financial statements, computation, reverse analysis, draft return and
the alerts - worked out by the engine each time. Only Team 3 > Local's cards (Client.workflow == "local_tax")."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .engine import depth as DP
from .engine import fs as FS
from .engine import returns as RT
from .engine import reverse as RV
from .engine.rules import MissingRules, Rules, years
from .engine.tax import compute
from .models import Adjustment, EngagementEvent, ReturnFieldReview, RuleReview, TaxEngagement

WORKFLOW = "local_tax"
ZERO = Decimal("0")
INCOME_CATEGORIES = ("employment", "business", "rent", "interest", "dividend", "foreign_service", "foreign_other", "investment_gain", "other")
TREATMENTS = ("auto", "taxable", "exempt", "final_wht", "special_rate")
EXPENSE_CLASSES = ("allowable", "disallowable", "capital", "clarify")
PAYMENT_TYPES = ("APIT", "AIT", "WHT", "provisional", "foreign_tax_credit", "final_wht", "other")
ASSET_KINDS = ("immovable", "movable", "investment", "bank", "vehicle", "shares", "other")
LIABILITY_KINDS = ("loan", "mortgage", "other")


class NotLocalTax(Exception):
    """The card is not one of Team 3 > Local's: the workflow does not apply to it."""


def is_local_tax(issue) -> bool:
    client = getattr(issue.project, "client", None)
    return bool(client and client.workflow == WORKFLOW)


def can_open(user, issue) -> bool:
    from apps.precheck.services import can_open_job

    return can_open_job(user, issue)


def can_approve(user, issue) -> bool:
    """A reviewer, lead or admin of the card: staff, the project's lead or admin, a lead of its workspace or of
    its sub-workspace's workspace (Team 3), or the card's own reviewer."""
    from apps.precheck.services import can_approve_lessons
    from apps.teams.models import TeamMembership

    client = getattr(issue.project, "client", None)
    leads_client_team = bool(client and client.team_id and TeamMembership.objects.filter(team_id=client.team_id, user=user,
                                                                                        role=TeamMembership.Role.LEAD).exists())
    return bool(user.is_staff or issue.reviewer_id == user.id or leads_client_team or can_approve_lessons(user, issue))


VALIDATORS_GROUP = "Local tax rule validators"


def can_validate(user) -> bool:
    """Who may validate or correct the tax rules and the return's field references (Phase 4): staff, or a member
    of the "Local tax rule validators" group (a tax professional)."""
    return bool(user and user.is_authenticated and (user.is_staff or user.groups.filter(name=VALIDATORS_GROUP).exists()))


def reviews_for(year_of_assessment: str) -> dict:
    return {r.rule: {"status": r.status, "value": r.value, "ref": r.ref, "by": r.by.display_name if r.by_id else "", "at": r.at.isoformat()}
            for r in RuleReview.objects.filter(year_of_assessment=year_of_assessment, active=True).select_related("by").order_by("at", "id")}


def rules_for(year_of_assessment: str) -> Rules:
    """The year's rules with the tax professionals' reviews applied."""
    return Rules(year_of_assessment, reviews_for(year_of_assessment))


def field_refs_for(year_of_assessment: str, entity_type: str) -> dict:
    return {r.code: {"official": r.official, "by": r.by.display_name if r.by_id else "", "at": r.at.isoformat()}
            for r in ReturnFieldReview.objects.filter(year_of_assessment=year_of_assessment, entity_type=entity_type, active=True)
            .select_related("by").order_by("at", "id")}


def year_for(fy_end: date | None) -> str:
    """The year of assessment a financial year ends in: YA 2024/25 is 1 April 2024 - 31 March 2025."""
    if fy_end is None:
        return years()[0]
    start = fy_end.year - 1 if fy_end.month <= 3 else fy_end.year
    return f"{start}/{str(start + 1)[-2:]}"


def engagement_for(issue, user=None) -> TaxEngagement:
    if not is_local_tax(issue):
        raise NotLocalTax(issue.key)
    try:
        return issue.tax_engagement
    except TaxEngagement.DoesNotExist:
        pass
    eng = TaxEngagement.objects.create(issue=issue, legal_name=issue.summary[:200], client_name=issue.summary[:200], created_by=user,
                                       stages={s: {"status": "not_started"} for s in TaxEngagement.STAGES})
    log(eng, user, "created", {"from": issue.key})
    return eng


def log(eng: TaxEngagement, user, action: str, detail: dict, actor: str = "person") -> EngagementEvent:
    return EngagementEvent.objects.create(engagement=eng, user=user if getattr(user, "is_authenticated", False) else None,
                                          actor=actor, action=action[:60], detail=_jsonable(detail))


def _jsonable(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, date):
        return v.isoformat()
    return v


def money(v, field: str = "amount") -> str:
    """A money value as text (kept exact in JSON); "" stays empty."""
    if v in (None, ""):
        return ""
    try:
        return str(Decimal(str(v).replace(",", "")).quantize(Decimal("0.01")))
    except InvalidOperation as exc:
        raise ValueError(f"{field}: give a number.") from exc


# --- the engine's inputs --------------------------------------------------------------------------------------

def tb_lines(eng: TaxEngagement) -> list[dict]:
    return [{"code": ln.code, "name": ln.name, "amount": ln.amount, "comparative": ln.comparative, "heading": ln.heading,
             "heading_by": ln.heading_by} for ln in eng.tb_lines.all()]


def approved(eng: TaxEngagement, scope: str | None = None):
    qs = eng.adjustments.filter(status=Adjustment.Status.APPROVED).order_by("decided_at", "id")
    return qs.filter(scope=scope) if scope else qs


def financials(eng: TaxEngagement) -> dict | None:
    """Companies: the statements from the TB with the approved accounting adjustments. Individuals: the income
    and expenses by source. None for a company without a trial balance."""
    data = eng.data or {}
    if eng.entity_type == TaxEngagement.Entity.INDIVIDUAL:
        return {"kind": "individual", **FS.individual_statement(data.get("income") or [])}
    lines = tb_lines(eng)
    if not lines:
        return None
    adjusted = FS.apply_adjustments(lines, [{"lines": a.lines} for a in approved(eng, "accounting")])
    return {"kind": "company", **FS.statements(adjusted, fs_scope(eng)), "lines": adjusted}


def fs_scope(eng: TaxEngagement) -> str:
    """What the client asked for: "full" (the full set of financial statements) or "income_statement" only."""
    return (eng.data or {}).get("fs_scope") or "full"


def pl_accounts(fs_result: dict | None) -> list[dict]:
    """The P&L accounts the reverse analysis can offer, with whether each is income or an expense."""
    if not fs_result or fs_result.get("kind") != "company":
        return []
    out = []
    for ln in fs_result["lines"]:
        h = ln.get("heading")
        if h in FS.INCOME_HEADINGS or h in FS.EXPENSE_HEADINGS:
            if h == "income_tax_expense":
                continue
            income = h in FS.INCOME_HEADINGS
            out.append({"code": ln["code"], "name": ln["name"], "kind": "income" if income else "expense",
                        "amount": -ln["amount"] if income else ln["amount"], "group": FS.HEADINGS[h][1]})
    return out


def inputs(eng: TaxEngagement, fs_result: dict | None = None) -> dict:
    """The engine's inputs from the records, with the approved tax adjustments applied (a tax-only adjustment
    changes its computation line, never the accounting profit)."""
    data = eng.data or {}
    comp = data.get("computation") or {}
    if eng.entity_type == TaxEngagement.Entity.INDIVIDUAL:
        base = {"entity_type": "individual", "residency": eng.residency, "income": data.get("income") or []}
    else:
        fs_result = fs_result if fs_result is not None else financials(eng)
        pbt = fs_result["pbt"] if fs_result else comp.get("pbt_manual") or "0"
        base = {"entity_type": "company", "pbt": pbt, "add_backs": comp.get("add_backs") or [], "deductions": comp.get("deductions") or [],
                "capital_allowances": comp.get("capital_allowances") or [], "special_income": comp.get("special_income") or []}
    history = data.get("loss_history") or []
    losses_bf = sum((Decimal(h["amount"]) for h in history if h.get("amount")), ZERO) if history else data.get("losses_bf") or "0"
    base.update({"qualifying_payments": data.get("qualifying_payments") or "0", "losses_bf": str(losses_bf), "loss_history": history,
                 "payments": data.get("payments") or []})
    if base["entity_type"] == "company" and data.get("fixed_assets"):
        base["fixed_assets"] = data["fixed_assets"]
    for adj in approved(eng, "tax"):
        base = _apply_tax_adjustment(base, adj, fs_result)
    return base


def _apply_tax_adjustment(base: dict, adj: Adjustment, fs_result) -> dict:
    lever = next((lv for lv in RV.levers(base, pl_accounts(fs_result)) if lv["key"] == adj.target), None)
    if lever is None or adj.proposed is None:
        return base
    return RV.with_change(base, lever, adj.proposed)


# --- the whole state ---------------------------------------------------------------------------------------

REQUIRED_BASIC = [("legal_name", "Legal name"), ("tin", "TIN"), ("year_of_assessment", "Year of assessment"), ("fy_end", "Financial year-end"),
                  ("activity", "Nature of business / income")]


def state(eng: TaxEngagement, user=None) -> dict:
    data = eng.data or {}
    alerts = []
    for f, label in REQUIRED_BASIC:
        if not getattr(eng, f):
            alerts.append({"stage": "questionnaire", "severity": "review", "text": f"{label} is missing."})
    if eng.entity_type == TaxEngagement.Entity.COMPANY and not eng.nic_or_reg:
        alerts.append({"stage": "questionnaire", "severity": "review", "text": "Company registration number is missing."})
    fs_result = financials(eng)
    if eng.entity_type == TaxEngagement.Entity.COMPANY and fs_result is None:
        alerts.append({"stage": "fs", "severity": "blocking",
                       "text": "Upload the current year's trial balance in Client Info > Supporting Documents to prepare the financial statements."})
    if fs_result and fs_result.get("kind") == "company":
        for c in fs_result["checks"]:
            if not c["passed"]:
                alerts.append({"stage": "fs", "severity": "blocking", "text": f"{c['label']}: difference {c['difference']:,.2f}."})
        alerts += [{"stage": "fs", "severity": "review", "text": u} for u in fs_result["unusual"]]
    if eng.entity_type == TaxEngagement.Entity.INDIVIDUAL and not data.get("income"):
        alerts.append({"stage": "questionnaire", "severity": "blocking", "text": "Add the income sources."})
    from . import prefill

    docs = prefill.summary(eng)
    if docs["to_verify"]:
        alerts.append({"stage": "questionnaire", "severity": "review",
                       "text": f"{docs['to_verify']} value(s) found in the documents are waiting for you to verify (Supporting Documents)."})
    if docs["open_flags"]:
        alerts.append({"stage": "questionnaire", "severity": "review",
                       "text": f"{docs['open_flags']} document issue(s) to resolve: missing, unclear or inconsistent information (Supporting Documents)."})
    try:
        rules = rules_for(eng.year_of_assessment)
    except MissingRules as exc:
        return {"engagement": engagement_dict(eng, user), "financials": _clean(fs_result), "computation": None, "reverse": None, "return": None,
                "alerts": alerts + [{"stage": "computation", "severity": "blocking", "text": str(exc)}], "years": years(), "documents": docs,
                "adjustments": [adjustment_dict(a) for a in eng.adjustments.select_related("created_by", "decided_by", "evidence")]}
    ins = inputs(eng, fs_result)
    comp = compute(ins, rules.fresh())
    alerts += [{"stage": "computation", "severity": f["severity"], "text": f["text"]} for f in comp["flags"]]
    if comp["unvalidated"]:
        n = sum(1 for r in comp["rules"] if not r["validated"])
        alerts.append({"stage": "computation", "severity": "info",
                       "text": f"{n} of the YA {eng.year_of_assessment} rules used are not yet validated by a tax professional (see the rules review)."})
    rev = RV.analyse(ins, rules, eng.expected_tax, eng.expected_basis, pl_accounts(fs_result)) if eng.expected_tax is not None else None
    ret = RT.build({**engagement_dict(eng, user), "assets": data.get("assets") or [], "liabilities": data.get("liabilities") or []},
                   fs_result, comp, data.get("return_overrides") or {}, field_refs_for(eng.year_of_assessment, eng.entity_type))
    alerts += [{"stage": "return", "severity": "review", "text": f"Return field missing: {m['label']} ({m['section']})."} for m in ret["missing"]]
    pending = eng.adjustments.filter(status=Adjustment.Status.PROPOSED).count()
    if pending:
        alerts.append({"stage": "computation", "severity": "review", "text": f"{pending} proposed adjustment(s) waiting for approval: not in the figures yet."})
    statements = depth(eng, fs_result, comp)
    for key in ("equity", "cash_flows"):
        chk = ((statements or {}).get(key) or {}).get("check")
        if chk and not chk["passed"]:
            alerts.append({"stage": "fs", "severity": "review", "text": f"{chk['label']}: difference {chk['difference']:,.2f}."})
    return {"engagement": engagement_dict(eng, user), "financials": _clean(fs_result), "computation": comp, "reverse": rev, "return": ret,
            "statements": statements, "alerts": alerts, "years": years(), "rules_status": rules.data.get("status", ""), "documents": docs,
            "adjustments": [adjustment_dict(a) for a in eng.adjustments.select_related("created_by", "decided_by", "evidence")],
            "levers": [{k: lv[k] for k in ("key", "label", "group", "amount", "scope")} for lv in RV.levers(ins, pl_accounts(fs_result))],
            "progress": progress(eng, fs_result, comp)}


def depth(eng: TaxEngagement, fs_result, comp) -> dict | None:
    """The statement of changes in equity, cash flows, notes, policies and the draft audit report (companies)."""
    if not fs_result or fs_result.get("kind") != "company":
        return None
    info = engagement_dict(eng)
    ye = eng.fy_end.strftime("%d %B %Y").lstrip("0") if eng.fy_end else "[year end]"
    full = fs_scope(eng) == "full"
    return {"scope": fs_scope(eng), "equity": DP.equity_changes(fs_result) if full else None, "cash_flows": DP.cash_flows(fs_result) if full else None,
            "notes": DP.notes(fs_result, info, comp, _standard_rate(eng)), "audit_report": DP.audit_report(info, ye) if eng.audited else None}


def _standard_rate(eng: TaxEngagement):
    """The year's standard corporate rate, for the income tax note's reconciliation (None when the rules lack it)."""
    try:
        return rules_for(eng.year_of_assessment).value("company", "standard_rate")
    except Exception:  # noqa: BLE001 - the note falls back to the computation's own figures
        return None


def _clean(fs_result):
    if not fs_result:
        return fs_result
    return {k: v for k, v in fs_result.items() if k != "lines"} | ({"tb": fs_result["lines"]} if "lines" in fs_result else {})


def progress(eng: TaxEngagement, fs_result, comp) -> dict:
    """How complete each stage is (0-100), for the overview cards."""
    data = eng.data or {}
    q_parts = [all(getattr(eng, f) for f, _ in REQUIRED_BASIC), bool(data.get("income")) or eng.entity_type == "company",
               bool(data.get("payments")), eng.expected_tax is not None or bool(data.get("expected_skipped")), bool(eng.issue.attachments.exists())]
    fs_parts = [bool(fs_result), bool(fs_result) and all(c["passed"] for c in fs_result.get("checks", [])) if fs_result and fs_result.get("kind") == "company" else bool(fs_result),
                not eng.adjustments.filter(scope="accounting", status="proposed").exists(), eng.stage("fs")["status"] in ("ready_for_review", "approved")]
    c_parts = [comp is not None, not [f for f in (comp or {}).get("flags", []) if f["severity"] == "blocking"],
               not eng.adjustments.filter(scope="tax", status="proposed").exists(), eng.stage("computation")["status"] in ("ready_for_review", "approved")]
    pct = lambda parts: round(sum(1 for p in parts if p) / len(parts) * 100)  # noqa: E731
    return {"questionnaire": pct(q_parts), "fs": pct(fs_parts), "computation": pct(c_parts),
            "return": 100 if eng.stage("return")["status"] == "approved" else (60 if eng.stage("computation")["status"] == "approved" else 0)}


def engagement_dict(eng: TaxEngagement, user=None) -> dict:
    return {"id": eng.id, "task": eng.issue.key, "entity_type": eng.entity_type, "residency": eng.residency, "year_of_assessment": eng.year_of_assessment,
            "fy_end": eng.fy_end.isoformat() if eng.fy_end else None, "tax_type": eng.tax_type, "legal_name": eng.legal_name, "client_name": eng.client_name,
            "tin": eng.tin, "nic_or_reg": eng.nic_or_reg, "address": eng.address, "activity": eng.activity,
            "reporting_framework": eng.reporting_framework, "audited": eng.audited,
            "expected_tax": str(eng.expected_tax) if eng.expected_tax is not None else None, "expected_basis": eng.expected_basis,
            "data": eng.data or {}, "stages": {s: eng.stage(s) for s in TaxEngagement.STAGES}, "version": eng.version,
            "can_approve": bool(user and can_approve(user, eng.issue)), "can_validate": can_validate(user), "updated_at": eng.updated_at}


def adjustment_dict(a: Adjustment) -> dict:
    return {"id": a.id, "kind": a.kind, "scope": a.scope, "target": a.target, "label": a.label,
            "original": str(a.original) if a.original is not None else None, "proposed": str(a.proposed) if a.proposed is not None else None,
            "difference": str(a.proposed - a.original) if a.original is not None and a.proposed is not None else None,
            "lines": a.lines, "reason": a.reason, "evidence": {"id": a.evidence_id, "name": a.evidence.filename} if a.evidence_id else None,
            "evidence_note": a.evidence_note, "status": a.status, "history": a.history,
            "created_by": a.created_by.display_name if a.created_by_id else "", "created_at": a.created_at,
            "decided_by": a.decided_by.display_name if a.decided_by_id else "", "decided_at": a.decided_at, "decision_note": a.decision_note}


def set_stage(eng: TaxEngagement, stage: str, status: str, user) -> None:
    before = eng.stage(stage)["status"]
    eng.stages = {**(eng.stages or {}), stage: {"status": status, "by": user.display_name, "at": timezone.now().isoformat()}}
    eng.save(update_fields=["stages", "updated_at"])
    log(eng, user, "stage", {"stage": stage, "from": before, "to": status})


def touch(eng: TaxEngagement, stage: str, user) -> None:
    """Something in a stage changed: an approved stage goes back to In progress (and so do the stages after it,
    whose figures follow from it); a stage not started is now in progress."""
    order = list(TaxEngagement.STAGES)
    stages = dict(eng.stages or {})
    for s in order[order.index(stage):]:
        status = (stages.get(s) or {}).get("status", "not_started")
        if s == stage and status == "not_started":
            stages[s] = {"status": "in_progress", "by": user.display_name, "at": timezone.now().isoformat()}
        elif status in ("approved", "ready_for_review"):
            stages[s] = {"status": "in_progress", "by": user.display_name, "at": timezone.now().isoformat(), "reopened": True}
    eng.stages = stages
    eng.version += 1
