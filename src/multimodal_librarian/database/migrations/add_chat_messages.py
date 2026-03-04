"""
Database migration to add chat_messages table for AI chat functionality.

This migration adds the chat_messages table to support conversation history
and AI-powered chat features.
"""

import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from ..connection import get_async_session
from ...config import get_settings

logger = logging.getLogger(__name__)

# SQL for creating chat_messages table
CREATE_CHAT_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(20) NOT NULL DEFAULT 'user',
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    sources TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT check_chat_message_type CHECK (message_type IN ('user', 'assistant', 'system'))
);
"""

# SQL for creating indexes
CREATE_CHAT_MESSAGES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_type ON chat_messages(message_type);"
]

# SQL for dropping the table (rollback)
DROP_CHAT_MESSAGES_TABLE = "DROP TABLE IF EXISTS chat_messages CASCADE;"

async def apply_migration():
    """Apply the chat messages migration."""
    try:
        async with get_async_session() as session:
            # Create the table
            await session.execute(text(CREATE_CHAT_MESSAGES_TABLE))
            logger.info("Created chat_messages table")
            
            # Create indexes
            for index_sql in CREATE_CHAT_MESSAGES_INDEXES:
                await session.execute(text(index_sql))
            
            logger.info("Created chat_messages indexes")
            
            # Commit the changes
            await session.commit()
            logger.info("Chat messages migration applied successfully")
            
            return True
            
    except Exception as e:
        logger.error(f"Failed to apply chat messages migration: {e}")
        return False

async def rollback_migration():
    """Rollback the chat messages migration."""
    try:
        async with get_async_session() as session:
            # Drop the table
            await session.execute(text(DROP_CHAT_MESSAGES_TABLE))
            
            # Commit the changes
            await session.commit()
            logger.info("Chat messages migration rolled back successfully")
            
            return True
            
    except Exception as e:
        logger.error(f"Failed to rollback chat messages migration: {e}")
        return False

async def check_migration_status():
    """Check if the migration has been applied."""
    try:
        async with get_async_session() as session:
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'chat_messages'
                );
            """))
            
            exists = result.scalar()
            return exists
            
    except Exception as e:
        logger.error(f"Failed to check migration status: {e}")
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
            # Check if already applied
            already_applied = await check_migration_status()
            if already_applied:
                print("Migration already applied")
                return
            
            # Apply migration
            success = await apply_migration()
            if success:
                print("Migration applied successfully")
            else:
                print("Failed to apply migration")
                sys.exit(1)
    
    asyncio.run(main())