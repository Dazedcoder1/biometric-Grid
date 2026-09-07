from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db, verify_device
from app.schemas.schemas import BulkAttendanceRequest, AttendanceLogResponse
from app.services.attendance_service import (
    process_attendance,
    process_bulk_attendance,
    get_attendance_history
)
from app.services.notification_service import notify_single_user
from typing import List

router = APIRouter()


async def create_attendance_notifications_bg(
    tenant_id: int,
    user_id: int,
    log_id: int,
    record_type: str,
    punch_time: str,
    is_late: bool,
    db: AsyncSession
):
    """Background task: Create attendance notifications"""
    
    # Notify employee of punch
    await notify_single_user(
        db=db,
        tenant_id=tenant_id,
        actor_id=None,
        recipient_id=user_id,
        event_type="attendance_marked",
        title=f"Attendance {record_type}",
        message=f"You punched {record_type} at {punch_time}",
        entity_type="Attendance",
        entity_id=log_id
    )
    
    # Late arrival notification
    if is_late:
        await notify_single_user(
            db=db,
            tenant_id=tenant_id,
            actor_id=None,
            recipient_id=user_id,
            event_type="late_arrival",
            title="Late Arrival",
            message=f"You arrived late today at {punch_time}",
            entity_type="Attendance",
            entity_id=log_id
        )


@router.post("/mark")
async def mark_attendance(
    finger_id: int,
    background_tasks: BackgroundTasks,
    device = Depends(verify_device),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = device.tenant_id

    log, user_name, is_late, late_message = await process_attendance(
        tenant_id,
        device.device_id,
        finger_id,
        db
    )
    
    # Schedule notifications in BACKGROUND
    if log.user_id:
        punch_time = log.timestamp.strftime("%H:%M")
        
        background_tasks.add_task(
            create_attendance_notifications_bg,
            tenant_id=tenant_id,
            user_id=log.user_id,
            log_id=log.id,
            record_type=log.record_type,
            punch_time=punch_time,
            is_late=is_late,
            db=db
        )

    return {
        "status": "success",
        "user_id": log.user_id,
        "finger_id": log.finger_id,
        "record_type": log.record_type,
        "user_name": user_name,
        "is_late": is_late,
        "late_message": late_message,
        "message": f"Successfully marked {log.record_type}"
    }


@router.post("/sync-offline")
async def sync_offline_attendance(
    payload: BulkAttendanceRequest,
    device = Depends(verify_device),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = device.tenant_id
    count = await process_bulk_attendance(tenant_id, device.device_id, payload.logs, db)
    return {"status": "success", "synced_records": count}


@router.get("/history", response_model=List[AttendanceLogResponse])
async def attendance_history(
    device = Depends(verify_device),
    db: AsyncSession = Depends(get_db)
):
    tenant_id = device.tenant_id
    return await get_attendance_history(tenant_id, db)