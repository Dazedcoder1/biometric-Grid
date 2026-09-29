"""
Run a .sql file against the database, without needing psql installed.

    python scripts/run_sql.py sql/01_create_app_role.sql

Uses asyncpg, which is already a dependency, and the DIRECT (unpooled) Neon
endpoint — DDL and role management through PgBouncer's transaction pooling is
unreliable, the same reason pg_restore needs the direct endpoint.

Deliberately simple: it sends the file as one script and prints what comes
back. It is not a migration tool — Alembic owns schema changes. This is for
one-off operational SQL such as creating roles and grants.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make `app` importable when run from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.url import describe  # noqa: E402


def _connect_url() -> str:
    """
    The direct endpoint, stripped of libpq-only parameters asyncpg rejects.

    DATABASE_URL_UNPOOLED is not part of Settings (it is read by tooling, not
    the app), so it is pulled from the .env file that config.py already found.
    """
    from app.core.config import ENV_FILE

    raw = None
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL_UNPOOLED="):
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

    if not raw:
        raw = settings.DATABASE_URL
        print("  ! DATABASE_URL_UNPOOLED not found; falling back to DATABASE_URL.")
        if "-pooler" in raw:
            print("  ! That is the POOLED endpoint. Role changes may fail.")

    # asyncpg speaks its own dialect: no +asyncpg suffix, no sslmode.
    for prefix in ("postgresql+asyncpg://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix):]
            break

    return raw.split("?")[0]


async def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"Not found: {path}")
        return 1

    script = path.read_text(encoding="utf-8")

    if "CHANGE_ME_BEFORE_RUNNING" in script:
        print(f"\n  {path} still contains the placeholder password.")
        print("  Replace CHANGE_ME_BEFORE_RUNNING with a real value first.\n")
        return 1

    url = _connect_url()
    print(f"\n  Target : {describe(url)}")
    print(f"  Script : {path}\n")

    try:
        conn = await asyncpg.connect(url, ssl="require")
    except Exception as exc:
        print(f"  Could not connect: {exc}")
        return 1

    try:
        await conn.execute(script)
        print("  OK — script executed.\n")
        return 0
    except Exception as exc:
        # Printed rather than raised: a traceback here buries the one line that
        # says what Postgres actually objected to.
        print(f"  FAILED: {exc}\n")
        return 1
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
