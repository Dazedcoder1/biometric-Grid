"""
Audit hash chain and secret scrubbing.

The hashing and scrubbing are pure functions, so they are tested without a
database. Chain behaviour against real rows needs Postgres and is covered by
the integration tests in test_security_integration.py.
"""

from __future__ import annotations

from app.core.audit import _canonical, _scrub, compute_hash

# ─── hashing ─────────────────────────────────────────────────────────────────

def test_hash_is_deterministic():
    payload = {"seq": 1, "action": "auth.login", "actor_id": 7}
    assert compute_hash(payload, None) == compute_hash(payload, None)


def test_hash_ignores_key_order():
    """Verification months later must not depend on dict ordering."""
    a = {"seq": 1, "action": "auth.login", "actor_id": 7}
    b = {"actor_id": 7, "action": "auth.login", "seq": 1}
    assert compute_hash(a, None) == compute_hash(b, None)


def test_any_field_change_changes_the_hash():
    base = {"seq": 1, "action": "auth.login", "actor_id": 7}
    original = compute_hash(base, None)

    for field, new_value in (
        ("seq", 2),
        ("action", "auth.logout"),
        ("actor_id", 8),
    ):
        tampered = dict(base, **{field: new_value})
        assert compute_hash(tampered, None) != original, f"{field} change went undetected"


def test_chain_position_affects_the_hash():
    """Identical content at a different point in the chain hashes differently.

    This is what stops an entry being copied from elsewhere in the log.
    """
    payload = {"seq": 5, "action": "credential.revealed"}
    assert compute_hash(payload, "aaaa") != compute_hash(payload, "bbbb")
    assert compute_hash(payload, None) != compute_hash(payload, "aaaa")


def test_hash_is_sha256_hex():
    h = compute_hash({"seq": 1}, None)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_canonical_form_is_compact_and_sorted():
    out = _canonical({"b": 1, "a": 2})
    assert out == '{"a":2,"b":1}'


# ─── scrubbing ───────────────────────────────────────────────────────────────

def test_scrub_redacts_obvious_secret_keys():
    out = _scrub({
        "password": "hunter2",
        "api_key": "sk-live-abc",
        "token": "ghp_xxx",
        "private_key": "-----BEGIN",
        "plaintext": "secret",
        "username": "alice",
    })
    assert out["password"] == "[redacted]"
    assert out["api_key"] == "[redacted]"
    assert out["token"] == "[redacted]"
    assert out["private_key"] == "[redacted]"
    assert out["plaintext"] == "[redacted]"
    assert out["username"] == "alice"       # innocent key survives


def test_scrub_is_case_insensitive_and_matches_substrings():
    out = _scrub({"UserPassword": "x", "OAuthToken": "y", "DEK_wrapped": "z"})
    assert all(v == "[redacted]" for v in out.values())


def test_scrub_recurses_into_nested_structures():
    out = _scrub({"outer": {"inner": {"password": "hunter2"}}})
    assert out["outer"]["inner"]["password"] == "[redacted]"

    out = _scrub({"items": [{"token": "a"}, {"name": "b"}]})
    assert out["items"][0]["token"] == "[redacted]"
    assert out["items"][1]["name"] == "b"


def test_scrub_stops_at_depth_limit():
    """Guards against a hostile or accidental deeply nested payload."""
    deep = current = {}
    for _ in range(20):
        current["next"] = {}
        current = current["next"]
    current["password"] = "hunter2"

    out = _scrub(deep)
    flat = repr(out)
    assert "hunter2" not in flat


def test_scrub_cannot_catch_secrets_under_innocent_keys():
    """Documents a real limitation rather than pretending it does not exist.

    Key-based screening catches accidents. It cannot tell that a free-text note
    contains a password, which is why callers must not pass secrets at all.
    """
    out = _scrub({"note": "the password is hunter2"})
    assert out["note"] == "the password is hunter2"      # NOT redacted
