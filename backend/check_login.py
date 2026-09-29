"""
Why is sign-in failing?

`/api/auth/login` answers every failure with "Invalid credentials", on purpose
— an error that distinguished "no such account" from "wrong password" would
confirm which accounts exist to anyone who asked. That is right for the API and
useless when you are the one holding the password, so this reproduces the same
lookup locally and says which half went wrong.

    python check_login.py                                  # list accounts
    python check_login.py ops.admin@northwind.local Demo@1234

It reads the same .env the server does, so if it disagrees with the browser,
the two are talking to different databases — which is the usual answer.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.security import verify_password
from app.db.session import AsyncSessionLocal
from app.db.url import describe
from app.models.domain import Tenant, User


async def list_accounts(db) -> None:
    users = (await db.execute(select(User).order_by(User.tenant_id, User.id))).scalars().all()
    if not users:
        print("\n  No users at all. Nothing has been seeded into THIS database.")
        print("  Run:  python seed_demo_data.py\n")
        return

    tenants = {t.id: t.name for t in (await db.execute(select(Tenant))).scalars().all()}
    print(f"\n  {len(users)} account(s):\n")
    print(f"    {'EMAIL':<34} {'ROLE':<13} {'ORGANISATION':<22} ACTIVE  PASSWORD")
    for u in users:
        org = tenants.get(u.tenant_id, "— none —")
        # A user with no password hash cannot sign in however correct the
        # password is; the login route falls through to the API-key branch and
        # ends at the same "Invalid credentials".
        pw = "set" if u.password_hash else "NOT SET"
        print(f"    {(u.email or '—'):<34} {u.role:<13} {org:<22} "
              f"{'yes' if u.is_active else 'NO':<6}  {pw}")
    print()


async def check(db, username: str, password: str) -> int:
    user = (await db.execute(select(User).where(or_(
        User.employee_code == username,
        User.email == username,
    )))).scalars().first()

    if not user:
        print(f"\n  No account with email or employee code {username!r} in this database.")
        print("  Either it was never seeded, or the server is using a different one.")
        print("  Run:  python seed_demo_data.py\n")
        return 1

    print(f"\n  Found  {user.email}  (id={user.id}, role={user.role})")

    if not user.is_active:
        print("  DEACTIVATED — sign-in is refused regardless of the password.\n")
        return 1
    if not user.password_hash:
        print("  NO PASSWORD SET — this account can only be reached another way.")
        print("  Run:  python seed_demo_data.py    to give it one.\n")
        return 1
    if verify_password(password, user.password_hash):
        print("  Password is CORRECT. Sign-in should work.")
        print("  If the browser still refuses, it is reaching a different backend —")
        print("  check VITE_API_BASE_URL in .env, and rebuild the frontend if in Docker.\n")
        return 0

    print("  Password does NOT match the stored hash.")
    print("  Run:  python seed_demo_data.py    to reset it to the demo password.\n")
    return 1


async def main() -> int:
    print(f"\nDatabase: {describe(settings.DATABASE_URL)}")
    async with AsyncSessionLocal() as db:
        if len(sys.argv) >= 3:
            return await check(db, sys.argv[1], sys.argv[2])
        await list_accounts(db)
        return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:                      # noqa: BLE001
        # Connection failures land here, and they are the most useful answer of
        # all: the server cannot reach this database either.
        print(f"\n  Could not query the database: {type(exc).__name__}: {exc}\n")
        sys.exit(2)
