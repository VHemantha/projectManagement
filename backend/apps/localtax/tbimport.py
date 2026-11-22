"""Reading a trial balance file (AFIT, 22 Nov 2026): an Excel workbook (.xlsx) or a CSV, the first sheet. The
header row is found by its words (code / account / name / debit / credit / amount / balance / comparative or prior
year); each row below is an account. Read by code only - the figures never pass through the AI."""
import csv
import io
import re

HEADERS = {
    "code": r"^(a/?c|acc(ount)?)?\s*(code|no\.?|number|#)$|^code$",
    "name": r"^(account|account name|name|description|particulars|ledger)$",
    "debit": r"^(debit|dr)(\s*\(lkr\))?$",
    "credit": r"^(credit|cr)(\s*\(lkr\))?$",
    "amount": r"^(amount|balance|closing balance|current year|this year|cy)(\s*\(lkr\))?$",
    "comparative": r"^(comparative|prior year|previous year|last year|py)(\s*\(lkr\))?$",
}


class TbImportError(ValueError):
    pass


def _rows(data: bytes, name: str) -> list[list]:
    if name.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001 - a damaged or password-protected file
            raise TbImportError("The workbook could not be opened.") from exc
        ws = wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)][:5000]
    if name.lower().endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        return [list(r) for r in csv.reader(io.StringIO(text))][:5000]
    raise TbImportError("Use an Excel (.xlsx) or CSV file.")


def read(data: bytes, name: str) -> list[dict]:
    rows = _rows(data, name)
    for n, row in enumerate(rows[:30]):
        cols = {}
        for i, cell in enumerate(row):
            text = " ".join(str(cell or "").lower().split())
            for key, pattern in HEADERS.items():
                if key not in cols and re.match(pattern, text):
                    cols[key] = i
        if "name" in cols and ("amount" in cols or "debit" in cols or "credit" in cols):
            out = []
            for r in rows[n + 1:]:
                get = lambda k: (r[cols[k]] if k in cols and cols[k] < len(r) else None)  # noqa: E731
                if not str(get("name") or "").strip() or re.match(r"^(total|grand total)", str(get("name")).strip().lower()):
                    continue
                out.append({"code": get("code"), "name": get("name"), "debit": get("debit"), "credit": get("credit"), "amount": get("amount"),
                            "comparative": get("comparative")})
            return out
    raise TbImportError("No header row was found: the file needs columns such as Code, Account, Debit and Credit (or Amount).")
