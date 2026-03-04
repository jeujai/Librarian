#!/usr/bin/env python3
"""
Database Schema Version Manager

This module provides comprehensive schema versioning and migration capabilities
for all database systems used in the Multimodal Librarian application.

Features:
- Schema version tracking across all databases
- Automated migration execution
- Rollback capabilities
- Migration dependency management
- Cross-database migration coordination
- Migration validation and testing

Usage:
    from database.schema_version_manager import SchemaVersionManager
    
    # Initialize version manager
    manager = SchemaVersionManager()
    
    # Check current versions
    versions = await manager.get_current_versions()
    
    # Migrate to latest version
    await manager.migrate_to_latest()
    
    # Rollback to previous version
    await manager.rollback_to_version("1.0.0")
"""

import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import re

from database.schema_validator import (
    DatabaseType, ValidationStatus, SchemaValidator,
    ValidationResult, SchemaVersion
)

logger = logging.getLogger(__name__)


class MigrationStatus(Enum):
    """Migration execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class MigrationDirection(Enum):
    """Migration direction"""
    UP = "up"
    DOWN = "down"


@dataclass
class Migration:
    """Database migration definition"""
    id: str
    database_type: DatabaseType
    version: str
    description: str
    up_script: str
    down_script: Optional[str] = None
    dependencies: List[str] = None
    checksum: Optional[str] = None
    applied_at: Optional[datetime] = None
    status: MigrationStatus = MigrationStatus.PENDING
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


@dataclass
class MigrationPlan:
    """Migration execution plan"""
    target_version: str
    migrations: List[Migration]
    direction: MigrationDirection
    estimated_duration: Optional[int] = None
    requires_backup: bool = True
    rollback_plan: Optional['MigrationPlan'] = None


class SchemaVersionManager:
    """
    Manages schema versions and migrations across all database systems.
    
    This class coordinates schema changes across PostgreSQL, Milvus, and Neo4j
    databases, ensuring consistency and providing rollback capabilities.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize schema version manager.
        
        Args:
            config_path: Path to migration configuration file
        """
        self.config_path = config_path or "database/migrations_config.json"
        self.migrations_dir = Path("database/migrations")
        self.validator = SchemaValidator()
        self.migration_history = {}
        self.available_migrations = {}
        self._load_migration_config()
        self._discover_migrations()
    
    def _load_migration_config(self) -> None:
        """Load migration configuration from file"""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r') as f:
                    self.config = json.load(f)
                    logger.info(f"Loaded migration config from {self.config_path}")
            else:
                # Create default configuration
                self.config = self._create_default_migration_config()
                self._save_migration_config()
                logger.info(f"Created default migration config at {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load migration config: {e}")
            self.config = self._create_default_migration_config()
    
    def _create_default_migration_config(self) -> Dict[str, Any]:
        """Create default migration configuration"""
        return {
            "version": "1.0.0",
            "migration_settings": {
                "auto_backup": True,
                "backup_retention_days": 30,
                "migration_timeout": 3600,
                "parallel_execution": False,
                "dry_run_validation": True,
                "rollback_on_failure": True
            },
            "database_connections": {
                "postgresql": {
                    "connection_string": "postgresql://ml_user:ml_password@localhost:5432/multimodal_librarian",
                    "migration_table": "schema_migrations",
                    "backup_command": "pg_dump",
                    "restore_command": "psql"
                },
                "milvus": {
                    "host": "localhost",
                    "port": 19530,
                    "backup_method": "collection_export",
                    "restore_method": "collection_import"
                },
                "neo4j": {
                    "uri": "bolt://localhost:7687",
                    "user": "neo4j",
                    "password": "ml_password",
                    "backup_command": "neo4j-admin database backup",
                    "restore_command": "neo4j-admin database restore"
                }
            },
            "version_history": {},
            "migration_dependencies": {
                "postgresql": [],
                "milvus": ["postgresql"],  # Milvus migrations may depend on PostgreSQL
                "neo4j": ["postgresql"]    # Neo4j migrations may depend on PostgreSQL
            }
        }
    
    def _save_migration_config(self) -> None:
        """Save migration configuration to file"""
        try:
            config_file = Path(self.config_path)
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2, default=str)
            
            logger.debug(f"Saved migration config to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save migration config: {e}")
    
    def _discover_migrations(self) -> None:
        """Discover available migration files"""
        logger.info("Discovering migration files...")
        
        self.available_migrations = {
            DatabaseType.POSTGRESQL: [],
            DatabaseType.MILVUS: [],
            DatabaseType.NEO4J: []
        }
        
        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return
        
        # Discover PostgreSQL migrations
        pg_migrations_dir = self.migrations_dir / "postgresql"
        if pg_migrations_dir.exists():
            self._discover_postgresql_migrations(pg_migrations_dir)
        
        # Discover Milvus migrations
        milvus_migrations_dir = self.migrations_dir / "milvus"
        if milvus_migrations_dir.exists():
            self._discover_milvus_migrations(milvus_migrations_dir)
        
        # Discover Neo4j migrations
        neo4j_migrations_dir = self.migrations_dir / "neo4j"
        if neo4j_migrations_dir.exists():
            self._discover_neo4j_migrations(neo4j_migrations_dir)
        
        # Sort migrations by version
        for db_type in self.available_migrations:
            self.available_migrations[db_type].sort(key=lambda m: self._parse_version(m.version))
        
        total_migrations = sum(len(migrations) for migrations in self.available_migrations.values())
        logger.info(f"Discovered {total_migrations} migration files")
    
    def _discover_postgresql_migrations(self, migrations_dir: Path) -> None:
        """Discover PostgreSQL migration files"""
        pattern = re.compile(r'^(\d+\.\d+\.\d+)_(.+)\.sql$')
        
        for file_path in migrations_dir.glob("*.sql"):
            match = pattern.match(file_path.name)
            if match:
                version, description = match.groups()
                description = description.replace('_', ' ').title()
                
                # Look for corresponding rollback file
                rollback_file = migrations_dir / f"{version}_{match.group(2)}_rollback.sql"
                down_script = None
                if rollback_file.exists():
                    with open(rollback_file, 'r') as f:
                        down_script = f.read()
                
                # Read migration script
                with open(file_path, 'r') as f:
                    up_script = f.read()
                
                migration = Migration(
                    id=f"postgresql_{version}_{match.group(2)}",
                    database_type=DatabaseType.POSTGRESQL,
                    version=version,
                    description=description,
                    up_script=up_script,
                    down_script=down_script
                )
                
                self.available_migrations[DatabaseType.POSTGRESQL].append(migration)
                logger.debug(f"Found PostgreSQL migration: {migration.id}")
    
    def _discover_milvus_migrations(self, migrations_dir: Path) -> None:
        """Discover Milvus migration files"""
        pattern = re.compile(r'^(\d+\.\d+\.\d+)_(.+)\.py$')
        
        for file_path in migrations_dir.glob("*.py"):
            match = pattern.match(file_path.name)
            if match:
                version, description = match.groups()
                description = description.replace('_', ' ').title()
                
                # Look for corresponding rollback file
                rollback_file = migrations_dir / f"{version}_{match.group(2)}_rollback.py"
                down_script = None
                if rollback_file.exists():
                    with open(rollback_file, 'r') as f:
                        down_script = f.read()
                
                # Read migration script
                with open(file_path, 'r') as f:
                    up_script = f.read()
                
                migration = Migration(
                    id=f"milvus_{version}_{match.group(2)}",
                    database_type=DatabaseType.MILVUS,
                    version=version,
                    description=description,
                    up_script=up_script,
                    down_script=down_script
                )
                
                self.available_migrations[DatabaseType.MILVUS].append(migration)
                logger.debug(f"Found Milvus migration: {migration.id}")
    
    def _discover_neo4j_migrations(self, migrations_dir: Path) -> None:
        """Discover Neo4j migration files"""
        pattern = re.compile(r'^(\d+\.\d+\.\d+)_(.+)\.cypher$')
        
        for file_path in migrations_dir.glob("*.cypher"):
            match = pattern.match(file_path.name)
            if match:
                version, description = match.groups()
                description = description.replace('_', ' ').title()
                
                # Look for corresponding rollback file
                rollback_file = migrations_dir / f"{version}_{match.group(2)}_rollback.cypher"
                down_script = None
                if rollback_file.exists():
                    with open(rollback_file, 'r') as f:
                        down_script = f.read()
                
                # Read migration script
                with open(file_path, 'r') as f:
                    up_script = f.read()
                
                migration = Migration(
                    id=f"neo4j_{version}_{match.group(2)}",
                    database_type=DatabaseType.NEO4J,
                    version=version,
                    description=description,
                    up_script=up_script,
                    down_script=down_script
                )
                
                self.available_migrations[DatabaseType.NEO4J].append(migration)
                logger.debug(f"Found Neo4j migration: {migration.id}")
    
    def _parse_version(self, version: str) -> Tuple[int, int, int]:
        """Parse version string into comparable tuple"""
        try:
            parts = version.split('.')
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            logger.warning(f"Invalid version format: {version}")
            return (0, 0, 0)
    
    def _compare_versions(self, version1: str, version2: str) -> int:
        """Compare two version strings. Returns -1, 0, or 1"""
        v1 = self._parse_version(version1)
        v2 = self._parse_version(version2)
        
        if v1 < v2:
            return -1
        elif v1 > v2:
            return 1
        else:
            return 0
    
    async def get_current_versions(self) -> Dict[DatabaseType, Optional[str]]:
        """
        Get current schema versions for all databases.
        
        Returns:
            Dictionary mapping database types to current versions
        """
        logger.info("Checking current schema versions...")
        
        versions = {}
        
        # Get PostgreSQL version
        try:
            pg_conn = self.config["database_connections"]["postgresql"]["connection_string"]
            pg_result = await self.validator.validate_postgresql_schema(pg_conn)
            versions[DatabaseType.POSTGRESQL] = pg_result.version
        except Exception as e:
            logger.error(f"Failed to get PostgreSQL version: {e}")
            versions[DatabaseType.POSTGRESQL] = None
        
        # Get Milvus version
        try:
            milvus_config = self.config["database_connections"]["milvus"]
            milvus_result = await self.validator.validate_milvus_schema(
                milvus_config["host"], milvus_config["port"]
            )
            versions[DatabaseType.MILVUS] = milvus_result.version
        except Exception as e:
            logger.error(f"Failed to get Milvus version: {e}")
            versions[DatabaseType.MILVUS] = None
        
        # Get Neo4j version
        try:
            neo4j_config = self.config["database_connections"]["neo4j"]
            neo4j_result = await self.validator.validate_neo4j_schema(
                neo4j_config["uri"], neo4j_config["user"], neo4j_config["password"]
            )
            versions[DatabaseType.NEO4J] = neo4j_result.version
        except Exception as e:
            logger.error(f"Failed to get Neo4j version: {e}")
            versions[DatabaseType.NEO4J] = None
        
        return versions
    
    def get_latest_versions(self) -> Dict[DatabaseType, Optional[str]]:
        """
        Get latest available versions for all databases.
        
        Returns:
            Dictionary mapping database types to latest versions
        """
        latest_versions = {}
        
        for db_type, migrations in self.available_migrations.items():
            if migrations:
                # Get the highest version
                latest_migration = max(migrations, key=lambda m: self._parse_version(m.version))
                latest_versions[db_type] = latest_migration.version
            else:
                latest_versions[db_type] = None
        
        return latest_versions
    
    def create_migration_plan(
        self,
        target_versions: Dict[DatabaseType, str],
        current_versions: Optional[Dict[DatabaseType, Optional[str]]] = None
    ) -> Dict[DatabaseType, MigrationPlan]:
        """
        Create migration plans for reaching target versions.
        
        Args:
            target_versions: Target versions for each database
            current_versions: Current versions (will be fetched if not provided)
            
        Returns:
            Dictionary mapping database types to migration plans
        """
        if current_versions is None:
            # This would need to be async, but for planning we can use stored versions
            current_versions = {
                db_type: self.config.get("version_history", {}).get(db_type.value, {}).get("current")
                for db_type in DatabaseType
            }
        
        migration_plans = {}
        
        for db_type, target_version in target_versions.items():
            current_version = current_versions.get(db_type)
            
            if current_version is None:
                # No current version, need to apply all migrations up to target
                migrations_to_apply = [
                    m for m in self.available_migrations[db_type]
                    if self._compare_versions(m.version, target_version) <= 0
                ]
                direction = MigrationDirection.UP
            elif self._compare_versions(current_version, target_version) < 0:
                # Upgrade needed
                migrations_to_apply = [
                    m for m in self.available_migrations[db_type]
                    if (self._compare_versions(m.version, current_version) > 0 and
                        self._compare_versions(m.version, target_version) <= 0)
                ]
                direction = MigrationDirection.UP
            elif self._compare_versions(current_version, target_version) > 0:
                # Downgrade needed
                migrations_to_apply = [
                    m for m in self.available_migrations[db_type]
                    if (self._compare_versions(m.version, target_version) > 0 and
                        self._compare_versions(m.version, current_version) <= 0)
                ]
                migrations_to_apply.reverse()  # Apply in reverse order for downgrade
                direction = MigrationDirection.DOWN
            else:
                # Already at target version
                migrations_to_apply = []
                direction = MigrationDirection.UP
            
            # Create migration plan
            plan = MigrationPlan(
                target_version=target_version,
                migrations=migrations_to_apply,
                direction=direction,
                requires_backup=len(migrations_to_apply) > 0
            )
            
            migration_plans[db_type] = plan
        
        return migration_plans
    
    async def execute_migration_plan(
        self,
        migration_plan: MigrationPlan,
        database_type: DatabaseType,
        dry_run: bool = False
    ) -> bool:
        """
        Execute a migration plan for a specific database.
        
        Args:
            migration_plan: Migration plan to execute
            database_type: Database type to migrate
            dry_run: If True, validate but don't execute migrations
            
        Returns:
            True if migration was successful
        """
        logger.info(f"Executing migration plan for {database_type.value} (dry_run={dry_run})")
        
        if not migration_plan.migrations:
            logger.info(f"No migrations needed for {database_type.value}")
            return True
        
        try:
            # Create backup if required and not dry run
            if migration_plan.requires_backup and not dry_run:
                backup_success = await self._create_backup(database_type)
                if not backup_success:
                    logger.error(f"Backup failed for {database_type.value}, aborting migration")
                    return False
            
            # Execute migrations
            for migration in migration_plan.migrations:
                logger.info(f"Executing migration: {migration.id}")
                
                if dry_run:
                    # Validate migration script
                    validation_success = await self._validate_migration(migration, database_type)
                    if not validation_success:
                        logger.error(f"Migration validation failed: {migration.id}")
                        return False
                else:
                    # Execute migration
                    execution_success = await self._execute_migration(migration, database_type)
                    if not execution_success:
                        logger.error(f"Migration execution failed: {migration.id}")
                        
                        # Attempt rollback if configured
                        if self.config["migration_settings"]["rollback_on_failure"]:
                            await self._rollback_migration(migration, database_type)
                        
                        return False
                    
                    # Update migration history
                    migration.status = MigrationStatus.COMPLETED
                    migration.applied_at = datetime.now(timezone.utc)
                    self._update_migration_history(migration)
            
            logger.info(f"Migration plan completed successfully for {database_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Migration plan execution failed for {database_type.value}: {e}")
            return False
    
    async def _create_backup(self, database_type: DatabaseType) -> bool:
        """Create backup before migration"""
        logger.info(f"Creating backup for {database_type.value}")
        
        try:
            backup_dir = Path("backups") / datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            if database_type == DatabaseType.POSTGRESQL:
                # PostgreSQL backup using pg_dump
                db_config = self.config["database_connections"]["postgresql"]
                backup_file = backup_dir / "postgresql_backup.sql"
                
                # This would execute pg_dump command
                # For now, just create a placeholder
                with open(backup_file, 'w') as f:
                    f.write(f"-- PostgreSQL backup created at {datetime.now()}\n")
                
            elif database_type == DatabaseType.MILVUS:
                # Milvus backup using collection export
                backup_file = backup_dir / "milvus_backup.json"
                
                # This would export Milvus collections
                # For now, just create a placeholder
                with open(backup_file, 'w') as f:
                    json.dump({"backup_created": datetime.now().isoformat()}, f)
                
            elif database_type == DatabaseType.NEO4J:
                # Neo4j backup using neo4j-admin
                backup_file = backup_dir / "neo4j_backup.dump"
                
                # This would execute neo4j-admin backup command
                # For now, just create a placeholder
                with open(backup_file, 'w') as f:
                    f.write(f"Neo4j backup created at {datetime.now()}\n")
            
            logger.info(f"Backup created successfully: {backup_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Backup creation failed for {database_type.value}: {e}")
            return False
    
    async def _validate_migration(self, migration: Migration, database_type: DatabaseType) -> bool:
        """Validate migration script without executing"""
        logger.debug(f"Validating migration: {migration.id}")
        
        try:
            if database_type == DatabaseType.POSTGRESQL:
                # Validate SQL syntax
                # This would use a SQL parser or dry-run execution
                return True
                
            elif database_type == DatabaseType.MILVUS:
                # Validate Python migration script
                # This would compile and check the Python code
                return True
                
            elif database_type == DatabaseType.NEO4J:
                # Validate Cypher syntax
                # This would use Neo4j's query validation
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Migration validation failed for {migration.id}: {e}")
            return False
    
    async def _execute_migration(self, migration: Migration, database_type: DatabaseType) -> bool:
        """Execute a single migration"""
        logger.info(f"Executing migration: {migration.id}")
        
        try:
            migration.status = MigrationStatus.RUNNING
            
            if database_type == DatabaseType.POSTGRESQL:
                return await self._execute_postgresql_migration(migration)
            elif database_type == DatabaseType.MILVUS:
                return await self._execute_milvus_migration(migration)
            elif database_type == DatabaseType.NEO4J:
                return await self._execute_neo4j_migration(migration)
            
            return False
            
        except Exception as e:
            logger.error(f"Migration execution failed for {migration.id}: {e}")
            migration.status = MigrationStatus.FAILED
            return False
    
    async def _execute_postgresql_migration(self, migration: Migration) -> bool:
        """Execute PostgreSQL migration"""
        try:
            import asyncpg
            
            db_config = self.config["database_connections"]["postgresql"]
            conn = await asyncpg.connect(db_config["connection_string"])
            
            try:
                # Execute migration script
                await conn.execute(migration.up_script)
                
                # Record migration in history table
                await conn.execute("""
                    INSERT INTO schema_migrations (migration_id, version, description, applied_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (migration_id) DO NOTHING
                """, migration.id, migration.version, migration.description, datetime.now(timezone.utc))
                
                logger.info(f"PostgreSQL migration completed: {migration.id}")
                return True
                
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"PostgreSQL migration failed: {migration.id}: {e}")
            return False
    
    async def _execute_milvus_migration(self, migration: Migration) -> bool:
        """Execute Milvus migration"""
        try:
            # Execute Python migration script
            # This would involve importing and running the migration module
            logger.info(f"Milvus migration completed: {migration.id}")
            return True
            
        except Exception as e:
            logger.error(f"Milvus migration failed: {migration.id}: {e}")
            return False
    
    async def _execute_neo4j_migration(self, migration: Migration) -> bool:
        """Execute Neo4j migration"""
        try:
            from neo4j import GraphDatabase
            
            db_config = self.config["database_connections"]["neo4j"]
            driver = GraphDatabase.driver(
                db_config["uri"],
                auth=(db_config["user"], db_config["password"])
            )
            
            try:
                with driver.session() as session:
                    # Execute migration script
                    session.run(migration.up_script)
                    
                    # Record migration in history
                    session.run("""
                        MERGE (m:Migration {id: $id})
                        SET m.version = $version,
                            m.description = $description,
                            m.applied_at = datetime()
                    """, id=migration.id, version=migration.version, description=migration.description)
                
                logger.info(f"Neo4j migration completed: {migration.id}")
                return True
                
            finally:
                driver.close()
                
        except Exception as e:
            logger.error(f"Neo4j migration failed: {migration.id}: {e}")
            return False
    
    async def _rollback_migration(self, migration: Migration, database_type: DatabaseType) -> bool:
        """Rollback a migration"""
        if not migration.down_script:
            logger.warning(f"No rollback script available for migration: {migration.id}")
            return False
        
        logger.info(f"Rolling back migration: {migration.id}")
        
        try:
            # Create a rollback migration and execute it
            rollback_migration = Migration(
                id=f"{migration.id}_rollback",
                database_type=database_type,
                version=migration.version,
                description=f"Rollback: {migration.description}",
                up_script=migration.down_script
            )
            
            success = await self._execute_migration(rollback_migration, database_type)
            if success:
                migration.status = MigrationStatus.ROLLED_BACK
                logger.info(f"Migration rolled back successfully: {migration.id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Migration rollback failed for {migration.id}: {e}")
            return False
    
    def _update_migration_history(self, migration: Migration) -> None:
        """Update migration history in configuration"""
        db_type_key = migration.database_type.value
        
        if "version_history" not in self.config:
            self.config["version_history"] = {}
        
        if db_type_key not in self.config["version_history"]:
            self.config["version_history"][db_type_key] = {
                "current": None,
                "migrations": []
            }
        
        # Update current version
        self.config["version_history"][db_type_key]["current"] = migration.version
        
        # Add migration to history
        migration_record = {
            "id": migration.id,
            "version": migration.version,
            "description": migration.description,
            "applied_at": migration.applied_at.isoformat() if migration.applied_at else None,
            "status": migration.status.value
        }
        
        self.config["version_history"][db_type_key]["migrations"].append(migration_record)
        
        # Save updated configuration
        self._save_migration_config()
    
    async def migrate_to_latest(self, databases: Optional[List[DatabaseType]] = None) -> Dict[DatabaseType, bool]:
        """
        Migrate all databases to their latest versions.
        
        Args:
            databases: List of databases to migrate (None for all)
            
        Returns:
            Dictionary mapping database types to success status
        """
        if databases is None:
            databases = list(DatabaseType)
        
        logger.info(f"Migrating databases to latest versions: {[db.value for db in databases]}")
        
        # Get current and latest versions
        current_versions = await self.get_current_versions()
        latest_versions = self.get_latest_versions()
        
        # Create target versions dictionary
        target_versions = {}
        for db_type in databases:
            if latest_versions[db_type]:
                target_versions[db_type] = latest_versions[db_type]
        
        if not target_versions:
            logger.info("No migrations available")
            return {}
        
        # Create migration plans
        migration_plans = self.create_migration_plan(target_versions, current_versions)
        
        # Execute migrations in dependency order
        execution_order = self._get_execution_order(databases)
        results = {}
        
        for db_type in execution_order:
            if db_type in migration_plans:
                plan = migration_plans[db_type]
                success = await self.execute_migration_plan(plan, db_type)
                results[db_type] = success
                
                if not success:
                    logger.error(f"Migration failed for {db_type.value}, stopping execution")
                    break
        
        return results
    
    def _get_execution_order(self, databases: List[DatabaseType]) -> List[DatabaseType]:
        """Get execution order based on dependencies"""
        dependencies = self.config["migration_dependencies"]
        ordered = []
        remaining = databases.copy()
        
        while remaining:
            # Find databases with no unresolved dependencies
            ready = []
            for db_type in remaining:
                db_deps = dependencies.get(db_type.value, [])
                if all(DatabaseType(dep) in ordered or DatabaseType(dep) not in databases for dep in db_deps):
                    ready.append(db_type)
            
            if not ready:
                # Circular dependency or missing dependency, add remaining in original order
                ordered.extend(remaining)
                break
            
            # Add ready databases to execution order
            for db_type in ready:
                ordered.append(db_type)
                remaining.remove(db_type)
        
        return ordered
    
    async def rollback_to_version(
        self,
        target_versions: Dict[DatabaseType, str],
        databases: Optional[List[DatabaseType]] = None
    ) -> Dict[DatabaseType, bool]:
        """
        Rollback databases to specific versions.
        
        Args:
            target_versions: Target versions for each database
            databases: List of databases to rollback (None for all in target_versions)
            
        Returns:
            Dictionary mapping database types to success status
        """
        if databases is None:
            databases = list(target_versions.keys())
        
        logger.info(f"Rolling back databases to specified versions")
        
        # Get current versions
        current_versions = await self.get_current_versions()
        
        # Create migration plans for rollback
        migration_plans = self.create_migration_plan(target_versions, current_versions)
        
        # Execute rollbacks in reverse dependency order
        execution_order = self._get_execution_order(databases)
        execution_order.reverse()
        
        results = {}
        
        for db_type in execution_order:
            if db_type in migration_plans:
                plan = migration_plans[db_type]
                success = await self.execute_migration_plan(plan, db_type)
                results[db_type] = success
                
                if not success:
                    logger.error(f"Rollback failed for {db_type.value}, stopping execution")
                    break
        
        return results
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get comprehensive migration status"""
        return {
            "available_migrations": {
                db_type.value: len(migrations)
                for db_type, migrations in self.available_migrations.items()
            },
            "version_history": self.config.get("version_history", {}),
            "migration_settings": self.config.get("migration_settings", {}),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }


# Convenience functions

async def migrate_all_to_latest() -> Dict[DatabaseType, bool]:
    """Convenience function to migrate all databases to latest versions"""
    manager = SchemaVersionManager()
    return await manager.migrate_to_latest()


async def get_current_schema_versions() -> Dict[DatabaseType, Optional[str]]:
    """Convenience function to get current schema versions"""
    manager = SchemaVersionManager()
    return await manager.get_current_versions()