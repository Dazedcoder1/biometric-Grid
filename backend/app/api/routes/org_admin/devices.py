"""
Devices, for an Org Admin.

The Org Admin device pages were built against these four routes and none of
them existed — `orgApi.getDevices`, `getDeviceStatus`, `createDevice` and
`fireCommand` all 404'd, so the Devices screen loaded empty and enrolling a
fingerprint failed with no explanation.

Devices belong to the tenant, not to a department, so these are deliberately
tenant-wide reads rather than being filtered by `dept_id` the way employees and
attendance are: a reader in the lobby serves everyone, and hiding it from a
department admin would make the enrolment flow impossible to complete. What is
scoped is the *target* of a command — see fire_command below.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.db.session import get_db
from app.models.domain import Command, Device, User
from app.mqtt.client import mqtt_manager

router = APIRouter()


class DeviceIn(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=128)
    secret_key: str = Field(..., min_length=8)


class FireCommandRequest(BaseModel):
    device_id: str
    command: str
    target_id: int | None = None


@router.get("/devices")
async def list_devices(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Device)
            .where(Device.tenant_id == current_user.tenant_id)
            .order_by(Device.device_id)
        )
    ).scalars().all()
    # secret_key is deliberately not returned. It authenticates the device to
    # the server; a list endpoint has no reason to hand it out, and the Org
    # Admin screens never display it.
    return [
        {"device_id": d.device_id, "status": d.status, "last_seen": d.last_seen}
        for d in rows
    ]


@router.get("/devices/status")
async def devices_status(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'online')  AS online,
                   COUNT(*) FILTER (WHERE status != 'online') AS offline
              FROM devices
             WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": current_user.tenant_id},
    )
    return result.mappings().first()


@router.post("/devices", status_code=201)
async def create_device(
    data: DeviceIn,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    existing = (
        await db.execute(
            select(Device).where(
                Device.tenant_id == current_user.tenant_id,
                Device.device_id == data.device_id,
            )
        )
    ).scalars().first()
    # Checked rather than relying on the unique index: a raw IntegrityError
    # surfaces as a 500, which reads as "the server is broken" for what is
    # simply a name already in use.
    if existing:
        raise HTTPException(409, f"A device called '{data.device_id}' already exists.")

    device = Device(
        tenant_id=current_user.tenant_id,
        device_id=data.device_id,
        secret_key=data.secret_key,
        status="offline",
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return {"device_id": device.device_id, "status": device.status}


@router.post("/devices/fire-command")
async def fire_command(
    data: FireCommandRequest,
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Queue a command for a device.

    The device is tenant-scoped; the *target* is department-scoped. An Org
    Admin administers one department, so enrolling or deleting a fingerprint
    for somebody outside it must be refused — otherwise a department admin
    could use the shared lobby reader to overwrite any employee's fingerprint
    in the organisation.
    """
    device = (
        await db.execute(
            select(Device).where(
                Device.device_id == data.device_id,
                Device.tenant_id == current_user.tenant_id,
            )
        )
    ).scalars().first()
    if not device:
        raise HTTPException(404, "Device not found")

    if data.target_id is not None:
        target = (
            await db.execute(
                select(User).where(
                    User.id == data.target_id,
                    User.tenant_id == current_user.tenant_id,
                )
            )
        ).scalars().first()
        if not target:
            raise HTTPException(404, "Employee not found")
        if current_user.dept_id is not None and target.dept_id != current_user.dept_id:
            raise HTTPException(403, "That employee is not in your department.")

    cmd = Command(
        tenant_id=current_user.tenant_id,
        device_id=data.device_id,
        command=data.command,
        target_id=data.target_id,
    )
    db.add(cmd)
    await db.commit()
    await db.refresh(cmd)

    mqtt_manager.publish_command(
        current_user.tenant_id, data.device_id, cmd.id, data.command, data.target_id
    )
    return {"message": "Command dispatched", "command_id": cmd.id}
