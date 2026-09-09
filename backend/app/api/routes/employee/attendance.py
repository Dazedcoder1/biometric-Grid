from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from datetime import datetime, date, timedelta
from typing import List
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, AttendanceLog, Holiday
from app.schemas.schemas import AttendanceLogResponse, AttendanceStats, MonthlyStats
import calendar

router = APIRouter()

@router.get("/attendance/today", response_model=dict)
async def get_today_attendance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get today's check-in/out status and hours"""
    result = await db.execute(text("""
        SELECT 
            MIN(timestamp) FILTER (WHERE record_type = 'IN') as check_in,
            MAX(timestamp) FILTER (WHERE record_type = 'OUT') as check_out,
            EXTRACT(EPOCH FROM (MAX(timestamp) FILTER (WHERE record_type = 'OUT') - 
                               MIN(timestamp) FILTER (WHERE record_type = 'IN')))/3600 as hours
        FROM attendance_logs 
        WHERE user_id = :u_id AND DATE(timestamp) = CURRENT_DATE
    """), {"u_id": current_user.id})
    
    row = result.mappings().first()
    return {
        "status": "present" if row["check_in"] else "absent",
        "check_in": row["check_in"],
        "check_out": row["check_out"],
        "working_hours": round(row["hours"] or 0, 2)
    }

@router.get("/attendance/stats", response_model=AttendanceStats)
async def get_attendance_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Total stats for the current user"""
    result = await db.execute(text("""
        SELECT 
            COUNT(DISTINCT DATE(timestamp)) as present_days,
            SUM(CASE WHEN (timestamp::time > '09:15:00' AND record_type='IN') THEN 1 ELSE 0 END) as late_days,
            SUM(EXTRACT(EPOCH FROM (timestamp)))/3600 as total_hours
        FROM attendance_logs 
        WHERE user_id = :u_id
    """), {"u_id": current_user.id})
    
    row = result.mappings().first()
    pres = row["present_days"] or 0
    return {
        "total_present_days": pres,
        "total_late_days": row["late_days"] or 0,
        "total_hours_worked": round(row["total_hours"] or 0, 2),
        "average_hours_per_day": round(row["total_hours"] / pres if pres > 0 else 0, 2)
    }

@router.get("/attendance/stats/monthly", response_model=MonthlyStats)
async def get_monthly_stats(
    month: int = None,
    year: int = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not month: month = datetime.now().month
    if not year: year = datetime.now().year
    
    # 1. Total working days in month (simplification: weekdays)
    _, last_day = calendar.monthrange(year, month)
    working_days = 0
    for d in range(1, last_day + 1):
        if date(year, month, d).weekday() < 5: # Mon-Fri
            working_days += 1
            
    # 2. Actual presence
    res = await db.execute(text("""
        SELECT COUNT(DISTINCT DATE(timestamp)) 
        FROM attendance_logs 
        WHERE user_id = :u_id 
          AND EXTRACT(MONTH FROM timestamp) = :m
          AND EXTRACT(YEAR FROM timestamp) = :y
    """), {"u_id": current_user.id, "m": month, "y": year})
    present = res.scalar() or 0
    
    return {
        "month": month,
        "year": year,
        "attendance_percentage": round((present / working_days * 100) if working_days > 0 else 0, 1),
        "present_days": present,
        "absent_days": max(0, working_days - present),
        "late_days": 0 # TODO: Implement late logic for monthly
    }

@router.get("/attendance/hours/summary")
async def get_hours_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Weekly/Monthly hours for trend chart"""
    # Just returning some dummy weekly data for now to power the chart
    return [8.5, 7.2, 8.0, 9.1]

@router.get("/attendance/calendar")
async def get_attendance_calendar(
    month: int,
    year: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns a list of dates with status for the calendar view"""
    result = await db.execute(text("""
        SELECT DATE(timestamp) as dt, MIN(record_type) as status
        FROM attendance_logs
        WHERE user_id = :u_id 
          AND EXTRACT(MONTH FROM timestamp) = :m
          AND EXTRACT(YEAR FROM timestamp) = :y
        GROUP BY DATE(timestamp)
    """), {"u_id": current_user.id, "m": month, "y": year})
    
    return [{"date": str(r.dt), "status": "present"} for r in result]

@router.get("/attendance", response_model=List[AttendanceLogResponse])
async def get_attendance(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get raw log history"""
    stmt = select(AttendanceLog).where(AttendanceLog.user_id == current_user.id).order_by(AttendanceLog.timestamp.desc()).limit(limit)
    res = await db.execute(stmt)
    logs = res.scalars().all()
    return logs