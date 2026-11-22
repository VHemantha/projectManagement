"""Client info pre-filled from the client's supporting documents (AFIT, Team 3 > Local cards only).

The documents are the task's attachments - uploaded directly, or copied from the client's Google Drive folder once it
is shared with TASKO's service account (read-only). Local_Tax_AI reads each document once per version (bank
statements, bank balance confirmations, trial balances, ledgers, prior returns, certificates...) and says what it
states, citing where. Here, by code, the readings of all documents are put together:

- each client detail, income, payment, asset, liability, trial balance and bank balance becomes a Suggestion with
  its sources; nothing is used until the accountant confirms it (as it is or edited) - then it flows through to the
  financial statements and the tax computation like anything typed in;
- what is missing, unclear or inconsistent - across documents (two TINs, two balances for one account on one date,
  two trial balances), with the client info, or with the trial balance (bank balances at the year end against cash
  and bank) - becomes a Flag for the accountant to resolve.
"""
import base64
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.utils import timezone

from . import ai
from . import services as S
from . import validation as V
from .models import Flag, SourceDocument, Suggestion, TaxEngagement

FIELD_LABELS = {"legal_name": "Legal name", "tin": "TIN", "nic_or_reg": "Registration / NIC no.", "address": "Address", "activity": "Nature of business",
                "fy_end": "Financial year end", "entity_type": "Entity type"}
LISTS = ("income", "payments", "assets", "liabilities")
MAX_SYNC = 60  # files copied from Drive per request; the rest on the next sync


# --- documents ------------------------------------------------------------------------------------------------------

def ensure_documents(eng: TaxEngagement) -> None:
    """Every file attached to the task is a supporting document (uploads included)."""
    known = set(eng.documents.values_list("attachment_id", flat=True))
    for att in eng.issue.attachments.exclude(pk__in=known).order_by("id"):
        SourceDocument.objects.create(engagement=eng, attachment=att, origin=SourceDocument.Origin.UPLOAD)


def document_dict(d: SourceDocument) -> dict:
    r = d.reading or {}
    return {"id": d.id, "attachment_id": d.attachment_id, "name": d.attachment.filename, "url": d.attachment.file.url if d.attachment.file else "",
            "origin": d.origin, "drive_path": d.drive_path, "drive_url": d.drive_url, "kind": d.kind, "summary": d.summary,
            "period_end": d.period_end.isoformat() if d.period_end else None, "read_at": d.read_at, "read_error": d.read_error,
            "found": {"fields": len(r.get("fields") or []), "lines": len(r.get("lines") or []), "balances": len(r.get("balances") or [])}}


def suggestion_dict(s: Suggestion) -> dict:
    return {"id": s.id, "target": s.target, "value": s.value, "sources": s.sources, "status": s.status, "edited": s.edited,
            "decided_by": s.decided_by.display_name if s.decided_by_id else "", "decided_at": s.decided_at}


def flag_dict(f: Flag) -> dict:
    return {"id": f.id, "kind": f.kind, "target": f.target, "text": f.text, "sources": f.sources, "status": f.status, "resolution": f.resolution,
            "resolved_by": f.resolved_by.display_name if f.resolved_by_id else "", "resolved_at": f.resolved_at}


def payload(eng: TaxEngagement) -> dict:
    ensure_documents(eng)
    folder = getattr(eng.issue, "drive_folder", None)
    return {
        "documents": [document_dict(d) for d in eng.documents.select_related("attachment")],
        "suggestions": [suggestion_dict(s) for s in eng.suggestions.exclude(status=Suggestion.Status.SUPERSEDED).select_related("decided_by")],
        "flags": [flag_dict(f) for f in eng.flags.exclude(status=Flag.Status.SUPERSEDED).select_related("resolved_by")],
        "drive": {"url": folder.folder_url if folder else "", "folder_id": folder.folder_id if folder else "",
                  "synced_at": (eng.data or {}).get("drive_synced_at")},
    }


# --- Google Drive -----------------------------------------------------------------------------------------------------

def drive_account() -> dict:
    try:
        return ai._call("/v1/drive/account", {}, timeout=30)
    except ai.Unavailable:
        return {"account_email": "", "configured": False, "detail": "Local_Tax_AI is not available just now."}


def link_drive(eng: TaxEngagement, url: str, user) -> dict:
    """The client's Drive folder for this card (the task's folder): checked that TASKO can open it."""
    from apps.precheck.models import JobFolder, folder_id_from

    folder_id = folder_id_from(url)
    if not folder_id:
        raise ai.Refused("Paste the link to the client's Google Drive folder (https://drive.google.com/drive/folders/...).")
    listing = ai._call("/v1/drive/list", {"folder_id": folder_id}, timeout=120)  # Refused (400) carries the share instruction
    JobFolder.objects.update_or_create(issue=eng.issue, defaults={"folder_id": folder_id, "folder_url": url.strip()[:500], "updated_by": user})
    eng.issue.refresh_from_db()
    S.log(eng, user, "drive_linked", {"folder_id": folder_id, "files": len(listing.get("files") or [])})
    return listing


def sync_drive(eng: TaxEngagement, user) -> dict:
    """New or changed files in the folder copied to the task (a changed one is read again); the rest left as they are."""
    folder = getattr(eng.issue, "drive_folder", None)
    if folder is None:
        raise ai.Refused("Link the client's Google Drive folder first.")
    listing = ai._call("/v1/drive/list", {"folder_id": folder.folder_id}, timeout=120)
    by_id = {d.drive_file_id: d for d in eng.documents.filter(origin=SourceDocument.Origin.DRIVE)}
    added, updated, unchanged, skipped, left = 0, 0, 0, [], 0
    for f in listing.get("files") or []:
        doc = by_id.get(f["id"])
        if doc and doc.drive_version == f["version"]:
            unchanged += 1
            continue
        if added + updated >= MAX_SYNC:
            left += 1
            continue
        try:
            got = ai._call("/v1/drive/download", {"file_id": f["id"]}, timeout=180)
        except ai.Refused as exc:
            skipped.append({"name": f["name"], "reason": str(exc)})
            continue
        from apps.issues.models import Attachment

        att = Attachment.objects.create(issue=eng.issue, file=ContentFile(base64.b64decode(got["content_b64"]), name=got["name"][:200]),
                                        filename=got["name"][:255], uploaded_by=user)
        fields = {"attachment": att, "drive_version": f["version"], "drive_path": f.get("path", "")[:500], "drive_url": f.get("web_url", "")[:1000],
                  "read_at": None, "reading": {}, "kind": "", "summary": "", "read_error": ""}
        if doc:
            old = doc.attachment
            for k, v in fields.items():
                setattr(doc, k, v)
            doc.save()
            old.delete()
            updated += 1
        else:
            SourceDocument.objects.create(engagement=eng, origin=SourceDocument.Origin.DRIVE, drive_file_id=f["id"][:200], **fields)
            added += 1
    eng.data = {**(eng.data or {}), "drive_synced_at": timezone.now().isoformat()}
    eng.save(update_fields=["data", "updated_at"])
    S.log(eng, user, "drive_synced", {"added": added, "updated": updated, "unchanged": unchanged, "skipped": len(skipped), "left": left})
    return {"added": added, "updated": updated, "unchanged": unchanged, "skipped": skipped, "left": left + int(bool(listing.get("truncated")))}


# --- reading ------------------------------------------------------------------------------------------------------------

def _context(eng: TaxEngagement) -> dict:
    data = eng.data or {}
    return {"engagement": {k: getattr(eng, k) for k in ("entity_type", "residency", "year_of_assessment", "legal_name", "tin", "nic_or_reg", "address",
                                                         "activity")} | {"fy_end": eng.fy_end.isoformat() if eng.fy_end else ""},
            "already_entered": {k: len(data.get(k) or []) for k in LISTS} | {"trial_balance_accounts": eng.tb_lines.count()}}


def to_read(eng: TaxEngagement, again: bool = False) -> list[int]:
    ensure_documents(eng)
    qs = eng.documents.all() if again else eng.documents.filter(read_at__isnull=True)
    return list(qs.values_list("id", flat=True))


def read_document(eng: TaxEngagement, doc: SourceDocument) -> SourceDocument:
    att = doc.attachment
    try:
        data = att.file.read()
    except (OSError, ValueError):
        data = b""
    if not data or len(data) > ai.MAX_FILE:
        doc.read_error, doc.read_at, doc.reading = ("The file is empty or too large to read (15 MB at most)."), timezone.now(), {}
        doc.save()
        return doc
    try:
        out = ai._call("/v1/prefill", {"context": _context(eng), "name": att.filename, "content_b64": base64.b64encode(data).decode()}, timeout=300)
        doc.reading, doc.read_error = out, ""
        doc.kind, doc.summary = str(out.get("kind") or "other")[:30], str(out.get("summary") or "")[:500]
        pe = str(out.get("period_end") or "")
        doc.period_end = date.fromisoformat(pe) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pe) else None
    except ai.Refused as exc:
        doc.reading, doc.read_error = {}, str(exc)[:500]
    doc.read_at = timezone.now()
    doc.save()
    return doc


# --- putting the readings together --------------------------------------------------------------------------------------

def _norm(field: str, v: str) -> str:
    v = " ".join(str(v).split()).casefold()
    if field in ("tin", "nic_or_reg"):
        return re.sub(r"[^0-9a-z]", "", v)
    if field == "legal_name":
        return re.sub(r"[^0-9a-z]", "", v.replace("private", "pvt").replace("limited", "ltd").replace("&", "and"))
    return v


def _dec(v) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _src(doc: SourceDocument, cite: str) -> dict:
    return {"document": doc.attachment.filename, "attachment_id": doc.attachment_id, "document_id": doc.id, "cite": str(cite or "")[:200]}


def _where(sources: list[dict]) -> str:
    return "; ".join(f"{s['document']}{(' ' + s['cite']) if s.get('cite') else ''}" for s in sources[:4])


def finish(eng: TaxEngagement, user) -> dict:
    """Suggestions and flags from every document's reading, replacing the earlier ones still waiting."""
    run = uuid.uuid4().hex[:12]
    eng.suggestions.filter(status=Suggestion.Status.PENDING).update(status=Suggestion.Status.SUPERSEDED)
    eng.flags.filter(status=Flag.Status.OPEN).update(status=Flag.Status.SUPERSEDED)
    decided = {(s.target, _key(s.target, s.value)) for s in eng.suggestions.filter(status__in=["confirmed", "rejected"])}
    docs = list(eng.documents.select_related("attachment").exclude(read_at__isnull=True))
    data = eng.data or {}
    suggestions, flags = [], []

    def suggest(target, value, sources):
        if (target, _key(target, value)) not in decided:
            suggestions.append(Suggestion(engagement=eng, run=run, target=target, value=S._jsonable(value), sources=sources))

    def flag(kind, text, sources=(), target=""):
        flags.append(Flag(engagement=eng, run=run, kind=kind, target=target, text=text[:1000], sources=list(sources)))

    # client details: one suggestion per distinct value; disagreements flagged
    by_field: dict[str, dict[str, dict]] = {}
    for d in docs:
        for f in (d.reading or {}).get("fields") or []:
            slot = by_field.setdefault(f["field"], {}).setdefault(_norm(f["field"], f["value"]), {"value": f["value"], "sources": []})
            slot["sources"].append(_src(d, f.get("cite")))
    for field, values in by_field.items():
        label = FIELD_LABELS.get(field, field)
        current = str(getattr(eng, field) or "") if field != "fy_end" else (eng.fy_end.isoformat() if eng.fy_end else "")
        if len(values) > 1:
            flag("inconsistent", f"{label} differs between documents: " + "; ".join(f"“{v['value']}” ({_where(v['sources'])})" for v in values.values()),
                 [s for v in values.values() for s in v["sources"]], f"field:{field}")
        for norm, v in values.items():
            if current and _norm(field, current) == norm:
                continue
            if current and len(values) == 1:
                flag("inconsistent", f"{label} in the client info is “{current}”, but {_where(v['sources'])} says “{v['value']}”.", v["sources"], f"field:{field}")
            suggest(f"field:{field}", v["value"], v["sources"])

    # trial balances
    tbs = [d for d in docs if any(ln["list"] == "trial_balance" for ln in (d.reading or {}).get("lines") or [])]
    if len(tbs) > 1:
        flag("inconsistent", f"{len(tbs)} documents contain a trial balance ({', '.join(d.attachment.filename for d in tbs)}): confirm only the right one.",
             [_src(d, "") for d in tbs], "trial_balance")
    for d in tbs:
        lines = [{"code": ln.get("code") or "", "name": ln.get("description") or ln.get("code") or "", "amount": ln.get("amount") or "0",
                  "comparative": ln.get("comparative") or ""} for ln in d.reading["lines"] if ln["list"] == "trial_balance"]
        total = sum((_dec(ln["amount"]) or Decimal(0) for ln in lines), Decimal(0))
        if abs(total) >= 1:
            flag("unclear", f"The trial balance in {d.attachment.filename} does not balance (difference {total:,.2f}): check it was read completely.",
                 [_src(d, "")], "trial_balance")
        suggest("trial_balance", {"lines": lines, "document": d.attachment.filename}, [_src(d, f"{len(lines)} accounts")])
        if eng.fy_end and d.period_end and d.period_end != eng.fy_end:
            flag("inconsistent", f"{d.attachment.filename} is as at {d.period_end:%d %b %Y}, but the financial year ends on {eng.fy_end:%d %b %Y}.",
                 [_src(d, "")], "trial_balance")

    # income, payments, assets, liabilities: one suggestion per line not already entered
    for d in docs:
        for ln in (d.reading or {}).get("lines") or []:
            if ln["list"] not in LISTS or not ln.get("amount"):
                continue
            item = _line(ln["list"], ln, _where([_src(d, ln.get("cite"))]))
            if not _already(data.get(ln["list"]) or [], ln["list"], item):
                suggest(ln["list"], item, [_src(d, ln.get("cite"))])

    # bank balances: agree across documents, with the year end, and with the trial balance
    balances: dict[tuple, list] = {}
    for d in docs:
        for b in (d.reading or {}).get("balances") or []:
            acct = re.sub(r"[^0-9]", "", b.get("account") or "")[-4:] or (b.get("bank") or "").casefold()
            balances.setdefault((acct, b.get("date") or ""), []).append((d, b))
    for (acct, day), found in balances.items():
        values = {(_dec(b["balance"]) or Decimal(0)).quantize(Decimal("0.01")) for _, b in found}
        if len(values) > 1:
            flag("inconsistent", f"Account …{acct} on {day or 'an undated statement'}: " + "; ".join(
                f"{_dec(b['balance']):,.2f} ({d.attachment.filename} {b.get('cite', '')})" for d, b in found) + ".",
                [_src(d, b.get("cite")) for d, b in found], "bank_balance")
        d, b = found[0]
        suggest("bank_balance", {"bank": b.get("bank", ""), "account": b.get("account", ""), "date": b.get("date", ""), "balance": b["balance"]},
                [_src(x, y.get("cite")) for x, y in found])
    if eng.fy_end and balances:
        at_ye = {k: v for k, v in balances.items() if k[1] == eng.fy_end.isoformat()}
        if not at_ye:
            flag("missing", f"No bank statement or balance confirmation shows the balances at the year end ({eng.fy_end:%d %b %Y}).", target="bank_balance")
        elif eng.entity_type == TaxEngagement.Entity.COMPANY and eng.tb_lines.exists():
            bank_total = sum(((_dec(v[0][1]["balance"]) or Decimal(0)) for v in at_ye.values()), Decimal(0))
            tb_cash = sum((ln.amount for ln in eng.tb_lines.filter(heading="cash") if not re.search(r"cash in hand|petty", ln.name, re.I)), Decimal(0))
            if abs(bank_total - tb_cash) >= 1:
                flag("inconsistent", f"Bank balances at the year end total {bank_total:,.2f} in the documents, but the trial balance's bank accounts total "
                                     f"{tb_cash:,.2f} (difference {bank_total - tb_cash:,.2f}): reconcile them.",
                     [_src(d, b.get("cite")) for v in at_ye.values() for d, b in v], "bank_balance")

    # what the AI flagged in each document, and the documents it could not read
    for d in docs:
        for f in (d.reading or {}).get("flags") or []:
            flag(f["kind"], f"{d.attachment.filename}: {f['text']}", [_src(d, f.get("cite"))])
        if d.read_error:
            flag("unclear", f"{d.attachment.filename} could not be read: {d.read_error}", [_src(d, "")])

    # what is still missing after the documents
    targets = {s.target for s in suggestions}
    for field, label in S.REQUIRED_BASIC:
        if field in FIELD_LABELS and not getattr(eng, field) and f"field:{field}" not in targets:
            flag("missing", f"{label} is not in the client info and was not found in the documents: ask the client.", target=f"field:{field}")
    if eng.entity_type == TaxEngagement.Entity.COMPANY and not eng.tb_lines.exists() and "trial_balance" not in targets:
        flag("missing", "No trial balance in the client info or the documents: upload it, or ask the client for it.", target="trial_balance")
    if not docs:
        flag("missing", "No supporting documents have been read yet.")

    Suggestion.objects.bulk_create(suggestions)
    Flag.objects.bulk_create(flags)
    S.log(eng, user, "prefill", {"run": run, "documents": len(docs), "suggestions": len(suggestions), "flags": len(flags)}, actor="ai")
    return payload(eng)


def _line(kind: str, ln: dict, source: str) -> dict:
    if kind == "income":
        return {"category": ln.get("category") if ln.get("category") in S.INCOME_CATEGORIES else "other", "description": ln.get("description", ""),
                "amount": ln["amount"], "source": source}
    if kind == "payments":
        return {"type": ln.get("category") if ln.get("category") in S.PAYMENT_TYPES else "other", "amount": ln["amount"], "date": ln.get("date", ""),
                "reference": (ln.get("description") or "")[:80], "source": source}
    if kind == "assets":
        return {"kind": ln.get("category") if ln.get("category") in S.ASSET_KINDS else "other", "description": ln.get("description", ""),
                "value": ln["amount"], "source": source}
    return {"kind": ln.get("category") if ln.get("category") in S.LIABILITY_KINDS else "other", "description": ln.get("description", ""),
            "value": ln["amount"], "source": source}


def _amount(item: dict) -> Decimal | None:
    return _dec(item.get("amount") if item.get("amount") not in (None, "") else item.get("value"))


def _already(existing: list, kind: str, item: dict) -> bool:
    a = _amount(item)
    return any(_amount(x) == a and (x.get("type") or x.get("category") or x.get("kind")) == (item.get("type") or item.get("category") or item.get("kind"))
               for x in existing)


def _key(target: str, value) -> str:
    if target.startswith("field:"):
        return _norm(target[6:], value if isinstance(value, str) else str(value))
    if target == "trial_balance":
        return f"{(value or {}).get('document')}:{len((value or {}).get('lines') or [])}"
    if isinstance(value, dict):
        return f"{_amount(value) or _dec(value.get('balance'))}:{value.get('type') or value.get('category') or value.get('kind') or value.get('account')}:" \
               f"{value.get('date', '')}"
    return str(value)


# --- the accountant's decisions -------------------------------------------------------------------------------------

def decide(eng: TaxEngagement, sug: Suggestion, decision: str, user, value=None) -> None:
    """Confirm (with the accountant's edit, if any) or reject. A confirmed value is written to the client info with
    its source; from there it flows into the statements and the computation."""
    if decision == "reject":
        sug.status = Suggestion.Status.REJECTED
    else:
        final = sug.value if value is None else value
        sug.edited = value is not None and value != sug.value
        source = _where(sug.sources) + (" (edited by the accountant)" if sug.edited else "")
        _apply(eng, sug.target, final, source, user)
        sug.value = S._jsonable(final)
        sug.status = Suggestion.Status.CONFIRMED
    sug.decided_by, sug.decided_at = user, timezone.now()
    sug.save()
    S.log(eng, user, f"suggestion_{sug.status}", {"target": sug.target, "value": sug.value, "sources": sug.sources, "edited": sug.edited})


def _apply(eng: TaxEngagement, target: str, value, source: str, user) -> None:
    data = dict(eng.data or {})
    if target.startswith("field:"):
        field = target[6:]
        patch = {field: value}
        if field == "entity_type":
            patch["tax_type"] = "CIT" if value == "company" else "IIT"
        fields, _ = V.update(patch)
        for k, v in fields.items():
            setattr(eng, k, v)
        data["field_sources"] = {**(data.get("field_sources") or {}), field: source}
    elif target == "trial_balance":
        from .views import _replace_tb, _tb_rows

        rows = _tb_rows((value or {}).get("lines") or [])
        _replace_tb(eng, rows, user, f"Confirmed from {source}")
        eng.refresh_from_db()
        data = dict(eng.data or {})
    elif target == "bank_balance":
        item = {"bank": str(value.get("bank", ""))[:120], "account": str(value.get("account", ""))[:60], "date": str(value.get("date", ""))[:10],
                "balance": str(value.get("balance", "")), "source": source[:200]}
        if eng.entity_type == TaxEngagement.Entity.INDIVIDUAL:
            _, clean = V.update({"data": {"assets": (data.get("assets") or []) + [
                {"kind": "bank", "description": f"{item['bank']} {item['account']} at {item['date']}".strip(), "value": item["balance"], "source": source}]}})
            data.update(clean)
        else:
            _, clean = V.update({"data": {"bank_balances": (data.get("bank_balances") or []) + [item]}})
            data.update(clean)
    elif target in LISTS:
        _, clean = V.update({"data": {target: (data.get(target) or []) + [{**value, "source": source}]}})
        data.update(clean)
    else:
        raise V.Invalid({"target": "Unknown suggestion."})
    eng.data = data
    S.touch(eng, "questionnaire", user)
    eng.save()


def resolve(eng: TaxEngagement, f: Flag, resolution: str, user) -> None:
    f.status, f.resolution, f.resolved_by, f.resolved_at = Flag.Status.RESOLVED, resolution[:1000], user, timezone.now()
    f.save()
    S.log(eng, user, "flag_resolved", {"flag": f.text, "resolution": f.resolution})


def summary(eng: TaxEngagement) -> dict:
    return {"documents": eng.documents.count(), "unread": eng.documents.filter(read_at__isnull=True).count(),
            "to_verify": eng.suggestions.filter(status=Suggestion.Status.PENDING).count(), "open_flags": eng.flags.filter(status=Flag.Status.OPEN).count()}

