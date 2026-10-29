"""Deterministic verification engine (rules only, no ML).

Pure functions with no database or web dependencies, so it is easy to test and to expose as an API later.

Pipeline:  read_table -> suggest_mapping -> build_rows (parse + normalise + hash) -> analyse (findings + summary)

Conventions
- "Row N" is the N-th data row of the file (the header is not counted). In Excel/CSV viewers that is line N+1.
- Dates are read day-first (31/12/2025) unless they are ISO (2025-12-31).
- Amounts accept 1,234.56 / 1.234,56 / 1234.56 / (100.00) and currency symbols.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CANONICAL_FIELDS = ["invoice_id", "debtor", "amount", "currency", "issue_date", "due_date"]
REQUIRED_FIELDS = ["invoice_id", "debtor", "amount"]
FIELD_LABELS = {
    "invoice_id": "Invoice ID",
    "debtor": "Debtor (customer)",
    "amount": "Amount",
    "currency": "Currency",
    "issue_date": "Issue date",
    "due_date": "Due date",
}

# Two invoices with the same debtor, amount and currency but different IDs are flagged as a
# possible economic duplicate when their issue dates (or, if missing, due dates) are this close.
ECONOMIC_WINDOW_DAYS = 3

KIND_EXACT = "EXACT_DUPLICATE"
KIND_COLLISION = "ID_COLLISION"
KIND_ECONOMIC = "ECONOMIC_DUPLICATE"
KIND_DQ = "DATA_QUALITY"

VERDICT_CLEAR = "CLEAR"
VERDICT_POTENTIAL = "POTENTIAL_DUPLICATES"
VERDICT_FOUND = "DUPLICATES_FOUND"

DQ_CATALOG = {
    "missing_invoice_id": ("HIGH", "Missing invoice ID"),
    "missing_debtor": ("HIGH", "Missing debtor"),
    "missing_amount": ("HIGH", "Missing amount"),
    "invalid_amount": ("HIGH", "Amount could not be read as a number"),
    "non_positive_amount": ("MEDIUM", "Zero or negative amount"),
    "invalid_issue_date": ("MEDIUM", "Issue date could not be read"),
    "invalid_due_date": ("MEDIUM", "Due date could not be read"),
    "due_before_issue": ("MEDIUM", "Due date is before the issue date"),
    "future_issue_date": ("LOW", "Issue date is in the future"),
    "missing_currency": ("LOW", "Missing currency"),
    "missing_issue_date": ("LOW", "Missing issue date"),
    "missing_due_date": ("LOW", "Missing due date"),
}

SYNONYMS = {
    "invoice_id": ["invoice id", "invoice no", "invoice number", "invoice", "inv no", "inv number", "document number",
                   "doc number", "doc no", "fatura", "n fatura", "no fatura", "n o fatura", "num fatura", "numero fatura",
                   "numero da fatura", "id"],
    "debtor": ["debtor", "debtor name", "customer", "customer name", "client", "client name", "obligor",
               "counterparty", "buyer", "devedor", "cliente", "nome cliente"],
    "amount": ["amount", "invoice amount", "gross amount", "face value", "value", "total", "outstanding",
               "montante", "valor", "valor total"],
    "currency": ["currency", "ccy", "curr", "moeda"],
    "issue_date": ["issue date", "invoice date", "date", "issued", "data emissao", "data de emissao", "data fatura",
                   "emissao"],
    "due_date": ["due date", "maturity", "maturity date", "payment due", "due", "data vencimento",
                 "data de vencimento", "vencimento"],
}

LEGAL_SUFFIXES = {"lda", "limitada", "sa", "sl", "slu", "sas", "sarl", "gmbh", "ag", "bv", "nv", "ltd", "limited",
                  "llc", "inc", "corp", "co", "plc", "spa", "srl", "unipessoal", "sgps"}
CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}


# --------------------------------------------------------------------------- reading files

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _key(s: str) -> str:
    s = _strip_accents(str(s)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _dedupe_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, h in enumerate(headers):
        h = (h or "").strip() or f"column_{i + 1}"
        seen[h] = seen.get(h, 0) + 1
        out.append(h if seen[h] == 1 else f"{h}_{seen[h]}")
    return out


def _cell_to_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat() if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else format(Decimal(repr(v)), "f")
    return str(v).strip()


def _read_csv(content: bytes):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = max([",", ";", "\t", "|"], key=lambda d: first_line.count(d))
    if first_line.count(delim) == 0:
        delim = ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    headers = None
    rows = []
    n = 0
    for rec in reader:
        if headers is None:
            if not any(c.strip() for c in rec):
                continue
            headers = _dedupe_headers([c.strip() for c in rec])
            continue
        n += 1
        if not any(c.strip() for c in rec):
            continue
        rec = (rec + [""] * len(headers))[: len(headers)]
        rows.append((n, {h: c.strip() for h, c in zip(headers, rec)}))
    return headers or [], rows


def _read_xlsx(content: bytes):
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    headers = None
    rows = []
    n = 0
    for rec in ws.iter_rows(values_only=True):
        cells = [_cell_to_str(c) for c in rec]
        if headers is None:
            if not any(cells):
                continue
            headers = _dedupe_headers(cells)
            continue
        n += 1
        if not any(cells):
            continue
        cells = (cells + [""] * len(headers))[: len(headers)]
        rows.append((n, dict(zip(headers, cells))))
    wb.close()
    return headers or [], rows


def read_table(filename: str, content: bytes):
    """Return (headers, [(row_number, {header: text})]). Supports .csv and .xlsx."""
    name = (filename or "").lower()
    if name.endswith((".csv", ".txt")):
        return _read_csv(content)
    if name.endswith((".xlsx", ".xlsm")):
        try:
            return _read_xlsx(content)
        except Exception as ex:  # corrupt or password-protected workbook
            raise ValueError(f"Could not read the Excel file: {ex}")
    raise ValueError("Unsupported file type. Upload a .csv or .xlsx file.")


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    """Guess which file column holds each canonical field, from the header names."""
    keyed = {h: _key(h) for h in headers}
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for f in CANONICAL_FIELDS:
        found = None
        for syn in SYNONYMS[f]:
            for h, k in keyed.items():
                if h not in used and k == syn:
                    found = h
                    break
            if found:
                break
        if found:
            used.add(found)
        mapping[f] = found
    return mapping


def validate_mapping(mapping: dict, headers: list[str]) -> list[str]:
    errors = []
    for f in REQUIRED_FIELDS:
        if not mapping.get(f):
            errors.append(f"Map a column to '{FIELD_LABELS[f]}'.")
    for f, h in mapping.items():
        if f not in CANONICAL_FIELDS:
            errors.append(f"Unknown field '{f}'.")
        elif h and h not in headers:
            errors.append(f"Column '{h}' is not in the file.")
    chosen = [h for h in mapping.values() if h]
    if len(chosen) != len(set(chosen)):
        errors.append("The same column is mapped to more than one field.")
    return errors


# --------------------------------------------------------------------------- parsing / normalising

def parse_amount(s) -> int | None:
    """Text -> integer cents (None if unreadable)."""
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = re.sub(r"[^\d,.\-+]", "", t)
    if t.startswith("-"):
        neg, t = True, t[1:]
    elif t.startswith("+"):
        t = t[1:]
    if not t or "-" in t or "+" in t or not re.search(r"\d", t):
        return None
    has_dot, has_comma = "." in t, "," in t
    if has_dot and has_comma:
        dec = "." if t.rfind(".") > t.rfind(",") else ","
        thou = "," if dec == "." else "."
        t = t.replace(thou, "").replace(dec, ".")
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        parts = t.split(sep)
        if len(parts) > 2:  # 1,234,567  -> thousands separators
            t = "".join(parts)
        else:
            left, right = parts
            if len(right) == 3 and left not in ("", "0"):  # 1,234 / 250.000 -> thousands
                t = left + right
            else:  # 12,5 / 1234.56 -> decimal
                t = left + "." + right
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    cents = int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return -cents if neg else cents


_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y", "%d-%m-%y", "%Y%m%d",
                 "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"]


def parse_date(s) -> date | None:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T]", t)
    if m:
        t = m.group(1)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def normalise_invoice_id(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _strip_accents(s or "").upper())


def normalise_debtor(s: str) -> str:
    t = _strip_accents(s or "").casefold().replace("&", " and ").replace(".", "")
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    tokens = t.split()
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalise_currency(s: str) -> str | None:
    t = (s or "").strip()
    if not t:
        return None
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in t:
            return code
    return t.upper()[:8]


def fingerprint(invoice_id_norm: str, debtor_norm: str, amount_cents: int, currency: str | None,
                issue: date | None, due: date | None) -> str:
    """Deterministic internal ID: SHA-256 over the normalised business fields."""
    parts = [invoice_id_norm, debtor_norm, str(amount_cents), currency or "",
             issue.isoformat() if issue else "", due.isoformat() if due else ""]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass
class Row:
    row_number: int
    raw: dict
    invoice_id_norm: str
    debtor_norm: str
    amount_cents: int | None
    currency: str | None
    issue_date: date | None
    due_date: date | None
    row_hash: str | None
    issues: list[str] = field(default_factory=list)


def build_rows(table_rows, mapping: dict, today: date | None = None) -> list[Row]:
    today = today or date.today()
    out: list[Row] = []
    for n, rec in table_rows:
        raw = {f: (rec.get(mapping[f], "") if mapping.get(f) else "").strip() for f in CANONICAL_FIELDS}
        inv = normalise_invoice_id(raw["invoice_id"])
        deb = normalise_debtor(raw["debtor"])
        amt = parse_amount(raw["amount"])
        ccy = normalise_currency(raw["currency"])
        issue = parse_date(raw["issue_date"])
        due = parse_date(raw["due_date"])

        issues = []
        if not inv:
            issues.append("missing_invoice_id")
        if not deb:
            issues.append("missing_debtor")
        if not raw["amount"]:
            issues.append("missing_amount")
        elif amt is None:
            issues.append("invalid_amount")
        elif amt <= 0:
            issues.append("non_positive_amount")
        if mapping.get("currency") and not ccy:
            issues.append("missing_currency")
        if mapping.get("issue_date"):
            if not raw["issue_date"]:
                issues.append("missing_issue_date")
            elif issue is None:
                issues.append("invalid_issue_date")
            elif issue > today:
                issues.append("future_issue_date")
        if mapping.get("due_date"):
            if not raw["due_date"]:
                issues.append("missing_due_date")
            elif due is None:
                issues.append("invalid_due_date")
        if issue and due and due < issue:
            issues.append("due_before_issue")

        h = fingerprint(inv, deb, amt, ccy, issue, due) if (inv and deb and amt is not None) else None
        out.append(Row(n, raw, inv, deb, amt, ccy, issue, due, h, issues))
    return out


# --------------------------------------------------------------------------- checks

def fmt_amount(cents: int | None, ccy: str | None = None) -> str:
    if cents is None:
        return "n/a"
    s = f"{Decimal(cents) / 100:,.2f}"
    return f"{s} {ccy}" if ccy else s


def _rows_text(nums: list[int], limit: int = 8) -> str:
    shown = ", ".join(str(n) for n in nums[:limit])
    return shown + (f" and {len(nums) - limit} more" if len(nums) > limit else "")


def _exact_duplicates(rows: list[Row]) -> list[dict]:
    groups: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.row_hash:
            groups[r.row_hash].append(r)
    out = []
    for g in groups.values():
        if len(g) < 2:
            continue
        nums = sorted(r.row_number for r in g)
        r0 = g[0]
        out.append({
            "kind": KIND_EXACT, "code": "exact_duplicate", "severity": "HIGH",
            "title": f'Exact duplicate: invoice "{r0.raw["invoice_id"]}" appears {len(g)} times',
            "description": (f"Rows {_rows_text(nums)} have the same invoice ID, debtor, amount, currency and dates "
                            f"({fmt_amount(r0.amount_cents, r0.currency)}, {r0.raw['debtor']})."),
            "rows": nums,
        })
    return out


def _id_collisions(rows: list[Row]) -> list[dict]:
    groups: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.row_hash:
            groups[r.invoice_id_norm].append(r)
    out = []
    for g in groups.values():
        distinct = {r.row_hash for r in g}
        if len(distinct) < 2:
            continue
        g = sorted(g, key=lambda r: r.row_number)
        nums = [r.row_number for r in g]
        bits = "; ".join(f"row {r.row_number}: {r.raw['debtor']}, {fmt_amount(r.amount_cents, r.currency)}" for r in g[:4])
        out.append({
            "kind": KIND_COLLISION, "code": "id_collision", "severity": "HIGH",
            "title": f'Invoice ID collision: "{g[0].raw["invoice_id"]}" is used by {len(distinct)} different invoices',
            "description": f"The same invoice ID carries different data. {bits}.",
            "rows": nums,
        })
    return out


def _close(a: Row, b: Row) -> bool:
    w = timedelta(days=ECONOMIC_WINDOW_DAYS)
    if a.issue_date and b.issue_date:
        return abs(a.issue_date - b.issue_date) <= w
    if a.due_date and b.due_date:
        return abs(a.due_date - b.due_date) <= w
    return False


def _economic_duplicates(rows: list[Row]) -> list[dict]:
    groups: dict[tuple, list[Row]] = defaultdict(list)
    for r in rows:
        if r.row_hash:
            groups[(r.debtor_norm, r.amount_cents, r.currency or "")].append(r)
    out = []
    for g in groups.values():
        if len(g) < 2:
            continue
        g = sorted(g, key=lambda r: r.row_number)
        parent = list(range(len(g)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                if g[i].invoice_id_norm != g[j].invoice_id_norm and _close(g[i], g[j]):
                    parent[find(i)] = find(j)
        clusters: dict[int, list[Row]] = defaultdict(list)
        for i, r in enumerate(g):
            clusters[find(i)].append(r)
        for c in clusters.values():
            ids = sorted({r.invoice_id_norm for r in c})
            if len(ids) < 2:
                continue
            nums = [r.row_number for r in c]
            shown_ids = ", ".join(sorted({r.raw["invoice_id"] for r in c})[:5])
            r0 = c[0]
            out.append({
                "kind": KIND_ECONOMIC, "code": "economic_duplicate", "severity": "MEDIUM",
                "title": f"Possible economic duplicate: {fmt_amount(r0.amount_cents, r0.currency)} owed by {r0.raw['debtor']}",
                "description": (f"Different invoice IDs ({shown_ids}) with the same debtor, amount and currency, "
                                f"issued within {ECONOMIC_WINDOW_DAYS} days of each other. Rows {_rows_text(nums)}."),
                "rows": nums,
            })
    return out


def _data_quality(rows: list[Row], mapping: dict) -> list[dict]:
    by_code: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        for code in r.issues:
            by_code[code].append(r.row_number)
    out = []
    for code, nums in by_code.items():
        sev, title = DQ_CATALOG[code]
        out.append({
            "kind": KIND_DQ, "code": code, "severity": sev,
            "title": f"{title} ({len(nums)} row{'s' if len(nums) != 1 else ''})",
            "description": f"Rows {_rows_text(nums)}.",
            "rows": nums,
        })
    if not mapping.get("currency"):
        out.append({"kind": KIND_DQ, "code": "currency_not_mapped", "severity": "LOW",
                    "title": "No currency column mapped",
                    "description": "Amounts are compared without a currency. Map a currency column if the file has one.",
                    "rows": []})
    return out


_SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_KIND_ORDER = {KIND_EXACT: 0, KIND_COLLISION: 1, KIND_ECONOMIC: 2, KIND_DQ: 3}


def analyse(rows: list[Row], mapping: dict) -> tuple[list[dict], dict]:
    findings = (_exact_duplicates(rows) + _id_collisions(rows) + _economic_duplicates(rows)
                + _data_quality(rows, mapping))
    findings.sort(key=lambda f: (_SEV_ORDER[f["severity"]], _KIND_ORDER[f["kind"]], f["rows"][:1] or [0]))

    counts = {k: 0 for k in (KIND_EXACT, KIND_COLLISION, KIND_ECONOMIC, KIND_DQ)}
    for f in findings:
        counts[f["kind"]] += 1

    by_row = {r.row_number: r for r in rows}
    totals: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.amount_cents is not None and r.amount_cents > 0:
            totals[r.currency or "no currency"] += r.amount_cents
    # Amount that would be counted twice: every row of a duplicate group except the first.
    overstated: dict[str, int] = defaultdict(int)
    for f in findings:
        if f["kind"] in (KIND_EXACT, KIND_ECONOMIC):
            for n in f["rows"][1:]:
                r = by_row[n]
                if r.amount_cents:
                    overstated[r.currency or "no currency"] += r.amount_cents
    flagged = {n for f in findings for n in f["rows"]}
    dq_rows = {n for f in findings if f["kind"] == KIND_DQ for n in f["rows"]}

    if counts[KIND_EXACT] or counts[KIND_COLLISION]:
        verdict = VERDICT_FOUND
    elif counts[KIND_ECONOMIC]:
        verdict = VERDICT_POTENTIAL
    else:
        verdict = VERDICT_CLEAR

    summary = {
        "total_rows": len(rows),
        "rows_flagged": len(flagged),
        "data_quality_rows": len(dq_rows),
        "counts": counts,
        "amount_by_currency_cents": dict(totals),
        "potential_overstatement_cents": dict(overstated),
        "verdict": verdict,
    }
    return findings, summary
