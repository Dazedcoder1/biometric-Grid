"""
Tenant Attendance Routes
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant
from app.services.attendance_service import get_today_summary, get_attendance_history
from app.services.tenant_settings_service import get_tenant_settings, calculate_valid_working_hours, calculate_late_status

router = APIRouter()


class EmployeeAttendanceResponse(BaseModel):
    id: int
    name: str
    employee_code: Optional[str]
    department_name: Optional[str]
    check_in: Optional[datetime]
    check_out: Optional[datetime]
    hours_worked: float
    met_min_hours: bool
    is_late: bool


class AttendanceSummaryResponse(BaseModel):
    date: date
    summary: dict
    employees: List[EmployeeAttendanceResponse]


@router.get("/attendance/today", response_model=AttendanceSummaryResponse)
async def get_today_attendance(
    dept_id: Optional[int] = Query(None, description="Filter by department ID"),
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Get today's attendance with working hours compliance"""
    result = await get_today_summary(tenant.id, db, dept_id)
    return result


@router.get("/attendance/date/{attendance_date}")
async def attendance_by_date(
    attendance_date: date,
    dept_id: Optional[int] = None,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Get attendance for a specific date with working hours"""
    
    from sqlalchemy import text
    
    settings = await get_tenant_settings(tenant.id, db)
    
    query = """
        SELECT 
            u.id as user_id,
            u.name as user_name,
            u.employee_code,
            d.department_name,
            MIN(CASE WHEN a.record_type = 'IN' THEN a.timestamp END) as check_in,
            MAX(CASE WHEN a.record_type = 'OUT' THEN a.timestamp END) as check_out
        FROM users u
        LEFT JOIN departments d ON u.dept_id = d.department_id
        LEFT JOIN attendance_logs a ON u.id = a.user_id 
            AND DATE(a.timestamp) = :attendance_date
        WHERE u.tenant_id = :tenant_id
        AND u.role = 'employee'
        AND u.is_active = true
    """
    
    params = {
        "tenant_id": tenant.id,
        "attendance_date": attendance_date
    }
    
    if dept_id:
        query += " AND u.dept_id = :dept_id"
        params["dept_id"] = dept_id
    
    query += " GROUP BY u.id, u.name, u.employee_code, d.department_name ORDER BY u.name"
    
    result = await db.execute(text(query), params)
    rows = result.mappings().all()
    
    enriched_rows = []
    for row in rows:
        valid_hours, actual_duration, lost_hours, met_min_hours, status_msg = calculate_valid_working_hours(
            row["check_in"],
            row["check_out"],
            settings
        )
        
        is_late = False
        if row["check_in"]:
            is_late, _ = calculate_late_status(row["check_in"], settings)
        
        enriched_rows.append({
            "id": row["user_id"],
            "name": row["user_name"],
            "employee_code": row["employee_code"],
            "department_name": row["department_name"],
            "check_in": row["check_in"],
            "check_out": row["check_out"],
            "hours_worked": round(valid_hours, 2),
            "actual_duration": round(actual_duration, 2),
            "lost_hours": round(lost_hours, 2),
            "met_min_hours": met_min_hours,
            "is_late": is_late,
            "status_message": status_msg,
            "status": "present" if row["check_in"] else "absent"
        })
    
    total = len(enriched_rows)
    present = len([r for r in enriched_rows if r["check_in"]])
    late = len([r for r in enriched_rows if r["is_late"]])
    met_min = len([r for r in enriched_rows if r["met_min_hours"]])
    total_valid_hours = sum([r["hours_worked"] for r in enriched_rows])
    total_lost_hours = sum([r["lost_hours"] for r in enriched_rows])
    
    return {
        "date": attendance_date,
        "summary": {
            "total_employees": total,
            "present": present,
            "absent": total - present,
            "late_checkins": late,
            "on_time_checkins": present - late,
            "met_minimum_hours": met_min,
            "attendance_rate": round((present / total * 100), 1) if total > 0 else 0,
            "compliance_rate": round((met_min / present * 100), 1) if present > 0 else 0,
            "total_valid_hours": round(total_valid_hours, 1),
            "total_lost_hours": round(total_lost_hours, 1)
        },
        "employees": enriched_rows
    }


@router.get("/attendance/settings")
async def get_attendance_settings(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Get attendance-related settings for the tenant"""
    
    settings = await get_tenant_settings(tenant.id, db)
    
    return {
        "office_start_time": settings["office_start_time"],
        "office_start": settings["office_start"].strftime("%H:%M"),
        "office_end_time": settings["office_end_time"],
        "office_end": settings["office_end"].strftime("%H:%M"),
        "late_threshold_minutes": settings["late_threshold_minutes"],
        "min_working_hours": settings["min_working_hours"],
        "working_days": settings["working_days"]
    }