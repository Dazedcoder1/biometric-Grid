import asyncio
import sys
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def check_schema():
    try:
        async with AsyncSessionLocal() as db:
            # Check if user_id column exists in attendance_logs
            res = await db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'attendance_logs' AND column_name = 'user_id'
            """))
            column = res.scalar()
            if column:
                print("SUCCESS: user_id column exists in attendance_logs")
            else:
                print("ERROR: user_id column MISSING in attendance_logs. Need to run migrations.")
                
            # Check if tenants.id exists (vs tenants.tenant_id)
            res = await db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'tenants' AND column_name = 'id'
            """))
            if res.scalar():
                print("SUCCESS: tenants.id exists")
            else:
                print("ERROR: tenants.id MISSING (likely named tenant_id).")
                
    except Exception as e:
        print(f"DATABASE ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(check_schema())


