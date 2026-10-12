"""
Documents out of a payroll run: the register and summary CSVs for
accounting, and the PDF payslip.

Payslips are built from the entry's frozen snapshot, never from current
data, so a closed month's payslip is the same document every time it is
downloaded — a later salary revision or a corrected bank account does not
rewrite history. reportlab's `invariant` mode keeps the bytes stable too.

Amounts say "Rs." rather than the rupee sign: the PDF base fonts have no
glyph for it, and it would print as an empty box.
"""

from __future__ import annotations

import csv
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.payroll_calc import rupees_in_words

# ─── CSV ─────────────────────────────────────────────────────────────────────


def _cell(value):
    """Neutralise spreadsheet formulas in text — a name like '=HYPERLINK(...)'
    must not execute when accounting opens the file."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return "" if value is None else value


def _columns(entries: list[dict], key: str) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for e in entries:
        for line in e.get(key, []):
            label = line["name"] if line.get("code") == "ADJ" else line["code"]
            col = line["name"] if line.get("code") == "ADJ" else f'{line["name"]} ({line["code"]})'
            seen.setdefault(label, col)
    return list(seen.items())


def _sum_by(entry: dict, key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in entry.get(key, []):
        label = line["name"] if line.get("code") == "ADJ" else line["code"]
        out[label] = out.get(label, 0.0) + line["amount"]
    return out


def register_csv(entries: list[dict], *, organisation: str, period_label: str, status: str) -> str:
    """One row per person, one column per component. Full bank details: this
    is the file accounting pays from."""
    earn_cols = _columns(entries, "earnings")
    ded_cols = _columns(entries, "deductions")
    emp_cols = _columns(entries, "employer_contributions")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Payroll register — {organisation} — {period_label} ({status})"])
    w.writerow([
        "Employee code", "Name", "Department", "Designation", "Pay type", "PAN", "UAN",
        "PF number", "ESIC number", "PT state", "Bank", "Account number", "IFSC",
        "Days in month", "Paid days", "LOP days",
        *[c for _, c in earn_cols], "Gross earnings",
        *[c for _, c in ded_cols], "Total deductions",
        "Reimbursements", "Net pay",
        *[c for _, c in emp_cols], "Employer contributions", "Annual CTC",
    ])
    for e in entries:
        emp, days = e["employee"], e["days"]
        earn, ded, er = _sum_by(e, "earnings"), _sum_by(e, "deductions"), _sum_by(e, "employer_contributions")
        w.writerow([_cell(x) for x in [
            emp.get("employee_code"), emp.get("name"), emp.get("department"), emp.get("designation"),
            emp.get("pay_type"), emp.get("pan"), emp.get("uan"), emp.get("pf_number"),
            emp.get("esic_number"), emp.get("pt_state"), emp.get("bank_name"),
            emp.get("bank_account"), emp.get("bank_ifsc"),
            days.get("days_in_month"), days.get("paid_days"), days.get("lop_days"),
            *[earn.get(k, 0) for k, _ in earn_cols], e["gross"],
            *[ded.get(k, 0) for k, _ in ded_cols], e["total_deductions"],
            e["reimbursement_total"], e["net_pay"],
            *[er.get(k, 0) for k, _ in emp_cols], e["employer_total"],
            e.get("structure", {}).get("annual_ctc"),
        ]])
    w.writerow([])
    w.writerow(["Totals", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
                *[round(sum(_sum_by(e, "earnings").get(k, 0) for e in entries), 2) for k, _ in earn_cols],
                round(sum(e["gross"] for e in entries), 2),
                *[round(sum(_sum_by(e, "deductions").get(k, 0) for e in entries), 2) for k, _ in ded_cols],
                round(sum(e["total_deductions"] for e in entries), 2),
                round(sum(e["reimbursement_total"] for e in entries), 2),
                round(sum(e["net_pay"] for e in entries), 2),
                *[round(sum(_sum_by(e, "employer_contributions").get(k, 0) for e in entries), 2)
                  for k, _ in emp_cols],
                round(sum(e["employer_total"] for e in entries), 2), ""])
    return buf.getvalue()


def summary_csv(entries: list[dict], *, organisation: str, period_label: str, status: str) -> str:
    """Component totals — the figures a journal entry is posted from."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Payroll summary — {organisation} — {period_label} ({status})"])
    w.writerow(["Head", "Type", "Amount", "People"])
    for key, kind in (("earnings", "Earning"), ("deductions", "Deduction (payable)"),
                      ("employer_contributions", "Employer contribution (expense)"),
                      ("reimbursements", "Reimbursement")):
        totals: dict[str, list] = {}
        for e in entries:
            for line in e.get(key, []):
                t = totals.setdefault(line["name"], [0.0, 0])
                t[0] += line["amount"]
                t[1] += 1
        for name, (amount, count) in totals.items():
            w.writerow([_cell(name), kind, round(amount, 2), count])
    w.writerow([])
    w.writerow(["Gross earnings", "", round(sum(e["gross"] for e in entries), 2), len(entries)])
    w.writerow(["Total deductions", "", round(sum(e["total_deductions"] for e in entries), 2), ""])
    w.writerow(["Reimbursements", "", round(sum(e["reimbursement_total"] for e in entries), 2), ""])
    w.writerow(["Net pay (bank transfer)", "", round(sum(e["net_pay"] for e in entries), 2), ""])
    w.writerow(["Employer contributions", "", round(sum(e["employer_total"] for e in entries), 2), ""])
    return buf.getvalue()


# ─── PDF payslip ─────────────────────────────────────────────────────────────

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#475569")
LINE = colors.HexColor("#cbd5e1")
SHADE = colors.HexColor("#f1f5f9")
ACCENT = colors.HexColor("#0f766e")


def _inr(amount) -> str:
    """12,34,567.00 — Indian digit grouping."""
    neg = amount < 0
    whole, frac = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return ("-" if neg else "") + whole + "." + frac


def payslip_pdf(entry: dict, *, organisation: str, period_label: str, status: str) -> bytes:
    emp, days = entry["employee"], entry["days"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
        bottomMargin=14 * mm, title=f"Payslip {period_label} — {emp.get('name')}",
        author=organisation, invariant=1,
    )
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Title"], fontSize=16, textColor=INK, alignment=0, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=9.5, textColor=MUTED)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=MUTED, leading=10)
    cellp = ParagraphStyle("cell", parent=ss["Normal"], fontSize=9, textColor=INK, leading=11)

    story = [
        Paragraph(organisation or "Payslip", h),
        Paragraph(f"Payslip for {period_label}"
                  + ("" if status == "closed" else f" &nbsp;·&nbsp; <b>{status.upper()} — not final</b>"), sub),
        Spacer(1, 6 * mm),
    ]

    def kv(label, value):
        return [Paragraph(f'<font color="#475569">{label}</font>', cellp),
                Paragraph(str(value) if value not in (None, "") else "—", cellp)]

    left = [kv("Employee", emp.get("name")), kv("Employee code", emp.get("employee_code")),
            kv("Department", emp.get("department")), kv("Designation", emp.get("designation")),
            kv("Date of joining", emp.get("date_of_joining")),
            kv("Pay type", (emp.get("pay_type") or "salary").title())]
    acct = emp.get("bank_account") or ""
    right = [kv("PAN", emp.get("pan")), kv("UAN", emp.get("uan")), kv("PF number", emp.get("pf_number")),
             kv("ESIC number", emp.get("esic_number")),
             kv("Bank", emp.get("bank_name")),
             kv("Account", ("XXXX" + acct[-4:]) if len(acct) > 4 else acct)]
    details = Table([[*a, *b] for a, b in zip(left, right, strict=False)], colWidths=[28 * mm, 58 * mm, 26 * mm, 66 * mm])
    details.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [details, Spacer(1, 4 * mm)]

    day_tbl = Table([[
        f"Days in month: {days.get('days_in_month')}",
        f"Paid days: {days.get('paid_days'):g}",
        f"LOP days: {days.get('lop_days'):g}",
        f"Present: {days.get('present')}  ·  Leave: {days.get('paid_leave')}  ·  Holidays: {days.get('holidays')}",
    ]], colWidths=[34 * mm, 30 * mm, 28 * mm, 86 * mm])
    day_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), MUTED),
        ("BACKGROUND", (0, 0), (-1, -1), SHADE), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
    ]))
    story += [day_tbl, Spacer(1, 4 * mm)]

    earn, ded = entry.get("earnings", []), entry.get("deductions", [])
    n = max(len(earn), len(ded), 1)
    rows = [["Earnings", "Amount (Rs.)", "Deductions", "Amount (Rs.)"]]
    for i in range(n):
        e = earn[i] if i < len(earn) else None
        d = ded[i] if i < len(ded) else None
        rows.append([e["name"] if e else "", _inr(e["amount"]) if e else "",
                     d["name"] if d else "", _inr(d["amount"]) if d else ""])
    rows.append(["Gross earnings", _inr(entry["gross"]), "Total deductions", _inr(entry["total_deductions"])])
    pay = Table(rows, colWidths=[56 * mm, 33 * mm, 56 * mm, 33 * mm])
    pay.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("BACKGROUND", (0, 0), (-1, 0), SHADE), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, LINE),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("LINEAFTER", (1, 0), (1, -1), 0.6, LINE),
    ]))
    story += [pay, Spacer(1, 3 * mm)]

    if entry.get("reimbursements"):
        r_rows = [["Reimbursements", "Amount (Rs.)"]] + [[r["name"], _inr(r["amount"])] for r in entry["reimbursements"]]
        r_tbl = Table(r_rows, colWidths=[145 * mm, 33 * mm])
        r_tbl.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), SHADE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ]))
        story += [r_tbl, Spacer(1, 3 * mm)]

    net = Table([
        [Paragraph('<font color="#ffffff"><b>Net pay</b></font>', cellp),
         Paragraph(f'<font color="#ffffff" size="13"><b>Rs. {_inr(entry["net_pay"])}</b></font>', cellp)],
        [Paragraph(f'<font color="#e2e8f0">{rupees_in_words(entry["net_pay"])}</font>', cellp), ""],
    ], colWidths=[120 * mm, 58 * mm])
    net.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT), ("SPAN", (0, 1), (1, 1)),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [net, Spacer(1, 4 * mm)]

    er = entry.get("employer_contributions") or []
    if er:
        story.append(Paragraph(
            "Employer contributions (part of CTC, not deducted from pay): "
            + ", ".join(f'{x["name"].replace(" (employer)", "")} Rs. {_inr(x["amount"])}' for x in er), small))
    ctc = (entry.get("structure") or {}).get("annual_ctc")
    if ctc:
        story.append(Paragraph(f"Annual CTC: Rs. {_inr(ctc)}", small))
    story += [Spacer(1, 6 * mm), Paragraph(
        "This is a computer-generated payslip and does not need a signature.", small)]

    doc.build(story)
    return buf.getvalue()
