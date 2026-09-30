"""
Create a Super Admin, or reset one's password.

A Super Admin runs the platform: it creates organisations and can work inside
any of them. There is no screen for making one — deliberately, since the only
account that could use such a screen is another Super Admin — so it is done
here, against whatever database the backend's .env points at.

    python create_super_admin.py ops@yourcompany.com --name "Platform Ops"
    python create_super_admin.py ops@yourcompany.com --reset      # new password
    python create_super_admin.py ops@yourcompany.com --generate   # make one up

The password is read from a hidden prompt, never from the command line: an
argument lands in shell history and in the process list, where anyone else on
the machine can read it. With --generate a strong one is made up and printed
once, in this terminal only.

Before writing anything the script prints which database it is about to change
and asks you to confirm, unless that database is on this machine. The .env
lookup walks up from the backend, and a stray file can point it somewhere you
did not expect — this is the moment to notice.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import secrets
import string
import sys

from sqlalchemy import func, select

from app.core.config import settings as app_settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.db.url import describe
from app.models.domain import User

MIN_LENGTH = 12
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def password_problem(pw: str) -> str | None:
    """The stricter end of the app's rules: this account can reach everything."""
    if len(pw) < MIN_LENGTH:
        return f"must be at least {MIN_LENGTH} characters"
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "must contain at least one letter and one number"
    return None


def generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "-_.!@#"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(20))
        if not password_problem(pw):
            return pw


def ask_password() -> str:
    while True:
        pw = getpass.getpass("Password (hidden): ")
        problem = password_problem(pw)
        if problem:
            print(f"  Password {problem}. Try again.")
            continue
        if getpass.getpass("Repeat password:   ") != pw:
            print("  Those did not match. Try again.")
            continue
        return pw


def is_local(db_description: str) -> bool:
    host = db_description.split("/", 1)[0].lower()
    return host in {"localhost", "127.0.0.1", "::1", "db", "postgres"}


async def run(args) -> int:
    email = args.email.strip().lower()
    if not EMAIL.match(email):
        print(f"'{args.email}' does not look like an email address.")
        return 1

    target = describe(app_settings.DATABASE_URL)
    print(f"\n  Database: {target}")
    if not is_local(target) and not args.yes:
        answer = input("  This is not a local database. Type 'yes' to continue: ").strip().lower()
        if answer != "yes":
            print("  Nothing was changed.")
            return 1

    async with AsyncSessionLocal() as db:
        # Sign-in looks accounts up by email alone and takes the first match,
        # so one address must mean one account across every organisation.
        existing = (
            await db.execute(select(User).where(func.lower(User.email) == email))
        ).scalars().first()

        if existing and existing.role != "super_admin":
            print(
                f"\n  {email} already belongs to a {existing.role} account"
                f"{f' in organisation #{existing.tenant_id}' if existing.tenant_id else ''}."
                "\n  Use a different address — turning an existing account into a Super"
                "\n  Admin would give that person every organisation without anyone"
                "\n  deciding they should have it."
            )
            return 1

        if existing and not args.reset:
            print(
                f"\n  {email} is already a Super Admin. Nothing was changed."
                "\n  To set a new password, run this again with --reset."
            )
            return 1

        if not existing and args.reset:
            print(f"\n  No Super Admin with email {email}. Leave off --reset to create one.")
            return 1

        password = generate_password() if args.generate else ask_password()

        if existing:
            existing.password_hash = hash_password(password)
            existing.is_active = True
            if args.name:
                existing.name = args.name.strip()
            action = "Password reset"
        else:
            db.add(User(
                tenant_id=None,          # belongs to the platform, not an organisation
                name=(args.name or "Super Admin").strip(),
                email=email,
                employee_code=None,
                finger_id=None,
                password_hash=hash_password(password),
                role="super_admin",
                is_active=True,
            ))
            action = "Super Admin created"

        await db.commit()

    bar = "=" * 64
    print(f"\n{bar}\n  {action}\n{bar}")
    print(f"  Database   {target}")
    print(f"  Email      {email}")
    if args.generate:
        print(f"  Password   {password}")
        print("\n  Shown once. Copy it into a password manager now, then clear")
        print("  this terminal (cls). It is not stored anywhere readable.")
    else:
        print("  Password   the one you just typed")
    print("\n  Sign in at /login. There is no role to pick; the account is")
    print("  recognised as a Super Admin and lands on the Organisations screen.")
    print(bar)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Super Admin, or reset one's password.")
    parser.add_argument("email", help="Email the Super Admin signs in with")
    parser.add_argument("--name", help='Display name, e.g. "Platform Ops"')
    parser.add_argument("--reset", action="store_true",
                        help="Set a new password for an existing Super Admin")
    parser.add_argument("--generate", action="store_true",
                        help="Generate a strong password instead of prompting for one")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the confirmation for a non-local database")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
