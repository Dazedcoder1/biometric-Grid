
import sys
import os
import asyncio
from datetime import datetime

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add the project root to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from sqlalchemy.future import select
from app.db.session import engine, AsyncSessionLocal
from app.models.domain import Tenant, AttendanceLog, User

async def add_mock_log():
    async with AsyncSessionLocal() as db:
        # Get our tenant
        result = await db.execute(select(Tenant).where(Tenant.api_key == 'GridSphere2026!'))
        tenant = result.scalars().first()
        
        if tenant:
            # Add a user first so the name resolution works (if used)
            result = await db.execute(select(User).where(User.tenant_id == tenant.id, User.finger_id == 1))
            user = result.scalars().first()
            if not user:
                user = User(tenant_id=tenant.id, finger_id=1, name="Admin User")
                db.add(user)
                await db.flush()

            # Add log
            log = AttendanceLog(
                tenant_id=tenant.id,
                device_id="ESP8266_DOOR1",
                finger_id=1,
                record_type="IN",
                timestamp=datetime.now()
            )
            db.add(log)
            await db.commit()
            print("Successfully added mock log for GridSphere.")
        else:
            print("Tenant GridSphere2026! not found.")

if __name__ == "__main__":
    asyncio.run(add_mock_log())
