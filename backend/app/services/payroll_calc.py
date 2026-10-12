"""
Payroll arithmetic. Pure functions: no database, no clock, no I/O — every rule
here is tested directly in tests/test_payroll_calc.py.

Money is Decimal throughout and rounded once per payslip line, half-up to the
rupee, which is how Indian payslips are printed. Reimbursements keep their
paise: they repay an exact bill.

Days
  Paid days = calendar days in the month − days before joining − LOP days.
  LOP (loss of pay) = working days with no attendance and no approved paid
  leave, plus approved unpaid leave. Weekly offs and holidays are paid. Days
  after today are assumed worked, so a month can be previewed before it ends.
  The admin can replace the LOP figure for anyone before the month closes.

Components (all defined by the organisation; none are built in)
  fixed    the monthly figure from the person's salary structure, scaled by
           paid days when `prorate` is on.
  percent  rate% of a base: the earnings listed in base_codes, or GROSS.
           The base is capped at wage_ceiling (PF: 15,000), and the component
           applies only while gross is within gross_limit (ESI: 21,000).
           employer_rate adds the employer's share, shown but not deducted.
  slab     a flat amount chosen by gross pay (Professional Tax):
           [{"upto": 15000, "amount": 0}, {"upto": null, "amount": 200}]
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
HUNDRED = Decimal("100")
UNPAID_LEAVE_TYPES = frozenset({"unpaid", "lwp", "lop"})
KINDS = ("earning", "deduction")
CALCS = ("fixed", "percent", "slab")
APPLIES_TO = ("all", "salary", "stipend")


def D(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return ZERO


def rupees(value) -> Decimal:
    return D(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def paise(value) -> Decimal:
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value) -> float:
    """For JSON. Always a 2-decimal figure, computed in Decimal first."""
    return float(paise(value))


# ─── periods ─────────────────────────────────────────────────────────────────

def parse_period(raw: str) -> dt.date:
    """'2026-10' -> 2026-10-01."""
    try:
        year, month = (int(x) for x in raw.split("-")[:2])
        return dt.date(year, month, 1)
    except (ValueError, AttributeError):
        raise ValueError("Period must look like 2026-10.") from None


def month_end(period: dt.date) -> dt.date:
    return period.replace(day=calendar.monthrange(period.year, period.month)[1])


def period_label(period: dt.date) -> str:
    return period.strftime("%B %Y")


def working_weekdays(spec: str | None) -> set[int]:
    """'1,2,3,4,5' -> ISO weekdays {1..5}. 0 and 7 both mean Sunday."""
    out = set()
    for part in (spec or "1,2,3,4,5").split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part)
            out.add(7 if n == 0 else n)
    return out or {1, 2, 3, 4, 5}


# ─── days ────────────────────────────────────────────────────────────────────

def count_days(
    period: dt.date,
    *,
    today: dt.date,
    joined: dt.date | None,
    holidays: set[dt.date],
    leave_days: dict[dt.date, str],
    present: set[dt.date],
    weekdays: set[int],
) -> dict:
    """Classify every day of the month for one person."""
    end = month_end(period)
    c = {"days_in_month": end.day, "not_employed": 0, "weekly_offs": 0, "holidays": 0, "present": 0,
         "paid_leave": 0, "unpaid_leave": 0, "absent": 0, "future": 0}
    d = period
    while d <= end:
        if joined and d < joined:
            c["not_employed"] += 1
        elif d > today:
            c["future"] += 1
        elif d.isoweekday() not in weekdays:
            c["weekly_offs"] += 1
        elif d in holidays:
            c["holidays"] += 1
        elif d in present:
            c["present"] += 1
        elif d in leave_days:
            if leave_days[d].lower() in UNPAID_LEAVE_TYPES:
                c["unpaid_leave"] += 1
            else:
                c["paid_leave"] += 1
        else:
            c["absent"] += 1
        d += dt.timedelta(days=1)
    c["lop"] = c["absent"] + c["unpaid_leave"]
    return c


def paid_days(days: dict, lop_override=None) -> tuple[Decimal, Decimal]:
    """(paid days, LOP days used). The override replaces computed LOP only."""
    lop = D(lop_override) if lop_override is not None else D(days["lop"])
    available = D(days["days_in_month"]) - D(days["not_employed"])
    lop = max(ZERO, min(lop, available))
    return available - lop, lop


# ─── pay ─────────────────────────────────────────────────────────────────────

def _codes(raw: str | None) -> list[str]:
    return [c.strip().upper() for c in (raw or "").split(",") if c.strip()]


def slab_amount(slabs, gross: Decimal) -> Decimal:
    """The first slab whose `upto` covers gross; `upto: null` is the top slab."""
    for slab in sorted(slabs or [], key=lambda s: (s.get("upto") is None, D(s.get("upto")))):
        upto = slab.get("upto")
        if upto is None or gross <= D(upto):
            return D(slab.get("amount"))
    return ZERO


def compute_pay(
    components: list[dict],
    lines: dict,
    *,
    pay_type: str,
    exempt: set[str],
    days_in_month: int,
    paid: Decimal,
    adjustments: list[dict] | None = None,
    reimbursements: list[dict] | None = None,
) -> dict:
    """One person's month. Returns lines, totals and any warnings."""
    factor = (D(paid) / D(days_in_month)) if days_in_month else ZERO
    factor = max(ZERO, min(factor, Decimal(1)))
    lines = {str(k).upper(): D(v) for k, v in (lines or {}).items()}
    exempt = {e.upper() for e in exempt}
    warnings: list[str] = []

    applicable = [
        c for c in sorted(components, key=lambda c: (c.get("sort_order", 100), c["code"]))
        if c.get("active", True)
        and c.get("applies_to", "all") in ("all", pay_type)
        and c["code"].upper() not in exempt
    ]

    earned: dict[str, Decimal] = {}
    earnings: list[dict] = []

    def add_earning(code, name, amount, statutory=False):
        amount = rupees(amount)
        if amount:
            earned[code] = earned.get(code, ZERO) + amount
            earnings.append({"code": code, "name": name, "amount": money(amount), "statutory": statutory})

    # Fixed earnings first, then anything computed from them.
    for c in applicable:
        if c["kind"] == "earning" and c["calc"] == "fixed":
            full = lines.get(c["code"].upper(), ZERO)
            add_earning(c["code"], c["name"], full * factor if c.get("prorate", True) else full,
                        c.get("is_statutory", False))
    for c in applicable:
        if c["kind"] == "earning" and c["calc"] == "percent":
            codes = _codes(c.get("base_codes"))
            if not codes or "GROSS" in codes:
                base = sum(earned.values(), ZERO)      # the fixed earnings so far
            else:
                base = sum((earned.get(x, ZERO) for x in codes), ZERO)
            if c.get("wage_ceiling") is not None:
                base = min(base, D(c["wage_ceiling"]))
            add_earning(c["code"], c["name"], base * D(c.get("rate")) / HUNDRED, c.get("is_statutory", False))
    for c in applicable:
        if c["kind"] == "earning" and c["calc"] == "slab":
            add_earning(c["code"], c["name"], slab_amount(c.get("slabs"), sum(earned.values(), ZERO)),
                        c.get("is_statutory", False))
    for a in adjustments or []:
        if a.get("kind") == "earning":
            amount = rupees(a.get("amount"))
            if amount:
                earnings.append({"code": "ADJ", "name": a.get("label") or "Adjustment",
                                 "amount": money(amount), "adjustment": True})

    gross = sum((D(e["amount"]) for e in earnings), ZERO)

    deductions: list[dict] = []
    employer: list[dict] = []
    for c in applicable:
        if c["kind"] != "deduction":
            continue
        if c.get("gross_limit") is not None and gross > D(c["gross_limit"]):
            continue                                   # e.g. ESI above 21,000
        employer_amount = ZERO
        if c["calc"] == "fixed":
            full = lines.get(c["code"].upper(), ZERO)
            amount = full * factor if c.get("prorate", True) else full
        elif c["calc"] == "percent":
            codes = _codes(c.get("base_codes"))
            if not codes or "GROSS" in codes:
                base = gross
            else:
                base = sum((earned.get(x, ZERO) for x in codes), ZERO)
            if c.get("wage_ceiling") is not None:
                base = min(base, D(c["wage_ceiling"]))
            amount = base * D(c.get("rate")) / HUNDRED
            employer_amount = base * D(c.get("employer_rate")) / HUNDRED
        else:
            amount = slab_amount(c.get("slabs"), gross)
        amount = rupees(amount)
        if amount:
            deductions.append({"code": c["code"], "name": c["name"], "amount": money(amount),
                               "statutory": c.get("is_statutory", False)})
        employer_amount = rupees(employer_amount)
        if employer_amount:
            employer.append({"code": c["code"], "name": f'{c["name"]} (employer)',
                             "amount": money(employer_amount)})
    for a in adjustments or []:
        if a.get("kind") == "deduction":
            amount = rupees(a.get("amount"))
            if amount:
                deductions.append({"code": "ADJ", "name": a.get("label") or "Adjustment",
                                   "amount": money(amount), "adjustment": True})

    total_deductions = sum((D(x["amount"]) for x in deductions), ZERO)
    reimb = [{"id": r.get("id"), "name": r.get("category") or "Reimbursement",
              "amount": money(paise(r.get("amount")))} for r in reimbursements or []]
    reimb_total = sum((D(r["amount"]) for r in reimb), ZERO)
    net = gross - total_deductions + reimb_total

    if not lines:
        warnings.append("No salary structure in force for this month.")
    if net < 0:
        warnings.append("Deductions exceed pay: net pay is negative.")

    return {
        "earnings": earnings,
        "deductions": deductions,
        "employer_contributions": employer,
        "reimbursements": reimb,
        "gross": money(gross),
        "total_deductions": money(total_deductions),
        "reimbursement_total": money(reimb_total),
        "net_pay": money(net),
        "employer_total": money(sum((D(x["amount"]) for x in employer), ZERO)),
        "warnings": warnings,
    }


# ─── amount in words (Indian numbering) ──────────────────────────────────────

_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _two(n: int) -> str:
    return _ONES[n] if n < 20 else (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))


def _three(n: int) -> str:
    h, rest = divmod(n, 100)
    parts = []
    if h:
        parts.append(_ONES[h] + " Hundred")
    if rest:
        parts.append(_two(rest))
    return " ".join(parts)


def rupees_in_words(amount) -> str:
    """53,250.50 -> 'Rupees Fifty Three Thousand Two Hundred Fifty and Fifty Paise Only'."""
    value = paise(amount)
    negative = value < 0
    value = abs(value)
    whole = int(value)
    p = int((value - whole) * 100)
    if whole == 0:
        words = "Zero"
    else:
        parts = []
        crore, whole = divmod(whole, 10_000_000)
        lakh, whole = divmod(whole, 100_000)
        thousand, whole = divmod(whole, 1000)
        if crore:
            parts.append((_three(crore) if crore < 1000 else f"{crore:,}") + " Crore")
        if lakh:
            parts.append(_two(lakh) + " Lakh")
        if thousand:
            parts.append(_two(thousand) + " Thousand")
        if whole:
            parts.append(_three(whole))
        words = " ".join(parts)
    out = ("Minus " if negative else "") + "Rupees " + words
    if p:
        out += f" and {_two(p)} Paise"
    return out + " Only"
