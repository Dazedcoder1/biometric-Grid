from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_db, verify_tenant
from app.schemas.schemas import CommandRequest
from app.models.domain import Command
from app.mqtt.client import mqtt_manager

router = APIRouter()

@router.post("/fire-command")
async def fire_command(
    data: CommandRequest,
    tenant_id: int = Depends(verify_tenant),
    db: AsyncSession = Depends(get_db)
):
    # 1. Log in DB
    cmd = Command(tenant_id=tenant_id, device_id=data.device_id, command=data.command, target_id=data.target_id)
    db.add(cmd)
    await db.commit()
    await db.refresh(cmd)

    # 2. Fire via MQTT
    mqtt_manager.publish_command(tenant_id, data.device_id, cmd.id, data.command, data.target_id)
    
    return {"message": "Command dispatched", "command_id": cmd.id}