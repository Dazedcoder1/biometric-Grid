import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal
from app.models.domain import User
from app.core.security import hash_password
from sqlalchemy.future import select

async def reset_super_admin():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.role == "super_admin"))
        user = result.scalars().first()
        
        if user:
            print(f"Found super admin: {user.email}. Resetting password to Admin@123...")
            user.password_hash = hash_password("Admin@123")
            await db.commit()
            print("Password reset successful.")
        else:
            print("No super admin found to reset.")

if __name__ == "__main__":
    import platform
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(reset_super_admin())
