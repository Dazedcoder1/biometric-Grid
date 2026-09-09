import asyncio
import os
import sys

# Add the project root to sys.path to allow imports from 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import engine, AsyncSessionLocal
from app.models.domain import Base, User, Tenant, Department
from app.core.security import hash_password

async def sync_db():
    print("Connecting to database and creating tables...")
    async with engine.begin() as conn:
        # This will create all tables defined in models/domain.py
        await conn.run_sync(Base.metadata.create_all)
    
    print("Tables created successfully.")
    
    # Create a default super admin if none exists
    async with AsyncSessionLocal() as db:
        from sqlalchemy.future import select
        
        # Check for super admin
        result = await db.execute(select(User).where(User.role == "super_admin"))
        if not result.scalars().first():
            print("Creating default super admin...")
            super_admin = User(
                name="Global Admin",
                email="admin@biometric.com",
                password_hash=hash_password("Admin@123"), # Change this!
                role="super_admin",
                is_active=True
            )
            db.add(super_admin)
            await db.commit()
            print("Super admin created: admin@biometric.com / Admin@123")
        else:
            print("Super admin already exists.")

if __name__ == "__main__":
    import platform
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(sync_db())
