from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from datetime import datetime, timedelta
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, AttendanceLog, Holiday, Leave
from app.schemas.schemas import EmployeeDashboardResponse
import calendar

router = APIRouter()

@router.get("/dashboard", response_model=EmployeeDashboardResponse)
async def get_employee_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unified endpoint for the Employee Dashboard (React)"""
    
    # 1. Today's presence
    today_res = await db.execute(text("""
        SELECT 
            MIN(timestamp) FILTER (WHERE record_type = 'IN') as check_in,
            MAX(timestamp) FILTER (WHERE record_type = 'OUT') as check_out,
            EXTRACT(EPOCH FROM (MAX(timestamp) FILTER (WHERE record_type = 'OUT') - 
                               MIN(timestamp) FILTER (WHERE record_type = 'IN')))/3600 as hours
        FROM attendance_logs 
        WHERE user_id = :u_id AND DATE(timestamp) = CURRENT_DATE
    """), {"u_id": current_user.id})
    today = today_res.mappings().first()

    # 2. Monthly Stats
    month = datetime.now().month
    year = datetime.now().year
    _, last_day = calendar.monthrange(year, month)
    
    stats_res = await db.execute(text("""
        SELECT 
            COUNT(DISTINCT DATE(timestamp)) as present,
            SUM(CASE WHEN (timestamp::time > '09:15:00' AND record_type='IN') THEN 1 ELSE 0 END) as late
        FROM attendance_logs 
        WHERE user_id = :u_id 
          AND EXTRACT(MONTH FROM timestamp) = :m
          AND EXTRACT(YEAR FROM timestamp) = :y
    """), {"u_id": current_user.id, "m": month, "y": year})
    stats = stats_res.mappings().first()
    
    present_count = stats["present"] or 0
    # Simple working days calculation (excluding weekends)
    total_working = sum(1 for d in range(1, last_day+1) if datetime(year, month, d).weekday() < 5)

    # 3. Upcoming Holiday
    holiday_stmt = select(Holiday).where(
        Holiday.tenant_id == current_user.tenant_id,
        Holiday.holiday_date >= datetime.now()
    ).order_by(Holiday.holiday_date).limit(1)
    holiday = (await db.execute(holiday_stmt)).scalars().first()

    # 4. Pending Leaves
    leave_count_stmt = select(func.count(Leave.leave_id)).where(
        Leave.employee_id == current_user.id,
        Leave.status == "pending"
    )
    pending_leaves = (await db.execute(leave_count_stmt)).scalar() or 0

    # 5. Last Check-in
    last_in_stmt = select(AttendanceLog.timestamp).where(
        AttendanceLog.user_id == current_user.id,
        AttendanceLog.record_type == 'IN'
    ).order_by(AttendanceLog.timestamp.desc()).limit(1)
    last_in = (await db.execute(last_in_stmt)).scalar()

    return {
        "today_status": "present" if today["check_in"] else "absent",
        "check_in": today["check_in"],
        "check_out": today["check_out"],
        "working_hours": round(today["hours"] or 0, 2),
        
        "monthly_attendance_pct": round((present_count / total_working * 100) if total_working > 0 else 0, 1),
        "present_days_count": present_count,
        "absent_days_count": max(0, total_working - present_count),
        "late_days_count": stats["late"] or 0,
        
        "upcoming_holiday": holiday,
        "pending_leaves_count": pending_leaves,
        "last_check_in": last_in,
        
        "attendance_trend": [7.5, 8.2, 6.5, 9.0] # Dummy for chart
    }