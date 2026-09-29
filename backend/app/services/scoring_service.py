"""
Credential security scoring.

A rules engine, not a points total. Each rule looks at one credential and
either fires or does not; the credential's severity is the worst severity among
the rules that fired. Healthy means nothing fired.

Why not a numeric score out of 100: a number invites tuning the weights until
the dashboard looks green, and it hides *why* something is bad behind an
arithmetic result. "Three findings, one Critical: a former employee still has
access" is actionable. "Security score: 62" is not.

Every threshold is configurable per tenant — see `Thresholds`. The defaults are
deliberately conservative; an organisation that rotates quarterly should say so
rather than living with a permanent sea of warnings, because a dashboard that
is always red gets ignored, and then a real finding goes unnoticed.

Scoring logic is documented for humans in docs/SCORING.md. Keep the two in step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credentials import (
    Credential,
    CredentialVersion,
    RotationPolicy,
    Share,
    TeamMember,
)
from app.models.domain import User


class Severity(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


#: Worst-wins ordering.
_ORDER = {Severity.HEALTHY: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


@dataclass(frozen=True)
class Thresholds:
    """
    Tunable inputs to the rules. One place, so nothing is hardcoded at a call
    site where nobody will find it.
    """

    #: A secret older than this is stale even without a rotation policy.
    password_age_warning_days: int = 180
    password_age_critical_days: int = 365

    #: How far past a rotation policy's due date before it escalates.
    rotation_overdue_critical_days: int = 30

    #: Active shares above this count suggest a credential that should be a
    #: service account rather than a shared password.
    excessive_share_count: int = 8

    #: No reveal, no edit, nobody looking at it. Possibly abandoned.
    unreviewed_days: int = 365

    #: Kinds where "no second factor" is a meaningful finding. An API key
    #: cannot have 2FA, so flagging one would be noise.
    kinds_expecting_2fa: tuple[str, ...] = ("password",)


DEFAULT_THRESHOLDS = Thresholds()


@dataclass
class Finding:
    code: str
    severity: Severity
    title: str
    detail: str
    #: What to do about it. A finding without a remedy is just a complaint.
    action: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "title": self.title,
            "detail": self.detail,
            "action": self.action,
        }


@dataclass
class Assessment:
    credential_id: int
    name: str
    severity: Severity
    findings: list[Finding] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "credential_id": self.credential_id,
            "name": self.name,
            "severity": self.severity.value,
            "findings": [f.as_dict() for f in self.findings],
            **self.facts,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Facts
# ─────────────────────────────────────────────────────────────────────────────


async def gather_facts(db: AsyncSession, credential: Credential) -> dict:
    """
    Everything the rules need, collected once.

    Deliberately separate from the rules themselves: the rules become pure
    functions over a dict, which is why they can be tested without a database.
    """
    now = datetime.now(timezone.utc)

    last_rotation = (
        await db.execute(
            select(func.max(CredentialVersion.created_at)).where(
                CredentialVersion.credential_id == credential.id
            )
        )
    ).scalar_one_or_none()

    version_count = (
        await db.execute(
            select(func.count(CredentialVersion.id)).where(
                CredentialVersion.credential_id == credential.id
            )
        )
    ).scalar_one()

    active_shares = (
        await db.execute(
            select(func.count(Share.id)).where(
                Share.credential_id == credential.id, Share.status == "active"
            )
        )
    ).scalar_one()

    policy = (
        await db.execute(
            select(RotationPolicy).where(
                RotationPolicy.enabled.is_(True),
                (RotationPolicy.credential_id == credential.id)
                | (RotationPolicy.rack_id == credential.rack_id),
            ).order_by(RotationPolicy.credential_id.desc().nullslast())
        )
    ).scalars().first()

    # Anyone with live access whose employment has ended. Covers both direct
    # shares and team membership, because leaving a company does not remove you
    # from a team automatically.
    team_ids = select(TeamMember.team_id).where(TeamMember.user_id == User.id)
    departed = (
        await db.execute(
            select(User.id, User.name, User.employment_status)
            .join(
                Share,
                (Share.grantee_user_id == User.id)
                | (Share.grantee_team_id.in_(team_ids)),
            )
            .where(
                Share.credential_id == credential.id,
                Share.status == "active",
                User.employment_status.in_(("leaving", "deactivated")),
            )
            .distinct()
        )
    ).all()

    owner = (
        await db.execute(select(User).where(User.id == credential.owner_id))
    ).scalars().first()

    def _aware(value):
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    last_rotation = _aware(last_rotation) or _aware(credential.created_at)
    last_accessed = _aware(credential.last_accessed_at)

    return {
        "now": now,
        "kind": credential.kind,
        "has_2fa": credential.has_2fa,
        "owner_id": credential.owner_id,
        "owner_name": owner.name if owner else None,
        "owner_status": owner.employment_status if owner else None,
        "password_age_days": (now - last_rotation).days if last_rotation else None,
        "last_rotated_at": last_rotation,
        "version_count": version_count,
        "active_share_count": active_shares,
        "last_accessed_at": last_accessed,
        "days_since_access": (now - last_accessed).days if last_accessed else None,
        "has_rotation_policy": policy is not None,
        "rotation_interval_days": policy.interval_days if policy else None,
        "departed_with_access": [
            {"user_id": uid, "name": name, "status": status}
            for uid, name, status in departed
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rules
# ─────────────────────────────────────────────────────────────────────────────
# Each takes (facts, thresholds) and returns a Finding or None. Pure, so they
# are tested directly without a database.


def rule_departed_access(f: dict, t: Thresholds) -> Finding | None:
    people = f.get("departed_with_access") or []
    if not people:
        return None
    names = ", ".join(p["name"] or f"user #{p['user_id']}" for p in people[:3])
    more = f" and {len(people) - 3} more" if len(people) > 3 else ""
    return Finding(
        code="departed_access",
        severity=Severity.CRITICAL,
        title="A former employee still has access",
        detail=f"{names}{more} " + ("has" if len(people) == 1 else "have")
               + " an active share but no longer works here.",
        action="Revoke their access, then rotate the secret — they have already seen it.",
    )


def rule_owner_departed(f: dict, t: Thresholds) -> Finding | None:
    if f.get("owner_status") in ("leaving", "deactivated"):
        return Finding(
            code="owner_departed",
            severity=Severity.CRITICAL,
            title="The owner has left",
            detail=f"{f.get('owner_name') or 'The owner'} is marked "
                   f"{f['owner_status']} but still owns this credential.",
            action="Transfer ownership to someone who can maintain it.",
        )
    return None


def rule_overdue_rotation(f: dict, t: Thresholds) -> Finding | None:
    interval = f.get("rotation_interval_days")
    age = f.get("password_age_days")
    if not interval or age is None or age <= interval:
        return None

    overdue = age - interval
    critical = overdue >= t.rotation_overdue_critical_days
    return Finding(
        code="overdue_rotation",
        severity=Severity.CRITICAL if critical else Severity.WARNING,
        title=f"Rotation overdue by {overdue} days",
        detail=f"Policy says every {interval} days; this is {age} days old.",
        action="Rotate the secret. Check the dependency map first for what uses it.",
    )


def rule_password_age(f: dict, t: Thresholds) -> Finding | None:
    """Only fires without a policy — otherwise overdue_rotation covers it."""
    if f.get("has_rotation_policy"):
        return None
    age = f.get("password_age_days")
    if age is None or age < t.password_age_warning_days:
        return None

    critical = age >= t.password_age_critical_days
    return Finding(
        code="password_age",
        severity=Severity.CRITICAL if critical else Severity.WARNING,
        title=f"Unchanged for {age} days",
        detail="No rotation policy applies, and the secret has not been "
               f"changed in {age} days.",
        action="Rotate it, and set a rotation policy so this is tracked.",
    )


def rule_missing_2fa(f: dict, t: Thresholds) -> Finding | None:
    if f.get("kind") not in t.kinds_expecting_2fa:
        return None
    if f.get("has_2fa"):
        return None
    return Finding(
        code="missing_2fa",
        severity=Severity.WARNING,
        title="No second factor",
        detail="This account password is not protected by 2FA, so the password "
               "alone is enough to use it.",
        action="Enable 2FA on the account, then tick the 2FA box here.",
    )


def rule_excessive_sharing(f: dict, t: Thresholds) -> Finding | None:
    count = f.get("active_share_count", 0)
    if count <= t.excessive_share_count:
        return None
    return Finding(
        code="excessive_sharing",
        severity=Severity.WARNING,
        title=f"Shared with {count} people",
        detail=f"Above the threshold of {t.excessive_share_count}. A secret "
               "this widely known cannot be meaningfully rotated or attributed.",
        action="Review who still needs it, or replace it with per-person "
               "service accounts.",
    )


def rule_no_rotation_policy(f: dict, t: Thresholds) -> Finding | None:
    if f.get("has_rotation_policy"):
        return None
    return Finding(
        code="no_rotation_policy",
        severity=Severity.WARNING,
        title="No rotation policy",
        detail="Nothing will prompt anyone to change this secret.",
        action="Attach a rotation policy to this credential or its rack.",
    )


def rule_unreviewed(f: dict, t: Thresholds) -> Finding | None:
    days = f.get("days_since_access")
    if days is None:
        # Never accessed since the feature started recording it. Not a finding
        # on its own — a brand-new credential would trip it — so age carries it.
        return None
    if days < t.unreviewed_days:
        return None
    return Finding(
        code="unreviewed",
        severity=Severity.WARNING,
        title=f"Not touched in {days} days",
        detail="Nobody has revealed or edited this in a long time. It may "
               "belong to a system that no longer exists.",
        action="Confirm it is still needed, or delete it.",
    )


#: Order matters only for presentation — the most serious first.
RULES = (
    rule_departed_access,
    rule_owner_departed,
    rule_overdue_rotation,
    rule_password_age,
    rule_missing_2fa,
    rule_excessive_sharing,
    rule_no_rotation_policy,
    rule_unreviewed,
)


def evaluate(facts: dict, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> list[Finding]:
    """Run every rule. Pure — no database, no clock beyond what facts carry."""
    found = [rule(facts, thresholds) for rule in RULES]
    return [f for f in found if f is not None]


def worst(findings: list[Finding]) -> Severity:
    """Worst-wins. No findings means healthy."""
    if not findings:
        return Severity.HEALTHY
    return max((f.severity for f in findings), key=lambda s: _ORDER[s])


async def assess(
    db: AsyncSession, credential: Credential,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Assessment:
    facts = await gather_facts(db, credential)
    findings = evaluate(facts, thresholds)

    # `now` is an implementation detail of the rules, not something an API
    # consumer needs.
    facts.pop("now", None)

    return Assessment(
        credential_id=credential.id,
        name=credential.name,
        severity=worst(findings),
        findings=findings,
        facts=facts,
    )
