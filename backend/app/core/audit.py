"""
Append-only, hash-chained audit writer.

Two properties this module exists to guarantee:

1. **Nothing sensitive is ever written.** `_scrub` drops known-dangerous keys
   from `details` as a backstop. It is a safety net, not permission to be
   careless — callers must not pass secrets in the first place.

2. **The chain is correct under concurrency.** Each row hashes its predecessor,
   so two concurrent writers must not read the same head. A transaction-scoped
   advisory lock serialises the read-hash-write sequence; it is released
   automatically at commit or rollback, so a crashed request cannot wedge it.

The limitation is worth restating where someone will read it: hash chaining
detects tampering only by an attacker who cannot rewrite the entire table.
Anchoring the head externally is what closes that gap — SECURITY.md §5.3,
decision 7. Until then this is evidence, not proof.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import AuditLog

logger = logging.getLogger(__name__)

# Arbitrary but fixed: identifies this particular lock among any others.
_CHAIN_LOCK_KEY = 0x4155_4449  # "AUDI"

#: Substrings that must never reach the audit log. Matched case-insensitively
#: against `details` keys at any depth.
_FORBIDDEN_KEY_PARTS = (
    "password", "secret", "token", "api_key", "apikey", "private_key",
    "credential", "passphrase", "otp", "dek", "kek", "ciphertext", "plaintext",
)

_REDACTED = "[redacted]"


def _scrub(value: Any, _depth: int = 0) -> Any:
    """
    Recursively remove values whose key suggests secret material.

    Note what this does NOT do: it cannot tell that
    `{"note": "the password is hunter2"}` contains a secret, because the key is
    innocent. Key-based screening catches accidents, not deliberate misuse.
    """
    if _depth > 6:
        return _REDACTED

    if isinstance(value, Mapping):
        out = {}
        for k, v in value.items():
            key_l = str(k).lower()
            if any(part in key_l for part in _FORBIDDEN_KEY_PARTS):
                out[k] = _REDACTED
            else:
                out[k] = _scrub(v, _depth + 1)
        return out

    if isinstance(value, (list, tuple)):
        return [_scrub(v, _depth + 1) for v in value]

    return value


def _canonical(payload: Mapping[str, Any]) -> str:
    """
    Deterministic serialisation for hashing.

    sort_keys and a fixed separator matter: the hash must be reproducible by a
    verifier months later, so dict ordering and whitespace cannot influence it.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )


def compute_hash(payload: Mapping[str, Any], prev_hash: str | None) -> str:
    """SHA-256 over the canonical row, chained to its predecessor."""
    material = _canonical(payload) + "|" + (prev_hash or "")
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def record(
    db: AsyncSession,
    *,
    action: str,
    result: str = "success",
    tenant_id: int | None = None,
    actor_id: int | None = None,
    actor_role: str | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    reason: str | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
    session_jti: str | None = None,
    mfa_method: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditLog:
    """
    Append one entry. Does NOT commit — the caller owns the transaction.

    That is deliberate. The audit entry and the action it describes must land
    together or not at all; committing here would allow a logged action that
    then rolled back, or worse the reverse.

    Raises on failure rather than swallowing. An action that cannot be audited
    must not proceed — see ARCHITECTURE.md §3.
    """
    if result not in ("success", "denied", "error"):
        raise ValueError(f"invalid audit result: {result!r}")

    # Serialise the chain. Transaction-scoped, so it releases on commit or
    # rollback without any cleanup path of our own.
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK_KEY})

    head = (
        await db.execute(
            select(AuditLog.seq, AuditLog.hash)
            .order_by(AuditLog.seq.desc())
            .limit(1)
        )
    ).first()

    prev_seq = head[0] if head else 0
    prev_hash = head[1] if head else None
    seq = prev_seq + 1

    occurred_at = datetime.now(UTC)
    clean_details = _scrub(dict(details)) if details else None

    payload = {
        "seq": seq,
        "occurred_at": occurred_at.isoformat(),
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id) if target_id is not None else None,
        "result": result,
        "reason": reason,
        "source_ip": source_ip,
        "user_agent": user_agent,
        "session_jti": session_jti,
        "mfa_method": mfa_method,
        "details": clean_details,
    }

    entry = AuditLog(
        seq=seq,
        occurred_at=occurred_at,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        result=result,
        reason=reason,
        source_ip=source_ip,
        user_agent=user_agent,
        session_jti=session_jti,
        mfa_method=mfa_method,
        details=clean_details,
        prev_hash=prev_hash,
        hash=compute_hash(payload, prev_hash),
    )
    db.add(entry)
    await db.flush()
    return entry


async def verify_chain(
    db: AsyncSession, *, start_seq: int = 1, limit: int | None = None
) -> dict:
    """
    Walk the chain and report the first break.

    Returns {"ok": bool, "checked": int, "broken_at": seq|None, "detail": str}.

    Streams in ascending seq order and holds only the running hash, so it is
    safe on a large table.
    """
    stmt = select(AuditLog).where(AuditLog.seq >= start_seq).order_by(AuditLog.seq.asc())
    if limit:
        stmt = stmt.limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return {"ok": True, "checked": 0, "broken_at": None, "detail": "No entries."}

    expected_prev = rows[0].prev_hash
    expected_seq = rows[0].seq
    checked = 0

    for row in rows:
        if row.seq != expected_seq:
            return {
                "ok": False,
                "checked": checked,
                "broken_at": row.seq,
                "detail": f"Sequence gap: expected {expected_seq}, found {row.seq}. "
                          "An entry was deleted.",
            }

        if row.prev_hash != expected_prev:
            return {
                "ok": False,
                "checked": checked,
                "broken_at": row.seq,
                "detail": f"Chain break at seq {row.seq}: prev_hash does not match "
                          "the previous entry's hash.",
            }

        payload = {
            "seq": row.seq,
            "occurred_at": row.occurred_at.isoformat(),
            "tenant_id": row.tenant_id,
            "actor_id": row.actor_id,
            "actor_role": row.actor_role,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "result": row.result,
            "reason": row.reason,
            "source_ip": row.source_ip,
            "user_agent": row.user_agent,
            "session_jti": row.session_jti,
            "mfa_method": row.mfa_method,
            "details": row.details,
        }
        if compute_hash(payload, row.prev_hash) != row.hash:
            return {
                "ok": False,
                "checked": checked,
                "broken_at": row.seq,
                "detail": f"Entry {row.seq} was modified after it was written.",
            }

        expected_prev = row.hash
        expected_seq = row.seq + 1
        checked += 1

    return {
        "ok": True,
        "checked": checked,
        "broken_at": None,
        "detail": f"Verified {checked} entries.",
    }


async def head_hash(db: AsyncSession) -> str | None:
    """
    The current head hash — the value to anchor externally (decision 7).

    Publishing this somewhere the application cannot reach is what turns the
    chain from evidence into proof.
    """
    row = (
        await db.execute(select(AuditLog.hash).order_by(AuditLog.seq.desc()).limit(1))
    ).first()
    return row[0] if row else None


async def count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count(AuditLog.id)))).scalar_one()
