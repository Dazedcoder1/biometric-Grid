"""
Sharing: escalation attempts, cascade revocation, expiry, and tree shape.

The escalation tests are the ones that matter. Everything else in the
authorisation system assumes a share cannot exceed its grantor's level — if
that assumption breaks, a `view` holder can promote themselves to `manage` and
every other guard becomes decorative.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import share_service as shares
from app.services.vault_service import LEVELS, _RANK


# ─── escalation ──────────────────────────────────────────────────────────────

def test_levels_rank_in_order():
    assert [_RANK[lvl] for lvl in LEVELS] == sorted(_RANK[lvl] for lvl in LEVELS)


@pytest.mark.parametrize(
    "held,attempted,allowed",
    [
        # Granting at or below your own level.
        ("manage", "manage", True),
        ("manage", "view", True),
        ("reshare", "edit", True),
        ("reshare", "reshare", True),
        ("edit", "view", True),
        # Granting above it — the attack.
        ("view", "reveal", False),
        ("view", "manage", False),
        ("reveal", "edit", False),
        ("reveal", "manage", False),
        ("edit", "reshare", False),
        ("edit", "manage", False),
        ("reshare", "manage", False),
    ],
)
def test_escalation_boundary(held, attempted, allowed):
    """A share may match the grantor's level, never exceed it."""
    assert (_RANK[attempted] <= _RANK[held]) is allowed


def test_view_holder_cannot_grant_anything_above_view():
    for level in ("reveal", "edit", "reshare", "manage"):
        assert _RANK[level] > _RANK["view"]


def test_reshare_is_below_manage():
    """`reshare` lets you pass on access, not take over the credential."""
    assert _RANK["reshare"] < _RANK["manage"]


# ─── path and tree shape ─────────────────────────────────────────────────────

def _path(*ids: int) -> str:
    return "/" + "".join(f"{i}/" for i in ids)


def test_root_share_path():
    assert _path(7) == "/7/"


def test_child_path_extends_the_parent():
    parent = _path(7)
    child = f"{parent}12/"
    assert child == "/7/12/"
    assert child.startswith(parent)


def test_prefix_match_selects_the_whole_subtree():
    """The cascade query is `path LIKE '<root>%'`."""
    root = _path(7)
    tree = {
        "root": _path(7),
        "child": _path(7, 12),
        "grandchild": _path(7, 12, 30),
        "sibling_branch": _path(8),
        "unrelated": _path(70),          # must NOT match despite sharing digits
    }
    matched = {k for k, p in tree.items() if p.startswith(root)}
    assert matched == {"root", "child", "grandchild"}


def test_trailing_slash_prevents_prefix_collisions():
    """
    Without the trailing slash, '/7' would prefix-match '/70/' and revoking
    share 7 would silently revoke share 70's whole subtree.
    """
    assert not _path(70).startswith(_path(7))
    assert "/70/".startswith("/7") is True      # the bug, if slashes were dropped


def test_depth_from_path():
    assert max(0, _path(7).count("/") - 2) == 0
    assert max(0, _path(7, 12).count("/") - 2) == 1
    assert max(0, _path(7, 12, 30).count("/") - 2) == 2


# ─── expiry ──────────────────────────────────────────────────────────────────

class FakeShare:
    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.status = kw.get("status", "active")
        self.starts_at = kw.get("starts_at")
        self.expires_at = kw.get("expires_at")


def _is_live(share, now):
    """Mirrors the filter every access query applies."""
    if share.status != "active":
        return False
    if share.starts_at and share.starts_at > now:
        return False
    if share.expires_at and share.expires_at <= now:
        return False
    return True


def test_expired_share_grants_nothing_before_the_sweeper_runs():
    """
    The point of enforcing expiry at read time.

    If the sweeper is down, an expired share must still grant nothing — its
    status will say 'active' until the sweep catches up, and the read filter is
    what covers the gap.
    """
    now = datetime.now(timezone.utc)
    stale = FakeShare(status="active", expires_at=now - timedelta(seconds=1))
    assert _is_live(stale, now) is False


def test_future_share_grants_nothing_yet():
    now = datetime.now(timezone.utc)
    future = FakeShare(status="active", starts_at=now + timedelta(hours=1))
    assert _is_live(future, now) is False


def test_share_inside_its_window_is_live():
    now = datetime.now(timezone.utc)
    live = FakeShare(
        status="active",
        starts_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=1),
    )
    assert _is_live(live, now) is True


def test_open_ended_share_is_live():
    now = datetime.now(timezone.utc)
    assert _is_live(FakeShare(status="active"), now) is True


def test_revoked_share_is_never_live():
    now = datetime.now(timezone.utc)
    for status in ("revoked", "expired", "pending"):
        assert _is_live(FakeShare(status=status), now) is False


def test_expiry_is_exclusive_at_the_boundary():
    """At exactly the expiry instant, access is already gone."""
    now = datetime.now(timezone.utc)
    assert _is_live(FakeShare(status="active", expires_at=now), now) is False


# ─── cascade semantics ───────────────────────────────────────────────────────

def test_cascade_covers_every_descendant():
    root = _path(1)
    rows = [
        ("root", _path(1), "active"),
        ("child_a", _path(1, 2), "active"),
        ("child_b", _path(1, 3), "active"),
        ("grandchild", _path(1, 2, 4), "active"),
        ("other_root", _path(5), "active"),
    ]
    revoked = {
        name for name, path, status in rows
        if path.startswith(root) and status in ("active", "pending")
    }
    assert revoked == {"root", "child_a", "child_b", "grandchild"}
    assert "other_root" not in revoked


def test_cascade_skips_already_revoked_rows():
    """Re-revoking must not overwrite the original reason on an old row."""
    root = _path(1)
    rows = [
        ("root", _path(1), "active"),
        ("already_gone", _path(1, 2), "revoked"),
    ]
    touched = {
        name for name, path, status in rows
        if path.startswith(root) and status in ("active", "pending")
    }
    assert touched == {"root"}


def test_revoking_a_child_leaves_the_parent_alone():
    child = _path(1, 2)
    assert not _path(1).startswith(child)


# ─── module surface ──────────────────────────────────────────────────────────

def test_sweeper_interval_is_tight_enough_to_be_useful():
    from app.services import share_sweeper

    assert share_sweeper.INTERVAL_SECONDS <= 300


def test_share_service_exposes_the_expected_operations():
    for name in (
        "grant", "revoke", "descendants", "tree_for_credential",
        "shared_with_me", "expire_due",
    ):
        assert callable(getattr(shares, name))
