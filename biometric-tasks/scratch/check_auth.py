
import sys
import os
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.future import select
from app.db.session import engine, AsyncSessionLocal
from app.models.domain import Tenant, Device

async def check_auth():
    async with AsyncSessionLocal() as db:
        # Get the tenant for 'test_api_key'
        result = await db.execute(select(Tenant).where(Tenant.api_key == 'test_api_key'))
        tenant = result.scalars().first()
        
        if tenant:
            print(f"Tenant Found: {tenant.name} (ID: {tenant.id})")
            # Check for devices
            result = await db.execute(select(Device).where(Device.tenant_id == tenant.id))
            devices = result.scalars().all()
            print(f"Devices for this tenant: {[d.device_id for d in devices]}")
        else:
            print("Tenant 'test_api_key' not found.")

if __name__ == "__main__":
    asyncio.run(check_auth())
