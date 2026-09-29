"""
Security scoring rules.

The rules are pure functions over a facts dict, which is exactly why they were
written that way — every case here runs without a database or a clock.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import scoring_service as sc
from app.services.scoring_service import Severity, Thresholds

T = sc.DEFAULT_THRESHOLDS


def facts(**overrides) -> dict:
    """A healthy credential. Override one thing per test."""
    base = {
        "now": datetime.now(timezone.utc),
        "kind": "password",
        "has_2fa": True,
        "owner_id": 1,
        "owner_name": "Alice",
        "owner_status": "active",
        "password_age_days": 10,
        "version_count": 1,
        "active_share_count": 2,
        "days_since_access": 3,
        "has_rotation_policy": True,
        "rotation_interval_days": 90,
        "departed_with_access": [],
    }
    base.update(overrides)
    return base


# ─── healthy baseline ────────────────────────────────────────────────────────

def test_a_well_kept_credential_is_healthy():
    assert sc.evaluate(facts()) == []
    assert sc.worst([]) is Severity.HEALTHY


# ─── departed access ─────────────────────────────────────────────────────────

def test_departed_employee_with_access_is_critical():
    found = sc.evaluate(facts(departed_with_access=[
        {"user_id": 7, "name": "Priya Raman", "status": "deactivated"},
    ]))
    codes = {f.code for f in found}
    assert "departed_access" in codes
    assert sc.worst(found) is Severity.CRITICAL


def test_departed_finding_names_the_person():
    found = sc.evaluate(facts(departed_with_access=[
        {"user_id": 7, "name": "Priya Raman", "status": "leaving"},
    ]))
    finding = next(f for f in found if f.code == "departed_access")
    assert "Priya Raman" in finding.detail
    # Revoking alone is not enough — they have already seen it.
    assert "rotate" in finding.action.lower()


def test_many_departed_people_are_summarised():
    people = [{"user_id": i, "name": f"P{i}", "status": "deactivated"}
              for i in range(6)]
    finding = next(
        f for f in sc.evaluate(facts(departed_with_access=people))
        if f.code == "departed_access"
    )
    assert "and 3 more" in finding.detail


def test_departed_owner_is_critical():
    found = sc.evaluate(facts(owner_status="deactivated"))
    assert any(f.code == "owner_departed" for f in found)
    assert sc.worst(found) is Severity.CRITICAL


def test_leaving_counts_as_departed():
    assert any(
        f.code == "owner_departed" for f in sc.evaluate(facts(owner_status="leaving"))
    )


# ─── rotation ────────────────────────────────────────────────────────────────

def test_within_policy_is_fine():
    assert not any(
        f.code == "overdue_rotation"
        for f in sc.evaluate(facts(password_age_days=89, rotation_interval_days=90))
    )


def test_slightly_overdue_is_a_warning():
    finding = next(
        f for f in sc.evaluate(facts(password_age_days=95, rotation_interval_days=90))
        if f.code == "overdue_rotation"
    )
    assert finding.severity is Severity.WARNING


def test_long_overdue_escalates_to_critical():
    """Thirty days past due means nobody is watching — that is the real problem."""
    finding = next(
        f for f in sc.evaluate(facts(password_age_days=125, rotation_interval_days=90))
        if f.code == "overdue_rotation"
    )
    assert finding.severity is Severity.CRITICAL


def test_overdue_boundary_is_exact():
    at = sc.evaluate(facts(password_age_days=90 + T.rotation_overdue_critical_days,
                           rotation_interval_days=90))
    just_under = sc.evaluate(facts(password_age_days=90 + T.rotation_overdue_critical_days - 1,
                                   rotation_interval_days=90))
    assert next(f for f in at if f.code == "overdue_rotation").severity is Severity.CRITICAL
    assert next(f for f in just_under if f.code == "overdue_rotation").severity is Severity.WARNING


def test_age_rule_is_suppressed_when_a_policy_exists():
    """One fact must not produce two findings."""
    found = sc.evaluate(facts(password_age_days=400, has_rotation_policy=True,
                              rotation_interval_days=90))
    codes = {f.code for f in found}
    assert "overdue_rotation" in codes
    assert "password_age" not in codes


def test_age_rule_fires_without_a_policy():
    found = sc.evaluate(facts(password_age_days=200, has_rotation_policy=False,
                              rotation_interval_days=None))
    finding = next(f for f in found if f.code == "password_age")
    assert finding.severity is Severity.WARNING


def test_very_old_password_without_policy_is_critical():
    found = sc.evaluate(facts(password_age_days=400, has_rotation_policy=False,
                              rotation_interval_days=None))
    finding = next(f for f in found if f.code == "password_age")
    assert finding.severity is Severity.CRITICAL


def test_missing_policy_is_flagged():
    found = sc.evaluate(facts(has_rotation_policy=False, rotation_interval_days=None))
    assert any(f.code == "no_rotation_policy" for f in found)


# ─── 2FA ─────────────────────────────────────────────────────────────────────

def test_password_without_2fa_is_a_warning():
    found = sc.evaluate(facts(has_2fa=False))
    finding = next(f for f in found if f.code == "missing_2fa")
    assert finding.severity is Severity.WARNING


@pytest.mark.parametrize("kind", ["api_key", "token", "ssh_key", "certificate"])
def test_2fa_is_not_expected_of_non_passwords(kind):
    """An API key cannot have a second factor. Flagging it would be noise."""
    found = sc.evaluate(facts(kind=kind, has_2fa=False))
    assert not any(f.code == "missing_2fa" for f in found)


# ─── sharing ─────────────────────────────────────────────────────────────────

def test_normal_sharing_is_fine():
    assert not any(
        f.code == "excessive_sharing"
        for f in sc.evaluate(facts(active_share_count=T.excessive_share_count))
    )


def test_excessive_sharing_is_flagged_above_the_threshold():
    found = sc.evaluate(facts(active_share_count=T.excessive_share_count + 1))
    assert any(f.code == "excessive_sharing" for f in found)


def test_sharing_threshold_is_configurable():
    tight = Thresholds(excessive_share_count=2)
    assert any(
        f.code == "excessive_sharing"
        for f in sc.evaluate(facts(active_share_count=3), tight)
    )
    assert not any(
        f.code == "excessive_sharing"
        for f in sc.evaluate(facts(active_share_count=3))
    )


# ─── staleness ───────────────────────────────────────────────────────────────

def test_long_unused_credential_is_flagged():
    found = sc.evaluate(facts(days_since_access=T.unreviewed_days + 1))
    assert any(f.code == "unreviewed" for f in found)


def test_never_accessed_does_not_fire_unreviewed():
    """A credential created a minute ago must not be called abandoned."""
    found = sc.evaluate(facts(days_since_access=None))
    assert not any(f.code == "unreviewed" for f in found)


# ─── severity aggregation ────────────────────────────────────────────────────

def test_worst_wins():
    warn = sc.Finding("a", Severity.WARNING, "t", "d", "x")
    crit = sc.Finding("b", Severity.CRITICAL, "t", "d", "x")
    assert sc.worst([warn]) is Severity.WARNING
    assert sc.worst([warn, crit]) is Severity.CRITICAL
    assert sc.worst([crit, warn]) is Severity.CRITICAL


def test_no_findings_is_healthy():
    assert sc.worst([]) is Severity.HEALTHY


def test_a_single_critical_outranks_many_warnings():
    """Five warnings are not worse than one former employee holding access."""
    findings = [sc.Finding(f"w{i}", Severity.WARNING, "t", "d", "x") for i in range(5)]
    assert sc.worst(findings) is Severity.WARNING
    findings.append(sc.Finding("c", Severity.CRITICAL, "t", "d", "x"))
    assert sc.worst(findings) is Severity.CRITICAL


# ─── contract ────────────────────────────────────────────────────────────────

def test_every_finding_carries_an_action():
    """A finding without a remedy is a complaint, and complaints get dismissed."""
    found = sc.evaluate(facts(
        departed_with_access=[{"user_id": 1, "name": "X", "status": "deactivated"}],
        owner_status="deactivated",
        has_2fa=False,
        has_rotation_policy=False,
        rotation_interval_days=None,
        password_age_days=400,
        active_share_count=20,
        days_since_access=500,
    ))
    assert len(found) >= 6
    for f in found:
        assert f.action and len(f.action) > 10
        assert f.title and f.detail


def test_rule_codes_are_unique():
    codes = [r(facts(
        departed_with_access=[{"user_id": 1, "name": "X", "status": "leaving"}],
        owner_status="leaving", has_2fa=False, has_rotation_policy=False,
        rotation_interval_days=None, password_age_days=400,
        active_share_count=99, days_since_access=999,
    ), T) for r in sc.RULES]
    codes = [c.code for c in codes if c]
    assert len(codes) == len(set(codes))
