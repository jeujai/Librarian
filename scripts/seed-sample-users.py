#!/usr/bin/env python3
"""
Sample Users and Authentication Data Generator

This script generates sample user accounts and authentication data for local development.
It creates realistic test users with proper password hashing and role assignments.

Usage:
    python scripts/seed-sample-users.py [--count N] [--reset]
    
    --count N: Number of users to create (default: 10)
    --reset: Drop existing users before creating new ones
"""

import asyncio
import argparse
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path
import sys
import os

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.local_config import LocalDatabaseConfig
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from multimodal_librarian.security.auth import hash_password, generate_salt
from multimodal_librarian.database.models import UserDB, APIKeyDB

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SampleUserGenerator:
    """Generator for sample user accounts and authentication data."""
    
    def __init__(self, config: LocalDatabaseConfig):
        """Initialize the generator with database configuration."""
        self.config = config
        self.factory = DatabaseClientFactory(config)
        
        # Sample user data templates
        self.sample_users = [
            {
                "username": "admin",
                "email": "admin@multimodal-librarian.local",
                "role": "admin",
                "is_verified": True,
                "password": "admin123"
            },
            {
                "username": "researcher",
                "email": "researcher@multimodal-librarian.local", 
                "role": "ml_researcher",
                "is_verified": True,
                "password": "research123"
            },
            {
                "username": "alice_dev",
                "email": "alice@example.com",
                "role": "user",
                "is_verified": True,
                "password": "alice123"
            },
            {
                "username": "bob_tester",
                "email": "bob@example.com",
                "role": "user", 
                "is_verified": True,
                "password": "bob123"
            },
            {
                "username": "charlie_readonly",
                "email": "charlie@example.com",
                "role": "read_only",
                "is_verified": True,
                "password": "charlie123"
            },
            {
                "username": "demo_user",
                "email": "demo@multimodal-librarian.local",
                "role": "user",
                "is_verified": False,
                "password": "demo123"
            }
        ]
        
        # Additional user templates for bulk generation
        self.user_templates = [
            {"role": "user", "verified_ratio": 0.8},
            {"role": "ml_researcher", "verified_ratio": 0.9},
            {"role": "read_only", "verified_ratio": 0.7},
        ]
    
    async def generate_users(self, count: int = 10, reset: bool = False) -> List[Dict[str, Any]]:
        """
        Generate sample users with authentication data.
        
        Args:
            count: Total number of users to create
            reset: Whether to reset existing users first
            
        Returns:
            List of created user data dictionaries
        """
        logger.info(f"Generating {count} sample users (reset={reset})")
        
        try:
            # Get database client
            db_client = await self.factory.get_relational_client()
            
            # Reset users if requested
            if reset:
                await self._reset_users(db_client)
            
            # Create predefined users first
            created_users = []
            users_to_create = min(count, len(self.sample_users))
            
            for i in range(users_to_create):
                user_data = self.sample_users[i].copy()
                user = await self._create_user(db_client, user_data)
                created_users.append(user)
                logger.info(f"Created user: {user['username']} ({user['role']})")
            
            # Generate additional users if needed
            remaining_count = count - len(created_users)
            if remaining_count > 0:
                for i in range(remaining_count):
                    user_data = self._generate_random_user(i + len(self.sample_users))
                    user = await self._create_user(db_client, user_data)
                    created_users.append(user)
                    logger.info(f"Created user: {user['username']} ({user['role']})")
            
            # Generate API keys for some users
            await self._generate_api_keys(db_client, created_users)
            
            logger.info(f"Successfully created {len(created_users)} users")
            return created_users
            
        except Exception as e:
            logger.error(f"Failed to generate users: {e}")
            raise
    
    async def _reset_users(self, db_client) -> None:
        """Reset existing users and authentication data."""
        logger.info("Resetting existing users and authentication data")
        
        try:
            # Use raw SQL for cleanup since we're working with SQLAlchemy models
            async with db_client.get_async_session() as session:
                # Delete API keys first (foreign key constraint)
                await session.execute("DELETE FROM api_keys")
                
                # Delete users
                await session.execute("DELETE FROM users")
                
                # Reset sequences if they exist
                try:
                    await session.execute("ALTER SEQUENCE users_id_seq RESTART WITH 1")
                    await session.execute("ALTER SEQUENCE api_keys_id_seq RESTART WITH 1")
                except Exception:
                    # Sequences might not exist, ignore
                    pass
                
                await session.commit()
                
            logger.info("Successfully reset user data")
            
        except Exception as e:
            logger.error(f"Failed to reset users: {e}")
            raise
    
    async def _create_user(self, db_client, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a single user with authentication data."""
        
        # Generate secure password hash
        salt = generate_salt()
        password_hash = hash_password(user_data["password"], salt)
        
        # Create user record
        user_id = str(uuid.uuid4())
        user_uuid = str(uuid.uuid4())
        
        user_record = {
            "id": user_uuid,
            "user_id": user_id,
            "username": user_data["username"],
            "email": user_data["email"],
            "password_hash": password_hash,
            "salt": salt,
            "role": user_data["role"],
            "is_active": True,
            "is_verified": user_data.get("is_verified", True),
            "created_at": datetime.utcnow(),
            "last_login": None,
            "failed_login_attempts": 0,
            "locked_until": None
        }
        
        # Insert into database
        async with db_client.get_async_session() as session:
            # Use raw SQL insert since we're working with the models directly
            insert_sql = """
                INSERT INTO users (
                    id, user_id, username, email, password_hash, salt, role,
                    is_active, is_verified, created_at, last_login, 
                    failed_login_attempts, locked_until
                ) VALUES (
                    :id, :user_id, :username, :email, :password_hash, :salt, :role,
                    :is_active, :is_verified, :created_at, :last_login,
                    :failed_login_attempts, :locked_until
                )
            """
            
            await session.execute(insert_sql, user_record)
            await session.commit()
        
        # Return user data (without sensitive info)
        return {
            "id": user_record["id"],
            "user_id": user_record["user_id"],
            "username": user_record["username"],
            "email": user_record["email"],
            "role": user_record["role"],
            "is_active": user_record["is_active"],
            "is_verified": user_record["is_verified"],
            "created_at": user_record["created_at"]
        }
    
    def _generate_random_user(self, index: int) -> Dict[str, Any]:
        """Generate a random user based on templates."""
        import random
        
        # Select random template
        template = random.choice(self.user_templates)
        
        # Generate user data
        username = f"user_{index:03d}"
        email = f"user{index:03d}@example.com"
        is_verified = random.random() < template["verified_ratio"]
        
        return {
            "username": username,
            "email": email,
            "role": template["role"],
            "is_verified": is_verified,
            "password": f"password{index:03d}"
        }
    
    async def _generate_api_keys(self, db_client, users: List[Dict[str, Any]]) -> None:
        """Generate API keys for some users."""
        import random
        import hashlib
        
        logger.info("Generating API keys for users")
        
        # Generate API keys for admin and researcher users, and 30% of regular users
        for user in users:
            should_create_key = (
                user["role"] in ["admin", "ml_researcher"] or
                (user["role"] == "user" and random.random() < 0.3)
            )
            
            if should_create_key:
                # Generate API key
                api_key = f"ml_local_{uuid.uuid4().hex[:16]}"
                key_hash = hashlib.sha256(api_key.encode()).hexdigest()
                
                # Determine permissions based on role
                permissions = self._get_permissions_for_role(user["role"])
                
                api_key_record = {
                    "id": str(uuid.uuid4()),
                    "key_id": f"key_{uuid.uuid4().hex[:8]}",
                    "user_id": user["id"],
                    "name": f"{user['username']}_dev_key",
                    "key_hash": key_hash,
                    "permissions": permissions,
                    "is_active": True,
                    "created_at": datetime.utcnow(),
                    "expires_at": datetime.utcnow() + timedelta(days=365),
                    "last_used": None,
                    "usage_count": 0
                }
                
                # Insert API key
                async with db_client.get_async_session() as session:
                    insert_sql = """
                        INSERT INTO api_keys (
                            id, key_id, user_id, name, key_hash, permissions,
                            is_active, created_at, expires_at, last_used, usage_count
                        ) VALUES (
                            :id, :key_id, :user_id, :name, :key_hash, :permissions,
                            :is_active, :created_at, :expires_at, :last_used, :usage_count
                        )
                    """
                    
                    # Convert permissions list to PostgreSQL array format
                    permissions_array = "{" + ",".join(f'"{p}"' for p in permissions) + "}"
                    api_key_record["permissions"] = permissions_array
                    
                    await session.execute(insert_sql, api_key_record)
                    await session.commit()
                
                logger.info(f"Created API key for {user['username']}: {api_key}")
    
    def _get_permissions_for_role(self, role: str) -> List[str]:
        """Get permissions list based on user role."""
        permission_map = {
            "admin": [
                "read", "write", "delete", "admin", "user_management",
                "system_config", "analytics", "export", "upload"
            ],
            "ml_researcher": [
                "read", "write", "analytics", "export", "upload", "ml_training"
            ],
            "user": [
                "read", "write", "upload", "export"
            ],
            "read_only": [
                "read"
            ]
        }
        
        return permission_map.get(role, ["read"])
    
    async def close(self) -> None:
        """Close database connections."""
        await self.factory.close()


async def main():
    """Main function to run the sample user generator."""
    parser = argparse.ArgumentParser(description="Generate sample users for local development")
    parser.add_argument("--count", type=int, default=10, help="Number of users to create")
    parser.add_argument("--reset", action="store_true", help="Reset existing users first")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    try:
        config = LocalDatabaseConfig()
        logger.info(f"Loaded configuration for {config.database_type} environment")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1
    
    # Generate sample users
    generator = SampleUserGenerator(config)
    
    try:
        users = await generator.generate_users(count=args.count, reset=args.reset)
        
        print(f"\n✅ Successfully created {len(users)} sample users!")
        print("\nSample login credentials:")
        print("=" * 50)
        
        # Show first few users for reference
        for user in users[:6]:  # Show first 6 users
            role_emoji = {
                "admin": "👑",
                "ml_researcher": "🔬", 
                "user": "👤",
                "read_only": "👁️"
            }.get(user["role"], "👤")
            
            print(f"{role_emoji} {user['username']:15} | {user['email']:30} | {user['role']}")
        
        if len(users) > 6:
            print(f"... and {len(users) - 6} more users")
        
        print("\n💡 Default passwords follow the pattern: username + '123'")
        print("   Example: admin/admin123, alice_dev/alice123")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate sample users: {e}")
        return 1
    
    finally:
        await generator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)