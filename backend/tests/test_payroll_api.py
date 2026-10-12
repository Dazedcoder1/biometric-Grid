"""
Payroll rules that live outside the arithmetic: maker-checker, what can
change when, input validation, and the documents.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import payroll as routes
from app.services import payroll_docs
from app.services import payroll_service as svc


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


MAKER = Obj(id=1, name="Maker")
CHECKER = Obj(id=2, name="Checker")


def run(status="draft", **kw):
    base = {"id": 9, "status": status, "period": dt.date(2026, 10, 1), "totals": {"people": 3},
                "submitted_by": None, "submitted_at": None, "approved_by": None, "approved_at": None,
                "returned_note": None}
    return Obj(**{**base, **kw})


class _Res:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class ClaimsDB:
    def __init__(self, claims):
        self.claims = claims

    async def execute(self, _):
        return _Res(self.claims)


# ─── maker-checker ───────────────────────────────────────────────────────────

def test_submit_records_the_maker():
    r = run()
    svc.submit(r, MAKER)
    assert r.status == "submitted" and r.submitted_by == 1


def test_cannot_submit_an_empty_month():
    with pytest.raises(HTTPException) as exc:
        svc.submit(run(totals={}), MAKER)
    assert exc.value.status_code == 409


async def test_maker_cannot_approve_their_own_submission():
    r = run("submitted")
    r.submitted_by = 1
    with pytest.raises(HTTPException) as exc:
        await svc.approve(ClaimsDB([]), r, MAKER)
    assert exc.value.status_code == 403 and "someone else" in exc.value.detail
    assert r.status == "submitted"


async def test_checker_approves_closes_and_pays_claims():
    r = run("submitted")
    r.submitted_by = 1
    claim = Obj(status="approved")
    await svc.approve(ClaimsDB([claim]), r, CHECKER)
    assert r.status == "closed" and r.approved_by == 2
    assert claim.status == "paid"


async def test_only_a_submitted_month_can_be_approved():
    with pytest.raises(HTTPException) as exc:
        await svc.approve(ClaimsDB([]), run("draft"), CHECKER)
    assert exc.value.status_code == 409


def test_send_back_returns_to_draft_with_the_reason():
    r = run("submitted")
    r.submitted_by = 1
    svc.send_back(r, "LOP for Kiran is wrong")
    assert r.status == "draft" and r.returned_note == "LOP for Kiran is wrong" and r.submitted_by is None


def test_a_closed_month_cannot_be_sent_back():
    with pytest.raises(HTTPException):
        svc.send_back(run("closed"), "too late")


async def test_a_closed_month_is_never_recalculated():
    with pytest.raises(HTTPException) as exc:
        await svc.prepare(None, 1, dt.date(2026, 9, 1), MAKER, run=run("closed"))
    assert exc.value.status_code == 409


async def test_future_months_cannot_be_prepared():
    with pytest.raises(HTTPException) as exc:
        await svc.prepare(None, 1, dt.date(2099, 1, 1), MAKER)
    assert exc.value.status_code == 400


# ─── validation ──────────────────────────────────────────────────────────────

def test_component_codes_are_normalised_and_checked():
    assert routes.ComponentIn(code=" basic ", name="Basic", kind="earning").code == "BASIC"
    for bad in ("1PF", "P", "GROSS", "ADJ", "with space"):
        with pytest.raises(ValidationError):
            routes.ComponentIn(code=bad, name="x", kind="earning")


def test_component_shape_rules():
    with pytest.raises(HTTPException):
        routes._check_component({"calc": "percent", "rate": None})
    with pytest.raises(HTTPException):
        routes._check_component({"calc": "slab", "slabs": []})
    with pytest.raises(HTTPException):
        routes._check_component({"calc": "slab", "slabs": [{"upto": None, "amount": 1}, {"upto": None, "amount": 2}]})
    routes._check_component({"calc": "slab", "slabs": [{"upto": 10000, "amount": 0}, {"upto": None, "amount": 200}]})


def test_indian_identifiers_are_validated():
    p = routes.ProfileIn(pan="abcde1234f", uan="1001 2345 6789", bank_ifsc="hdfc0001234",
                         bank_account="00112233445566", esic_number="1234567890")
    assert (p.pan, p.uan, p.bank_ifsc) == ("ABCDE1234F", "100123456789", "HDFC0001234")
    for field, bad in (("pan", "ABCD1234F"), ("uan", "12345"), ("bank_ifsc", "HDFC1234567"),
                       ("bank_account", "12ab"), ("esic_number", "123")):
        with pytest.raises(ValidationError):
            routes.ProfileIn(**{field: bad})


def test_blank_identifiers_are_stored_as_none():
    assert routes.ProfileIn(pan="  ").pan is None


def test_bank_account_is_masked():
    assert svc.mask("00112233445566") == "••••••••••5566"
    assert svc.mask(None) is None


# ─── documents ───────────────────────────────────────────────────────────────

ENTRY = {
    "employee": {"name": "Aarti Deshpande", "employee_code": "EMP-019", "department": "Production",
                 "designation": "Engineer", "pay_type": "salary", "pan": "ABCDE1234F", "uan": "100123456789",
                 "bank_name": "HDFC Bank", "bank_account": "00112233445566", "bank_ifsc": "HDFC0001234",
                 "date_of_joining": "2024-04-01"},
    "days": {"days_in_month": 31, "paid_days": 29.0, "lop_days": 2.0, "present": 20, "paid_leave": 1,
             "holidays": 1},
    "structure": {"annual_ctc": 540000.0},
    "earnings": [{"code": "BASIC", "name": "Basic", "amount": 23387.0},
                 {"code": "HRA", "name": "House Rent Allowance", "amount": 9355.0},
                 {"code": "ADJ", "name": "Diwali bonus", "amount": 5000.0}],
    "deductions": [{"code": "PF", "name": "Provident Fund", "amount": 1800.0},
                   {"code": "PT", "name": "Professional Tax", "amount": 200.0}],
    "employer_contributions": [{"code": "PF", "name": "Provident Fund (employer)", "amount": 1800.0}],
    "reimbursements": [{"id": 4, "name": "Travel", "amount": 1234.5}],
    "gross": 37742.0, "total_deductions": 2000.0, "reimbursement_total": 1234.5,
    "net_pay": 36976.5, "employer_total": 1800.0,
}


def test_payslip_pdf_is_a_stable_pdf():
    a = payroll_docs.payslip_pdf(ENTRY, organisation="Northwind", period_label="October 2026", status="closed")
    b = payroll_docs.payslip_pdf(ENTRY, organisation="Northwind", period_label="October 2026", status="closed")
    assert a.startswith(b"%PDF") and len(a) > 1500
    assert a == b                                  # same payslip, same bytes


def test_register_has_a_column_per_component_and_full_bank_details():
    text = payroll_docs.register_csv([ENTRY], organisation="Northwind", period_label="October 2026",
                                     status="closed")
    lines = text.splitlines()
    header = lines[1]
    for col in ("Basic (BASIC)", "House Rent Allowance (HRA)", "Diwali bonus", "Provident Fund (PF)",
                "Professional Tax (PT)", "Net pay", "Account number"):
        assert col in header
    assert "00112233445566" in lines[2]
    assert "36976.5" in lines[2]


def test_register_neutralises_formulas():
    evil = {**ENTRY, "employee": {**ENTRY["employee"], "name": "=HYPERLINK(\"http://x\")"}}
    text = payroll_docs.register_csv([evil], organisation="N", period_label="P", status="draft")
    assert "'=HYPERLINK" in text


def test_summary_totals_by_head():
    text = payroll_docs.summary_csv([ENTRY, ENTRY], organisation="N", period_label="P", status="closed")
    assert "Provident Fund,Deduction (payable),3600.0,2" in text
    assert "Net pay (bank transfer),,73953.0" in text


def test_indian_digit_grouping():
    assert payroll_docs._inr(1234567.5) == "12,34,567.50"
    assert payroll_docs._inr(999) == "999.00"
