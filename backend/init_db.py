import asyncio
import sys
import os

# Ensure the app folder is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import engine
from app.db.base_class import Base
# Import all models so Base knows about them
from app.db.models import User, Report, HealthMetric

async def init_tables():
    async with engine.begin() as conn:
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_tables())
