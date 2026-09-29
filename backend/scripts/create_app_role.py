"""
Create the limited application role and prove the audit log is append-only.

    python scripts/create_app_role.py

Generates the password with `secrets`, runs sql/01_create_app_role.sql against
the DIRECT Neon endpoint as the owner, verifies the grants, then attempts a
DELETE on audit_log and expects to be refused.

That last step is the point. A control nobody has watched fail is not known to
work — the same lesson the ModuleNotFoundError taught when the tests first ran.

Prints the DATABASE_URL line to paste into .env. The password is shown once and
is not stored anywhere by this script.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.core.config import ENV_FILE, settings  # noqa: E402

SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "01_create_app_role.sql"
ROLE = "gridsphere_app"
PLACEHOLDER = "CHANGE_ME_BEFORE_RUNNING"


def _env_value(key: str) -> str | None:
    if not ENV_FILE.is_file():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _asyncpg_url(raw: str) -> str:
    """Strip the SQLAlchemy driver suffix and libpq-only query parameters."""
    for prefix in ("postgresql+asyncpg://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix):]
            break
    return raw.split("?")[0]


def _with_credentials(url: str, user: str, password: str) -> str:
    """Swap the userinfo in a URL, leaving host, port and database intact."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, f"{user}:{password}@{host}", parts.path, "", ""))


async def main() -> int:
    owner_raw = _env_value("DATABASE_URL_UNPOOLED") or settings.DATABASE_URL
    if "-pooler" in owner_raw:
        print("\n  ! Only the pooled endpoint is available. Role changes through")
        print("    PgBouncer are unreliable. Add DATABASE_URL_UNPOOLED to .env.\n")
        return 1

    owner_url = _asyncpg_url(owner_raw)

    if not SQL_FILE.is_file():
        print(f"  Not found: {SQL_FILE}")
        return 1

    # 32 bytes of CSPRNG output. This password guards the credential vault's
    # data path; it is sized like a key, not like a login.
    password = secrets.token_urlsafe(32)
    script = SQL_FILE.read_text(encoding="utf-8").replace(PLACEHOLDER, password)

    parts = urlsplit(owner_url)
    print(f"\n  Target : {parts.hostname}{parts.path}")
    print(f"  Role   : {ROLE}\n")

    try:
        conn = await asyncpg.connect(owner_url, ssl="require")
    except Exception as exc:
        print(f"  Could not connect as owner: {exc}\n")
        return 1

    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = $1", ROLE
        )
        if exists:
            print(f"  Role {ROLE} already exists — rotating its password and")
            print("  re-applying grants.\n")
            await conn.execute(
                f'ALTER ROLE "{ROLE}" WITH LOGIN PASSWORD $${password}$$'
            )
            # Re-run everything except CREATE ROLE, which would fail.
            body = script.split("\n")
            body = [
                ln for ln in body
                if not ln.strip().upper().startswith("CREATE ROLE")
            ]
            await conn.execute("\n".join(body))
        else:
            await conn.execute(script)

        print("  Grants applied. Verifying...\n")

        rows = await conn.fetch(
            """
            SELECT privilege_type
              FROM information_schema.role_table_grants
             WHERE grantee = $1 AND table_name = 'audit_log'
             ORDER BY privilege_type
            """,
            ROLE,
        )
        granted = sorted(r["privilege_type"] for r in rows)
        print(f"  audit_log privileges for {ROLE}: {granted or '(none)'}")

        if set(granted) - {"INSERT", "SELECT"}:
            print("\n  ! FAILED: more than INSERT and SELECT are granted.")
            print("    The audit log is NOT append-only.\n")
            return 1
        if "INSERT" not in granted:
            print("\n  ! FAILED: no INSERT. The app cannot write audit entries.\n")
            return 1

    finally:
        await conn.close()

    # ── prove it, as the new role ────────────────────────────────────────────
    app_url = _with_credentials(owner_url, ROLE, password)
    print("\n  Proving the control, connected as the new role...")

    try:
        app_conn = await asyncpg.connect(app_url, ssl="require")
    except Exception as exc:
        print(f"  ! Could not connect as {ROLE}: {exc}\n")
        return 1

    try:
        await app_conn.fetchval("SELECT count(*) FROM audit_log")
        print("    SELECT on audit_log     : allowed  (expected)")

        try:
            # Inside a transaction that is always rolled back, so this proves
            # the permission without touching data even if it unexpectedly
            # succeeds.
            tx = app_conn.transaction()
            await tx.start()
            try:
                await app_conn.execute("DELETE FROM audit_log WHERE seq = -1")
                await tx.rollback()
            except Exception:
                await tx.rollback()
                raise
        except asyncpg.InsufficientPrivilegeError:
            print("    DELETE on audit_log     : REFUSED  (expected)\n")
            print("  Append-only is enforced by the database, not by convention.\n")
        else:
            print("    DELETE on audit_log     : ALLOWED  ← NOT PROTECTED\n")
            print("  ! The revoke did not take. audit_log can still be rewritten.\n")
            return 1
    finally:
        await app_conn.close()

    # ── hand over the connection string ──────────────────────────────────────
    pooled_raw = _env_value("DATABASE_URL") or ""
    pooled_clean = _asyncpg_url(pooled_raw) if pooled_raw else owner_url
    suffix = "?channel_binding=require&sslmode=require"
    new_url = _with_credentials(pooled_clean, ROLE, password) + suffix

    bar = "=" * 74
    print(bar)
    print("REPLACE DATABASE_URL IN .env WITH THIS LINE")
    print(bar)
    print(f'\nDATABASE_URL="{new_url}"\n')
    print(bar)
    print("Leave DATABASE_URL_UNPOOLED on the owner role — Alembic needs DDL")
    print("rights that the application deliberately does not have.")
    print("")
    print("This password is shown once and stored nowhere. Copy it now.")
    print(bar)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
