"""The draft income tax return (AFIT, 22 Nov 2026): the approved figures of the financial statements and the tax
computation placed in the return's sections and schedules, with the mandatory fields that are still missing.

The layout follows the structure of the IRD's individual and corporate income tax returns, but each field's
reference ("cage" number) is a placeholder: it must be checked against the year's return in RAMIS before use
(`validated: False`). The return is prepared for the accountant to enter into RAMIS; nothing is submitted.
"""
import re
from decimal import Decimal

ZERO = Decimal("0")


def _f(code: str, label: str, value, *, source: str = "", required: bool = False, kind: str = "amount") -> dict:
    missing = required and (value in (None, "") or (kind == "amount" and value == ZERO and False))
    return {"code": code, "label": label, "value": value, "source": source, "required": required, "missing": bool(missing), "kind": kind,
            "validated": False}


def build(engagement: dict, fs: dict | None, comp: dict, overrides: dict | None = None, field_refs: dict | None = None) -> dict:
    """{"sections": [{key, title, fields}], "missing": [...], "validated": bool}. `overrides`: the accountant's
    corrections, by field code (kept apart from the computed value). `field_refs`: the fields checked against the
    year's return in RAMIS (Phase 4), code -> {"official", "by", "at"}."""
    overrides = overrides or {}
    field_refs = field_refs or {}
    entity = engagement.get("entity_type")
    company = entity in ("company", "partnership")  # the books-based return (accounting profit, adjustments, allowances)
    basic = [
        _f("B1", "Taxpayer (legal) name", engagement.get("legal_name"), source="Questionnaire", required=True, kind="text"),
        _f("B2", "Taxpayer identification number (TIN)", engagement.get("tin"), source="Questionnaire", required=True, kind="text"),
        _f("B3", {"company": "Company registration no.", "partnership": "Business registration no."}.get(entity, "NIC / passport no."), engagement.get("nic_or_reg"), source="Questionnaire",
           required=True, kind="text"),
        _f("B4", "Year of assessment", engagement.get("year_of_assessment"), source="Questionnaire", required=True, kind="text"),
        _f("B5", "Residency", "Resident" if engagement.get("residency") == "resident" else "Non-resident", source="Questionnaire", kind="text"),
        _f("B6", "Nature of business / main activity", engagement.get("activity"), source="Questionnaire", required=True, kind="text"),
        _f("B7", "Reporting framework" if company else "Address", engagement.get("reporting_framework") if company else engagement.get("address"),
           source="Questionnaire", kind="text"),
    ]
    sections = [{"key": "basic", "title": "A. Basic information", "fields": basic}]
    lines = {ln["key"]: ln for ln in comp.get("lines") or []}

    def amount(key):
        ln = lines.get(key)
        return None if ln is None else ln["amount"]

    if company:
        income = [
            _f("C1", "Accounting profit before tax", comp.get("pbt"), source="Financial statements / computation", required=True),
            _f("C2", "Total add backs (disallowable expenses)", comp.get("total_add_backs"), source="Tax computation"),
            _f("C3", "Total deductions and allowances", comp.get("total_deductions"), source="Tax computation"),
            _f("C4", "Taxable income", comp.get("taxable_income"), source="Tax computation", required=True),
        ]
        if fs:
            income.insert(0, _f("C0", "Revenue", (fs.get("pl") or {}).get("current", {}).get("revenue"), source="Financial statements"))
        sections.append({"key": "income", "title": "B. Taxable income", "fields": income})
        adjustments = [_f(f"D{n}", ln["label"], ln["amount"], source="Tax computation") for n, ln in enumerate(
            [ln for ln in comp.get("lines") or [] if ln["key"].startswith(("add_", "ded_", "ca_", "losses", "qualifying"))], start=1)]
        sections.append({"key": "adjustments", "title": "C. Tax adjustments, capital allowances and losses", "fields": adjustments})
    else:
        income = [_f(f"C{n}", ln["label"], ln["amount"], source="Tax computation") for n, ln in enumerate(
            [ln for ln in comp.get("lines") or [] if ln["key"].startswith("inc_")], start=1)]
        income += [_f("C90", "Total assessable income", comp.get("assessable_income"), source="Tax computation", required=True),
                   _f("C91", "Exempt income", comp.get("exempt_income"), source="Tax computation"),
                   _f("C92", "Income subject to final withholding tax", comp.get("final_wht_income"), source="Tax computation"),
                   _f("C93", "Personal relief", amount("relief"), source="Tax computation"),
                   _f("C94", "Taxable income", comp.get("taxable_income"), source="Tax computation", required=True)]
        sections.append({"key": "income", "title": "B. Income, reliefs and deductions", "fields": income})
    tax = [_f("T1", "Income tax", comp.get("income_tax"), source="Tax computation", required=True),
           _f("T2", "Tax credits and payments", comp.get("credits"), source="Tax computation"),
           _f("T3", "Tax payable / (refundable)", comp.get("payable"), source="Tax computation", required=True)]
    sections.append({"key": "tax", "title": "D. Tax calculation and payments" if company else "C. Tax calculation and payments", "fields": tax})
    if not company:
        assets = [_f(f"S{n}", f"{a.get('kind', 'Asset')}: {a.get('description', '')}", a.get("value"), source="Questionnaire")
                  for n, a in enumerate(engagement.get("assets") or [], start=1)]
        liabilities = [_f(f"L{n}", f"{a.get('kind', 'Liability')}: {a.get('description', '')}", a.get("value"), source="Questionnaire")
                       for n, a in enumerate(engagement.get("liabilities") or [], start=1)]
        sections.append({"key": "assets", "title": "D. Statement of assets and liabilities", "fields": assets + liabilities})
    sections += schedules(comp, company)
    sections.append({"key": "declaration", "title": "Declaration", "fields": [
        _f("X1", "Declared by (name and designation)", overrides.get("X1"), required=True, kind="text"),
        _f("X2", "Date", overrides.get("X2"), required=True, kind="text")]})
    for s in sections:
        for f in s["fields"]:
            if f["code"] in overrides:
                f["computed"], f["value"], f["overridden"] = f["value"], overrides[f["code"]], True
                f["missing"] = f["required"] and overrides[f["code"]] in (None, "")
            # a review may cover one field ("C4") or a family of numbered lines ("SCA*")
            ref = field_refs.get(f["code"]) or field_refs.get(re.sub(r"\d+$", "", f["code"]) + "*")
            if ref:
                f["validated"], f["official"], f["reviewed_by"] = True, ref.get("official", ""), ref.get("by", "")
    missing = [{"section": s["title"], "code": f["code"], "label": f["label"]} for s in sections for f in s["fields"] if f["missing"]]
    fields = [f for s in sections for f in s["fields"]]
    validated = bool(fields) and all(f["validated"] for f in fields)
    unchecked = sum(1 for f in fields if not f["validated"])
    return {"sections": sections, "missing": missing, "validated": validated, "unchecked": unchecked,
            "note": ("Every field has been checked against the year's return in RAMIS." if validated else
                     f"{unchecked} field reference(s) are placeholders: check each against the year's return in RAMIS.") +
                    " Prepared for entry into RAMIS; not submitted."}


def schedules(comp: dict, company: bool) -> list[dict]:
    """The return's schedules: capital allowances (from the fixed asset register), tax losses, special-rate income
    and the tax credits, each line from the computation."""
    out = []
    ca = comp.get("capital_allowance_schedule")
    if company and ca and ca.get("rows"):
        fields = []
        for n, r in enumerate(ca["rows"], start=1):
            amount = r["allowance"] or -r["balancing_charge"] + r["balancing_allowance"]
            fields.append(_f(f"SCA{n}", f"{r['description']} ({r['label']}){' - disposed' if r['disposed'] else ''}", amount,
                             source="Fixed asset register"))
        t = ca["totals"]
        fields += [_f("SCA90", "Total capital allowances", t["allowance"], source="Fixed asset register"),
                   _f("SCA91", "Total balancing charges", t["balancing_charge"], source="Fixed asset register"),
                   _f("SCA92", "Total balancing allowances", t["balancing_allowance"], source="Fixed asset register"),
                   _f("SCA93", "Tax written-down value carried forward", t["wdv_cf"], source="Fixed asset register")]
        out.append({"key": "sch_ca", "title": "Schedule - Capital allowances", "fields": fields})
    ls = comp.get("loss_schedule")
    if ls and ls.get("rows"):
        fields = []
        for n, r in enumerate(ls["rows"], start=1):
            fields.append(_f(f"SL{n}", f"Loss of YA {r['ya']}: brought forward {r['bf']:,.2f}, used {r['utilised']:,.2f}", r["cf"],
                             source="Tax computation"))
        fields += [_f("SL90", "Losses brought forward", ls["totals"]["bf"], source="Tax computation"),
                   _f("SL91", "Losses utilised this year", ls["totals"]["utilised"], source="Tax computation"),
                   _f("SL92", "Losses carried forward", ls["totals"]["cf"], source="Tax computation")]
        out.append({"key": "sch_losses", "title": "Schedule - Tax losses", "fields": fields})
    special = [ln for ln in comp.get("lines") or [] if ln["key"].startswith("special_")]
    if special:
        out.append({"key": "sch_special", "title": "Schedule - Income at special rates", "fields": [
            _f(f"SR{n}", ln["label"], ln["amount"], source="Tax computation") for n, ln in enumerate(special, start=1)]})
    credits = [ln for ln in comp.get("lines") or [] if ln["key"].startswith("credit_")]
    if credits:
        out.append({"key": "sch_credits", "title": "Schedule - Tax credits and payments", "fields": [
            _f(f"SW{n}", ln["label"], -ln["amount"], source=ln.get("source") or "Questionnaire") for n, ln in enumerate(credits, start=1)]})
    return out
