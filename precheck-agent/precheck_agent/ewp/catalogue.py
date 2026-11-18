"""The template's workpapers, B1's rows and the cell plan of each workpaper (Electronic Workpapers Static
2026; mapped from the template itself, 16 Nov 2026). Every cell named here is an input cell of the
template; the writer still refuses any that holds a formula."""
from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "Electronic Workpapers Static 2026.xlsm"
TEMPLATE_NAME = "Electronic Workpapers Static 2026"

# The workpapers the agent prepares (L1 - GST - is the WP Agent's own GST reconciliation).
WORKPAPERS = [
    ("B1", "Review summary", "General ledger balances by workpaper, prior-year balances"),
    ("F1.1", "Bank reconciliation", "Bank statement balance, unprocessed receipts and payments"),
    ("M1", "Accounts payable", "Creditors at balance date against the ledger"),
    ("Q1", "Taxation due", "Tax payable, provisional and terminal tax, refunds"),
    ("Q3a", "Imputation credit account", "Opening ICA, tax paid, credits received and attached"),
    ("S2", "Income reconciliation", "Receivables movement and income per ledger"),
    ("T2", "Investment income", "Interest and dividends with RWT and imputation credits"),
    ("V1", "Expenses", "Expense accounts by category, with tax-treatment flags"),
    ("V2", "Use of home as office", "Home-office claim from its evidence"),
    ("V5", "Accounting fee reconciliation", "Fees billed against accounting fees in the accounts"),
    ("D1", "Journals", "Proposed journals from the workpapers (not posted)"),
]
KEYS = [k for k, _, _ in WORKPAPERS]
TITLES = {k: t for k, t, _ in WORKPAPERS}

ENTITY_TYPES = ("Company", "Trust", "Partnership", "Sole trader", "Look-through company")

# --- B1: one row per workpaper balance (column G "GL Bal", column K "Prior GL") -------------------------
B1_BANK_ROWS = list(range(18, 28))  # F1.1 .. F1.10
# The number of bank reconciliations: the Workbench's "Qty" column (M, headed in row 38) on the F1 row.
# The template's macro makes one F1 sheet per bank account from it; the agent does the same itself
# (AFIT, 18 Nov 2026).
WORKBENCH_BANK_QTY = "M40"
HIDDEN_F1_COUNT = "S25"  # the F1 group's sheet count in the hidden link table
HIDDEN_F1_ROW = 26  # the link table's row for F1.1, which F1.2 onwards copy
F_LEAD_ROWS = [10, 11]  # the F lead sheet's bank rows (F1.1, F1.2)
B1 = {
    "receivables": 28, "gst_asset": 30, "tax_asset": 31, "stock": 32, "wip": 33, "cash": 34, "prepayments": 35, "other_current_asset": 36,
    "payables": 46, "gst_liability": 47, "tax_liability": 48, "other_current_liability": 49, "term_loan": 116, "hire_purchase": 126,
    "fixed_assets": 84, "investments": 95, "other_assets": 106, "reserves": 141,
    "depreciation": 152, "sales": 153, "purchases": 154, "rental_income": 155, "rental_expenses": 156, "interest_income": 161, "dividend_income": 162,
    "fbt_reimbursement": 169, "wages": 173, "contractors": 174, "professional_fees": 175, "acc": 176, "entertainment": 177,
    "entertainment_nd": 178, "fbt": 179, "insurance": 180, "interest_overdraft": 181, "interest_hp": 182, "interest_loans": 183,
    "interest_other": 184, "uomi": 185, "lease": 186, "legal": 187, "legal_nd": 188, "rates": 189, "rent": 190, "repairs": 191,
    "vehicles": 192, "non_deductible": 193, "other_expenses": 194, "home_office": 195, "accounting_fees": 197,
    "current_account": 208, "retained_earnings": 228,
}
B1_LABEL = {
    "receivables": "Accounts receivable", "gst_asset": "Total GST (asset)", "tax_asset": "Taxation due (asset)", "stock": "Stock", "wip": "WIP",
    "cash": "Cash on hand", "prepayments": "Prepayments", "other_current_asset": "Other current assets", "payables": "Accounts payable",
    "gst_liability": "Total GST (liability)", "tax_liability": "Taxation due (liability)", "other_current_liability": "Other current liabilities",
    "term_loan": "Term loan", "hire_purchase": "Hire purchase", "fixed_assets": "Fixed assets", "investments": "Investments - shares",
    "other_assets": "Other assets", "reserves": "Reserves", "depreciation": "Depreciation", "sales": "Sales", "purchases": "Purchases",
    "rental_income": "Rental income", "rental_expenses": "Rental expenses", "interest_income": "Interest income", "dividend_income": "Dividend income",
    "fbt_reimbursement": "FBT reimbursement", "wages": "Wages", "contractors": "Contractor payments", "professional_fees": "Professional & consulting fees",
    "acc": "ACC", "entertainment": "Entertainment - deductible", "entertainment_nd": "Entertainment - non-deductible", "fbt": "FBT",
    "insurance": "Insurance", "interest_overdraft": "Interest - overdraft", "interest_hp": "Interest - HP", "interest_loans": "Interest - loans",
    "interest_other": "Interest - other", "uomi": "Use of money interest", "lease": "Lease payments", "legal": "Legal - deductible",
    "legal_nd": "Legal - non-deductible", "rates": "Rates", "rent": "Rent", "repairs": "Repairs & maintenance", "vehicles": "Vehicles",
    "non_deductible": "Non-deductible", "other_expenses": "Other expenses", "home_office": "Use of home as office",
    "accounting_fees": "Accounting fees", "current_account": "Current account # 1", "retained_earnings": "Retained earnings",
}
B1_WP = {"receivables": "G1", "gst_asset": "L1", "gst_liability": "L1", "tax_asset": "Q1", "tax_liability": "Q1", "payables": "M1", "fixed_assets": "H1",
         "interest_income": "T2", "dividend_income": "T2", "home_office": "V2", "accounting_fees": "V5", "current_account": "N1.1",
         "retained_earnings": "Q3b", **{k: "V1" for k in ("acc", "entertainment", "fbt", "insurance", "interest_overdraft", "interest_hp", "interest_loans",
                                                          "interest_other", "uomi", "lease", "legal", "rates", "rent", "repairs", "vehicles",
                                                          "non_deductible", "other_expenses")}}

# Account type from the account code (MYOB: 1 asset, 2 liability, 3 equity, 4 income, 5 cost of sales,
# 6 expense, 8 other income, 9 other expense) or the trial balance's own type column.
_CODE_TYPE = {"1": "asset", "2": "liability", "3": "equity", "4": "income", "5": "cost_of_sales", "6": "expense", "7": "expense", "8": "income",
              "9": "expense"}
_TYPE_WORDS = [("asset", r"asset|bank|receivable|inventory|prepay|fixed"), ("liability", r"liabilit|payable"), ("equity", r"equity|capital"),
               ("cost_of_sales", r"cost of sales|direct cost|purchases"), ("income", r"revenue|income|sales"), ("expense", r"expense|overhead")]


def account_type(code: str, name: str, type_text: str = "") -> str:
    if type_text:
        t = type_text.lower()
        for kind, pattern in _TYPE_WORDS:
            if re.search(pattern, t):
                return kind
    m = re.match(r"^\s*(\d)", code or "")
    if m and m.group(1) in _CODE_TYPE:
        return _CODE_TYPE[m.group(1)]
    return ""


_RULES = {
    "asset": [
        ("bank", r"\bbank\b|cheque|call account|on call|savings|current account|kiwibank|\banz\b|\basb\b|\bbnz\b|westpac|\btsb\b|term deposit|cash management"),
        ("receivables", r"receivable|debtors"), ("gst", r"\bgst\b"), ("tax", r"income tax|provisional tax|\brwt\b|withholding|taxation|tax refund"),
        ("prepayments", r"prepa"), ("stock", r"stock|inventory"), ("wip", r"\bwip\b|work in progress"), ("cash", r"cash on hand|petty cash|float"),
        ("fixed_assets", r"vehicle|equipment|plant|furniture|computer|fixed asset|depreciation|building|land|fit.?out|machinery|tools"),
        ("investments", r"investment|shares in|shareholding"), ("other_assets", r"loan to|advance to|deposit|bond"),
    ],
    "liability": [
        ("payables", r"payable|creditor"), ("gst", r"\bgst\b"), ("tax", r"income tax|provisional tax|\brwt\b|withholding|taxation"),
        ("hire_purchase", r"hire purchase|\bhp\b"), ("term_loan", r"loan|mortgage|finance"),
        ("current_account", r"owner|shareholder|drawing|director|current account|advance from"),
    ],
    "equity": [
        ("retained_earnings", r"retained|accumulated (profit|loss|earnings)"),
        ("current_account", r"owner|shareholder|drawing|director|current account|contribution|funds introduced|advance"),
    ],
    "income": [
        ("interest_income", r"interest"), ("dividend_income", r"dividend"), ("rental_income", r"\brent"), ("fbt_reimbursement", r"fbt"),
        ("sales", r"."),
    ],
    "cost_of_sales": [("purchases", r".")],
    "expense": [
        ("acc", r"\bacc\b|a\.c\.c"), ("entertainment", r"entertain"), ("fbt", r"\bfbt\b|fringe"), ("insurance", r"insurance"),
        ("uomi", r"use of money|uomi"), ("interest_hp", r"hire purchase interest|interest.*\bhp\b"),
        ("interest_overdraft", r"overdraft"), ("interest_loans", r"(loan|mortgage).*interest|interest.*(loan|mortgage)"),
        ("interest_other", r"interest"), ("lease", r"lease"), ("legal", r"legal"), ("rates", r"\brates\b"), ("rent", r"\brent\b"),
        ("repairs", r"repair|maintenance"), ("vehicles", r"motor vehicle|vehicle|fuel|\bcar\b|petrol"),
        ("non_deductible", r"non.?deduct|penalt|fines?\b|donation"), ("home_office", r"home office|use of home"),
        ("accounting_fees", r"accountan|accounting|audit"), ("wages", r"wage|salar|kiwisaver|paye"), ("contractors", r"contract"),
        ("professional_fees", r"consult|professional"), ("depreciation", r"depreciation"), ("other_expenses", r"."),
    ],
}
# Accounts no workpaper takes on its own: shown for review, never guessed.
REVIEW_ONLY = re.compile(r"suspense|clearing|historical balancing|allocate me|rounding|opening balance|unallocated", re.I)


def b1_group(code: str, name: str, type_text: str = "", balance=None) -> tuple[str, str]:
    """(B1 group key or "", account type). GST and tax accounts are netted and placed by their sign later."""
    kind = account_type(code, name, type_text)
    if REVIEW_ONLY.search(name or ""):
        return "", kind
    n = (name or "").lower()
    if kind == "equity" and re.search(r"income tax|taxation", n):
        return "", kind  # a tax appropriation in equity: for review, not Q1
    for group, pattern in _RULES.get(kind, []):
        if re.search(pattern, n):
            return group, kind
    return "", kind


# --- V1: the expense sections and their entry rows ------------------------------------------------------
V1_SECTIONS = {
    # group: (title, first row, last row, description col, amount col, gross (GST-inclusive) or excl GST)
    "acc": ("ACC", 21, 27, "C", "J", "gross"),
    "insurance": ("Insurance", 74, 84, "C", "J", "gross"),
    "interest_overdraft": ("Interest - bank overdraft", 95, 97, "C", "N", "net"),
    "interest_hp": ("Interest - hire purchase", 108, 110, "C", "N", "net"),
    "interest_loans": ("Interest - bank loan", 121, 125, "C", "N", "net"),
    "interest_other": ("Interest - other", 136, 138, "C", "N", "net"),
    "uomi": ("Use of money interest", 149, 151, "C", "N", "net"),
    "lease": ("Lease payments", 164, 167, "C", "N", "net"),
    "legal": ("Legal", 182, 183, "C", "N", "net"),  # rows 180-181 carry the template's own labels
    "rates": ("Rates", 194, 200, "C", "N", "net"),
    "rent": ("Rent", 211, 215, "C", "N", "net"),
    "repairs": ("Repairs & maintenance", 225, 233, "C", "N", "net"),
    "vehicles": ("Vehicles", 247, 252, "E", "N", "net"),
    "non_deductible": ("Non-deductible expenses", 265, 271, "C", "N", "net"),
    "other_expenses": ("Other expenses", 282, 288, "C", "N", "net"),
}
V1_ENTERTAINMENT = ("N39", "P39")  # total per GL (GST-inclusive), "GST Inc?"
V1_TICKS = {"acc": "E10", "entertainment": "E11", "fbt": "E12", "insurance": "E13", "interest": "E14", "lease": "E15", "legal": "E16",
            "rates": "L10", "rent": "L11", "repairs": "L12", "vehicles": "L13", "non_deductible": "L14", "other_expenses": "L15"}

# --- other cell plans -----------------------------------------------------------------------------------
F11_PAYMENTS = (23, 38)  # B date, C ref, D description, I gross
F11_RECEIPTS = (45, 54)
M1_NO_GST = (13, 19)  # B description, F ref, I gross (row 12: posted into the client's ledger)
M1_GST = (27, 51)  # row 26: posted into the client's ledger
T2_INTEREST = (17, 56)  # B date, C payer, G gross, H RWT
T2_DIVIDENDS = (67, 77)  # B date, C company, G gross, H RWT, I imputation credits
Q1_OTHER_PAYMENTS = (33, 35)  # B date, C description, I amount
Q1_PRIOR_ARREARS = (53, 55)  # B description, I amount
Q1_REFUNDS = (62, 65)  # B description, I amount
Q3A_TERMINAL = (24, 26)  # C date, H amount
Q3A_REFUNDS = (44, 46)  # C date, H amount
Q3A_DIVIDENDS = (50, 51)  # C date, D description, H amount
Q3A_OTHER_DEBITS = (54, 55)  # C date, D description, H amount
D1_ROWS = (14, 28)  # B date, C account, H code, J debit, K credit, L narration
SUPPORTING_DOCS_COLS = ["B", "C", "D", "E", "F", "G"]
