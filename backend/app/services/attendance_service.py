from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.future import select
from sqlalchemy import desc
from app.models.domain import AttendanceLog, User
import datetime

async def process_attendance(tenant_id: int, device_id: str, finger_id: int, db: AsyncSession):
    """Logs attendance directly to DB with automatic IN/OUT toggling and fetches User name."""
    
    # 1. Lookup the User
    user_stmt = select(User).where(User.tenant_id == tenant_id, User.finger_id == finger_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalars().first()
    user_name = user.name if user else "Unknown User"
    user_id = user.id if user else None
    
    # 2. Reset cycle every night at midnight (local/server time)
    now = datetime.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 3. Fetch the user's most recent log for today
    stmt = select(AttendanceLog).where(
        AttendanceLog.tenant_id == tenant_id,
        AttendanceLog.finger_id == finger_id,
        AttendanceLog.timestamp >= today_start
    ).order_by(desc(AttendanceLog.timestamp)).limit(1)
    
    result = await db.execute(stmt)
    last_log = result.scalars().first()
    
    # 4. Toggle Logic (Default to IN if no previous record exists today)
    current_type = "IN"
    if last_log and last_log.record_type == "IN":
        current_type = "OUT"
        
    # 5. Save the new log
    log = AttendanceLog(
        tenant_id=tenant_id,
        device_id=device_id,
        user_id=user_id, # <--- FIXED
        finger_id=finger_id,
        timestamp=datetime.datetime.now(),
        record_type=current_type
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    
    # Return both the log and the user_name
    return log, user_name


async def process_bulk_attendance(tenant_id: int, device_id: str, logs: list, db: AsyncSession):
    """Handles offline sync logs."""
    if not logs:
        return 0

    values = [
        {
            "tenant_id": tenant_id,
            "device_id": device_id,
            "finger_id": l.finger_id,
            "timestamp": l.timestamp,
            "record_type": "IN" # Offline sync default to IN for now to avoid logic mess
        }
        for l in logs
    ]

    stmt = insert(AttendanceLog).values(values)
    stmt = stmt.on_conflict_do_nothing(constraint='uix_attendance_record')
    
    result = await db.execute(stmt)
    await db.commit()
    
    return result.rowcount
async def get_attendance_history(tenant_id: int, db: AsyncSession):
    """Fetches the last 50 attendance records."""
    stmt = (
        select(AttendanceLog, User.name)
        .outerjoin(
            User, 
            (AttendanceLog.tenant_id == User.tenant_id) & (AttendanceLog.finger_id == User.finger_id)
        )
        .where(AttendanceLog.tenant_id == tenant_id)
        .order_by(AttendanceLog.timestamp.desc())
        .limit(50)
    )
    
    result = await db.execute(stmt)
    
    # .mappings() safely turns the result into dictionary-like objects
    response_data = []
    for row in result.mappings():
        log = row["AttendanceLog"]
        user_name = row["name"]
        
        response_data.append({
            "timestamp": log.timestamp,
            "finger_id": log.finger_id,
            "device_id": log.device_id,
            "record_type": log.record_type,
            "user_name": user_name if user_name else "Unknown"
        })
        
    return response_data