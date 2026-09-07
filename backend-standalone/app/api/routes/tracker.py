# api/routes/tracker.py
"""
Tracker Routes - Employee Activity Monitoring
For Org Admin to view employee activity, sessions, and screenshots
Uses work_sessions table for tracking data
"""
import os
import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.api.dependencies import get_current_user, require_role
from app.models.domain import User

# =========================
# R2 / S3 CLIENT
# =========================

R2_ACCOUNT_ID      = os.getenv("R2_ACCOUNT_ID",      "bdce6341de1e7b4818a4832fbe29d68c")
R2_ACCESS_KEY_ID   = os.getenv("R2_ACCESS_KEY_ID",   "28fb692bc554c8feb96a963c00bbc3e1")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "2f73fcce066c3c441c3f15d25827892aa6371934de593ebaf4658be7758aa199")
R2_BUCKET_NAME     = os.getenv("R2_BUCKET_NAME",     "tracker")

s3_client = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto",
    config=Config(signature_version="s3v4"),
)

router = APIRouter()


# =========================
# SCHEMAS
# =========================

class TrackerEmployeeResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    employee_code: Optional[str]
    hasActiveSession: bool
    todayHours: float
    totalWorkingHours: float
    screenshotCount: int
    sessionCount: int
    department_name: Optional[str]


class TrackerSessionResponse(BaseModel):
    sessionId: str
    checkInTime: Optional[datetime]
    checkOutTime: Optional[datetime]
    durationHours: float
    screenshotCount: int
    status: str


class TrackerDashboardResponse(BaseModel):
    totalEmployees: int
    activeEmployees: int
    totalHoursToday: float
    totalScreenshots: int
    avgHoursPerEmployee: float
    complianceRate: float
    department_name: Optional[str]


# =========================
# HELPER FUNCTIONS
# =========================

def safe_str(value: int) -> str:
    """Convert integer to string safely for database queries"""
    return str(value)


async def get_today_hours(user_id: int, tenant_id: int, db: AsyncSession) -> float:
    """Get today's total working hours for a user"""
    # FIX: Pass date.today() directly as a date object, NOT as an ISO string.
    # asyncpg (the async PostgreSQL driver) requires native Python date/datetime
    # objects for date parameters — it does not accept plain strings like '2026-06-06'.
    today = date.today()
    user_id_str = safe_str(user_id)

    result = await db.execute(text("""
        SELECT COALESCE(SUM(duration_seconds), 0) as total_seconds
        FROM work_sessions
        WHERE user_id = :user_id
        AND tenant_id = :tenant_id
        AND DATE(check_in_time) = :today
        AND status IN ('completed', 'auto_checked_out')
    """), {
        "user_id": user_id_str,
        "tenant_id": tenant_id,
        "today": today
    })
    seconds = result.scalar() or 0
    return seconds / 3600


async def get_total_hours(user_id: int, tenant_id: int, db: AsyncSession) -> float:
    """Get total working hours for a user (all time)"""
    user_id_str = safe_str(user_id)

    result = await db.execute(text("""
        SELECT COALESCE(SUM(duration_seconds), 0) as total_seconds
        FROM work_sessions
        WHERE user_id = :user_id
        AND tenant_id = :tenant_id
        AND status IN ('completed', 'auto_checked_out')
    """), {
        "user_id": user_id_str,
        "tenant_id": tenant_id
    })
    seconds = result.scalar() or 0
    return seconds / 3600


async def get_screenshot_count(user_id: int, tenant_id: int, db: AsyncSession) -> int:
    """Get total screenshot count for a user"""
    user_id_str = safe_str(user_id)

    result = await db.execute(text("""
        SELECT COALESCE(SUM(screenshot_count), 0) as total
        FROM work_sessions
        WHERE user_id = :user_id
        AND tenant_id = :tenant_id
        AND status IN ('completed', 'auto_checked_out')
    """), {
        "user_id": user_id_str,
        "tenant_id": tenant_id
    })
    return result.scalar() or 0


async def get_session_count(user_id: int, tenant_id: int, db: AsyncSession) -> int:
    """Get total session count for a user"""
    user_id_str = safe_str(user_id)

    result = await db.execute(text("""
        SELECT COUNT(*) as total
        FROM work_sessions
        WHERE user_id = :user_id
        AND tenant_id = :tenant_id
        AND status IN ('completed', 'auto_checked_out')
    """), {
        "user_id": user_id_str,
        "tenant_id": tenant_id
    })
    return result.scalar() or 0


async def has_active_session(user_id: int, tenant_id: int, db: AsyncSession) -> bool:
    """Check if user has an active session"""
    user_id_str = safe_str(user_id)

    result = await db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM work_sessions
            WHERE user_id = :user_id
            AND tenant_id = :tenant_id
            AND status = 'active'
        )
    """), {
        "user_id": user_id_str,
        "tenant_id": tenant_id
    })
    return result.scalar() or False


async def get_active_sessions_count(tenant_id: int, dept_id: int, db: AsyncSession) -> int:
    """Get count of active sessions in department"""
    result = await db.execute(text("""
        SELECT COUNT(DISTINCT ws.user_id) as active_count
        FROM work_sessions ws
        JOIN users u ON ws.user_id = CAST(u.id AS TEXT)
        WHERE ws.tenant_id = :tenant_id
        AND ws.status = 'active'
        AND u.dept_id = :dept_id
        AND u.role = 'employee'
        AND u.is_active = true
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id
    })
    return result.scalar() or 0


async def get_department_employees(tenant_id: int, dept_id: int, db: AsyncSession) -> List[dict]:
    """Get all employees in department"""
    result = await db.execute(text("""
        SELECT
            u.id,
            u.name,
            u.email,
            u.employee_code,
            d.department_name
        FROM users u
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE u.tenant_id = :tenant_id
        AND u.dept_id = :dept_id
        AND u.role = 'employee'
        AND u.is_active = true
        ORDER BY u.name
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id
    })
    return result.mappings().all()


async def get_department_name(dept_id: int, db: AsyncSession) -> Optional[str]:
    """Get department name by ID"""
    result = await db.execute(text("""
        SELECT department_name FROM departments WHERE department_id = :dept_id
    """), {"dept_id": dept_id})
    return result.scalar()


async def get_total_employees_count(tenant_id: int, dept_id: int, db: AsyncSession) -> int:
    """Get total active employees count in department"""
    result = await db.execute(text("""
        SELECT COUNT(*) as total
        FROM users
        WHERE tenant_id = :tenant_id
        AND dept_id = :dept_id
        AND role = 'employee'
        AND is_active = true
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id
    })
    return result.scalar() or 0


async def get_today_total_hours(tenant_id: int, dept_id: int, db: AsyncSession) -> float:
    """Get total working hours for today in department"""
    # FIX: Pass date.today() directly as a date object, NOT as an ISO string.
    today = date.today()

    result = await db.execute(text("""
        SELECT COALESCE(SUM(ws.duration_seconds), 0) as total_seconds
        FROM work_sessions ws
        JOIN users u ON ws.user_id = CAST(u.id AS TEXT)
        WHERE ws.tenant_id = :tenant_id
        AND DATE(ws.check_in_time) = :today
        AND ws.status IN ('completed', 'auto_checked_out')
        AND u.dept_id = :dept_id
        AND u.role = 'employee'
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id,
        "today": today
    })
    total_seconds = result.scalar() or 0
    return total_seconds / 3600


async def get_total_screenshots(tenant_id: int, dept_id: int, db: AsyncSession) -> int:
    """Get total screenshots in department"""
    result = await db.execute(text("""
        SELECT COALESCE(SUM(ws.screenshot_count), 0) as total_shots
        FROM work_sessions ws
        JOIN users u ON ws.user_id = CAST(u.id AS TEXT)
        WHERE ws.tenant_id = :tenant_id
        AND ws.status IN ('completed', 'auto_checked_out')
        AND u.dept_id = :dept_id
        AND u.role = 'employee'
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id
    })
    return result.scalar() or 0


async def get_low_activity_count(tenant_id: int, dept_id: int, db: AsyncSession) -> int:
    """Get count of employees with less than 4 hours today"""
    # FIX: Pass date.today() directly as a date object, NOT as an ISO string.
    today = date.today()

    result = await db.execute(text("""
        SELECT COUNT(*) as low_count
        FROM (
            SELECT ws.user_id, COALESCE(SUM(ws.duration_seconds), 0) as total_seconds
            FROM work_sessions ws
            JOIN users u ON ws.user_id = CAST(u.id AS TEXT)
            WHERE ws.tenant_id = :tenant_id
            AND DATE(ws.check_in_time) = :today
            AND ws.status IN ('completed', 'auto_checked_out')
            AND u.dept_id = :dept_id
            AND u.role = 'employee'
            GROUP BY ws.user_id
            HAVING COALESCE(SUM(ws.duration_seconds), 0) / 3600 < 4
        ) as low_activity_users
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id,
        "today": today
    })
    return result.scalar() or 0


# =========================
# TRACKER ROUTES
# =========================

@router.get("/tracker/employees", response_model=List[TrackerEmployeeResponse])
async def get_tracker_employees(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    """Org Admin: Get all employees in department with tracking data from work_sessions"""
    tenant_id = current_user.tenant_id
    dept_id = current_user.dept_id

    employees = await get_department_employees(tenant_id, dept_id, db)

    tracker_employees = []
    for emp in employees:
        today_hours = await get_today_hours(emp["id"], tenant_id, db)
        total_hours = await get_total_hours(emp["id"], tenant_id, db)
        screenshot_count = await get_screenshot_count(emp["id"], tenant_id, db)
        session_count = await get_session_count(emp["id"], tenant_id, db)
        has_active = await has_active_session(emp["id"], tenant_id, db)

        tracker_employees.append(TrackerEmployeeResponse(
            id=emp["id"],
            name=emp["name"],
            email=emp["email"],
            employee_code=emp["employee_code"],
            hasActiveSession=has_active,
            todayHours=round(today_hours, 2),
            totalWorkingHours=round(total_hours, 2),
            screenshotCount=screenshot_count,
            sessionCount=session_count,
            department_name=emp["department_name"]
        ))

    return tracker_employees


@router.get("/tracker/dashboard", response_model=TrackerDashboardResponse)
async def get_tracker_dashboard(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    """Org Admin: Get dashboard statistics from work_sessions"""
    tenant_id = current_user.tenant_id
    dept_id = current_user.dept_id

    department_name = await get_department_name(dept_id, db)
    total_employees = await get_total_employees_count(tenant_id, dept_id, db)
    active_sessions = await get_active_sessions_count(tenant_id, dept_id, db)
    total_hours_today = await get_today_total_hours(tenant_id, dept_id, db)
    total_screenshots = await get_total_screenshots(tenant_id, dept_id, db)

    avg_hours = round(total_hours_today / total_employees, 2) if total_employees > 0 else 0
    compliance_rate = round((active_sessions / total_employees * 100), 1) if total_employees > 0 else 0

    return TrackerDashboardResponse(
        totalEmployees=total_employees,
        activeEmployees=active_sessions,
        totalHoursToday=round(total_hours_today, 2),
        totalScreenshots=total_screenshots,
        avgHoursPerEmployee=avg_hours,
        complianceRate=compliance_rate,
        department_name=department_name
    )


@router.get("/tracker/employee/{user_id}")
async def get_tracker_employee_detail(
    user_id: int,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    """Org Admin: Get detailed employee tracking data from work_sessions"""
    tenant_id = current_user.tenant_id
    dept_id = current_user.dept_id

    # Verify employee belongs to department
    emp_result = await db.execute(text("""
        SELECT u.id, u.name, u.email, u.employee_code, d.department_name
        FROM users u
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE u.id = :user_id
        AND u.tenant_id = :tenant_id
        AND u.dept_id = :dept_id
        AND u.role = 'employee'
    """), {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "dept_id": dept_id
    })
    employee = emp_result.mappings().first()

    if not employee:
        raise HTTPException(404, "Employee not found in your department")

    today_hours = await get_today_hours(user_id, tenant_id, db)
    total_hours = await get_total_hours(user_id, tenant_id, db)
    screenshot_count = await get_screenshot_count(user_id, tenant_id, db)
    session_count = await get_session_count(user_id, tenant_id, db)
    has_active = await has_active_session(user_id, tenant_id, db)

    # Get active session details
    user_id_str = safe_str(user_id)
    active_session_result = await db.execute(text("""
        SELECT session_id, check_in_time, screenshot_count
        FROM work_sessions
        WHERE user_id = :user_id
        AND tenant_id = :tenant_id
        AND status = 'active'
        LIMIT 1
    """), {
        "user_id": user_id_str,
        "tenant_id": tenant_id
    })
    active_session = active_session_result.mappings().first()

    # Get session history (last 30 sessions)
    sessions_result = await db.execute(text("""
        SELECT
            session_id,
            check_in_time,
            check_out_time,
            duration_seconds,
            screenshot_count,
            status
        FROM work_sessions
        WHERE user_id = :user_id
        AND tenant_id = :tenant_id
        AND status IN ('completed', 'auto_checked_out')
        ORDER BY check_in_time DESC
        LIMIT 30
    """), {
        "user_id": user_id_str,
        "tenant_id": tenant_id
    })

    sessions = []
    for session in sessions_result.mappings().all():
        duration = (session["duration_seconds"] or 0) / 3600
        sessions.append(TrackerSessionResponse(
            sessionId=session["session_id"],
            checkInTime=session["check_in_time"],
            checkOutTime=session["check_out_time"],
            durationHours=round(duration, 2),
            screenshotCount=session["screenshot_count"] or 0,
            status=session["status"]
        ))

    return {
        "id": employee["id"],
        "name": employee["name"],
        "email": employee["email"],
        "employee_code": employee["employee_code"],
        "department_name": employee["department_name"],
        "hasActiveSession": has_active,
        "sessionStart": active_session["check_in_time"] if active_session else None,
        "totalWorkingHours": round(total_hours, 2),
        "todayHours": round(today_hours, 2),
        "totalSessions": session_count,
        "screenshotCount": screenshot_count,
        "sessions": [s.dict() for s in sessions]
    }


@router.get("/tracker/sessions/{user_id}")
async def get_tracker_sessions(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    """Org Admin: Get session history for an employee from work_sessions"""
    tenant_id = current_user.tenant_id
    dept_id = current_user.dept_id

    # Verify employee belongs to department
    emp_check = await db.execute(text("""
        SELECT id FROM users
        WHERE id = :user_id
        AND tenant_id = :tenant_id
        AND dept_id = :dept_id
        AND role = 'employee'
    """), {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "dept_id": dept_id
    })
    if not emp_check.scalar():
        raise HTTPException(404, "Employee not found in your department")

    user_id_str = safe_str(user_id)
    result = await db.execute(text("""
        SELECT
            session_id,
            check_in_time,
            check_out_time,
            duration_seconds,
            screenshot_count,
            status
        FROM work_sessions
        WHERE user_id = :user_id
        AND tenant_id = :tenant_id
        AND status IN ('completed', 'auto_checked_out')
        ORDER BY check_in_time DESC
        LIMIT :limit
    """), {
        "user_id": user_id_str,
        "tenant_id": tenant_id,
        "limit": limit
    })

    sessions = []
    for session in result.mappings().all():
        duration = (session["duration_seconds"] or 0) / 3600
        sessions.append({
            "sessionId": session["session_id"],
            "checkInTime": session["check_in_time"],
            "checkOutTime": session["check_out_time"],
            "durationHours": round(duration, 2),
            "screenshotCount": session["screenshot_count"] or 0,
            "status": session["status"]
        })

    return {"sessions": sessions, "count": len(sessions)}


@router.get("/tracker/screenshots/{user_id}")
async def get_tracker_screenshots(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    """Org Admin: Get screenshots for an employee from R2/S3 storage"""
    tenant_id = current_user.tenant_id
    dept_id = current_user.dept_id

    # Verify employee belongs to department
    emp_check = await db.execute(text("""
        SELECT id FROM users
        WHERE id = :user_id
        AND tenant_id = :tenant_id
        AND dept_id = :dept_id
        AND role = 'employee'
    """), {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "dept_id": dept_id
    })
    if not emp_check.scalar():
        raise HTTPException(404, "Employee not found in your department")

    # List all objects under screenshots/{tenant_id}/{user_id}/
    # Mirrors Node.js: s3.listObjectsV2({ Bucket, Prefix: `screenshots/${tenantId}/${userId}/` })
    try:
        prefix = f"screenshots/{tenant_id}/{user_id}/"
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=R2_BUCKET_NAME, Prefix=prefix)

        objects = []
        for page in pages:
            for obj in page.get("Contents", []):
                objects.append(obj)

        # Sort newest first (mirrors Node: sort by timestamp desc)
        objects.sort(key=lambda o: o["LastModified"], reverse=True)

        # Apply limit
        objects = objects[:limit]

        screenshots = []
        for obj in objects:
            # Generate a presigned GET URL valid for 1 hour (3600s)
            # Mirrors Node.js: s3.getSignedUrlPromise('getObject', { Bucket, Key, Expires: 3600 })
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": R2_BUCKET_NAME, "Key": obj["Key"]},
                ExpiresIn=3600,
            )
            screenshots.append({
                "url": url,
                "key": obj["Key"],
                "timestamp": obj["LastModified"].isoformat(),
            })

        return {"screenshots": screenshots, "count": len(screenshots)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"R2 error: {str(e)}")


@router.get("/tracker/reports")
async def get_tracker_reports(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    """Org Admin: Get summary reports from work_sessions"""
    tenant_id = current_user.tenant_id
    dept_id = current_user.dept_id

    total_employees = await get_total_employees_count(tenant_id, dept_id, db)
    active_now = await get_active_sessions_count(tenant_id, dept_id, db)
    total_hours_today = await get_today_total_hours(tenant_id, dept_id, db)
    total_screenshots = await get_total_screenshots(tenant_id, dept_id, db)
    low_activity_count = await get_low_activity_count(tenant_id, dept_id, db)

    avg_hours = round(total_hours_today / total_employees, 1) if total_employees > 0 else 0

    return [
        {"label": "Total Employees", "value": total_employees},
        {"label": "Active Now", "value": active_now},
        {"label": "Total Hours Logged", "value": f"{total_hours_today:.1f}h"},
        {"label": "Avg Hours / Employee", "value": f"{avg_hours}h"},
        {"label": "Total Screenshots", "value": total_screenshots},
        {"label": "Low Activity (<4h)", "value": low_activity_count}
    ]