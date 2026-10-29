import json
from datetime import date
from pathlib import Path

import pytest

from app import engine as e
from scripts.make_synthetic import generate


@pytest.mark.parametrize("text,cents", [
    ("1.234,56", 123456), ("1,234.56", 123456), ("1234.5", 123450), ("1 234,50", 123450),
    ("€ 250.000", 25000000), ("250,000", 25000000), ("12,5", 1250), ("(100.00)", -10000), ("-1.234,50", -123450),
    ("0.125", 13), ("1,234,567.89", 123456789), ("abc", None), ("", None), ("--5", None),
])
def test_parse_amount(text, cents):
    assert e.parse_amount(text) == cents


@pytest.mark.parametrize("text,expected", [
    ("2025-12-31", date(2025, 12, 31)), ("31/12/2025", date(2025, 12, 31)), ("31-12-2025", date(2025, 12, 31)),
    ("31.12.2025", date(2025, 12, 31)), ("2025-12-31 00:00:00", date(2025, 12, 31)), ("31/02/2025", None),
    ("not a date", None), ("", None),
])
def test_parse_date(text, expected):
    assert e.parse_date(text) == expected


def test_normalisation():
    assert e.normalise_invoice_id(" inv-2025/000012 ") == "INV2025000012"
    assert e.normalise_debtor("ACME, S.A.") == e.normalise_debtor("Acme Lda") == "acme"
    assert e.normalise_debtor("Café Ibérico & Filhos, Lda.") == "cafe iberico and filhos"
    assert e.normalise_debtor("Lda") == "lda"  # never reduce to an empty name


def test_suggest_mapping_portuguese_headers():
    m = e.suggest_mapping(["Nº Fatura", "Cliente", "Valor", "Moeda", "Data Emissão", "Data Vencimento"])
    assert m == {"invoice_id": "Nº Fatura", "debtor": "Cliente", "amount": "Valor", "currency": "Moeda",
                 "issue_date": "Data Emissão", "due_date": "Data Vencimento"}


def test_validate_mapping():
    assert e.validate_mapping({"invoice_id": "A", "debtor": "B", "amount": "C"}, ["A", "B", "C"]) == []
    assert e.validate_mapping({"invoice_id": "A", "debtor": "A", "amount": "C"}, ["A", "C"])
    assert e.validate_mapping({"invoice_id": "A", "debtor": "B"}, ["A", "B"])


def _run(csv_text, name="x.csv"):
    headers, table = e.read_table(name, csv_text.encode())
    mp = e.suggest_mapping(headers)
    rows = e.build_rows(table, mp, today=date(2026, 1, 1))
    return e.analyse(rows, mp)


def test_clean_file_is_clear():
    findings, summary = _run("Invoice,Customer,Amount,Currency,Date,Due\n"
                             "A1,Acme,100.00,EUR,2025-01-01,2025-02-01\nA2,Beta,200.00,EUR,2025-01-02,2025-02-02\n")
    assert summary["verdict"] == e.VERDICT_CLEAR and findings == []


def test_exact_duplicate_ignores_cosmetic_differences():
    findings, summary = _run("Invoice,Customer,Amount,Currency,Date,Due\n"
                             "INV-1,Acme Lda,100.00,EUR,2025-01-01,2025-02-01\n"
                             " inv 1 ,ACME,100,EUR,01/01/2025,01/02/2025\n")
    assert summary["verdict"] == e.VERDICT_FOUND
    assert [f["kind"] for f in findings] == [e.KIND_EXACT] and findings[0]["rows"] == [1, 2]


def test_id_collision():
    findings, summary = _run("Invoice,Customer,Amount,Currency,Date,Due\n"
                             "INV-1,Acme,100.00,EUR,2025-01-01,2025-02-01\nINV-1,Beta,999.00,EUR,2025-03-01,2025-04-01\n")
    assert [f["kind"] for f in findings] == [e.KIND_COLLISION] and summary["verdict"] == e.VERDICT_FOUND


def test_economic_duplicate_and_window():
    findings, summary = _run("Invoice,Customer,Amount,Currency,Date,Due\n"
                             "INV-1,Acme,100.00,EUR,2025-01-01,2025-02-01\nINV-2,ACME LDA,100.00,EUR,2025-01-03,2025-02-03\n"
                             "INV-3,Beta,50.00,EUR,2025-01-01,2025-02-01\nINV-4,Beta,50.00,EUR,2025-06-01,2025-07-01\n")
    assert [f["rows"] for f in findings if f["kind"] == e.KIND_ECONOMIC] == [[1, 2]]  # Beta is months apart: no flag
    assert summary["verdict"] == e.VERDICT_POTENTIAL


def test_data_quality_aggregates_per_issue_type():
    findings, _ = _run("Invoice,Customer,Amount,Currency,Date,Due\n"
                       "A1,Acme,N/A,EUR,2025-01-01,2025-02-01\nA2,,10,EUR,2025-01-01,2025-02-01\n"
                       "A3,Beta,-5,,2025-03-01,2025-02-01\nA4,Gama,5,EUR,2027-01-01,2027-02-01\n")
    codes = {f["code"]: f["rows"] for f in findings}
    assert codes == {"invalid_amount": [1], "missing_debtor": [2], "non_positive_amount": [3],
                     "missing_currency": [3], "due_before_issue": [3], "future_issue_date": [4]}


def test_semicolon_csv_and_xlsx(tmp_path):
    headers, table = e.read_table("a.csv", "Invoice;Customer;Amount\nA1;Acme;1.234,56\n".encode())
    assert headers == ["Invoice", "Customer", "Amount"] and table[0][1]["Amount"] == "1.234,56"
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Invoice No", "Customer", "Amount", "Invoice Date"])
    ws.append(["A1", "Acme", 1234.5, date(2025, 1, 31)])
    p = tmp_path / "a.xlsx"
    wb.save(p)
    headers, table = e.read_table("a.xlsx", p.read_bytes())
    assert table[0][1] == {"Invoice No": "A1", "Customer": "Acme", "Amount": "1234.5", "Invoice Date": "2025-01-31"}


@pytest.mark.parametrize("eu", [False, True])
def test_synthetic_portfolio_success_test(eu):
    """The MVP success test: planted anomalies are found exactly, nothing else is flagged."""
    text, exp = generate(10000, seed=7, eu=eu)
    headers, table = e.read_table("p.csv", text.encode())
    mp = e.suggest_mapping(headers)
    findings, summary = e.analyse(e.build_rows(table, mp), mp)
    c = summary["counts"]
    assert summary["total_rows"] == 10000
    assert (c["EXACT_DUPLICATE"], c["ID_COLLISION"], c["ECONOMIC_DUPLICATE"]) == (2, 3, 5)
    dq = {f["code"]: len(f["rows"]) for f in findings if f["kind"] == e.KIND_DQ}
    assert dq == exp["data_quality_rows"]
    planted = exp["planted_rows"]
    for kind, tag, n in [(e.KIND_EXACT, "exact", 2), (e.KIND_COLLISION, "collision", 3), (e.KIND_ECONOMIC, "economic", 5)]:
        got = sorted(tuple(f["rows"]) for f in findings if f["kind"] == kind)
        assert got == sorted(tuple(sorted(planted[f"{tag}_{k}"])) for k in range(n))
