"""Reading a trial balance file (AFIT, 22 Nov 2026; widened 24 Nov 2026). Read by code only: the figures never pass
through the AI.

Accepted files:
- Excel: .xlsx, .xlsm, and the older .xls.
- CSV / text: comma, semicolon, tab or pipe separated, in UTF-8 or a Windows encoding.

Each sheet is tried in turn. The header row (in the first 40 rows) is found by its words:
- the account: "Code", "GL Code", "A/C No"; and "Account", "Account Name", "Ledger", "Particulars", "Description";
- the figures:
  - "Debit" / "Dr" and "Credit" / "Cr", including "Debit (Rs.)" and "Dr Balance";
  - or one "Amount" / "Balance" / "Closing Balance" column, with an optional Dr/Cr column beside it;
  - or year columns ("2025", "2024", "FY 2024/25"), the latest being this year;
- optionally "Prior year", "Comparative" or "Opening balance".

Amounts may be written 1,234.50, (1,234.50), 1,234.50 Cr, Rs. 1,234 or "-"; codes stored as numbers keep their
original text (1000, not 1000.0). Total and blank rows are skipped.
"""
import csv
import io
import re

CODE = r"(gl|ledger|account|a/?c|acc)?\.?\s*(code|no\.?|number|#|id)"
NAME = r"(account|a/?c)?\s*(name|title|description|head)|accounts?|ledger( name| account)?|particulars|description|details|narration"
DEBIT = r"(debit|dr\.?)(\s*balance|\s*amount)?"
CREDIT = r"(credit|cr\.?)(\s*balance|\s*amount)?"
AMOUNT = r"(closing |net |current )?(amount|balance|value)|current year|this year|cy|total"
COMPARATIVE = r"comparatives?|prior year|previous year|last year|py|opening( balance)?|brought forward|b/?f"
SIDE = r"dr\s*/\s*cr|cr\s*/\s*dr|dr\.?\s*or\s*cr\.?|side|type|nature"
UNIT = r"\s*(\((lkr|rs\.?|rupees|usd)\)|lkr|rs\.?)?\s*$"
YEAR = re.compile(r"^(fy\s*|ya\s*|year\s*)?(20\d{2})(\s*[/-]\s*(\d{2,4}))?$")


class TbImportError(ValueError):
    pass


def _clean_header(cell) -> str:
    return " ".join(str(cell if cell is not None else "").replace("\n", " ").lower().replace("_", " ").split()).strip(" :.")


def _matches(pattern: str, text: str) -> bool:
    return bool(re.fullmatch(f"(?:{pattern}){UNIT}", text))


def _sheets(data: bytes, name: str) -> list[list[list]]:
    """Every sheet of the file as rows of cells (at most 5,000 rows each)."""
    lower = name.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001 - a damaged or password-protected file
            raise TbImportError("The Excel workbook could not be opened (is it password-protected or damaged?).") from exc
        return [[list(r) for r in ws.iter_rows(values_only=True)][:5000] for ws in wb.worksheets]
    if lower.endswith(".xls"):
        try:
            import xlrd

            book = xlrd.open_workbook(file_contents=data)
        except ImportError as exc:
            raise TbImportError("Older Excel (.xls) files can't be read on this server yet: save it as .xlsx or CSV.") from exc
        except Exception as exc:  # noqa: BLE001
            raise TbImportError("The Excel (.xls) workbook could not be opened (is it password-protected or damaged?).") from exc
        out = []
        for sh in book.sheets():
            rows = []
            for r in range(min(sh.nrows, 5000)):
                rows.append([_xls_cell(sh.cell(r, c)) for c in range(sh.ncols)])
            out.append(rows)
        return out
    if lower.endswith((".csv", ".txt", ".tsv")):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sample = text[:20000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delim = dialect.delimiter
        except csv.Error:
            delim = "\t" if lower.endswith(".tsv") or sample.count("\t") > sample.count(",") else ","
        return [[list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)][:5000]]
    raise TbImportError("Use an Excel (.xlsx, .xls) or CSV file.")


def _xls_cell(cell):
    import xlrd

    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return None
    return cell.value


def _text(v) -> str:
    """A cell as text; a whole number stored as a float (an account code 1000.0) as 1000."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return " ".join(str(v if v is not None else "").split())


def amount(v) -> str | None:
    """A printed amount as a plain number ("-1234.50"): brackets, a trailing Cr or a leading minus are negative;
    "Rs.", "LKR", commas and a trailing Dr are dropped; "-", "nil" or empty is None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).strip().lower().replace(",", "").replace("rs.", "").replace("rs", "").replace("lkr", "").replace(" ", "")
    if s in ("", "-", "--", "nil", "n/a"):
        return None
    neg = False
    if s.endswith("cr"):
        neg, s = True, s[:-2]
    elif s.endswith("dr"):
        s = s[:-2]
    if s.startswith("(") and s.endswith(")"):
        neg, s = not neg, s[1:-1]
    if s.startswith("-"):
        neg, s = not neg, s[1:]
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    return f"-{s}" if neg else s


def _header(row: list) -> dict | None:
    """The columns of a header row, or None when the row is not one."""
    cols, years = {}, []
    for i, cell in enumerate(row):
        text = _clean_header(cell)
        if not text:
            continue
        m = YEAR.match(text)
        if m:
            years.append((int(m.group(4) if m.group(4) and len(m.group(4)) == 4 else m.group(2)), i))
            continue
        for key, pattern in (("code", CODE), ("debit", DEBIT), ("credit", CREDIT), ("side", SIDE), ("comparative", COMPARATIVE),
                             ("amount", AMOUNT), ("name", NAME)):
            if key not in cols and _matches(pattern, text):
                cols[key] = i
                break
    if "amount" not in cols and "debit" not in cols and "credit" not in cols and years:
        years.sort(reverse=True)
        cols["amount"] = years[0][1]
        if len(years) > 1 and "comparative" not in cols:
            cols["comparative"] = years[1][1]
    if "name" not in cols and "code" in cols and ("amount" in cols or "debit" in cols or "credit" in cols):
        cols["name"] = cols["code"]  # a file with only the account's name under "Account"/"Code"
    if "name" in cols and ("amount" in cols or "debit" in cols or "credit" in cols):
        return cols
    return None


def read(data: bytes, name: str) -> list[dict]:
    sheets = _sheets(data, name)
    for rows in sheets:
        for n, row in enumerate(rows[:40]):
            cols = _header(row)
            if not cols:
                continue
            out = []
            for r in rows[n + 1:]:
                def get(k):
                    return r[cols[k]] if k in cols and cols[k] < len(r) else None

                label = _text(get("name"))
                code = _text(get("code")) if cols.get("code") != cols.get("name") else ""
                if not label or re.match(r"^(total|grand total|net|difference|balance c/?f)\b", label.lower()):
                    continue
                amt, dr, cr = amount(get("amount")), amount(get("debit")), amount(get("credit"))
                if amt is not None and "side" in cols and str(get("side") or "").strip().lower().startswith("cr") and not amt.startswith("-"):
                    amt = f"-{amt}"
                if amt is None and dr is None and cr is None and amount(get("comparative")) is None:
                    continue  # a heading or blank row
                if dr is not None and cr is not None and amt is None:
                    # both columns: credit balances are negative; a credit written already negative stays a credit
                    cr = cr.lstrip("-")
                out.append({"code": code, "name": label, "debit": dr, "credit": cr.lstrip("-") if cr else cr, "amount": amt,
                            "comparative": amount(get("comparative"))})
            if out:
                return out
    raise TbImportError("No trial balance was found: the file needs a header row with the account (e.g. Account / Account Name) and its "
                        "figures (Debit and Credit, or Amount / Balance, or the years). Download the template to see the layout.")
