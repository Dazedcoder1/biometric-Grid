"""
Turn whatever DATABASE_URL is in .env into something asyncpg will accept.

Neon (and every other hosted Postgres) hands you a libpq-style URL:

    postgresql://user:pass@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require

Three things in that string break SQLAlchemy + asyncpg, and all three fail
with errors that don't name the real cause:

1. The `postgresql://` scheme picks the *sync* psycopg driver. Needs to be
   `postgresql+asyncpg://`.
2. `sslmode` and `channel_binding` are libpq parameters. asyncpg has never
   heard of them, so they arrive as unexpected keyword arguments to
   asyncpg.connect() and raise TypeError.
3. A hostname containing `-pooler` is Neon's PgBouncer endpoint, running in
   transaction pooling mode. Prepared statements do not survive that, and
   asyncpg prepares every statement by default — you get intermittent
   "prepared statement __asyncpg_stmt_x__ does not exist" errors under any
   real concurrency.

normalise() rewrites the URL and returns the connect_args that fix all three,
so .env can hold the string exactly as Neon printed it.
"""

from __future__ import annotations

import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# libpq understands these; asyncpg does not. Drop them from the query string
# and translate the ones that carry meaning into connect_args.
_LIBPQ_ONLY = {
    "sslmode",
    "channel_binding",
    "target_session_attrs",
    "options",
    "application_name",
    "connect_timeout",
    "gssencmode",
    "sslrootcert",
    "sslcert",
    "sslkey",
}

_SSL_MODES_REQUIRING_TLS = {"require", "verify-ca", "verify-full"}


def normalise(raw_url: str) -> tuple[str, dict]:
    """Return (url, connect_args) ready for create_async_engine()."""
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("DATABASE_URL is empty — see .env.example")

    # 1. Force the async driver, whatever scheme was pasted in.
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
            break

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    sslmode = query.get("sslmode")
    for key in _LIBPQ_ONLY:
        query.pop(key, None)

    connect_args: dict = {}
    host = (parts.hostname or "").lower()

    # 2. TLS. Hosted Postgres always wants it; Neon rejects plaintext outright.
    is_hosted = any(marker in host for marker in ("neon.tech", "supabase.", "rds.amazonaws", "render.com", "railway."))
    if (sslmode in _SSL_MODES_REQUIRING_TLS) or (is_hosted and sslmode != "disable"):
        # Full verification against the system CA store. libpq's `sslmode=require`
        # actually means "encrypt but don't check the certificate"; this is
        # stricter, and works with Neon, whose chain is publicly trusted.
        connect_args["ssl"] = ssl.create_default_context()

    # 3. PgBouncer in transaction mode cannot hold prepared statements.
    if "-pooler" in host or query.pop("pgbouncer", None) == "true":
        connect_args["statement_cache_size"] = 0          # asyncpg's own cache
        connect_args["prepared_statement_cache_size"] = 0  # SQLAlchemy's cache

    rebuilt = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    return rebuilt, connect_args


def describe(raw_url: str) -> str:
    """host/database, with the password stripped — safe to log."""
    try:
        parts = urlsplit(normalise(raw_url)[0])
        return f"{parts.hostname or '?'}{parts.path or ''}"
    except Exception:
        return "<unparseable DATABASE_URL>"
