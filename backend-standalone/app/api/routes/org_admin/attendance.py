"""
Org Admin Attendance Routes
Handles attendance viewing for department administrators
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import date, datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import pytz

from app.db.session import get_db
from app.api.dependencies import require_role
from app.models.domain import User
from app.services.tenant_settings_service import (
    get_tenant_settings, 
    calculate_valid_working_hours, 
    calculate_late_status,
    ensure_timezone_aware
)

router = APIRouter()

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')


@router.get("/attendance/today")
async def today_attendance(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Org Admin: Today's attendance for department with working hours calculation
    """
    try:
        # Get tenant settings
        settings = await get_tenant_settings(current_user.tenant_id, db)
        
        # Get today's date in IST
        now_ist = datetime.now(IST)
        today_date_ist = now_ist.date()
        
        # Create UTC range for today in IST
        # Convert IST start of day to UTC
        ist_start = IST.localize(datetime.combine(today_date_ist, datetime.min.time()))
        utc_start = ist_start.astimezone(timezone.utc)
        utc_end = utc_start + timedelta(days=1) - timedelta(microseconds=1)
        
        # Query using UTC timestamp range
        result = await db.execute(text("""
            SELECT 
                u.id, 
                u.name, 
                u.employee_code,
                MIN(CASE WHEN a.record_type = 'IN' THEN a.timestamp END) as check_in,
                MAX(CASE WHEN a.record_type = 'OUT' THEN a.timestamp END) as check_out
            FROM users u
            LEFT JOIN attendance_logs a ON u.id = a.user_id 
                AND a.timestamp >= :start_datetime
                AND a.timestamp <= :end_datetime
            WHERE u.tenant_id = :tenant_id 
                AND u.dept_id = :dept_id 
                AND u.role = 'employee' 
                AND u.is_active = true
            GROUP BY u.id, u.name, u.employee_code
            ORDER BY u.name
        """), {
            "tenant_id": current_user.tenant_id, 
            "dept_id": current_user.dept_id,
            "start_datetime": utc_start,
            "end_datetime": utc_end
        })
        
        rows = result.mappings().all()
        
        # Calculate working hours for each employee
        enriched_rows = []
        for row in rows:
            check_in = row["check_in"]
            check_out = row["check_out"]
            
            if check_in is None:
                enriched_rows.append({
                    "id": row["id"],
                    "name": row["name"],
                    "employee_code": row["employee_code"],
                    "check_in": None,
                    "check_out": None,
                    "hours_worked": 0,
                    "actual_duration": 0,
                    "lost_hours": 0,
                    "met_min_hours": False,
                    "is_late": False,
                    "late_message": "",
                    "status_message": "No check-in recorded",
                    "status": "absent"
                })
                continue
            
            # Ensure timestamps are timezone-aware and convert to IST for calculation
            check_in = ensure_timezone_aware(check_in).astimezone(IST)
            if check_out:
                check_out = ensure_timezone_aware(check_out).astimezone(IST)
            
            # Create a copy of settings with IST office hours
            # This ensures office hours are interpreted in IST
            settings_copy = settings.copy() if hasattr(settings, 'copy') else settings
            if hasattr(settings_copy, 'office_start_time') and settings_copy.office_start_time:
                # Keep office hours as is (they should be in IST)
                pass
            
            valid_hours, actual_duration, lost_hours, met_min_hours, status_msg = calculate_valid_working_hours(
                check_in,
                check_out,
                settings_copy
            )
            
            is_late, late_msg = calculate_late_status(check_in, settings_copy)
            
            # Convert back to UTC for storage in response
            enriched_rows.append({
                "id": row["id"],
                "name": row["name"],
                "employee_code": row["employee_code"],
                "check_in": check_in.astimezone(timezone.utc).isoformat() if check_in else None,
                "check_out": check_out.astimezone(timezone.utc).isoformat() if check_out else None,
                "hours_worked": round(valid_hours, 2),
                "actual_duration": round(actual_duration, 2),
                "lost_hours": round(lost_hours, 2),
                "met_min_hours": met_min_hours,
                "is_late": is_late,
                "late_message": late_msg,
                "status_message": status_msg,
                "status": "present"
            })
        
        # Calculate summary
        total = len(enriched_rows)
        present = len([r for r in enriched_rows if r["status"] == "present"])
        late = len([r for r in enriched_rows if r.get("is_late", False)])
        on_time = present - late
        met_min = len([r for r in enriched_rows if r.get("met_min_hours", False)])
        total_hours = sum([r.get("hours_worked", 0) for r in enriched_rows])
        
        return {
            "date": today_date_ist.isoformat(),
            "summary": {
                "total_employees": total,
                "present": present,
                "absent": total - present,
                "late": late,
                "on_time": on_time if on_time > 0 else 0,
                "met_minimum_hours": met_min,
                "attendance_rate": round((present / total * 100), 1) if total > 0 else 0,
                "compliance_rate": round((met_min / present * 100), 1) if present > 0 else 0,
                "total_valid_hours": round(total_hours, 1),
                "average_hours": round(total_hours / present, 1) if present > 0 else 0
            },
            "employees": enriched_rows
        }
        
    except Exception as e:
        import traceback
        print(f"Error in today_attendance: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching today's attendance: {str(e)}"
        )


@router.get("/attendance/date/{attendance_date}")
async def attendance_by_date(
    attendance_date: date,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    """
    Org Admin: Attendance for specific date with working hours calculation
    """
    try:
        # Get tenant settings
        settings = await get_tenant_settings(current_user.tenant_id, db)
        
        # Convert the input date to IST date
        # The attendance_date is treated as IST date
        ist_date = attendance_date
        
        # Create UTC range for the IST date
        # Convert IST start of day to UTC
        ist_start = IST.localize(datetime.combine(ist_date, datetime.min.time()))
        utc_start = ist_start.astimezone(timezone.utc)
        utc_end = utc_start + timedelta(days=1) - timedelta(microseconds=1)
        
        print(f"Querying for IST date: {ist_date}")
        print(f"UTC range: {utc_start} to {utc_end}")
        
        # Query using timestamp range
        result = await db.execute(text("""
            SELECT 
                u.id, 
                u.name, 
                u.employee_code,
                MIN(CASE WHEN a.record_type = 'IN' THEN a.timestamp END) as check_in,
                MAX(CASE WHEN a.record_type = 'OUT' THEN a.timestamp END) as check_out
            FROM users u
            LEFT JOIN attendance_logs a ON u.id = a.user_id 
                AND a.timestamp >= :start_datetime
                AND a.timestamp <= :end_datetime
            WHERE u.tenant_id = :tenant_id 
                AND u.dept_id = :dept_id 
                AND u.role = 'employee' 
                AND u.is_active = true
            GROUP BY u.id, u.name, u.employee_code
            ORDER BY u.name
        """), {
            "tenant_id": current_user.tenant_id,
            "dept_id": current_user.dept_id,
            "start_datetime": utc_start,
            "end_datetime": utc_end
        })
        
        rows = result.mappings().all()
        
        print(f"Found {len(rows)} employees for date {ist_date}")
        
        # Calculate working hours for each employee
        enriched_rows = []
        for row in rows:
            check_in = row["check_in"]
            check_out = row["check_out"]
            
            if check_in is None:
                enriched_rows.append({
                    "id": row["id"],
                    "name": row["name"],
                    "employee_code": row["employee_code"],
                    "check_in": None,
                    "check_out": None,
                    "hours_worked": 0,
                    "actual_duration": 0,
                    "lost_hours": 0,
                    "met_min_hours": False,
                    "is_late": False,
                    "late_message": "",
                    "status_message": "No check-in recorded",
                    "status": "absent"
                })
                continue
            
            # Convert UTC timestamps to IST for calculation
            check_in_ist = ensure_timezone_aware(check_in).astimezone(IST)
            check_out_ist = ensure_timezone_aware(check_out).astimezone(IST) if check_out else None
            
            print(f"Processing {row['name']}: IN_IST={check_in_ist}, OUT_IST={check_out_ist}")
            
            # Calculate working hours (office hours are in IST)
            valid_hours, actual_duration, lost_hours, met_min_hours, status_msg = calculate_valid_working_hours(
                check_in_ist,
                check_out_ist,
                settings
            )
            
            is_late, late_msg = calculate_late_status(check_in_ist, settings)
            
            # Keep UTC in response for consistency
            enriched_rows.append({
                "id": row["id"],
                "name": row["name"],
                "employee_code": row["employee_code"],
                "check_in": check_in.isoformat() if check_in else None,
                "check_out": check_out.isoformat() if check_out else None,
                "hours_worked": round(valid_hours, 2),
                "actual_duration": round(actual_duration, 2),
                "lost_hours": round(lost_hours, 2),
                "met_min_hours": met_min_hours,
                "is_late": is_late,
                "late_message": late_msg,
                "status_message": status_msg,
                "status": "present"
            })
        
        # Calculate summary
        total = len(enriched_rows)
        present = len([r for r in enriched_rows if r["status"] == "present"])
        late = len([r for r in enriched_rows if r.get("is_late", False)])
        on_time = present - late
        met_min = len([r for r in enriched_rows if r.get("met_min_hours", False)])
        total_hours = sum([r.get("hours_worked", 0) for r in enriched_rows])
        
        return {
            "date": ist_date.isoformat(),
            "summary": {
                "total_employees": total,
                "present": present,
                "absent": total - present,
                "late": late,
                "on_time": on_time if on_time > 0 else 0,
                "met_minimum_hours": met_min,
                "attendance_rate": round((present / total * 100), 1) if total > 0 else 0,
                "compliance_rate": round((met_min / present * 100), 1) if present > 0 else 0,
                "total_valid_hours": round(total_hours, 1),
                "average_hours": round(total_hours / present, 1) if present > 0 else 0
            },
            "employees": enriched_rows
        }
        
    except Exception as e:
        import traceback
        print(f"Error in attendance_by_date: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching attendance for {attendance_date}: {str(e)}"
        )


# ... (rest of the endpoints - summary and employee history remain the same 
# but also need similar timezone fixes)