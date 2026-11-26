"""The backend's side of Local_Tax_AI (AFIT, 22 Nov 2026), the Local Tax workflow's own LangGraph agent service
(local-tax-ai/). The backend sends the agent the engagement as the engine worked it out and the person's request;
the agent answers in a fixed shape; the answer is checked again here before it is shown or stored. The agent
explains, suggests and asks - every figure stays the engine's:
- chat: questions about the engagement. A "what if" names the line and the amount; the engine works out the
  effect, marked hypothetical.
- map-tb: an FS heading suggested for each trial balance account (a person accepts each).
- analyse: the income's treatment, possible tax adjustments and reliefs, with reasons and references.
- reverse: the questions to ask the accountant about the difference from the expected tax, and the lines to look at.
- return: the draft return checked for gaps and inconsistencies.
- extract: a document attached to the task read into lines citing it (confirmed by a person before use).
- tb-story: a DUMMY trial balance made up from the accountant's story (illustration and practice only), balanced by
  code and labelled dummy data wherever it is used.
- ppe-classify: each PPE account's asset category and role, suggested (a person accepts each).
"""
import base64
import json
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings

from .engine import fs as FS
from .engine import reverse as RV
from .models import AiMessage, Extraction

AGENTS = ("chat", "map-tb", "analyse", "reverse", "return", "extract", "policies", "tb-story", "ppe-classify")
MAX_FILE = 15 * 1024 * 1024


class Unavailable(Exception):
    pass


class Refused(Exception):
    pass


def _call(path: str, body: dict, timeout: int = 180) -> dict:
    request = urllib.request.Request(
        settings.LOCAL_TAX_AI_URL.rstrip("/") + path, data=json.dumps(body, default=str).encode(),
        headers={"Content-Type": "application/json", "X-Local-Tax-Token": settings.LOCAL_TAX_AI_TOKEN}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - a fixed, configured URL
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read() or b"{}").get("detail", "")
        except ValueError:
            pass
        if exc.code == 400:
            raise Refused(detail or "Local_Tax_AI refused the request.") from exc
        if exc.code == 502 and detail:  # it answered, but the AI's answer couldn't be used: say why
            raise Unavailable(detail) from exc
        raise Unavailable("Local_Tax_AI is not available just now. Try again shortly.") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise Unavailable("Local_Tax_AI is not available just now. Try again shortly.") from exc


def context(eng, st: dict) -> dict:
    """The engagement as the agent sees it: the facts and the engine's figures (no document text)."""
    e = st["engagement"]
    comp = st.get("computation") or {}
    fin = st.get("financials") or {}
    return {
        "engagement": {k: e.get(k) for k in ("task", "entity_type", "residency", "year_of_assessment", "fy_end", "tax_type", "legal_name", "activity",
                                             "reporting_framework", "audited", "expected_tax", "expected_basis")},
        "questionnaire": {k: (e.get("data") or {}).get(k) for k in ("income", "assets", "liabilities", "payments", "qualifying_payments", "losses_bf")},
        "computation": {"lines": [{k: ln[k] for k in ("key", "label", "amount", "note", "rule")} for ln in comp.get("lines") or []],
                        "taxable_income": comp.get("taxable_income"), "income_tax": comp.get("income_tax"), "payable": comp.get("payable"),
                        "rules": comp.get("rules") or []},
        "financials": {"pl": (fin.get("pl") or {}).get("current"), "checks": fin.get("checks"), "unusual": fin.get("unusual"),
                       "tb": [{k: ln.get(k) for k in ("code", "name", "amount", "comparative", "heading")} for ln in fin.get("tb") or []][:400]}
        if fin.get("kind") == "company" else ({"sources": fin.get("sources")} if fin else None),
        "reverse": st.get("reverse"),
        "levers": st.get("levers") or [],
        "alerts": st.get("alerts") or [],
        "adjustments": [{k: a[k] for k in ("kind", "scope", "label", "original", "proposed", "status", "reason")} for a in st.get("adjustments") or []],
        "headings": {k: v[1] for k, v in FS.HEADINGS.items()},
        "asset_classes": asset_classes(e.get("year_of_assessment")),
        "fs_scope": (e.get("data") or {}).get("fs_scope") or "full",
    }


def asset_classes(year) -> list[str]:
    from .engine.rules import MissingRules, load

    try:
        return [k for k in (load(year).get("capital_allowances") or {}) if k != "balancing"]
    except MissingRules:
        return []


def run(agent: str, eng, st: dict, body: dict, user) -> dict:
    from . import services as S

    ctx = context(eng, st)
    if agent == "chat":
        question = " ".join(str(body.get("question") or "").split())[:2000]
        if len(question) < 2:
            raise Refused("Ask a question.")
        history = [{"role": m.role, "text": m.text[:1500]} for m in eng.ai_messages.order_by("-at")[:8]][::-1]
        AiMessage.objects.create(engagement=eng, user=user, role="person", text=question)
        out = _call("/v1/chat", {"context": ctx, "question": question, "history": history})
        answer = str(out.get("answer") or "").strip()[:4000] or "I couldn't answer that this time. Try asking it differently."
        data = {"points": [str(p)[:600] for p in (out.get("points") or [])][:8], "uncertain": bool(out.get("uncertain"))}
        wi = out.get("what_if") or None
        if isinstance(wi, dict) and wi.get("lever") and wi.get("proposed") not in (None, ""):
            fs_result = S.financials(eng)
            try:
                data["what_if"] = RV.effect(S.inputs(eng, fs_result), S.rules_for(eng.year_of_assessment), str(wi["lever"]), Decimal(str(wi["proposed"])),
                                            eng.expected_tax, eng.expected_basis, S.pl_accounts(fs_result))
            except Exception:  # noqa: BLE001 - a line the engagement does not have: the answer stands without figures
                data["what_if"] = None
        msg = AiMessage.objects.create(engagement=eng, role="ai", text=answer, data=S._jsonable(data))
        return {"message": message_dict(msg)}
    if agent == "map-tb":
        out = _call("/v1/map-tb", {"context": ctx})
        codes = {ln.code for ln in eng.tb_lines.all()}
        suggestions = [{"code": str(s.get("code")), "heading": s.get("heading"), "reason": str(s.get("reason") or "")[:300]}
                       for s in out.get("suggestions") or [] if str(s.get("code")) in codes and s.get("heading") in FS.HEADINGS]
        S.log(eng, None, "ai_map_tb", {"suggestions": len(suggestions)}, actor="ai")
        return {"suggestions": suggestions, "notes": [str(n)[:400] for n in out.get("notes") or []][:10]}
    if agent in ("analyse", "reverse", "return"):
        out = _call(f"/v1/{agent}", {"context": ctx, "request": str(body.get("request") or "")[:1000]})
        lever_keys = {lv["key"] for lv in st.get("levers") or []}
        items = [{"title": str(i.get("title") or "")[:200], "text": str(i.get("text") or "")[:1200], "reference": str(i.get("reference") or "")[:300],
                  "lever": i.get("lever") if i.get("lever") in lever_keys else None, "severity": i.get("severity") if i.get("severity") in ("high", "medium", "low") else "medium",
                  "needs_review": bool(i.get("needs_review", True))} for i in out.get("items") or []][:20]
        S.log(eng, None, f"ai_{agent}", {"items": len(items)}, actor="ai")
        return {"summary": str(out.get("summary") or "")[:1500], "questions": [str(q)[:500] for q in out.get("questions") or []][:8], "items": items}
    if agent == "tb-story":
        story = " ".join(str(body.get("story") or "").split())[:4000]
        if len(story) < 20:
            raise Refused("Tell the story of the business in a few sentences: what it does, its size, the year's events.")
        out = _call("/v1/tb-story", {"context": ctx, "request": story}, timeout=240)
        rows, notes = story_rows(out.get("accounts") or [], ctx["fs_scope"])
        S.log(eng, user, "ai_tb_story", {"accounts": len(rows)}, actor="ai")
        return {"rows": rows, "story": story, "assumptions": [str(a)[:400] for a in out.get("assumptions") or []][:12],
                "notes": notes + [str(n)[:400] for n in out.get("notes") or []][:8]}
    if agent == "ppe-classify":
        ppe = st.get("ppe") or {}
        accounts = [{"code": a["code"], "name": a["name"]} for a in ppe.get("accounts") or []]
        if not accounts:
            raise Refused("The trial balance has no property, plant and equipment accounts to classify.")
        categories = [{"key": c["key"], "label": c["label"]} for c in ppe.get("policy") or []]
        out = _call("/v1/ppe-classify", {"policies": [{"accounts": accounts, "categories": categories}]})
        codes, keys = {a["code"] for a in accounts}, {c["key"] for c in categories}
        suggestions = [{"code": str(x.get("code")), "category": x.get("category") if x.get("category") in keys else "",
                        "role": x.get("role") if x.get("role") in ("cost", "accumulated") else "cost", "reason": str(x.get("reason") or "")[:300]}
                       for x in out.get("suggestions") or [] if str(x.get("code")) in codes]
        S.log(eng, None, "ai_ppe_classify", {"suggestions": len(suggestions)}, actor="ai")
        return {"suggestions": suggestions, "notes": [str(n)[:400] for n in out.get("notes") or []][:10]}
    if agent == "policies":
        # Phase 3: the standard policies tailored to the entity - suggestions the accountant accepts one by one.
        standard = [{"key": p["key"], "title": p["title"], "text": p["text"]}
                    for n in (st.get("statements") or {}).get("notes") or [] if n["key"] == "policies" for p in n["policies"]]
        if not standard:
            raise Refused("The accounting policies need the mapped trial balance first.")
        out = _call("/v1/policies", {"context": ctx, "policies": standard})
        keys = {p["key"] for p in standard}
        policies = [{"key": p["key"], "title": str(p.get("title") or "")[:120], "text": str(p.get("text") or "")[:3000]}
                    for p in out.get("policies") or [] if p.get("key") in keys]
        S.log(eng, None, "ai_policies", {"policies": len(policies)}, actor="ai")
        return {"policies": policies, "notes": [str(n)[:400] for n in out.get("notes") or []][:10]}
    # extract: a document attached to the task, read into lines that cite it
    from apps.issues.models import Attachment

    att = Attachment.objects.filter(pk=body.get("attachment_id"), issue=eng.issue).first()
    if att is None:
        raise Refused("Choose a document attached to this task.")
    data = att.file.read()
    if len(data) > MAX_FILE:
        raise Refused("The document is too large to read (15 MB at most).")
    out = _call("/v1/extract", {"context": ctx, "name": att.filename, "kind": str(body.get("kind") or "auto")[:40],
                                "content_b64": base64.b64encode(data).decode()}, timeout=300)
    lines = [{"description": str(ln.get("description") or "")[:300], "amount": str(ln.get("amount") or ""), "category": str(ln.get("category") or "")[:40],
              "code": str(ln.get("code") or "")[:40], "comparative": str(ln.get("comparative") or ""), "date": str(ln.get("date") or "")[:10],
              "cite": str(ln.get("cite") or "")[:200]}
             for ln in out.get("lines") or []][:2000]
    ex = Extraction.objects.create(engagement=eng, attachment=att, kind=str(out.get("kind") or "other")[:40],
                                   data={"lines": lines, "gaps": [str(g)[:300] for g in out.get("gaps") or []][:20], "summary": str(out.get("summary") or "")[:1000],
                                         "year_of_assessment": str(out.get("year_of_assessment") or "")[:9]})
    S.log(eng, None, "ai_extract", {"document": att.filename, "lines": len(lines), "extraction": ex.id}, actor="ai")
    return {"extraction": extraction_dict(ex)}


def story_rows(accounts: list, scope: str) -> tuple[list[dict], list[str]]:
    """The dummy trial balance's accounts, checked: unique codes, a known heading (or the rule's), numbers only. A full
    set is made to balance by its retained earnings, in each column, and the accountant is told by how much."""
    rows, seen, notes = [], set(), []
    for n, a in enumerate(accounts):
        if not isinstance(a, dict) or not str(a.get("name") or "").strip():
            continue
        code = " ".join(str(a.get("code") or "").split())[:40] or f"D{n + 1:03d}"
        if code in seen:
            continue
        seen.add(code)

        def num(v):
            try:
                return Decimal(str(v).replace(",", "")).quantize(Decimal("1")) if str(v or "").strip() else Decimal("0")
            except Exception:  # noqa: BLE001 - not a number: nothing
                return Decimal("0")

        name = " ".join(str(a["name"]).split())[:200]
        heading = a.get("heading") if a.get("heading") in FS.HEADINGS else FS.suggest_heading(name, num(a.get("amount")))
        rows.append({"code": code, "name": name, "heading": heading, "amount": num(a.get("amount")), "comparative": num(a.get("comparative"))})
    if scope == "full" and rows:
        re_row = next((r for r in rows if r["heading"] == "retained_earnings"), None)
        if re_row is None:
            re_row = {"code": "3999", "name": "Retained earnings", "heading": "retained_earnings", "amount": Decimal("0"), "comparative": Decimal("0")}
            rows.append(re_row)
        for col, label in (("amount", "this year"), ("comparative", "last year")):
            diff = sum((r[col] for r in rows), Decimal("0"))
            if diff:
                re_row[col] -= diff
                notes.append(f"Retained earnings adjusted by {-diff:,.0f} so that {label}'s column balances.")
    return [{**r, "amount": str(r["amount"]), "comparative": str(r["comparative"])} for r in rows][:300], notes


def message_dict(m: AiMessage) -> dict:
    return {"id": m.id, "role": m.role, "text": m.text, "data": m.data, "by": m.user.display_name if m.user_id else "", "at": m.at}


def extraction_dict(ex: Extraction) -> dict:
    return {"id": ex.id, "kind": ex.kind, "document": ex.attachment.filename if ex.attachment_id else "", "data": ex.data, "status": ex.status,
            "created_at": ex.created_at}



def rule_check(rule: dict, name: str, data: bytes) -> dict:
    """Phase 4: Local_Tax_AI reads a law document (Act, amendment, gazette) for a rule under review and says
    whether it agrees, with a quote and where. The tax professional decides; nothing is stored as validated."""
    if len(data) > MAX_FILE:
        raise Refused("The document is too large to read (15 MB at most).")
    out = _call("/v1/rule-check", {"rule": rule, "name": name, "content_b64": base64.b64encode(data).decode()}, timeout=300)
    return {"agrees": out.get("agrees") if out.get("agrees") in ("yes", "no", "unclear") else "unclear",
            "value_in_document": str(out.get("value_in_document") or "")[:200], "quote": str(out.get("quote") or "")[:1500],
            "cite": str(out.get("cite") or "")[:300], "note": str(out.get("note") or "")[:1000], "document": name}
