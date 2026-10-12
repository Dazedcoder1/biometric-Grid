"""
HR letters and documents: templates fill correctly, unknown fields are asked
for rather than silently printed, uploads are checked by content, and expiry
reminders go out once per stage.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.services import hr_documents as hd
from app.services import letters as L


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ─── templates ───────────────────────────────────────────────────────────────

def test_fill_replaces_known_fields_and_reports_the_rest():
    text, missing = L.fill("Dear {{first_name}}, from {{ joining_date }} at {{work_location}}.",
                           {"first_name": "Aarti", "joining_date": "2026-11-02"})
    assert text == "Dear Aarti, from 2 November 2026 at {{work_location}}."
    assert missing == ["work_location"]


def test_salary_table_is_left_for_the_pdf():
    text, missing = L.fill("Structure:\n\n{{salary_table}}", {})
    assert "{{salary_table}}" in text and missing == []


def test_amount_fields_are_formatted_in_rupees():
    text, _ = L.fill("Stipend {{stipend_amount}}", {"stipend_amount": "1500000"})
    assert text == "Stipend Rs. 15,00,000"


@pytest.mark.parametrize("kind", sorted(L.STARTERS))
def test_every_starter_template_is_complete(kind):
    name, subject, body = L.starter(kind)
    assert name == L.KINDS[kind] and subject and "Yours sincerely" in body
    # Every field a starter uses is either filled automatically or has a
    # proper label and input type for HR — no raw snake_case prompts.
    for f in L.placeholders(subject, body):
        assert f in L.AUTO_FIELDS or f in L.MANUAL_HINTS, f"{kind}: {f}"


def test_auto_values_from_person_profile_and_payroll():
    user = Obj(name="Aarti Deshpande", employee_code="EMP-019", email="a@x")
    prof = Obj(designation="Engineer", date_of_joining=dt.date(2024, 4, 1), pay_type="salary")
    cur = Obj(annual_ctc=540000, lines={"BASIC": 25000, "HRA": 10000}, effective_from=dt.date(2026, 4, 1))
    prev = Obj(annual_ctc=480000, lines={}, effective_from=dt.date(2025, 4, 1))
    v = L.auto_values(user=user, department="Production", profile=prof, current_rev=cur, previous_rev=prev,
                      letterhead={"company_name": "Northwind", "signatory_name": "R. Iyer"},
                      letter_date=dt.date(2026, 10, 12), reference_no=None, component_names={"BASIC": "Basic"})
    assert v["first_name"] == "Aarti" and v["date_of_joining"] == "1 April 2024"
    assert v["annual_ctc"] == "Rs. 5,40,000" and v["previous_ctc"] == "Rs. 4,80,000"
    assert v["annual_ctc_words"] == "Five Lakh Forty Thousand rupees"
    assert v["monthly_fixed"] == "Rs. 35,000"
    assert v["salary_table"][0] == {"name": "Basic", "monthly": 25000.0, "annual": 300000.0}
    assert "reference_no" not in v                  # given on issue


def test_letter_pdf_escapes_input_and_is_stable():
    args = {"subject": "Offer <b>& more", "body": "Dear A & B <script>,\n\n**Welcome**\n\n{{salary_table}}",
                "letterhead": {"company_name": "Northwind & Co", "signatory_name": "R. Iyer", "footer": "f"},
                "recipient": {"name": "A <x>"}, "letter_date": dt.date(2026, 10, 12), "reference_no": "NW/OFFER/2026/0001",
                "status": "issued", "salary_rows": [{"name": "Basic", "monthly": 25000, "annual": 300000}]}
    a, b = L.letter_pdf(**args), L.letter_pdf(**args)
    assert a.startswith(b"%PDF") and a == b
    draft = L.letter_pdf(**{**args, "status": "draft"})
    assert draft != a                                # watermark


def test_indian_grouping():
    assert L.inr(12345678) == "Rs. 1,23,45,678"
    assert L.inr(999) == "Rs. 999"
    assert L.long_date("2026-01-05") == "5 January 2026"


# ─── uploads ─────────────────────────────────────────────────────────────────

def test_file_type_comes_from_the_bytes():
    assert hd.sniff(b"%PDF-1.7 ...", "policy.pdf") == "application/pdf"
    assert hd.sniff(b"\x89PNG\r\n\x1a\nxxxx", "a.png") == "image/png"
    assert hd.sniff(b"\xff\xd8\xff\xe0", "a.jpg") == "image/jpeg"
    assert hd.sniff(b"PK\x03\x04....word/document.xml", "a.docx").endswith("wordprocessingml.document")
    assert hd.sniff(b"Leave policy\nplain", "notes.txt").startswith("text/plain")
    # The name does not make it so.
    assert hd.sniff(b"<html><script>alert(1)</script>", "policy.pdf") is None
    assert hd.sniff(b"MZ\x90\x00", "handbook.pdf") is None
    assert hd.sniff(b"PK\x03\x04 not word", "a.zip") is None


def test_file_names_are_cleaned():
    assert hd.safe_name("../../etc/passwd") == "....etcpasswd"
    assert hd.safe_name('a"b<c>.pdf') == "abc.pdf"


# ─── expiry ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("left,already,stage", [
    (45, None, None),
    (30, None, 30), (12, None, 30),
    (12, 30, None),            # already told at 30 days
    (7, 30, 7), (3, 7, None),
    (0, 7, 0), (-5, 7, 0),
    (-5, 0, None),             # told on the day; not again every pass
    (2, None, 7),              # uploaded late: jump to the stage that applies
])
def test_reminder_stages(left, already, stage):
    assert hd.due_stage(left, already) == stage


def test_expiry_states():
    assert hd.expiry_state(None) == "none"
    assert hd.expiry_state(-1) == "expired"
    assert hd.expiry_state(0) == "expiring"
    assert hd.expiry_state(30) == "expiring"
    assert hd.expiry_state(31) == "valid"


def test_audience_by_department():
    doc = Obj(tenant_id=1, audience={"departments": [3]})
    assert hd.in_audience(doc, Obj(tenant_id=1, role="employee", dept_id=3))
    assert not hd.in_audience(doc, Obj(tenant_id=1, role="employee", dept_id=4))
    assert not hd.in_audience(doc, Obj(tenant_id=2, role="employee", dept_id=3))
    assert not hd.in_audience(Obj(tenant_id=1, audience=None), Obj(tenant_id=1, role="tenant_admin", dept_id=None))
    assert hd.in_audience(Obj(tenant_id=1, audience=None), Obj(tenant_id=1, role="org_admin", dept_id=None))
