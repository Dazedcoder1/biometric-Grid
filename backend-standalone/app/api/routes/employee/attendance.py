from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, date
from typing import Optional
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User
from app.services.tenant_settings_service import (
    get_tenant_settings, 
    calculate_valid_working_hours, 
    calculate_late_status
)

router = APIRouter()


@router.get("/attendance/today")
async def get_today_attendance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get today's attendance with working hours"""
    
    # Get tenant settings
    settings = await get_tenant_settings(current_user.tenant_id, db)
    
    query = text("""
        SELECT
            MIN(timestamp) FILTER (WHERE record_type = 'IN') as check_in,
            MAX(timestamp) FILTER (WHERE record_type = 'OUT') as check_out
        FROM attendance_logs
        WHERE user_id = :user_id
        AND DATE(timestamp) = CURRENT_DATE
    """)
    
    result = await db.execute(query, {"user_id": current_user.id})
    data = result.mappings().first()
    
    if not data or not data["check_in"]:
        return {
            "check_in": None,
            "check_out": None,
            "hours_worked": 0,
            "met_min_hours": False,
            "status": "absent",
            "is_late": False
        }
    
    valid_hours, actual_duration, lost_hours, met_min_hours, status_msg = calculate_valid_working_hours(
        data["check_in"],
        data["check_out"],
        settings
    )
    
    is_late, _ = calculate_late_status(data["check_in"], settings)
    
    return {
        "check_in": data["check_in"],
        "check_out": data["check_out"],
        "hours_worked": round(valid_hours, 2),
        "actual_duration": round(actual_duration, 2),
        "met_min_hours": met_min_hours,
        "is_late": is_late,
        "status": "present" if data["check_in"] else "absent"
    }


@router.get("/attendance")
async def get_attendance_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 90
):
    """Employee: Get personal attendance history with working hours"""
    
    # Get tenant settings
    settings = await get_tenant_settings(current_user.tenant_id, db)
    
    query = text("""
        SELECT
            DATE(timestamp) as attendance_date,
            MIN(timestamp) FILTER (WHERE record_type = 'IN') as check_in,
            MAX(timestamp) FILTER (WHERE record_type = 'OUT') as check_out
        FROM attendance_logs
        WHERE user_id = :user_id
        GROUP BY DATE(timestamp)
        ORDER BY attendance_date DESC
        LIMIT :limit
    """)
    
    result = await db.execute(query, {
        "user_id": current_user.id,
        "limit": limit
    })
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
            "date": str(row["attendance_date"]),
            "check_in": row["check_in"],
            "check_out": row["check_out"],
            "hours_worked": round(valid_hours, 2),
            "met_min_hours": met_min_hours,
            "is_late": is_late,
            "status": "present" if row["check_in"] else "absent",
            "punctuality": "late" if is_late else "on_time"
        })
    
    return enriched_rows


@router.get("/attendance/stats")
async def get_attendance_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get overall attendance statistics with working hours compliance"""
    
    # Get tenant settings
    settings = await get_tenant_settings(current_user.tenant_id, db)
    
    # Get all attendance records for the employee
    query = text("""
        SELECT
            DATE(timestamp) as attendance_date,
            MIN(timestamp) FILTER (WHERE record_type = 'IN') as check_in,
            MAX(timestamp) FILTER (WHERE record_type = 'OUT') as check_out
        FROM attendance_logs
        WHERE user_id = :user_id
        GROUP BY DATE(timestamp)
        ORDER BY attendance_date DESC
    """)
    
    result = await db.execute(query, {"user_id": current_user.id})
    rows = result.mappings().all()
    
    total_days = len(rows)
    days_with_checkin = 0
    days_met_min_hours = 0
    days_late = 0
    total_valid_hours = 0
    
    for row in rows:
        if row["check_in"]:
            days_with_checkin += 1
            
            valid_hours, _, _, met_min, _ = calculate_valid_working_hours(
                row["check_in"],
                row["check_out"],
                settings
            )
            total_valid_hours += valid_hours
            
            if met_min:
                days_met_min_hours += 1
            
            is_late, _ = calculate_late_status(row["check_in"], settings)
            if is_late:
                days_late += 1
    
    return {
        "total_days_worked": days_with_checkin,
        "total_valid_hours": round(total_valid_hours, 2),
        "days_met_min_hours": days_met_min_hours,
        "days_late": days_late,
        "compliance_rate": round((days_met_min_hours / days_with_checkin * 100), 1) if days_with_checkin > 0 else 0,
        "average_hours": round(total_valid_hours / days_with_checkin, 1) if days_with_checkin > 0 else 0
    }


@router.get("/attendance/stats/monthly")
async def get_monthly_stats(
    month: int,
    year: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get monthly attendance statistics with working hours compliance"""
    
    # Get tenant settings
    settings = await get_tenant_settings(current_user.tenant_id, db)
    
    # Get all attendance records for the month
    query = text("""
        SELECT
            DATE(timestamp) as attendance_date,
            MIN(timestamp) FILTER (WHERE record_type = 'IN') as check_in,
            MAX(timestamp) FILTER (WHERE record_type = 'OUT') as check_out
        FROM attendance_logs
        WHERE user_id = :user_id
        AND EXTRACT(MONTH FROM timestamp) = :month
        AND EXTRACT(YEAR FROM timestamp) = :year
        GROUP BY DATE(timestamp)
    """)
    
    result = await db.execute(query, {
        "user_id": current_user.id,
        "month": month,
        "year": year
    })
    rows = result.mappings().all()
    
    # Calculate statistics
    present_days = 0
    days_met_min_hours = 0
    late_days = 0
    on_time_days = 0
    total_valid_hours = 0
    
    for row in rows:
        if row["check_in"]:
            present_days += 1
            
            valid_hours, _, _, met_min, _ = calculate_valid_working_hours(
                row["check_in"],
                row["check_out"],
                settings
            )
            total_valid_hours += valid_hours
            
            if met_min:
                days_met_min_hours += 1
            
            is_late, _ = calculate_late_status(row["check_in"], settings)
            if is_late:
                late_days += 1
            else:
                on_time_days += 1
    
    # Calculate working days in month (Mon-Fri)
    from calendar import monthrange
    import datetime as dt
    
    first_day = dt.date(year, month, 1)
    last_day = dt.date(year, month, monthrange(year, month)[1])
    
    working_days = 0
    current = first_day
    while current <= last_day:
        if current.weekday() < 5:  # Monday to Friday
            working_days += 1
        current += dt.timedelta(days=1)
    
    absent_days = max(0, working_days - present_days)
    attendance_percentage = round((present_days / working_days * 100), 1) if working_days > 0 else 0
    compliance_rate = round((days_met_min_hours / present_days * 100), 1) if present_days > 0 else 0
    avg_hours = round(total_valid_hours / present_days, 1) if present_days > 0 else 0
    
    return {
        "present_days": present_days,
        "days_met_min_hours": days_met_min_hours,
        "total_hours": round(total_valid_hours, 1),
        "attendance_percentage": attendance_percentage,
        "total_days_in_month": monthrange(year, month)[1],
        "estimated_working_days": working_days,
        "absent_days": absent_days,
        "late_days": late_days,
        "on_time_days": on_time_days,
        "overtime_hours": 0,
        "average_hours_per_day": avg_hours,
        "compliance_rate": compliance_rate
    }


@router.get("/attendance/{date_str}")
async def get_attendance_by_date(
    date_str: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get attendance for a specific date (YYYY-MM-DD)"""
    
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")
    
    # Get tenant settings
    settings = await get_tenant_settings(current_user.tenant_id, db)
    
    query = text("""
        SELECT
            MIN(timestamp) FILTER (WHERE record_type = 'IN') as check_in,
            MAX(timestamp) FILTER (WHERE record_type = 'OUT') as check_out
        FROM attendance_logs
        WHERE user_id = :user_id AND DATE(timestamp) = :target_date
    """)
    
    result = await db.execute(query, {
        "user_id": current_user.id,
        "target_date": target_date
    })
    data = result.mappings().first()
    
    if not data or not data["check_in"]:
        return {
            "date": date_str,
            "check_in": None,
            "check_out": None,
            "hours_worked": 0,
            "met_min_hours": False,
            "status": "absent",
            "is_late": False
        }
    
    valid_hours, actual_duration, lost_hours, met_min_hours, status_msg = calculate_valid_working_hours(
        data["check_in"],
        data["check_out"],
        settings
    )
    
    is_late, _ = calculate_late_status(data["check_in"], settings)
    
    return {
        "date": date_str,
        "check_in": data["check_in"],
        "check_out": data["check_out"],
        "hours_worked": round(valid_hours, 2),
        "met_min_hours": met_min_hours,
        "is_late": is_late,
        "status": "present" if data["check_in"] else "absent"
    }