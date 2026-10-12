"""
HR letters: templates with {{placeholders}}, filled from the person's record
and payroll, frozen when issued, printed on the organisation's letterhead.

Template syntax, deliberately small:
  {{field}}            replaced by a value; unknown fields become inputs HR
                       fills in when issuing
  **bold**             bold text
  a blank line         a new paragraph
  {{salary_table}}     on a line of its own: the current salary structure as
                       a table (monthly and annual)

Everything typed into a template or a field is escaped before it reaches the
PDF renderer, so a name containing "<" or "&" prints as written and cannot
inject markup.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.payroll_calc import D, rupees_in_words

PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
TABLE_TOKEN = "salary_table"  # noqa: S105 — a placeholder name, not a secret

KINDS = {
    "offer": "Offer letter",
    "appointment": "Appointment letter",
    "internship": "Internship letter",
    "confirmation": "Confirmation letter",
    "promotion": "Promotion letter",
    "salary_revision": "Salary revision letter",
    "experience": "Experience letter",
    "relieving": "Relieving letter",
    "other": "Other letter",
}

# Filled automatically from the person, the organisation and payroll.
AUTO_FIELDS = {
    "employee_name": "Full name",
    "first_name": "First name",
    "employee_code": "Employee code",
    "email": "Email",
    "department": "Department",
    "designation": "Designation (from pay details)",
    "date_of_joining": "Date of joining",
    "company_name": "Company name (letterhead)",
    "company_address": "Company address (letterhead)",
    "signatory_name": "Signatory",
    "signatory_title": "Signatory's title",
    "letter_date": "Letter date",
    "reference_no": "Reference number (given on issue)",
    "annual_ctc": "Annual CTC (current structure)",
    "annual_ctc_words": "Annual CTC in words",
    "monthly_fixed": "Monthly fixed pay",
    "effective_from": "Current structure effective from",
    "previous_ctc": "Annual CTC before the latest revision",
    "pay_type": "Salary or stipend",
    TABLE_TOKEN: "Salary breakdown table",
}

# Fields HR types in. Anything else a template uses is asked for too, with
# its name turned into a label.
MANUAL_HINTS = {
    "joining_date": ("Date of joining", "date"),
    "offer_valid_until": ("Offer valid until", "date"),
    "probation_months": ("Probation (months)", "number"),
    "work_location": ("Work location", "text"),
    "reporting_manager": ("Reporting to", "text"),
    "internship_start": ("Internship starts", "date"),
    "internship_end": ("Internship ends", "date"),
    "stipend_amount": ("Monthly stipend (Rs.)", "number"),
    "confirmation_date": ("Confirmed with effect from", "date"),
    "new_designation": ("New designation", "text"),
    "previous_designation": ("Previous designation", "text"),
    "effective_date": ("Effective from", "date"),
    "resignation_date": ("Resignation received on", "date"),
    "last_working_day": ("Last working day", "date"),
    "notice_period_days": ("Notice period (days)", "number"),
}


def field_label(name: str) -> str:
    if name in AUTO_FIELDS:
        return AUTO_FIELDS[name]
    if name in MANUAL_HINTS:
        return MANUAL_HINTS[name][0]
    return name.replace("_", " ").capitalize()


def field_type(name: str) -> str:
    return MANUAL_HINTS.get(name, ("", "text"))[1]


def placeholders(*texts: str) -> list[str]:
    seen: list[str] = []
    for t in texts:
        for m in PLACEHOLDER.finditer(t or ""):
            if m.group(1) not in seen:
                seen.append(m.group(1))
    return seen


def long_date(value) -> str:
    """2026-10-12 -> 12 October 2026, the way Indian letters write it."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = dt.date.fromisoformat(value[:10])
        except ValueError:
            return value
    return f"{value.day} {value.strftime('%B %Y')}"


def inr(amount) -> str:
    whole = f"{int(D(amount)):,}"
    # 1,234,567 -> 12,34,567
    digits = whole.replace(",", "")
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"Rs. {whole}"


def fill(text: str, values: dict) -> tuple[str, list[str]]:
    """Replace placeholders; return the text and any still missing."""
    missing: list[str] = []

    def sub(m):
        name = m.group(1)
        if name == TABLE_TOKEN:
            return m.group(0)                 # drawn by the PDF, not inlined
        v = values.get(name)
        if v is None or str(v).strip() == "":
            if name not in missing:
                missing.append(name)
            return m.group(0)
        if field_type(name) == "date":
            return long_date(v)
        if name.endswith("_amount"):
            try:
                return inr(v)
            except Exception:  # noqa: BLE001 — not a number: print as typed
                return str(v)
        return str(v)

    return PLACEHOLDER.sub(sub, text or ""), missing


# ─── starter templates ───────────────────────────────────────────────────────
# Original wording, plain and neutral. Every organisation should read and
# adapt them — they are a starting point, not legal advice.

_CLOSE = "Yours sincerely,"

STARTERS = {
    "offer": ("Offer of employment", """Dear {{first_name}},

We are pleased to offer you the position of **{{designation}}** in the {{department}} team at {{company_name}}. We enjoyed getting to know you during the selection process and believe you will make a strong contribution.

Your expected date of joining is {{joining_date}}, and you will be based at {{work_location}}, reporting to {{reporting_manager}}. Your annual cost to company will be **{{annual_ctc}}** ({{annual_ctc_words}}), structured as follows:

{{salary_table}}

You will be on probation for {{probation_months}} months from your date of joining. Detailed terms of employment will be set out in your appointment letter on joining.

This offer is valid until {{offer_valid_until}}. Please confirm your acceptance by signing and returning a copy of this letter.

We look forward to welcoming you."""),

    "appointment": ("Letter of appointment", """Dear {{first_name}},

Further to your acceptance of our offer, we are pleased to appoint you as **{{designation}}** in the {{department}} team with effect from {{date_of_joining}}. Your employee code is {{employee_code}}.

Your annual cost to company is **{{annual_ctc}}**, structured as follows:

{{salary_table}}

You will be on probation for {{probation_months}} months, during which either party may end the employment with the notice set out in company policy. On satisfactory completion your confirmation will be communicated in writing.

You are expected to follow the policies set out in the employee handbook, as updated from time to time, and to keep all company information confidential during and after your employment.

Please sign and return a copy of this letter as acceptance of these terms."""),

    "internship": ("Internship letter", """Dear {{first_name}},

We are pleased to offer you an internship with the {{department}} team at {{company_name}} from {{internship_start}} to {{internship_end}}. You will be working with {{reporting_manager}}.

You will receive a monthly stipend of {{stipend_amount}} for the duration of the internship. The internship does not constitute an offer of employment; any such offer would be made separately in writing.

During the internship you are expected to follow company policies and keep all company information confidential.

We hope you find the experience rewarding."""),

    "confirmation": ("Confirmation of employment", """Dear {{first_name}},

We are pleased to inform you that, following a review of your performance during probation, your employment as **{{designation}}** is confirmed with effect from {{confirmation_date}}.

All other terms and conditions of your appointment remain unchanged.

Thank you for your contribution so far, and we look forward to your continued growth with {{company_name}}."""),

    "promotion": ("Promotion", """Dear {{first_name}},

In recognition of your performance and contribution, we are pleased to promote you from {{previous_designation}} to **{{new_designation}}** with effect from {{effective_date}}.

Your revised annual cost to company is **{{annual_ctc}}**, structured as follows:

{{salary_table}}

All other terms of your employment remain unchanged. Congratulations, and thank you for your continued commitment."""),

    "salary_revision": ("Revision of compensation", """Dear {{first_name}},

We are pleased to inform you that your annual cost to company has been revised from {{previous_ctc}} to **{{annual_ctc}}** ({{annual_ctc_words}}) with effect from {{effective_from}}.

Your revised structure is as follows:

{{salary_table}}

All other terms of your employment remain unchanged. Thank you for your contribution to {{company_name}}."""),

    "experience": ("Experience certificate", """To whom it may concern,

This is to certify that **{{employee_name}}** (employee code {{employee_code}}) was employed with {{company_name}} from {{date_of_joining}} to {{last_working_day}}. At the time of leaving, {{first_name}} held the position of {{designation}} in the {{department}} team.

During this period we found {{first_name}} to be sincere and dependable. We wish {{first_name}} every success in the future."""),

    "relieving": ("Relieving letter", """Dear {{first_name}},

This refers to your resignation dated {{resignation_date}}. We confirm that your resignation has been accepted and that you are relieved from your duties as {{designation}} at the close of business on {{last_working_day}}.

Your full and final settlement will be processed in line with company policy. We remind you of your continuing obligation to keep company information confidential.

We thank you for your contribution and wish you the very best."""),
}


def starter(kind: str) -> tuple[str, str, str]:
    """(name, subject, body) for a starter template, with the closing line."""
    subject, body = STARTERS[kind]
    return KINDS[kind], subject, body + f"\n\n{_CLOSE}"


# ─── values ──────────────────────────────────────────────────────────────────

def auto_values(*, user, department: str | None, profile, current_rev, previous_rev,
                letterhead: dict, letter_date: dt.date, reference_no: str | None,
                component_names: dict[str, str]) -> dict:
    name = (user.name or "").strip()
    v = {
        "employee_name": name,
        "first_name": name.split(" ")[0] if name else "",
        "employee_code": user.employee_code,
        "email": user.email,
        "department": department,
        "designation": getattr(profile, "designation", None),
        "date_of_joining": long_date(getattr(profile, "date_of_joining", None)),
        "company_name": letterhead.get("company_name"),
        "company_address": letterhead.get("address"),
        "signatory_name": letterhead.get("signatory_name"),
        "signatory_title": letterhead.get("signatory_title"),
        "letter_date": long_date(letter_date),
        # Left as {{reference_no}} on a draft; the number is given on issue.
        "reference_no": reference_no,
        "pay_type": (getattr(profile, "pay_type", None) or "salary").title(),
    }
    if current_rev:
        v["annual_ctc"] = inr(current_rev.annual_ctc)
        v["annual_ctc_words"] = rupees_in_words(current_rev.annual_ctc).replace("Rupees ", "").replace(" Only", "") + " rupees"
        lines = current_rev.lines or {}
        v["monthly_fixed"] = inr(sum(D(x) for x in lines.values()))
        v["effective_from"] = long_date(current_rev.effective_from)
        v[TABLE_TOKEN] = [
            {"name": component_names.get(code, code), "monthly": float(D(amount)), "annual": float(D(amount) * 12)}
            for code, amount in lines.items()
        ]
    if previous_rev:
        v["previous_ctc"] = inr(previous_rev.annual_ctc)
    return {k: val for k, val in v.items() if val not in (None, "")}


# ─── PDF ─────────────────────────────────────────────────────────────────────

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#475569")
LINE = colors.HexColor("#cbd5e1")
SHADE = colors.HexColor("#f1f5f9")
ACCENT = colors.HexColor("#0f766e")


def _markup(paragraph: str) -> str:
    """Escape, then turn **x** into bold and single newlines into breaks."""
    text = escape(paragraph)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text.replace("\n", "<br/>")


def letter_pdf(*, subject: str, body: str, letterhead: dict, recipient: dict, letter_date,
               reference_no: str | None, status: str, salary_rows: list[dict] | None) -> bytes:
    buf = io.BytesIO()
    lh = letterhead or {}

    def on_page(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(ACCENT)
        canvas.rect(0, h - 4 * mm, w, 4 * mm, stroke=0, fill=1)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        foot = " · ".join(x for x in (lh.get("footer"), f"CIN {lh['cin']}" if lh.get("cin") else None) if x)
        if foot:
            canvas.drawCentredString(w / 2, 10 * mm, foot[:150])
        canvas.drawRightString(w - 18 * mm, 10 * mm, f"Page {doc.page}")
        if status != "issued":
            canvas.setFont("Helvetica-Bold", 60)
            canvas.setFillColor(colors.Color(0.86, 0.15, 0.15, alpha=0.10))
            canvas.translate(w / 2, h / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "DRAFT" if status == "draft" else "REVOKED")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=16 * mm, bottomMargin=20 * mm, title=subject,
                            author=lh.get("company_name") or "", invariant=1)
    ss = getSampleStyleSheet()
    company = ParagraphStyle("co", parent=ss["Title"], fontSize=17, textColor=INK, alignment=0, spaceAfter=1, leading=20)
    small = ParagraphStyle("sm", parent=ss["Normal"], fontSize=8.5, textColor=MUTED, leading=11)
    body_style = ParagraphStyle("b", parent=ss["Normal"], fontSize=10.5, textColor=INK, leading=15.5, spaceAfter=8)
    subj = ParagraphStyle("s", parent=body_style, fontName="Helvetica-Bold", fontSize=11.5, spaceBefore=4, spaceAfter=10)

    story = [Paragraph(escape(lh.get("company_name") or ""), company)]
    if lh.get("address"):
        story.append(Paragraph(_markup(lh["address"]), small))
    if lh.get("contact_line"):
        story.append(Paragraph(escape(lh["contact_line"]), small))
    rule = Table([[""]], colWidths=[170 * mm], rowHeights=[2])
    rule.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, LINE)]))
    story += [Spacer(1, 3 * mm), rule, Spacer(1, 5 * mm)]

    meta = Table([[Paragraph(f"Ref: {escape(reference_no or '—')}", small),
                   Paragraph(f"Date: {escape(long_date(letter_date))}", ParagraphStyle("r", parent=small, alignment=2))]],
                 colWidths=[100 * mm, 70 * mm])
    story += [meta, Spacer(1, 5 * mm)]

    to = [escape(recipient.get("name") or "")]
    for k in ("designation", "employee_code"):
        if recipient.get(k):
            to.append(escape(str(recipient[k])))
    story += [Paragraph("<br/>".join(to), body_style), Spacer(1, 2 * mm),
              Paragraph(f"Subject: {escape(subject)}", subj)]

    for para in re.split(r"\n\s*\n", (body or "").strip()):
        para = para.strip()
        if not para:
            continue
        whole = PLACEHOLDER.fullmatch(para)
        if whole and whole.group(1) == TABLE_TOKEN:
            rows = [["Component", "Monthly (Rs.)", "Annual (Rs.)"]]
            total_m = total_a = 0.0
            for r in salary_rows or []:
                rows.append([r["name"], inr(r["monthly"])[4:], inr(r["annual"])[4:]])
                total_m += r["monthly"]
                total_a += r["annual"]
            rows.append(["Total fixed", inr(total_m)[4:], inr(total_a)[4:]])
            t = Table(rows, colWidths=[90 * mm, 40 * mm, 40 * mm])
            t.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("BACKGROUND", (0, 0), (-1, 0), SHADE), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, LINE),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story += [t, Spacer(1, 4 * mm)]
            continue
        story.append(Paragraph(_markup(para), body_style))

    sign = [Spacer(1, 4 * mm),
            Paragraph(f"For {escape(lh.get('company_name') or '')}", body_style),
            Spacer(1, 14 * mm),
            Paragraph(f"<b>{escape(lh.get('signatory_name') or '')}</b>", body_style)]
    if lh.get("signatory_title"):
        sign.append(Paragraph(escape(lh["signatory_title"]), small))
    story.append(KeepTogether(sign))
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
