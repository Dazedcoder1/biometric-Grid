"""
Background sweep that expires shares whose time has passed.

Worth being clear about what this is and is not.

It is **not** what enforces expiry. Every access query already filters on
`expires_at`, so an expired share grants nothing the moment it expires, whether
or not this loop has run. If the sweeper never ran at all, nobody would gain
access they should not have.

What it does is make the state visible — a share reads as `expired` rather than
`active` in the UI — and put "access expired" in the audit log at roughly the
right time rather than whenever someone next happens to look.

That distinction matters because it decides how much to worry when the loop
dies: the answer is "the log gets late entries", not "access leaks".

Follows the existing `reconcile_loop` pattern: an asyncio task started in the
FastAPI lifespan. Fine for a job this small. Re-encryption after key rotation
is the one that needs a resumable script instead — ARCHITECTURE.md §7.
"""

from __future__ import annotations

import asyncio
import logging

from app.db.session import AsyncSessionLocal
from app.services import share_service

logger = logging.getLogger(__name__)

#: A minute is comfortably tighter than the granularity anyone grants access at,
#: and the query is a partial-index lookup on a handful of rows.
INTERVAL_SECONDS = 60


async def sweep_once() -> int:
    """One pass. Returns how many shares were expired."""
    async with AsyncSessionLocal() as db:
        count = await share_service.expire_due(db)
        await db.commit()
        return count


async def expiry_loop() -> None:
    """
    Run until cancelled.

    Every exception is caught and logged: a failed pass must not kill the loop,
    because the next pass would fix whatever the last one missed. The one
    exception is CancelledError, which is shutdown and must propagate.
    """
    logger.info("Share expiry sweeper started (every %ss).", INTERVAL_SECONDS)

    while True:
        try:
            await asyncio.sleep(INTERVAL_SECONDS)
            expired = await sweep_once()
            if expired:
                logger.info("Share sweeper expired %s share(s).", expired)
        except asyncio.CancelledError:
            logger.info("Share expiry sweeper stopped.")
            raise
        except Exception:
            # Logged with the traceback rather than swallowed, so a persistently
            # failing sweep is visible in the logs instead of silently doing
            # nothing for weeks.
            logger.exception("Share expiry sweep failed; continuing.")
