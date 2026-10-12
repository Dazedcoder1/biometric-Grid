"""
The Audit Log is split into separate logs. Every entry must be reachable from
some tab, the tabs must not overlap (apart from Security alerts, which cuts
across them), and "views & downloads" must mean what it says.
"""

from __future__ import annotations

import pytest

from app.api.routes.vault import activity as A


def test_every_category_belongs_to_exactly_one_log():
    owners: dict[str, list[str]] = {}
    for name, spec in A.LOGS.items():
        for cat in spec["categories"]:
            owners.setdefault(cat, []).append(name)
    for cat in set(A.CATEGORIES.values()) | {"other"}:
        assert len(owners.get(cat, [])) == 1, f"category {cat!r} is in {owners.get(cat)}"


@pytest.mark.parametrize("action,log", [
    ("auth.signed_in", "signins"), ("mfa.enrolled", "signins"),
    ("user.password_reset", "people"), ("user.hr_granted", "people"),
    ("leave.approved", "attendance"), ("attendance.web_sign_in", "attendance"),
    ("payroll.run_approved", "payroll"), ("reimbursement.approved", "payroll"),
    ("letter.issued", "documents"), ("policy.acknowledged", "documents"),
    ("credential.revealed", "vault"), ("share.granted", "vault"), ("system.moved", "vault"),
    ("device.registered", "devices"), ("task.created", "tasks"),
    ("organisation.created", "organisation"), ("audit.exported", "organisation"),
    ("something.unheard_of", "organisation"),
])
def test_actions_land_in_the_right_log(action, log):
    assert A.log_of(action) == log


def test_every_labelled_action_has_a_tab():
    for action in A.LABELS:
        assert A.log_of(action) in A.LOGS


@pytest.mark.parametrize("action,read", [
    ("letter.viewed", True), ("letter.downloaded", True), ("payroll.payslip_downloaded", True),
    ("payroll.register_exported", True), ("audit.exported", True),
    ("credential.revealed", True), ("credential.revealed_by_admin", True),
    ("payroll.run_approved", False), ("letter.issued", False), ("auth.signed_in", False),
    ("credential.rotated", False), ("policy.acknowledged", False),
])
def test_views_and_downloads(action, read):
    assert A.is_read(action) is read


def test_unknown_log_matches_nothing():
    # A typo in the tab name must show an empty log, not everything.
    cond = A.log_condition("nonsense")
    assert "IS NULL" in str(cond)
