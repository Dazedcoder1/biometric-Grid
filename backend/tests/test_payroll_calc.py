"""
Payroll arithmetic, against the kind of setup an Indian organisation would
configure: Basic + HRA + Special, PF on Basic capped at 15,000, ESI on gross
up to 21,000, Professional Tax by slab. None of this is built in — the tests
define it the way an admin would.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.services import payroll_calc as calc


def comp(code, kind, calc_="fixed", **kw):
    return {"code": code, "name": kw.pop("name", code.title()), "kind": kind, "calc": calc_,
            "active": True, "applies_to": "all", "prorate": True, "sort_order": 100, **kw}


INDIA = [
    comp("BASIC", "earning", sort_order=1),
    comp("HRA", "earning", sort_order=2),
    comp("SPECIAL", "earning", sort_order=3),
    comp("PF", "deduction", "percent", rate=12, employer_rate=12, base_codes="BASIC",
         wage_ceiling=15000, is_statutory=True, applies_to="salary"),
    comp("ESI", "deduction", "percent", rate=0.75, employer_rate=3.25, base_codes="GROSS",
         gross_limit=21000, is_statutory=True, applies_to="salary"),
    comp("PT", "deduction", "slab", is_statutory=True, applies_to="salary",
         slabs=[{"upto": 7500, "amount": 0}, {"upto": 10000, "amount": 175}, {"upto": None, "amount": 200}]),
]
LINES = {"BASIC": 25000, "HRA": 10000, "SPECIAL": 5000}


def pay(lines=LINES, paid=31, dim=31, **kw):
    kw.setdefault("pay_type", "salary")
    kw.setdefault("exempt", set())
    return calc.compute_pay(INDIA, lines, days_in_month=dim, paid=Decimal(paid), **kw)


def amounts(lines):
    return {x["code"] if x["code"] != "ADJ" else x["name"]: x["amount"] for x in lines}


# ─── components ──────────────────────────────────────────────────────────────

def test_full_month_salary():
    p = pay()
    assert amounts(p["earnings"]) == {"BASIC": 25000, "HRA": 10000, "SPECIAL": 5000}
    assert p["gross"] == 40000
    # PF on Basic capped at 15,000 -> 1,800. ESI not applicable above 21,000.
    # PT top slab 200.
    assert amounts(p["deductions"]) == {"PF": 1800, "PT": 200}
    assert p["total_deductions"] == 2000
    assert p["net_pay"] == 38000
    assert amounts(p["employer_contributions"]) == {"PF": 1800}


def test_loss_of_pay_prorates_fixed_earnings_and_the_pf_base():
    p = pay(paid=26)                                   # 5 LOP days in a 31-day month
    e = amounts(p["earnings"])
    assert e["BASIC"] == round(25000 * 26 / 31)        # 20,968
    assert e["HRA"] == round(10000 * 26 / 31)
    assert amounts(p["deductions"])["PF"] == 1800      # prorated Basic still above the ceiling


def test_esi_applies_only_up_to_the_gross_limit():
    p = pay(lines={"BASIC": 12000, "HRA": 4800, "SPECIAL": 1200})   # gross 18,000
    d, er = amounts(p["deductions"]), amounts(p["employer_contributions"])
    assert d["ESI"] == 135                             # 0.75% of 18,000
    assert er["ESI"] == 585                            # 3.25%
    assert d["PF"] == 1440                             # 12% of 12,000 (below ceiling)
    assert d["PT"] == 200


def test_slab_picks_the_bracket_by_gross():
    assert calc.slab_amount(INDIA[5]["slabs"], Decimal(7000)) == 0
    assert calc.slab_amount(INDIA[5]["slabs"], Decimal(9000)) == 175
    assert calc.slab_amount(INDIA[5]["slabs"], Decimal(10000)) == 175
    assert calc.slab_amount(INDIA[5]["slabs"], Decimal(10001)) == 200


def test_stipend_skips_salary_only_components():
    p = pay(lines={"BASIC": 15000}, pay_type="stipend")
    assert p["deductions"] == [] and p["net_pay"] == 15000


def test_employee_exemption_drops_a_component():
    p = pay(exempt={"pf"})
    assert "PF" not in amounts(p["deductions"])


def test_inactive_component_is_ignored():
    comps = [dict(c) for c in INDIA]
    comps[5]["active"] = False
    p = calc.compute_pay(comps, LINES, pay_type="salary", exempt=set(), days_in_month=30, paid=Decimal(30))
    assert "PT" not in amounts(p["deductions"])


def test_percent_earning_from_basic():
    comps = [comp("BASIC", "earning", sort_order=1),
             comp("HRA", "earning", "percent", rate=40, base_codes="BASIC", sort_order=2)]
    p = calc.compute_pay(comps, {"BASIC": 20000}, pay_type="salary", exempt=set(),
                         days_in_month=30, paid=Decimal(15))
    assert amounts(p["earnings"]) == {"BASIC": 10000, "HRA": 4000}


def test_adjustments_and_reimbursements():
    p = pay(adjustments=[{"kind": "earning", "label": "Diwali bonus", "amount": 5000},
                         {"kind": "deduction", "label": "TDS", "amount": 3125}],
            reimbursements=[{"id": 1, "category": "Travel", "amount": "1234.50"}])
    assert p["gross"] == 45000
    assert amounts(p["deductions"])["TDS"] == 3125
    assert p["reimbursement_total"] == 1234.5
    # 45,000 - (1,800 + 200 + 3,125) + 1,234.50
    assert p["net_pay"] == 41109.5


def test_no_structure_warns_and_pays_nothing():
    p = pay(lines={})
    assert p["gross"] == 0 and p["warnings"]


def test_negative_net_is_flagged():
    p = pay(lines={"BASIC": 1000}, adjustments=[{"kind": "deduction", "label": "Advance", "amount": 5000}])
    assert p["net_pay"] < 0
    assert any("negative" in w for w in p["warnings"])


def test_lines_round_half_up_to_the_rupee():
    comps = [comp("BASIC", "earning")]
    p = calc.compute_pay(comps, {"BASIC": 1000}, pay_type="salary", exempt=set(),
                         days_in_month=30, paid=Decimal("0.5"))
    assert amounts(p["earnings"])["BASIC"] == 17      # 16.67 -> 17


# ─── days ────────────────────────────────────────────────────────────────────

OCT = dt.date(2026, 10, 1)            # 31 days; 1 Oct 2026 is a Thursday
WEEK = {1, 2, 3, 4, 5}


def days(**kw):
    kw.setdefault("today", dt.date(2026, 10, 31))
    kw.setdefault("joined", None)
    kw.setdefault("holidays", set())
    kw.setdefault("leave_days", {})
    kw.setdefault("weekdays", WEEK)
    return calc.count_days(OCT, **kw)


def all_weekdays():
    return {OCT + dt.timedelta(days=i) for i in range(31)
            if (OCT + dt.timedelta(days=i)).isoweekday() in WEEK}


def test_full_attendance_has_no_lop():
    c = days(present=all_weekdays())
    assert c["days_in_month"] == 31 and c["lop"] == 0
    assert c["present"] == 22 and c["weekly_offs"] == 9


def test_absence_is_lop_but_holidays_and_paid_leave_are_not():
    present = all_weekdays() - {dt.date(2026, 10, 2), dt.date(2026, 10, 5), dt.date(2026, 10, 6),
                                dt.date(2026, 10, 7)}
    c = days(present=present, holidays={dt.date(2026, 10, 2)},
             leave_days={dt.date(2026, 10, 5): "casual", dt.date(2026, 10, 6): "unpaid"})
    assert c["holidays"] == 1 and c["paid_leave"] == 1 and c["unpaid_leave"] == 1
    assert c["absent"] == 1                            # 7 Oct
    assert c["lop"] == 2
    paid, lop = calc.paid_days(c)
    assert (paid, lop) == (29, 2)


def test_days_before_joining_are_not_paid():
    c = days(present=all_weekdays(), joined=dt.date(2026, 10, 15))
    assert c["not_employed"] == 14
    paid, lop = calc.paid_days(c)
    assert paid == 17 and lop == 0


def test_future_days_are_assumed_worked():
    c = days(present=set(), today=dt.date(2026, 10, 1))   # 1 Oct, absent
    assert c["future"] == 30 and c["absent"] == 1


def test_override_replaces_lop_and_cannot_exceed_the_month():
    c = days(present=set())
    assert calc.paid_days(c, Decimal("1.5")) == (Decimal("29.5"), Decimal("1.5"))
    assert calc.paid_days(c, 99)[0] == 0


def test_working_week_spec():
    assert calc.working_weekdays("1,2,3,4,5,6") == {1, 2, 3, 4, 5, 6}
    assert calc.working_weekdays("0,1") == {7, 1}
    assert calc.working_weekdays("") == {1, 2, 3, 4, 5}


def test_period_parsing():
    assert calc.parse_period("2026-02") == dt.date(2026, 2, 1)
    assert calc.month_end(dt.date(2028, 2, 1)) == dt.date(2028, 2, 29)
    with pytest.raises(ValueError):
        calc.parse_period("Oct")


# ─── words ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("amount,words", [
    (0, "Rupees Zero Only"),
    (38000, "Rupees Thirty Eight Thousand Only"),
    (125000, "Rupees One Lakh Twenty Five Thousand Only"),
    (41109.5, "Rupees Forty One Thousand One Hundred Nine and Fifty Paise Only"),
    (12345678, "Rupees One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Only"),
])
def test_rupees_in_words(amount, words):
    assert calc.rupees_in_words(amount) == words
