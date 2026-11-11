"""Exact amounts and dates as the documents give them. Every sum in the reconciliation is a Decimal."""
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
CENT = Decimal("0.01")
_NUM = re.compile(r"^\(?-?\$?\s*[\d,]*\.?\d+\)?$")


def q(value) -> Decimal:
    """Rounded to the cent."""
    return (value if isinstance(value, Decimal) else Decimal(str(value))).quantize(CENT, rounding=ROUND_HALF_UP)


def amount(value) -> Decimal | None:
    """A cell or a piece of text as an amount: 1,234.56 | (1,234.56) | -1234.56 | $1,234 | 1,234.56 CR.
    None when there is no amount ('', '-', text)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace("−", "-").replace("NZD", "").replace("NZ$", "").strip()
    if text in ("", "-", "--", "—", "n/a", "N/A"):
        return None
    sign = 1
    upper = text.upper()
    if upper.endswith("CR"):
        sign, text = -1, text[:-2].strip()
    elif upper.endswith("DR"):
        text = text[:-2].strip()
    if text.endswith("-"):  # 1,234.56- (some ledgers)
        sign, text = -sign, text[:-1].strip()
    if not _NUM.match(text.replace(" ", "")):
        return None
    negative = text.startswith("(") and text.endswith(")") or text.startswith("-") or text.startswith("(-")
    digits = re.sub(r"[^\d.]", "", text)
    if digits in ("", "."):
        return None
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    return -value * sign if negative else value * sign


def money(value) -> Decimal:
    """An amount, with nothing as zero (for sums of columns where empty means nil)."""
    found = amount(value)
    return ZERO if found is None else found


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%b-%y", "%d %b %y",
                 "%Y/%m/%d", "%d.%m.%Y")


_SLASHED = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\b")


def month_first(values) -> bool:
    """Whether a document writes dates month first (myIR's exports: "3/31/2026"): some date in it has a
    second number above 12 and none has a first number above 12."""
    us = nz = False
    for v in values:
        m = _SLASHED.match(str(v or ""))
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            us, nz = us or b > 12, nz or a > 12
    return us and not nz


def day(value, us: bool = False) -> date | None:
    """A cell or text as a date (New Zealand order: day first; month first when `us`)."""
    if value is None or value == "":
        return None
    if us and isinstance(value, str) and (m := _SLASHED.match(value)):
        year = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        try:
            return date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and 20000 < value < 80000:  # an Excel serial date
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = " ".join(str(value).strip().split())
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text[:len(text)], fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if m:
        return date.fromisoformat(m.group(1))
    return None


def iso(value: date | None) -> str:
    return value.isoformat() if value else ""


def s(value: Decimal | None) -> str:
    """An amount for JSON: a string, so no precision is lost on the way."""
    return "" if value is None else str(q(value))


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    last = (date(year + (month // 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last))


def month_end(d: date) -> date:
    return date(d.year + (d.month // 12), d.month % 12 + 1, 1) - timedelta(days=1)


def gst_due_date(period_end: date) -> date:
    """When a GST return and payment are due (IRD): the 28th of the month after the period ends,
    except a period ending 31 March (7 May) or 30 November (15 January)."""
    if period_end.month == 3:
        return date(period_end.year, 5, 7)
    if period_end.month == 11:
        return date(period_end.year + 1, 1, 15)
    nxt = add_months(date(period_end.year, period_end.month, 1), 1)
    return date(nxt.year, nxt.month, 28)
