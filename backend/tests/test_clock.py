"""
The web sign-in clock: how punches become a day, and the rules on punching.

Pairing is the part that has to be right. Scanners double-read and offline
sync replays every punch as IN, so a stray punch must never create doubled or
negative time — and a web sign-in must be closable at the scanner.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException

from app.api.routes import clock as clock_routes
from app.api.routes.org_admin import clock as org_clock
from app.services import attendance_service, clock_service

UTC = dt.UTC


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def P(kind, h, m, source="device", day=dt.date(2026, 10, 12)):
    """A punch at local (IST) time h:m."""
    local = dt.datetime.combine(day, dt.time(h, m), tzinfo=clock_service.zone())
    return Obj(record_type=kind, timestamp=local.astimezone(UTC), source=source)


def ist(h, m, day=dt.date(2026, 10, 12)):
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=clock_service.zone()).astimezone(UTC)


@pytest.fixture(autouse=True)
def india(monkeypatch):
    monkeypatch.setattr(clock_service.settings, "APP_TIMEZONE", "Asia/Kolkata")


# ─── the day ─────────────────────────────────────────────────────────────────

def test_two_sessions_mixed_sources():
    day = clock_service.summarise(
        [P("IN", 9, 2, "web"), P("OUT", 13, 5), P("IN", 13, 48), P("OUT", 18, 31, "web")],
        ist(20, 0), is_today=True)
    assert day["status"] == "out"
    assert len(day["sessions"]) == 2
    assert day["sessions"][0]["in_source"] == "web" and day["sessions"][0]["out_source"] == "device"
    assert day["effective_seconds"] == (4 * 60 + 3 + 4 * 60 + 43) * 60      # 8h 46m
    assert day["gross_seconds"] == (9 * 60 + 29) * 60                       # 09:02 → 18:31


def test_open_session_counts_up_to_now_today():
    day = clock_service.summarise([P("IN", 9, 0, "web")], ist(11, 30), is_today=True)
    assert day["status"] == "in"
    assert day["signed_in_since"] is not None
    assert day["effective_seconds"] == day["gross_seconds"] == 150 * 60


def test_forgotten_sign_out_on_a_past_day_counts_nothing_for_that_session():
    day = clock_service.summarise([P("IN", 9, 0), P("OUT", 12, 0), P("IN", 13, 0)],
                                  ist(9, 0, dt.date(2026, 10, 13)), is_today=False)
    assert day["status"] == "out" and day["unclosed"] is True
    assert day["effective_seconds"] == 3 * 3600          # only the closed session


def test_double_read_and_stray_out_are_ignored():
    day = clock_service.summarise(
        [P("OUT", 8, 0), P("IN", 9, 0), P("IN", 9, 1), P("OUT", 17, 0), P("OUT", 17, 1)],
        ist(20, 0), is_today=True)
    assert len(day["sessions"]) == 1
    assert day["effective_seconds"] == 8 * 3600


def test_no_punches_is_absent():
    day = clock_service.summarise([], ist(12, 0), is_today=True)
    assert day["status"] == "absent" and day["effective_seconds"] == 0 and day["first_in"] is None


def test_today_is_local_not_utc():
    # 20:00 UTC on the 12th is 01:30 IST on the 13th.
    assert clock_service.local_today(dt.datetime(2026, 10, 12, 20, 0, tzinfo=UTC)) == dt.date(2026, 10, 13)
    start, end = clock_service.day_bounds(dt.date(2026, 10, 12))
    assert start == dt.datetime(2026, 10, 11, 18, 30, tzinfo=UTC)
    assert end - start == dt.timedelta(days=1)


def test_bad_timezone_falls_back_to_utc(monkeypatch):
    monkeypatch.setattr(clock_service.settings, "APP_TIMEZONE", "Mars/Olympus")
    assert clock_service.zone() == UTC


# ─── punching ────────────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self):
        self.added, self.commits = [], 0

    def add(self, o):
        self.added.append(o)

    async def commit(self):
        self.commits += 1


def _req():
    return Obj(client=Obj(host="49.36.10.7"), headers={"user-agent": "t"})


@pytest.fixture
def stub_today(monkeypatch):
    def use(status):
        async def today_for(db, user, now=None):
            return {"status": status, "signed_in_since": ist(9, 0).isoformat() if status == "in" else None}
        monkeypatch.setattr(clock_service, "today_for", today_for)
    return use


@pytest.fixture
def audited(monkeypatch):
    calls = []

    async def log(db, request, **kw):
        calls.append(kw)
    monkeypatch.setattr(clock_routes.activity, "log", log)
    return calls


EMP = Obj(id=5, tenant_id=1, name="Aarti", role="employee")


async def test_sign_in_writes_a_web_punch_and_audits_it(stub_today, audited):
    stub_today("out")
    db = FakeDB()
    await clock_routes._punch(db, _req(), EMP, "IN")
    row = db.added[0]
    assert (row.record_type, row.source, row.device_id, row.finger_id) == ("IN", "web", "web", None)
    assert row.user_id == 5 and row.tenant_id == 1 and row.source_ip == "49.36.10.7"
    assert audited[0]["action"] == "attendance.web_sign_in" and audited[0]["target_id"] == 5
    assert db.commits == 1


async def test_cannot_sign_in_twice(stub_today, audited):
    stub_today("in")
    db = FakeDB()
    with pytest.raises(HTTPException) as exc:
        await clock_routes._punch(db, _req(), EMP, "IN")
    assert exc.value.status_code == 409 and "already signed in" in exc.value.detail
    assert db.added == [] and audited == []


async def test_cannot_sign_out_when_not_signed_in(stub_today, audited):
    stub_today("absent")
    with pytest.raises(HTTPException) as exc:
        await clock_routes._punch(FakeDB(), _req(), EMP, "OUT")
    assert exc.value.status_code == 409


async def test_sign_out_audits(stub_today, audited):
    stub_today("in")
    db = FakeDB()
    await clock_routes._punch(db, _req(), EMP, "OUT")
    assert db.added[0].record_type == "OUT"
    assert audited[0]["action"] == "attendance.web_sign_out"


def test_super_admin_keeps_no_attendance():
    with pytest.raises(HTTPException) as exc:
        clock_routes._clock_user(Obj(tenant_id=None, role="super_admin"))
    assert exc.value.status_code == 409


def test_future_dates_are_refused():
    with pytest.raises(HTTPException) as exc:
        clock_routes._day((clock_service.local_today() + dt.timedelta(days=1)).isoformat())
    assert exc.value.status_code == 400


async def test_org_admin_without_department_sees_nothing():
    with pytest.raises(HTTPException) as exc:
        await org_clock.department_day(None, Obj(tenant_id=1, dept_id=None, role="org_admin"), FakeDB())
    assert exc.value.status_code == 409


# ─── the scanner sees web punches ────────────────────────────────────────────

class _Res:
    def __init__(self, v):
        self.v = v

    def scalars(self):
        return self

    def first(self):
        return self.v


class ScannerDB(FakeDB):
    def __init__(self, user, last):
        super().__init__()
        self.results = [user, last]
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(str(stmt))
        return _Res(self.results.pop(0))

    async def refresh(self, o):
        pass


async def test_scanner_after_web_sign_in_records_out():
    user = Obj(id=5, name="Aarti")
    db = ScannerDB(user, Obj(record_type="IN"))      # the last punch: a web IN
    log, name = await attendance_service.process_attendance(1, "GS-01", 3, db)
    assert log.record_type == "OUT" and log.source == "device" and name == "Aarti"
    # Looked up by the person, not the finger — a web punch has no finger.
    assert "attendance_logs.user_id" in db.statements[1]
