"""PDF verification report (ReportLab). Wording is deliberately qualified."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .engine import fmt_amount

INK = colors.HexColor("#12282B")
TEAL = colors.HexColor("#0B6E6A")
MUTED = colors.HexColor("#5B6F72")
RULE = colors.HexColor("#D6DFDD")
VERDICTS = {
    "CLEAR": ("No duplicates found", colors.HexColor("#1F7A52")),
    "POTENTIAL_DUPLICATES": ("Potential duplicates to review", colors.HexColor("#B9791A")),
    "DUPLICATES_FOUND": ("Duplicates found", colors.HexColor("#B83A3A")),
}
KIND_LABELS = {
    "EXACT_DUPLICATE": "Exact duplicate",
    "ID_COLLISION": "ID collision",
    "ECONOMIC_DUPLICATE": "Economic duplicate",
    "DATA_QUALITY": "Data quality",
}


def _p(text, style):
    return Paragraph(escape(str(text)), style)


def build_pdf(*, engagement, bank_name, client_email, upload, summary, findings, chain_head, generated_at) -> bytes:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, textColor=MUTED)
    cell = ParagraphStyle("cell", parent=body, fontSize=8.5, leading=11)
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK)
    h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=TEAL, spaceBefore=14, spaceAfter=4)

    label, color = VERDICTS.get(summary["verdict"], (summary["verdict"], INK))
    verdict_style = ParagraphStyle("verdict", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=color)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title="Receivables verification report")
    s = []
    s.append(_p("Receivables verification report", h1))
    s.append(Spacer(1, 4))
    s.append(_p("Automated checks on the receivables data submitted by the client", small))
    s.append(Spacer(1, 10))

    meta = [
        ["Engagement", engagement.name],
        ["Prepared for", bank_name],
        ["Client", client_email],
        ["File", upload.filename],
        ["File SHA-256", upload.file_sha256],
        ["Verification run", f"#{upload.id}, {upload.created_at:%Y-%m-%d %H:%M} UTC"],
        ["Report generated", f"{generated_at:%Y-%m-%d %H:%M} UTC"],
    ]
    t = Table([[_p(k, small), _p(v, cell)] for k, v in meta], colWidths=[38 * mm, 132 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    s.append(t)

    s.append(Spacer(1, 12))
    s.append(_p(label, verdict_style))

    c = summary["counts"]
    amounts = ", ".join(f"{fmt_amount(v)} {k}" for k, v in summary["amount_by_currency_cents"].items()) or "n/a"
    over = ", ".join(f"{fmt_amount(v)} {k}" for k, v in summary["potential_overstatement_cents"].items()) or "none"
    rows = [
        ["Rows analysed", f"{summary['total_rows']:,}"],
        ["Total amount submitted", amounts],
        ["Exact duplicates", c["EXACT_DUPLICATE"]],
        ["Invoice ID collisions", c["ID_COLLISION"]],
        ["Possible economic duplicates", c["ECONOMIC_DUPLICATE"]],
        ["Data quality issues (types)", c["DATA_QUALITY"]],
        ["Amount that could be counted twice", over],
    ]
    s.append(Spacer(1, 6))
    t = Table([[_p(k, cell), _p(v, cell)] for k, v in rows], colWidths=[70 * mm, 100 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    s.append(t)

    s.append(_p("Findings", h2))
    if not findings:
        s.append(_p("No findings.", body))
    else:
        shown = findings[:60]
        data = [[_p("Type", small), _p("Severity", small), _p("Status", small), _p("Detail", small), _p("Rows", small)]]
        for f in shown:
            rows_txt = ", ".join(str(n) for n in f["rows"][:6]) + (" ..." if len(f["rows"]) > 6 else "")
            data.append([_p(KIND_LABELS.get(f["kind"], f["kind"]), cell), _p(f["severity"].title(), cell),
                         _p(f["status"].replace("_", " ").title(), cell), _p(f["title"], cell), _p(rows_txt, cell)])
        t = Table(data, colWidths=[28 * mm, 18 * mm, 24 * mm, 76 * mm, 24 * mm], repeatRows=1)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        s.append(t)
        if len(findings) > len(shown):
            s.append(Spacer(1, 4))
            s.append(_p(f"{len(findings) - len(shown)} further findings are available in the application.", small))

    s.append(_p("Basis and limitations", h2))
    s.append(_p(
        "This report is produced by deterministic automated checks on the file supplied by the client. It identifies "
        "indications of duplicated or inconsistent receivables within that file. It does not verify the existence, "
        "validity, ownership or enforceability of any receivable, it cannot detect receivables that were left out of the "
        "file, and it does not check for financing or pledges recorded with other institutions. Economic duplicates are "
        "indications only and require review. Results should be read together with the lender's own due diligence.", body))
    s.append(Spacer(1, 6))
    s.append(_p("The client confirmed on submission that the file contains all of its receivables, including those already "
                "financed or pledged." if upload.declaration_accepted else "No client declaration was recorded.", body))
    s.append(Spacer(1, 8))
    s.append(_p(f"Audit trail reference (hash of the latest entry when this report was generated): {chain_head}", small))

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 10 * mm, "Receivables Registry - verification report")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
