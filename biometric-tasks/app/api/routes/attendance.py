from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db, verify_tenant_api_key, verify_device
from app.schemas.schemas import BulkAttendanceRequest, AttendanceLogResponse
from app.services.attendance_service import process_attendance, process_bulk_attendance, get_attendance_history
from app.models.domain import Tenant, Device
from typing import List

router = APIRouter()

@router.post("/mark")
async def mark_attendance(
    finger_id: int,
    device: Device = Depends(verify_device),
    db: AsyncSession = Depends(get_db)
):
    # Unpack the log and the fetched user_name
    # process_attendance needs tenant_id, device_id, finger_id
    log, user_name = await process_attendance(device.tenant_id, device.device_id, finger_id, db)
    
    # Send the state and user name right back to the hardware
    return {
        "status": "success", 
        "record_type": log.record_type,
        "user_name": user_name,
        "message": f"Successfully marked {log.record_type}"
    }

@router.post("/sync-offline")
async def sync_offline_attendance(
    payload: BulkAttendanceRequest,
    device: Device = Depends(verify_device),
    db: AsyncSession = Depends(get_db)
):
    count = await process_bulk_attendance(device.tenant_id, device.device_id, payload.logs, db)
    return {"status": "success", "synced_records": count}

@router.get("/history", response_model=List[AttendanceLogResponse])
async def attendance_history(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    return await get_attendance_history(tenant.id, db)