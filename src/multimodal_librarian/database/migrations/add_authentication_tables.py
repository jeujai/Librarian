#!/usr/bin/env python3
"""
Database migration to add authentication and authorization tables.

This migration creates all necessary tables for user authentication,
API key management, audit logging, and security features.
"""

import asyncio
import sys
import os
from datetime import datetime
from sqlalchemy import text

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from multimodal_librarian.database.connection import get_database_connection, Base, db_manager
from multimodal_librarian.database.models import (
    UserDB, APIKeyDB, AuditLogDB, DataDeletionLogDB, 
    PrivacyRequestDB, SecurityIncidentDB, EncryptionKeyDB
)
from multimodal_librarian.logging_config import get_logger

logger = get_logger(__name__)


async def create_authentication_tables():
    """Create all authentication and security tables."""
    try:
        logger.info("Starting authentication tables migration...")
        
        # Initialize database manager
        db_manager.initialize()
        
        # Create all tables defined in the models
        db_manager.create_all_tables()
        
        logger.info("Authentication tables created successfully")
        
        # Create initial admin user
        await create_initial_admin_user()
        
        logger.info("Authentication migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create authentication tables: {e}")
        return False


async def create_initial_admin_user():
    """Create initial admin user for system access."""
    try:
        from multimodal_librarian.security.auth import get_auth_service
        from multimodal_librarian.security.auth import User, UserRole
        
        auth_service = get_auth_service()
        
        # Check if admin user already exists
        with get_database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
            admin_exists = cursor.fetchone()[0] > 0
            
            if admin_exists:
                logger.info("Admin user already exists, skipping creation")
                return
            
            # Create admin user
            admin_user_id = "admin-001"
            admin_username = "admin"
            admin_email = "admin@multimodal-librarian.local"
            admin_password = "admin123"  # Should be changed in production
            
            # Hash password
            password_hash = auth_service.hash_password(admin_password)
            
            # Insert admin user
            cursor.execute("""
                INSERT INTO users (
                    id, user_id, username, email, password_hash, salt, 
                    role, is_active, is_verified, created_at
                ) VALUES (
                    gen_random_uuid(), %s, %s, %s, %s, '', %s, true, true, %s
                )
            """, (
                admin_user_id,
                admin_username,
                admin_email,
                password_hash,
                UserRole.ADMIN.value,
                datetime.utcnow()
            ))
            
            logger.info(f"Created initial admin user: {admin_username}")
            logger.info("Default admin credentials: admin / admin123")
            logger.warning("SECURITY: Change default admin password in production!")
            
    except Exception as e:
        logger.error(f"Failed to create initial admin user: {e}")
        raise


async def verify_tables():
    """Verify that all authentication tables were created successfully."""
    try:
        with get_database_connection() as conn:
            cursor = conn.cursor()
            
            # Check each table exists
            tables_to_check = [
                'users', 'api_keys', 'audit_logs', 'data_deletion_logs',
                'privacy_requests', 'security_incidents', 'encryption_keys'
            ]
            
            for table_name in tables_to_check:
                cursor.execute(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_name}'")
                table_exists = cursor.fetchone()[0] > 0
                
                if table_exists:
                    logger.info(f"✓ Table '{table_name}' created successfully")
                else:
                    logger.error(f"✗ Table '{table_name}' was not created")
                    return False
            
            # Check admin user was created
            cursor.execute("SELECT username, role FROM users WHERE role = 'admin'")
            admin_user = cursor.fetchone()
            
            if admin_user:
                logger.info(f"✓ Admin user '{admin_user[0]}' created successfully")
            else:
                logger.error("✗ Admin user was not created")
                return False
            
            logger.info("All authentication tables verified successfully")
            return True
            
    except Exception as e:
        logger.error(f"Failed to verify authentication tables: {e}")
        return False


async def main():
    """Main migration function."""
    logger.info("=== Authentication Tables Migration ===")
    
    try:
        # Create tables
        success = await create_authentication_tables()
        if not success:
            logger.error("Migration failed during table creation")
            return False
        
        # Verify tables
        success = await verify_tables()
        if not success:
            logger.error("Migration failed during verification")
            return False
        
        logger.info("=== Migration Completed Successfully ===")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        return False


if __name__ == "__main__":
    # Run the migration
    success = asyncio.run(main())
    sys.exit(0 if success else 1)