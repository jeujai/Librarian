"""
Database migration to add a privacy ``scope`` column to content tables.

Adds ``scope VARCHAR(20) NOT NULL DEFAULT 'private'`` to
``multimodal_librarian.knowledge_sources`` (documents/uploads/conversations)
and ``multimodal_librarian.conversation_threads``. This backs the Phase 6
private/public content toggle: content is private by default, and the column is
read back by the concept write paths when minting ``:Concept`` nodes.

Idempotent — uses ``ADD COLUMN IF NOT EXISTS``.
"""

import asyncio
import logging

from sqlalchemy import text

from ..connection import get_async_session

logger = logging.getLogger(__name__)

# ALTER statements, in dependency-free order.
ALTER_STATEMENTS = [
    "ALTER TABLE multimodal_librarian.knowledge_sources "
    "ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'private';",
    "ALTER TABLE multimodal_librarian.conversation_threads "
    "ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'private';",
]

DROP_STATEMENTS = [
    "ALTER TABLE multimodal_librarian.knowledge_sources DROP COLUMN IF EXISTS scope;",
    "ALTER TABLE multimodal_librarian.conversation_threads DROP COLUMN IF EXISTS scope;",
]


async def apply_migration() -> bool:
    """Apply the content scope migration."""
    try:
        async with get_async_session() as session:
            for stmt in ALTER_STATEMENTS:
                await session.execute(text(stmt))
            await session.commit()
        logger.info("Content scope migration applied successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to apply content scope migration: {e}")
        return False


async def rollback_migration() -> bool:
    """Rollback the content scope migration."""
    try:
        async with get_async_session() as session:
            for stmt in DROP_STATEMENTS:
                await session.execute(text(stmt))
            await session.commit()
        logger.info("Content scope migration rolled back successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to rollback content scope migration: {e}")
        return False


async def check_migration_status() -> bool:
    """Check whether both ``scope`` columns exist."""
    try:
        async with get_async_session() as session:
            result = await session.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'multimodal_librarian'
                  AND table_name IN ('knowledge_sources', 'conversation_threads')
                  AND column_name = 'scope';
            """))
            return result.scalar() == 2
    except Exception as e:
        logger.error(f"Failed to check content scope migration status: {e}")
        return False


if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) > 1 and sys.argv[1] == "rollback":
            success = await rollback_migration()
            if success:
                print("Migration rolled back successfully")
            else:
                print("Failed to rollback migration")
                sys.exit(1)
        else:
            if await check_migration_status():
                print("Migration already applied")
                return
            success = await apply_migration()
            if success:
                print("Migration applied successfully")
            else:
                print("Failed to apply migration")
                sys.exit(1)

    asyncio.run(main())
