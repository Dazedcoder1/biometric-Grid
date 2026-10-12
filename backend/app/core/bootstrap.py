"""
Startup housekeeping for the platform operator's account.

Two things, both run once per server start, both safe to run every time:

1. Make sure the configured Super Admin exists.
   With SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD in the server's .env, a
   fresh deployment can be signed into straight away — no shelling into the
   container to run create_super_admin.py.

   It only ever CREATES. If the account already exists it is left alone,
   password included, so a password changed after first sign-in is never
   reset back to whatever is in .env on the next restart. The account is
   created with must_change_password set: the .env value is a way in, not a
   password to keep using.

2. Switch off the demo Super Admin.
   seed_demo_data.py creates super@demo.local with the password Demo@1234,
   which is written in this repository. Once a real Super Admin is
   configured, that account is deactivated if it exists — anyone who has
   seen the code could otherwise sign in with full control of every
   organisation.

Neither step can stop the server starting. A database that is down, or an
account that cannot be created, is logged and skipped.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.domain import User

logger = logging.getLogger(__name__)

DEMO_SUPER_ADMIN = "super@demo.local"


def password_problem(pw: str) -> str | None:
    """Same bar as create_super_admin.py: this account can reach everything."""
    if len(pw) < 12:
        return "must be at least 12 characters"
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "must contain a letter and a number"
    return None


async def ensure_super_admin(db) -> str:
    """Create the configured Super Admin if missing. Returns what it did."""
    email = (settings.SUPER_ADMIN_EMAIL or "").strip().lower()
    password = settings.SUPER_ADMIN_PASSWORD or ""
    if not email or not password:
        return "not configured"

    problem = password_problem(password)
    if problem:
        logger.error("SUPER_ADMIN_PASSWORD %s — Super Admin not created.", problem)
        return "weak password"

    existing = (
        await db.execute(select(User).where(func.lower(User.email) == email))
    ).scalars().first()
    if existing:
        if existing.role != "super_admin":
            logger.error(
                "SUPER_ADMIN_EMAIL %s belongs to a %s account — not turning it into a "
                "Super Admin. Use a different address.", email, existing.role,
            )
            return "email taken"
        return "exists"

    db.add(User(
        tenant_id=None,
        name=(settings.SUPER_ADMIN_NAME or "Platform Super Admin").strip(),
        email=email,
        employee_code=None,
        finger_id=None,
        password_hash=hash_password(password),
        role="super_admin",
        is_active=True,
        must_change_password=True,
    ))
    await db.commit()
    logger.info("Created Super Admin %s from SUPER_ADMIN_EMAIL.", email)
    return "created"


async def disable_demo_super_admin(db) -> bool:
    """Deactivate super@demo.local once a real Super Admin is configured."""
    configured = (settings.SUPER_ADMIN_EMAIL or "").strip().lower()
    if not configured or configured == DEMO_SUPER_ADMIN:
        return False
    demo = (
        await db.execute(select(User).where(User.email == DEMO_SUPER_ADMIN))
    ).scalars().first()
    if not demo or not demo.is_active:
        return False
    demo.is_active = False
    await db.commit()
    logger.warning(
        "Deactivated %s — its password is published in seed_demo_data.py.", DEMO_SUPER_ADMIN,
    )
    return True


async def run() -> None:
    """Called once from the app's startup. Never raises."""
    try:
        async with AsyncSessionLocal() as db:
            await ensure_super_admin(db)
            await disable_demo_super_admin(db)
    except Exception as exc:  # noqa: BLE001 — startup must not die on this
        logger.error("Super Admin bootstrap skipped: %s", exc)
