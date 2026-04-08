import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def alter_users_table():
    print("Initiating non-destructive schema migration...")
    engine = create_async_engine(settings.DATABASE_URL)
    
    alter_statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS address VARCHAR;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS blood_type VARCHAR;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS emergency_contact_name VARCHAR;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS emergency_contact_phone VARCHAR;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_sms VARCHAR DEFAULT 'true';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_email VARCHAR DEFAULT 'true';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_report_ready VARCHAR DEFAULT 'true';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_high_risk VARCHAR DEFAULT 'true';"
    ]
    
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text
            for statement in alter_statements:
                await conn.execute(text(statement))
                print(f"Executed: {statement}")
        print("Schema migration completed successfully!")
    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(alter_users_table())
