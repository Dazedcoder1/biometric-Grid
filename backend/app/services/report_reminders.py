"""
End-of-day nudges for the day-end report.

From 30 minutes before each organisation's office end time, on its working
days, anyone who worked today (signed in, or started a draft) but has not
submitted their report gets one notification. One per person per day: a
reminder already sent for the date is never repeated.

Runs every 30 minutes. That interval is deliberate — anything tighter keeps a
serverless database (Neon) awake around the clock for no benefit.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.domain import AttendanceLog, DailyReport, Notification, Settings, Tenant, User
from app.services import clock_service, notification_service
from app.services import reporting as R

logger = logging.getLogger(__name__)
EVENT = "report_reminder"
DEFAULT_END = dt.time(18, 0)


async def send_report_reminders(db, now: dt.datetime | None = None) -> int:
    now = now or clock_service.now_utc()
    local = now.astimezone(clock_service.zone())
    today = local.date()
    start, end = clock_service.day_bounds(today)
    settings = {s.tenant_id: s for s in (await db.execute(select(Settings))).scalars().all()}
    sent = 0

    for tenant_id in (await db.execute(select(Tenant.id))).scalars().all():
        cfg = settings.get(tenant_id)
        office_end = R.parse_clock(cfg.office_end_time if cfg else None, DEFAULT_END)
        if not R.reminder_due(local, office_end, cfg.working_days if cfg else None):
            continue

        worked = set((await db.execute(select(AttendanceLog.user_id).where(
            AttendanceLog.tenant_id == tenant_id, AttendanceLog.user_id.is_not(None),
            AttendanceLog.timestamp >= start, AttendanceLog.timestamp < end))).scalars().all())
        reports = {r.user_id: r.status for r in (await db.execute(select(DailyReport).where(
            DailyReport.tenant_id == tenant_id, DailyReport.report_date == today))).scalars().all()}
        drafted = {uid for uid, st in reports.items() if st == "draft"}
        submitted = {uid for uid, st in reports.items() if st == "submitted"}
        candidates = (worked | drafted) - submitted
        if not candidates:
            continue

        already = set((await db.execute(select(Notification.recipient_id).where(
            Notification.tenant_id == tenant_id, Notification.event_type == EVENT,
            Notification.entity_name == today.isoformat()))).scalars().all())
        people = (await db.execute(select(User.id).where(
            User.id.in_(candidates - already), User.tenant_id == tenant_id,
            User.is_active.is_(True), User.role != "super_admin"))).scalars().all()
        for uid in people:
            await notification_service.notify_single_user(
                db, tenant_id=tenant_id, actor_id=None, recipient_id=uid, event_type=EVENT,
                title="Day-end report due",
                message=("Your draft for today is not submitted yet." if uid in drafted
                         else "Take two minutes to report what you did today in My Day."),
                entity_type="daily_report", entity_id=None, entity_name=today.isoformat())
            sent += 1
    return sent


async def reminder_loop(interval_seconds: int = 30 * 60) -> None:
    """Started from the app's lifespan. A dead loop means no nudges, nothing worse."""
    logger.info("Day-end report reminders started (every %ss).", interval_seconds)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                n = await send_report_reminders(db)
                await db.commit()
                if n:
                    logger.info("Sent %s day-end report reminder(s).", n)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            logger.error("Day-end reminder pass failed: %s", exc)
        await asyncio.sleep(interval_seconds)
