"""Generate a synthetic receivables ledger with known, planted anomalies (the MVP success test).

Planted in every file:
  2 exact duplicates, 3 invoice ID collisions, 5 economic duplicates, plus data quality problems
  (4 invalid amounts, 6 negative amounts, 5 due-before-issue, 8 missing currency, 3 missing debtor, 2 bad issue dates).

Usage (from backend/):
  python -m scripts.make_synthetic --rows 10000 --out sample_data/sample_10k.csv
  python -m scripts.make_synthetic --rows 300 --eu --out sample_data/sample_small_eu.csv
"""
import argparse
import csv
import io
import json
import random
from datetime import date, timedelta
from pathlib import Path

FIRST = ["Alfa", "Beta", "Gama", "Delta", "Lusitana", "Atlantica", "Iberica", "Nordic", "Rhein", "Seine", "Tejo",
         "Douro", "Minho", "Orion", "Vega", "Sirius", "Aurora", "Meridian", "Solaris", "Cobalt"]
SECOND = ["Logistica", "Tecnologias", "Construcoes", "Texteis", "Alimentar", "Energia", "Metalurgica", "Farmaceutica",
          "Transportes", "Comercio", "Freight", "Foods", "Systems", "Retail", "Materials"]
SUFFIX = ["Lda", "SA", "GmbH", "Ltd", "SL", "BV"]
SUFFIX_VARIANTS = {"Lda": "LDA.", "SA": "S.A.", "GmbH": "GMBH", "Ltd": "Ltd.", "SL": "S.L.", "BV": "B.V."}

DQ_PLAN = {"invalid_amount": 4, "non_positive_amount": 6, "due_before_issue": 5, "missing_currency": 8,
           "missing_debtor": 3, "invalid_issue_date": 2}
HEADERS = ["Invoice No", "Customer", "Amount", "Currency", "Invoice Date", "Due Date"]


def _fmt_amount(cents: int, eu: bool) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    whole, frac = divmod(cents, 100)
    if eu:
        return f"{sign}{whole:,}".replace(",", ".") + f",{frac:02d}"
    return f"{sign}{whole}.{frac:02d}"


def _fmt_date(d: date, eu: bool) -> str:
    return d.strftime("%d/%m/%Y") if eu else d.isoformat()


def generate(n_rows: int = 10000, seed: int = 42, eu: bool = False):
    rng = random.Random(seed)
    debtors = set()
    while len(debtors) < min(600, n_rows):
        debtors.add((rng.choice(FIRST), rng.choice(SECOND), rng.choice(SUFFIX)))
    debtors = sorted(debtors)

    n_base = n_rows - 10  # 2 exact + 3 collision + 5 economic rows are added on top
    used_amounts = set()

    def new_amount():
        while True:
            a = rng.randint(50_000, 50_000_000)
            if a not in used_amounts:
                used_amounts.add(a)
                return a

    base = []
    for i in range(1, n_base + 1):
        f, s, suf = rng.choice(debtors)
        issue = date(2025, 1, 6) + timedelta(days=rng.randint(0, 300))
        base.append({
            "id": f"INV-2025-{i:06d}", "debtor": f"{f} {s} {suf}", "suffix": suf, "cents": new_amount(), "ccy": "EUR",
            "issue": issue, "due": issue + timedelta(days=rng.choice([30, 45, 60, 90])), "tag": None,
        })

    picks = rng.sample(range(n_base), 10 + sum(DQ_PLAN.values()))
    it = iter(picks)
    extras = []

    for k in range(2):  # exact duplicates: same row, cosmetic differences only
        src = base[next(it)]
        src["tag"] = f"exact_{k}"
        extras.append({**src, "id": f" {src['id'].lower()} ", "debtor": src["debtor"].upper()})

    for k in range(3):  # ID collisions: same invoice number, different content
        src = base[next(it)]
        src["tag"] = f"collision_{k}"
        extras.append({**src, "id": src["id"].replace("-", " ").lower(), "cents": new_amount(),
                       "issue": src["issue"] + timedelta(days=40), "due": src["due"] + timedelta(days=40),
                       "tag": f"collision_{k}"})

    for k in range(5):  # economic duplicates: new invoice number, same debtor/amount, issued 0-2 days apart
        src = base[next(it)]
        src["tag"] = f"economic_{k}"
        delta = timedelta(days=rng.randint(0, 2))
        name = src["debtor"].rsplit(" ", 1)[0] + " " + SUFFIX_VARIANTS[src["suffix"]]
        extras.append({**src, "id": f"INV-2025-{n_base + 1 + k:06d}", "debtor": name.upper(),
                       "issue": src["issue"] + delta, "due": src["due"] + delta, "tag": f"economic_{k}"})

    for code, count in DQ_PLAN.items():  # data quality problems on otherwise clean rows
        for _ in range(count):
            r = base[next(it)]
            r["tag"] = f"dq_{code}"
            if code == "invalid_amount":
                r["cents_text"] = "N/A"
            elif code == "non_positive_amount":
                r["cents"] = -r["cents"]
            elif code == "due_before_issue":
                r["due"] = r["issue"] - timedelta(days=5)
            elif code == "missing_currency":
                r["ccy"] = ""
            elif code == "missing_debtor":
                r["debtor"] = ""
            elif code == "invalid_issue_date":
                r["issue_text"] = "not a date"

    rows = base + extras
    rng.shuffle(rows)

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";" if eu else ",", lineterminator="\n")
    w.writerow(HEADERS)
    tags: dict[str, list[int]] = {}
    for n, r in enumerate(rows, start=1):
        if r["tag"]:
            tags.setdefault(r["tag"], []).append(n)
        w.writerow([
            r["id"], r["debtor"], r.get("cents_text") or _fmt_amount(r["cents"], eu), r["ccy"],
            r.get("issue_text") or _fmt_date(r["issue"], eu), _fmt_date(r["due"], eu),
        ])
    expected = {
        "rows": len(rows), "exact_duplicates": 2, "id_collisions": 3, "economic_duplicates": 5,
        "data_quality_rows": dict(DQ_PLAN), "planted_rows": tags,
    }
    return buf.getvalue(), expected


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eu", action="store_true", help="semicolon delimiter, 1.234,56 amounts, dd/mm/yyyy dates")
    ap.add_argument("--out", default="sample_data/sample_10k.csv")
    a = ap.parse_args()
    text, expected = generate(a.rows, a.seed, a.eu)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    out.with_suffix(".expected.json").write_text(json.dumps(expected, indent=2))
    print(f"Wrote {out} ({expected['rows']} rows) and {out.with_suffix('.expected.json').name}")
