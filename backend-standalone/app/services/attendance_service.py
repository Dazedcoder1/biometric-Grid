"""
Attendance Service - Core attendance processing logic
"""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.future import select
from sqlalchemy import desc, text
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, Dict, Any

from app.models.domain import AttendanceLog, User
from app.services.tenant_settings_service import (
    get_tenant_settings,
    calculate_late_status,
    calculate_valid_working_hours,
    invalidate_tenant_settings_cache
)


async def get_user_by_finger(tenant_id: int, finger_id: int, db: AsyncSession) -> Optional[User]:
    """Get user by fingerprint ID"""
    result = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.finger_id == finger_id,
            User.is_active == True
        )
    )
    return result.scalars().first()


async def process_attendance(
    tenant_id: int,
    device_id: str,
    finger_id: int,
    db: AsyncSession
) -> Tuple[AttendanceLog, str, bool, str]:
    """
    Process a single attendance punch (IN/OUT).
    
    Returns:
        (attendance_log, user_name, is_late, late_message)
    """
    now = datetime.now(timezone.utc)
    
    # Get tenant settings
    settings = await get_tenant_settings(tenant_id, db)
    
    # Get user
    user = await get_user_by_finger(tenant_id, finger_id, db)
    user_id = user.id if user else None
    user_name = user.name if user else "Unknown User"
    
    # Get today's start
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get last log for today
    result = await db.execute(
        select(AttendanceLog)
        .where(
            AttendanceLog.tenant_id == tenant_id,
            AttendanceLog.finger_id == finger_id,
            AttendanceLog.timestamp >= today
        )
        .order_by(desc(AttendanceLog.timestamp))
        .limit(1)
    )
    last_log = result.scalars().first()
    
    # Determine IN or OUT
    if not last_log or last_log.record_type == "OUT":
        record_type = "IN"
    else:
        record_type = "OUT"
    
    # Calculate late status (only for IN punches)
    is_late = False
    late_message = None
    if record_type == "IN" and user:
        is_late, late_message = calculate_late_status(now, settings)
    
    # Create attendance log
    log = AttendanceLog(
        tenant_id=tenant_id,
        device_id=device_id,
        finger_id=finger_id,
        user_id=user_id,
        timestamp=now,
        record_type=record_type
    )
    
    db.add(log)
    await db.commit()
    await db.refresh(log)
    
    return log, user_name, is_late, late_message or ""


async def process_bulk_attendance(
    tenant_id: int,
    device_id: str,
    logs: List[Any],
    db: AsyncSession
) -> int:
    """Process bulk attendance logs from offline device sync"""
    if not logs:
        return 0
    
    values = []
    
    for log_item in logs:
        user = await get_user_by_finger(tenant_id, log_item.finger_id, db)
        
        values.append({
            "tenant_id": tenant_id,
            "device_id": device_id,
            "finger_id": log_item.finger_id,
            "user_id": user.id if user else None,
            "timestamp": log_item.timestamp,
            "record_type": "IN"
        })
    
    stmt = insert(AttendanceLog).values(values)
    stmt = stmt.on_conflict_do_nothing(constraint='uix_attendance_record')
    
    result = await db.execute(stmt)
    await db.commit()
    
    return result.rowcount or 0


async def get_attendance_history(
    tenant_id: int,
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get attendance history with working hours calculation"""
    
    settings = await get_tenant_settings(tenant_id, db)
    
    query = """
        WITH daily_attendance AS (
            SELECT 
                user_id,
                DATE(timestamp) as attendance_date,
                MIN(CASE WHEN record_type = 'IN' THEN timestamp END) as check_in,
                MAX(CASE WHEN record_type = 'OUT' THEN timestamp END) as check_out
            FROM attendance_logs
            WHERE tenant_id = :tenant_id
    """
    
    params = {"tenant_id": tenant_id}
    
    if user_id:
        query += " AND user_id = :user_id"
        params["user_id"] = user_id
    
    query += """
            GROUP BY user_id, DATE(timestamp)
        )
        SELECT 
            u.id as user_id,
            u.name as user_name,
            u.employee_code,
            d.department_name,
            da.attendance_date,
            da.check_in,
            da.check_out
        FROM daily_attendance da
        JOIN users u ON da.user_id = u.id
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE u.tenant_id = :tenant_id
        ORDER BY da.attendance_date DESC
        LIMIT :limit OFFSET :offset
    """
    
    params["limit"] = limit
    params["offset"] = offset
    
    result = await db.execute(text(query), params)
    rows = result.mappings().all()
    
    # Enrich with working hours calculation
    enriched_rows = []
    for row in rows:
        valid_hours, actual_duration, lost_hours, met_min_hours, status_msg = calculate_valid_working_hours(
            row["check_in"],
            row["check_out"],
            settings
        )
        
        enriched_rows.append({
            "date": row["attendance_date"],
            "user_id": row["user_id"],
            "user_name": row["user_name"],
            "employee_code": row["employee_code"],
            "department_name": row["department_name"],
            "check_in": row["check_in"],
            "check_out": row["check_out"],
            "hours_worked": valid_hours,
            "actual_duration": actual_duration,
            "lost_hours": lost_hours,
            "met_min_hours": met_min_hours,
            "status_message": status_msg
        })
    
    return enriched_rows


async def get_today_summary(
    tenant_id: int,
    db: AsyncSession,
    dept_id: Optional[int] = None
) -> Dict[str, Any]:
    """Get today's attendance summary with statistics"""
    
    settings = await get_tenant_settings(tenant_id, db)
    today = datetime.now().date()
    
    # Get all active employees
    emp_query = """
        SELECT u.id, u.name, u.employee_code, u.dept_id, d.department_name
        FROM users u
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE u.tenant_id = :tenant_id
        AND u.role = 'employee'
        AND u.is_active = true
    """
    
    emp_params = {"tenant_id": tenant_id}
    if dept_id:
        emp_query += " AND u.dept_id = :dept_id"
        emp_params["dept_id"] = dept_id
    
    employees_result = await db.execute(text(emp_query), emp_params)
    employees = employees_result.mappings().all()
    
    # Get today's attendance
    att_query = """
        SELECT 
            user_id,
            MIN(CASE WHEN record_type = 'IN' THEN timestamp END) as check_in,
            MAX(CASE WHEN record_type = 'OUT' THEN timestamp END) as check_out
        FROM attendance_logs
        WHERE tenant_id = :tenant_id
        AND DATE(timestamp) = CURRENT_DATE
        GROUP BY user_id
    """
    
    attendance_result = await db.execute(text(att_query), {"tenant_id": tenant_id})
    attendance_map = {row["user_id"]: row for row in attendance_result.mappings().all()}
    
    # Build summary for each employee
    employee_summaries = []
    present_count = 0
    late_count = 0
    met_min_hours_count = 0
    total_valid_hours = 0
    
    for emp in employees:
        att = attendance_map.get(emp["id"])
        
        if att and att["check_in"]:
            present_count += 1
            is_late, _ = calculate_late_status(att["check_in"], settings)
            if is_late:
                late_count += 1
            
            valid_hours, actual_duration, lost_hours, met_min, status_msg = calculate_valid_working_hours(
                att["check_in"],
                att["check_out"],
                settings
            )
            if met_min:
                met_min_hours_count += 1
            total_valid_hours += valid_hours
        else:
            valid_hours = 0
            met_min = False
            is_late = False
            status_msg = "No check-in"
        
        employee_summaries.append({
            "id": emp["id"],
            "name": emp["name"],
            "employee_code": emp["employee_code"],
            "department_name": emp["department_name"],
            "check_in": att["check_in"] if att else None,
            "check_out": att["check_out"] if att else None,
            "hours_worked": valid_hours,
            "met_min_hours": met_min,
            "is_late": is_late,
            "status_message": status_msg
        })
    
    total_employees = len(employees)
    absent_count = total_employees - present_count
    avg_hours = total_valid_hours / present_count if present_count > 0 else 0
    
    return {
        "date": today,
        "summary": {
            "total_employees": total_employees,
            "present": present_count,
            "absent": absent_count,
            "late": late_count,
            "on_time": present_count - late_count,
            "met_minimum_hours": met_min_hours_count,
            "attendance_rate": round((present_count / total_employees * 100), 1) if total_employees > 0 else 0,
            "compliance_rate": round((met_min_hours_count / present_count * 100), 1) if present_count > 0 else 0,
            "average_valid_hours": round(avg_hours, 1)
        },
        "employees": employee_summaries
    }