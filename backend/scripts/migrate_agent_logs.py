"""
Migration: Create agent_logs table.
Run: python scripts/migrate_agent_logs.py
"""
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings


async def migrate():
    print("Running agent_logs migration...")
    engine = create_async_engine(settings.DATABASE_URL)

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                agent_name VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                message VARCHAR,
                duration_ms FLOAT,
                timestamp TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_agent_logs_report_id ON agent_logs(report_id);"
        ))

    await engine.dispose()
    print("Migration complete: agent_logs table ready.")


if __name__ == "__main__":
    asyncio.run(migrate())
