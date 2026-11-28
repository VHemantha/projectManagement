"""Property, plant and equipment and depreciation for a Local client's card (AFIT, 24 Nov 2026): the workflow around
engine/depreciation.py.

- The depreciation policy is the client's own (ClientPolicy), so every later year's card uses it too.
- What the accountant enters for this year is kept in the engagement's data["ppe"]:
  - "accounts": the category and role of each PPE account. The rule suggests them, the AI may, and a person decides.
  - "opening": the opening cost and accumulated depreciation by category, when given rather than read from the TB.
  - "additions" and "disposals": the year's asset movements, each with its dates and source.
  - "options": the account the disposal proceeds were posted to, if any.
  - "approved": the approved schedule's fingerprint, by whom and when, and the journal it posted.
- Approving posts the depreciation journal (JE-DEP, one per card), or replaces it. A schedule that has changed since
  its approval says so, and is posted again only when it is approved again.
"""
import re
from datetime import date

from django.utils import timezone

from . import services as S
from .engine import depreciation as DEP
from .engine import fs as FS
from .models import Adjustment, ClientPolicy, TaxEngagement

AUTO = "auto:depreciation"
REF = "JE-DEP"


def client_of(eng: TaxEngagement):
    return getattr(eng.issue.project, "client", None)


def policy_for(eng: TaxEngagement) -> tuple[list[dict], dict]:
    """(the client's depreciation policy, about it). TASKO's illustrative rates until the client's own are saved."""
    client = client_of(eng)
    row = ClientPolicy.objects.filter(client=client).select_related("updated_by").first() if client else None
    if row and row.depreciation:
        return row.depreciation, {"saved": True, "client": client.name, "by": row.updated_by.display_name if row.updated_by_id else "",
                                  "at": row.updated_at}
    return DEP.default_policy(), {"saved": False, "client": client.name if client else ""}


def clean_policy(rows) -> list[dict]:
    """The policy as entered: each category's key, label, method, rate and residual (fractions of 1)."""
    out, seen, errors = [], set(), {}
    for n, r in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(r, dict):
            continue
        label = " ".join(str(r.get("label") or "").split())[:80]
        if not label:
            continue
        key = str(r.get("key") or "").strip()[:40] or "_".join(label.lower().split())[:40]
        key = "".join(ch for ch in key if ch.isalnum() or ch == "_") or f"category_{n + 1}"
        if key in seen:
            errors[f"policy.{n}"] = f"{label}: the category is listed twice."
            continue
        seen.add(key)
        method = r.get("method") if r.get("method") in DEP.METHODS else "straight_line"
        vals = {}
        for f, name in (("rate", "annual rate"), ("residual", "residual value")):
            v = DEP.d(r.get(f))
            if v > 1:  # given as a percentage
                v = v / 100
            if not 0 <= v <= 1:
                errors[f"policy.{n}.{f}"] = f"{label}: the {name} is a percentage between 0 and 100."
            vals[f] = str(v.normalize()) if v else "0"
        out.append({"key": key, "label": label, "method": method, **vals})
    if errors:
        from .validation import Invalid

        raise Invalid(errors)
    return out


def save_policy(eng: TaxEngagement, rows, user) -> list[dict]:
    client = client_of(eng)
    if client is None:
        from .validation import Invalid

        raise Invalid({"policy": "This card has no client to keep the policy with."})
    policy = clean_policy(rows)
    ClientPolicy.objects.update_or_create(client=client, defaults={"depreciation": policy, "updated_by": user})
    S.touch(eng, "fs", user)
    eng.save()
    S.log(eng, user, "depreciation_policy", {"client": client.name, "policy": policy})
    return policy


def _tb_before_depreciation(eng: TaxEngagement) -> list[dict]:
    """The trial balance with every approved accounting journal except the depreciation journal itself."""
    adjs = [{"lines": a.lines} for a in S.approved(eng, "accounting") if a.target != AUTO]
    return FS.apply_adjustments(S.tb_lines(eng), adjs)


def state(eng: TaxEngagement, fs_result: dict | None) -> dict | None:
    """Everything the PPE & Depreciation section shows. None when the card keeps no books, or when it has no PPE
    accounts and no asset movements entered."""
    if not fs_result or fs_result.get("kind") != "company":
        return None
    data = (eng.data or {}).get("ppe") or {}
    policy, about = policy_for(eng)
    tb = _tb_before_depreciation(eng)
    accounts = DEP.classify(tb, policy, data.get("accounts") or {})
    additions, disposals = data.get("additions") or [], data.get("disposals") or []
    if not accounts and not additions and not disposals:
        return None
    has_comp = any(ln.get("comparative") is not None for ln in tb)
    opening = DEP.openings(accounts, policy, data.get("opening") or {}, has_comp)
    sched = DEP.schedule(policy, opening, additions, disposals, eng.fy_end)
    prior = set(data.get("prior_categories") or [])
    labels = {c["key"]: c["label"] for c in policy}
    for a in accounts:
        if not a["category"]:
            sched["flags"].insert(0, {"severity": "blocking", "text": f"PPE account {a['code']} {a['name']}: choose its category."})
        elif prior and a["category"] not in prior and a.get("by") == "rule":
            # last year's statements set the categories (AFIT, 28 Nov 2026): a category they don't have is confirmed by a person
            sched["flags"].insert(0, {"severity": "blocking", "text": f"PPE account {a['code']} {a['name']} is put in "
                                      f"“{labels.get(a['category'], a['category'])}”, a category last year's statements don't have: choose its category "
                                      "(one of last year's, or confirm this new one)."})
    for k in data.get("rate_needed") or []:
        c = next((c for c in policy if c["key"] == k), None)
        if c and not DEP.d(c.get("rate")) and not re.search(r"\bland\b", c["label"], re.I):
            sched["flags"].append({"severity": "review", "text": f"“{c['label']}” comes from last year's statements: set its depreciation rate in the "
                                                                 "client's depreciation policy."})
    if not has_comp and not data.get("opening"):
        sched["flags"].append({"severity": "review", "text": "The trial balance has no prior-year column: enter the opening balances, or read them "
                                                             "from last year's financial statements."})
    proceeds_code = (data.get("options") or {}).get("proceeds_code") or ""
    jr = DEP.journal(sched, accounts, tb, policy, proceeds_code) if sched.get("available") else {"lines": [], "explain": [], "residual": "0", "charge": "0"}
    fp = DEP.fingerprint(jr["lines"], sched.get("totals"), policy)
    appr = data.get("approved") or {}
    auto = eng.adjustments.filter(target=AUTO, status=Adjustment.Status.APPROVED).first()
    status = "not_approved"
    if appr:
        status = "approved" if appr.get("fingerprint") == fp else "changed"
    reconciliation = DEP.reconcile(sched, accounts, fs_result.get("lines") or []) if appr and sched.get("available") else []
    return {"policy": policy, "policy_about": about, "methods": DEP.METHODS, "accounts": accounts, "opening": opening, "schedule": sched,
            "journal": jr, "fingerprint": fp, "status": status, "approved": appr, "journal_ref": auto.ref if auto else "",
            "reconciliation": reconciliation, "options": {"proceeds_code": proceeds_code}, "additions": additions, "disposals": disposals,
            "blocking": [f["text"] for f in sched.get("flags") or [] if f["severity"] == "blocking"]}


def alerts(ppe: dict | None) -> list[dict]:
    if not ppe:
        return []
    out = []
    if ppe["status"] == "not_approved" and (ppe["schedule"].get("totals") or {}).get("charge"):
        out.append({"stage": "fs", "severity": "review", "text": "This year's depreciation is not approved yet: review PPE & Depreciation and approve "
                                                                 "it to post the depreciation journal."})
    if ppe["status"] == "changed":
        out.append({"stage": "fs", "severity": "review", "text": "The depreciation schedule has changed since it was approved (policy, assets or the "
                                                                 "trial balance): approve it again to update the depreciation journal."})
    for r in ppe["reconciliation"]:
        if not r["agrees"] and ppe["status"] == "approved":
            out.append({"stage": "fs", "severity": "blocking",
                        "text": f"PPE note does not agree with the trial balance for {r['label']}: cost {r['schedule_cost']:,.2f} against "
                                f"{r['tb_cost']:,.2f}, accumulated depreciation {r['schedule_accumulated']:,.2f} against {r['tb_accumulated']:,.2f}."})
    return out


class NotReady(Exception):
    pass


def approve(eng: TaxEngagement, user) -> dict:
    """The schedule approved: the depreciation journal (JE-DEP) posted to the trial balance, replacing any earlier
    one (its lines kept in the journal's history), so the year's depreciation is never posted twice."""
    fs_result = S.financials(eng)
    st = state(eng, fs_result)
    if st is None:
        raise NotReady("There are no PPE accounts or asset movements to depreciate.")
    if not st["schedule"].get("available"):
        raise NotReady(st["schedule"].get("reason") or "The schedule can't be worked out yet.")
    if st["blocking"]:
        raise NotReady("Resolve these first: " + " ".join(st["blocking"]))
    lines = st["journal"]["lines"]
    auto = eng.adjustments.filter(target=AUTO).first()
    now = timezone.now()
    reason = (f"Depreciation for the year from the approved schedule: {DEP.d(st['schedule']['totals']['charge']):,.2f}"
              + (f"; {'; '.join(st['journal']['explain'])}" if st["journal"]["explain"] else ""))[:2000]
    if len(lines) >= 2:
        if auto:
            if auto.lines != lines:
                auto.history = [*auto.history, {"lines": auto.lines, "reason": auto.reason, "at": now.isoformat(), "by": user.display_name,
                                                "replaced": True}]
            auto.lines, auto.reason, auto.status = lines, reason, Adjustment.Status.APPROVED
            auto.decided_by, auto.decided_at = user, now
            auto.entry_date = eng.fy_end
            auto.save()
        else:
            auto = Adjustment.objects.create(engagement=eng, kind=Adjustment.Kind.JOURNAL, scope="accounting", target=AUTO, ref=REF,
                                             label="Depreciation for the year (from the depreciation schedule)", lines=lines, reason=reason,
                                             status=Adjustment.Status.APPROVED, created_by=user, decided_by=user, decided_at=now, entry_date=eng.fy_end)
    elif auto:
        auto.history = [*auto.history, {"lines": auto.lines, "reason": auto.reason, "at": now.isoformat(), "by": user.display_name, "replaced": True}]
        auto.lines, auto.status, auto.reason = [], Adjustment.Status.REJECTED, "Nothing to post: the trial balance already agrees with the schedule."
        auto.save()
    data = dict(eng.data or {})
    ppe = dict(data.get("ppe") or {})
    # The fingerprint of the schedule as it now stands: the journal posted, the trial balance before it is unchanged.
    ppe["approved"] = {"fingerprint": st["fingerprint"], "at": now.isoformat(), "by": user.display_name,
                       "charge": str(st["schedule"]["totals"]["charge"]), "lines": len(lines)}
    data["ppe"] = ppe
    eng.data = data
    S.touch(eng, "fs", user)
    eng.save()
    S.log(eng, user, "depreciation_approved", {"charge": str(st["schedule"]["totals"]["charge"]), "journal": REF if len(lines) >= 2 else "",
                                               "lines": S._jsonable(lines)})
    return state(eng, S.financials(eng))


def as_of(v) -> str:
    return v.isoformat() if isinstance(v, date) else str(v or "")
