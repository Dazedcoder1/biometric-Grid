"""
Every audited action must have a label and a category.

This is a source-scanning test rather than a behavioural one, and that is the
point: the failure it catches is an omission, not a bug in running code. An
action added anywhere in the application with no entry in LABELS still works
perfectly — it just surfaces in the audit log viewer, and in the CSV people
hand to auditors, as a raw identifier like `share.escalation_blocked` sitting
among phrases like `revoked a share`. Nothing fails, so nobody notices. That is
how seventeen of the twenty-seven actions came to be unlabelled.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api.routes.vault.activity import (
    CATEGORIES,
    LABELS,
    RESERVED,
    _category,
    _label,
)

APP_DIR = Path(__file__).resolve().parent.parent / "app"

#: `action=` is also a parameter name elsewhere (dependency_service.impact_of
#: takes action="rotate"), so restrict the scan to calls into the audit writer.
AUDIT_CALL = re.compile(r"audit\.record\s*\((?:[^()]|\([^()]*\))*?\)", re.S)
ACTION_ARG = re.compile(r'action\s*=\s*"([a-z_][a-z_.]*)"')


def recorded_actions() -> set[str]:
    found: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for call in AUDIT_CALL.findall(source):
            found.update(ACTION_ARG.findall(call))
    return found


def test_scan_finds_the_audit_calls():
    """Guard the guard: a regex that silently matches nothing proves nothing."""
    actions = recorded_actions()
    assert len(actions) > 15, f"only found {len(actions)} actions — has the scan broken?"
    assert "credential.revealed" in actions


def test_every_recorded_action_has_a_label():
    missing = sorted(recorded_actions() - set(LABELS))
    assert not missing, (
        "These actions are written to the audit log but have no label in "
        f"activity.LABELS, so they reach the viewer as raw identifiers: {missing}"
    )


def test_every_recorded_action_has_a_known_category():
    uncategorised = sorted(
        a for a in recorded_actions() if a.split(".", 1)[0] not in CATEGORIES
    )
    assert not uncategorised, (
        f"No category for the namespace of: {uncategorised}. Add it to "
        "activity.CATEGORIES or the viewer groups them under 'other'."
    )


def test_labels_do_not_describe_actions_nobody_records():
    """
    A label for an action that is never written is a claim the system makes
    about behaviour it does not have — someone reading the map sees a feature.
    Two are deliberate (activity.RESERVED); anything else is an action that was
    renamed, or a feature dropped with its label left behind.
    """
    orphans = sorted(set(LABELS) - recorded_actions() - RESERVED)
    assert not orphans, (
        f"Labelled but never recorded: {orphans}. Either the action was "
        "renamed, or the feature was dropped and the label outlived it. If it "
        "is genuinely planned, add it to activity.RESERVED with a reason."
    )


def test_reserved_labels_are_still_unwritten():
    """
    The other direction: once something starts recording a reserved action, it
    should leave RESERVED. Otherwise the set grows into a list of exceptions
    nobody rechecks.
    """
    now_live = sorted(RESERVED & recorded_actions())
    assert not now_live, (
        f"{now_live} are now recorded — remove them from activity.RESERVED."
    )


@pytest.mark.parametrize("action", sorted(LABELS))
def test_labels_are_readable(action):
    label = LABELS[action]
    assert label, f"{action} has an empty label"
    # A label containing a dot is almost certainly a copied identifier.
    assert "." not in label, f"{action} label looks like an identifier: {label!r}"
    assert "_" not in label, f"{action} label still has underscores: {label!r}"


def test_unknown_action_degrades_to_something_readable():
    assert _label("widget.frobnicated_twice") == "frobnicated twice"
    assert _label("bare") == "bare"
    assert _category("widget.frobnicated") == "other"


def test_known_action_categories():
    assert _category("credential.revealed") == "credential"
    assert _category("share.granted") == "access"
    assert _category("mfa.verified") == "auth"
    assert _category("audit.exported") == "audit"
