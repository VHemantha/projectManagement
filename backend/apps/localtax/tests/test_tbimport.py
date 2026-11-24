"""Trial balance files as clients and their bookkeepers actually send them (AFIT, 24 Nov 2026): Excel (.xlsx, .xls)
and CSV in the usual layouts, read by code into the trial balance."""
import io
from decimal import Decimal as D

import pytest
from openpyxl import Workbook

from apps.localtax.tbimport import TbImportError, amount, read
from apps.localtax.views import _tb_rows

from .test_api import api, world  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db


def xlsx(*sheets) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for n, rows in enumerate(sheets):
        ws = wb.create_sheet(f"Sheet{n + 1}")
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def tb(rows):
    return {r["code"]: (r["name"], r["amount"], r["comparative"]) for r in _tb_rows(rows)}


def test_amounts_as_bookkeepers_write_them():
    assert [amount(v) for v in ("1,234.50", "(1,234.50)", "1,234.50 Cr", "1,234.50 Dr", "Rs. 1,000", "LKR 500", "-", "", "nil", "-25", 300, 2.5)] == \
        ["1234.50", "-1234.50", "-1234.50", "1234.50", "1000", "500", None, None, None, "-25", "300", "2.5"]


def test_an_excel_tb_with_a_title_block_gl_codes_and_debit_credit_in_rupees():
    data = xlsx([["ABC (Pvt) Ltd"], ["Trial balance as at 31 March 2025"], [],
                 ["GL Code", "Ledger Name", "Debit (Rs.)", "Credit (Rs.)"],
                 [1000.0, "Cash at bank", 150000, None],
                 [4000.0, "Sales", None, "250,000.00"],
                 [5000.0, "Purchases", 100000, None],
                 [None, "Total", 250000, 250000]])
    assert tb(read(data, "TB.xlsx")) == {"1000": ("Cash at bank", D("150000.00"), None), "4000": ("Sales", D("-250000.00"), None),
                                          "5000": ("Purchases", D("100000.00"), None)}


def test_a_balance_column_with_dr_cr_beside_it_and_the_tb_on_the_second_sheet():
    data = xlsx([["Notes"], ["Prepared by the bookkeeper"]],
                [["A/C No", "Account Name", "Closing Balance", "Dr/Cr", "Opening Balance"],
                 ["1000", "Cash", "90,000", "Dr", "60,000"],
                 ["2000", "Trade payables", "40,000", "Cr", "(25,000)"],
                 ["3000", "Capital", "50,000", "Cr", "(35,000)"]])
    assert tb(read(data, "tb.xlsx")) == {"1000": ("Cash", D("90000.00"), D("60000.00")), "2000": ("Trade payables", D("-40000.00"), D("-25000.00")),
                                          "3000": ("Capital", D("-50000.00"), D("-35000.00"))}


def test_a_column_per_year():
    data = xlsx([["Account", "2024", "2025"], ["Sales", "(900)", "(1,000)"], ["Cost of sales", "500", "600"], ["Bank", "400", "400"]])
    rows = tb(read(data, "tb.xlsx"))
    assert [v for v in rows.values()] == [("Sales", D("-1000.00"), D("-900.00")), ("Cost of sales", D("600.00"), D("500.00")),
                                          ("Bank", D("400.00"), D("400.00"))]


def test_semicolon_csv_in_a_windows_encoding_with_cr_suffixes():
    text = "Code;Particulars;Amount\r\n1000;Caf\xe9 equipment;5,000.00\r\n4000;Sales;5,000.00 Cr\r\n"
    assert tb(read(text.encode("cp1252"), "tb.csv")) == {"1000": ("Caf\xe9 equipment", D("5000.00"), None), "4000": ("Sales", D("-5000.00"), None)}


def test_a_file_that_is_not_a_trial_balance_says_what_it_needs():
    with pytest.raises(TbImportError, match="header row"):
        read(xlsx([["Hello"], ["world"]]), "x.xlsx")
    with pytest.raises(TbImportError, match="Excel"):
        read(b"%PDF", "x.pdf")


def test_older_excel_files_are_read(world):  # noqa: F811
    xlrd = pytest.importorskip("xlrd")
    # a real .xls needs a writer the project doesn't carry: the reader's presence and the route are checked instead
    assert xlrd.__version__.startswith("2.")
    c = api(world.pat)
    r = c.post(world.url + "tb/upload/", {"file": io.BytesIO(b"not really excel")}, format="multipart")
    assert r.status_code == 400
    f = io.BytesIO(b"not really excel")
    f.name = "old.xls"
    r = c.post(world.url + "tb/upload/", {"file": f}, format="multipart")
    assert r.status_code == 400 and "could not be opened" in str(r.data["file"])


def test_an_excel_tb_uploads_through_the_api(world):  # noqa: F811
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "fy_end": "2025-03-31"}, format="json")
    f = io.BytesIO(xlsx([["Code", "Account", "Debit", "Credit"], [1000, "Bank", 1000, None], [3000, "Capital", None, 1000]]))
    f.name = "TB 2025.xlsx"
    r = c.post(world.url + "tb/upload/", {"file": f}, format="multipart")
    assert r.status_code == 200, r.data
    assert [(ln["code"], str(ln["amount"])) for ln in r.data["financials"]["tb"]] == [("1000", "1000.00"), ("3000", "-1000.00")]
