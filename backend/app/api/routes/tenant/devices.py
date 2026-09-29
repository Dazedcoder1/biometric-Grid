from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from pydantic import BaseModel
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant, Device, Command
from app.mqtt.client import mqtt_manager

router = APIRouter()

class FireCommandRequest(BaseModel):
    device_id: str
    command: str
    target_id: int = None


class DeviceIn(BaseModel):
    device_id: str
    secret_key: str


class DeviceUpdate(BaseModel):
    secret_key: str | None = None
    status: str | None = None

@router.get('/devices')
async def list_devices(tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.tenant_id == tenant.id).order_by(Device.device_id))
    devices = result.scalars().all()
    return [{"device_id": d.device_id, "status": d.status, "last_seen": d.last_seen} for d in devices]

@router.get('/devices/status')
async def devices_status(tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE status='online') as online,
               COUNT(*) FILTER (WHERE status!='online') as offline
        FROM devices WHERE tenant_id=:tenant_id
    """), {"tenant_id": tenant.id})
    return result.mappings().first()

@router.post('/devices', status_code=201)
async def create_device(data: DeviceIn, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    """Register a reader. The Devices page has always offered this; the route
    did not exist, so Add Device returned 404."""
    existing = (await db.execute(select(Device).where(
        Device.tenant_id == tenant.id, Device.device_id == data.device_id
    ))).scalars().first()
    # Checked explicitly: letting the unique index raise gives a 500, which
    # reads as a server fault for what is just a name already in use.
    if existing:
        raise HTTPException(409, f"A device called '{data.device_id}' already exists.")

    device = Device(tenant_id=tenant.id, device_id=data.device_id,
                    secret_key=data.secret_key, status="offline")
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return {"device_id": device.device_id, "status": device.status, "last_seen": device.last_seen}


@router.get('/devices/{device_id}')
async def get_device(device_id: str, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    device = (await db.execute(select(Device).where(
        Device.device_id == device_id, Device.tenant_id == tenant.id
    ))).scalars().first()
    if not device:
        raise HTTPException(404, "Device not found")

    pending = (await db.execute(text(
        "SELECT COUNT(*) FROM commands WHERE tenant_id=:t AND device_id=:d AND status='PENDING'"
    ), {"t": tenant.id, "d": device_id})).scalar_one()

    # secret_key is never returned. It authenticates the device to the server,
    # and a detail view has no use for it.
    return {
        "device_id": device.device_id,
        "status": device.status,
        "last_seen": device.last_seen,
        "pending_commands": pending,
    }


@router.put('/devices/{device_id}')
async def update_device(device_id: str, data: DeviceUpdate, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    device = (await db.execute(select(Device).where(
        Device.device_id == device_id, Device.tenant_id == tenant.id
    ))).scalars().first()
    if not device:
        raise HTTPException(404, "Device not found")

    if data.secret_key is not None:
        if len(data.secret_key) < 8:
            raise HTTPException(400, "Secret key must be at least 8 characters.")
        device.secret_key = data.secret_key
    if data.status is not None:
        # Only an offline mark is accepted. 'online' is a fact the device
        # asserts by checking in, not something an administrator can declare —
        # allowing it here would let the dashboard show a dead reader as
        # healthy.
        if data.status != "offline":
            raise HTTPException(
                400,
                "Only 'offline' can be set by hand. A device reports itself online "
                "when it connects.",
            )
        device.status = "offline"

    await db.commit()
    return {"message": "Device updated", "device_id": device.device_id}


@router.delete('/devices/{device_id}', status_code=204)
async def delete_device(device_id: str, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    device = (await db.execute(select(Device).where(
        Device.device_id == device_id, Device.tenant_id == tenant.id
    ))).scalars().first()
    if not device:
        raise HTTPException(404, "Device not found")
    await db.delete(device)
    await db.commit()


@router.post('/devices/fire-command')
async def fire_device_command(data: FireCommandRequest, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.device_id == data.device_id, Device.tenant_id == tenant.id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(404, "Device not found")
    cmd = Command(tenant_id=tenant.id, device_id=data.device_id, command=data.command, target_id=data.target_id)
    db.add(cmd)
    await db.commit()
    await db.refresh(cmd)
    mqtt_manager.publish_command(tenant.id, data.device_id, cmd.id, data.command, data.target_id)
    return {"message": "Command dispatched", "command_id": cmd.id}