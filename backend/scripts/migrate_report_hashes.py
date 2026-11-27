"""
Migration: add reports.content_sha256 for duplicate-upload detection.
Run: python scripts/migrate_report_hashes.py

The column is nullable on purpose. Rows written before it existed have no
hash, and backfilling would mean re-reading every stored file; those reports
simply never match a re-upload, which is the old behaviour and harmless.

The unique constraint is scoped to (user_id, content_sha256), not to the hash
alone. Two users may legitimately hold the same file - a public health
leaflet, a shared family report - and a global constraint would reject the
second person's upload and leak that someone else already has that file.

NULLs do not collide under a Postgres unique constraint, so any number of
pre-migration rows can coexist.
"""
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


async def migrate():
    print("Running reports.content_sha256 migration...")
    engine = create_async_engine(settings.DATABASE_URL)

    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE reports ADD COLUMN IF NOT EXISTS content_sha256 VARCHAR(64);"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_reports_content_sha256 "
            "ON reports(content_sha256);"
        ))
        # The constraint, not the SELECT in the endpoint, is what actually
        # prevents duplicates: two uploads of one file can race, and both
        # lookups can miss before either commits.
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_reports_user_content'
                ) THEN
                    ALTER TABLE reports
                        ADD CONSTRAINT uq_reports_user_content
                        UNIQUE (user_id, content_sha256);
                END IF;
            END $$;
        """))

    await engine.dispose()
    print("Migration complete: reports.content_sha256 ready.")


if __name__ == "__main__":
    asyncio.run(migrate())
