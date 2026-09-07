
import sys
import os
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.future import select
from app.db.session import engine, AsyncSessionLocal
from app.models.domain import Tenant, Device

async def seed():
    async with AsyncSessionLocal() as db:
        # 1. Add Tenant
        result = await db.execute(select(Tenant).where(Tenant.api_key == 'GridSphere2026!'))
        tenant = result.scalars().first()
        
        if not tenant:
            tenant = Tenant(name="GridSphere", api_key="GridSphere2026!")
            db.add(tenant)
            await db.flush()
            print(f"Added Tenant: {tenant.name} (ID: {tenant.id})")
        else:
            print(f"Tenant already exists: {tenant.name} (ID: {tenant.id})")

        # 2. Add Device
        result = await db.execute(select(Device).where(Device.device_id == 'ESP8266_DOOR1', Device.tenant_id == tenant.id))
        device = result.scalars().first()
        
        if not device:
            device = Device(tenant_id=tenant.id, device_id="ESP8266_DOOR1", secret_key="secret", status="online")
            db.add(device)
            print(f"Added Device: {device.device_id}")
        else:
            print(f"Device already exists: {device.device_id}")

        await db.commit()
        print("Seed completed successfully.")

if __name__ == "__main__":
    asyncio.run(seed())
