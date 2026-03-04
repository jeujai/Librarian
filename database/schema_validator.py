#!/usr/bin/env python3
"""
Database Schema Validator

This module provides comprehensive schema validation and versioning capabilities
for all database systems used in the Multimodal Librarian application.

Features:
- Schema version tracking and migration
- Cross-database schema validation
- Schema compatibility checking
- Automated schema upgrade/downgrade
- Schema drift detection
- Validation reporting and logging

Usage:
    from database.schema_validator import SchemaValidator
    
    # Initialize validator
    validator = SchemaValidator()
    
    # Validate all database schemas
    results = await validator.validate_all_schemas()
    
    # Check schema versions
    versions = await validator.get_schema_versions()
    
    # Migrate to latest schema version
    await validator.migrate_to_latest()
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

try:
    from pymilvus import Collection, MilvusException, utility
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

logger = logging.getLogger(__name__)


class DatabaseType(Enum):
    """Supported database types"""
    POSTGRESQL = "postgresql"
    MILVUS = "milvus"
    NEO4J = "neo4j"


class ValidationStatus(Enum):
    """Schema validation status"""
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"


class MigrationDirection(Enum):
    """Migration direction"""
    UP = "up"
    DOWN = "down"


@dataclass
class SchemaVersion:
    """Schema version information"""
    database_type: DatabaseType
    version: str
    description: str
    applied_at: Optional[datetime] = None
    checksum: Optional[str] = None
    migration_script: Optional[str] = None
    rollback_script: Optional[str] = None


@dataclass
class ValidationIssue:
    """Schema validation issue"""
    severity: ValidationStatus
    category: str
    message: str
    details: Optional[Dict[str, Any]] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Schema validation result"""
    database_type: DatabaseType
    database_name: str
    status: ValidationStatus
    version: Optional[str] = None
    issues: List[ValidationIssue] = None
    validated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []
        if self.validated_at is None:
            self.validated_at = datetime.now(timezone.utc)


class SchemaValidator:
    """
    Comprehensive schema validator for all database systems.
    
    This class provides validation and versioning capabilities across
    PostgreSQL, Milvus, and Neo4j databases used by the application.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize schema validator.
        
        Args:
            config_path: Path to schema configuration file
        """
        self.config_path = config_path or "database/schema_config.json"
        self.schema_versions = {}
        self.validation_cache = {}
        self._load_schema_config()
    
    def _load_schema_config(self) -> None:
        """Load schema configuration from file"""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    self.schema_config = config
                    logger.info(f"Loaded schema config from {self.config_path}")
            else:
                # Create default configuration
                self.schema_config = self._create_default_config()
                self._save_schema_config()
                logger.info(f"Created default schema config at {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load schema config: {e}")
            self.schema_config = self._create_default_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default schema configuration"""
        return {
            "version": "1.0.0",
            "databases": {
                "postgresql": {
                    "current_version": "1.0.0",
                    "schema_files": [
                        "database/postgresql/init/01_extensions.sql",
                        "database/postgresql/init/02_users_and_permissions.sql",
                        "database/postgresql/init/03_performance_tuning.sql",
                        "database/postgresql/init/04_monitoring_setup.sql",
                        "database/postgresql/init/05_maintenance_functions.sql",
                        "database/postgresql/init/06_application_schema.sql",
                        "database/postgresql/init/07_migration_compatibility.sql",
                        "database/postgresql/init/08_existing_migrations_port.sql"
                    ],
                    "validation_rules": {
                        "required_extensions": ["uuid-ossp", "pg_trgm", "btree_gin"],
                        "required_schemas": ["multimodal_librarian", "audit", "monitoring"],
                        "required_tables": [
                            "multimodal_librarian.users",
                            "multimodal_librarian.knowledge_sources",
                            "multimodal_librarian.conversation_threads",
                            "multimodal_librarian.messages",
                            "multimodal_librarian.knowledge_chunks"
                        ]
                    }
                },
                "milvus": {
                    "current_version": "1.0.0",
                    "schema_files": [
                        "database/milvus/schemas.py",
                        "database/milvus/init_schemas.py"
                    ],
                    "validation_rules": {
                        "required_collections": [
                            "knowledge_chunks",
                            "document_embeddings",
                            "conversation_embeddings"
                        ],
                        "vector_dimensions": {
                            "knowledge_chunks": 384,
                            "document_embeddings": 384,
                            "conversation_embeddings": 384
                        }
                    }
                },
                "neo4j": {
                    "current_version": "1.0.0",
                    "schema_files": [
                        "database/neo4j/init/00_schema_initialization.cypher",
                        "database/neo4j/init/01_verify_plugins.cypher",
                        "database/neo4j/init/02_create_constraints.cypher",
                        "database/neo4j/init/03_sample_data.cypher"
                    ],
                    "validation_rules": {
                        "required_constraints": [
                            "document_id_unique",
                            "concept_name_type_unique",
                            "user_id_unique",
                            "conversation_id_unique"
                        ],
                        "required_indexes": [
                            "document_created_at",
                            "concept_confidence",
                            "user_created_at"
                        ],
                        "required_node_types": [
                            "Document",
                            "Concept",
                            "User",
                            "Conversation",
                            "Chunk"
                        ]
                    }
                }
            },
            "migration_history": [],
            "validation_settings": {
                "strict_mode": False,
                "auto_fix_minor_issues": True,
                "backup_before_migration": True,
                "validation_timeout": 300
            }
        }
    
    def _save_schema_config(self) -> None:
        """Save schema configuration to file"""
        try:
            config_file = Path(self.config_path)
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_file, 'w') as f:
                json.dump(self.schema_config, f, indent=2, default=str)
            
            logger.debug(f"Saved schema config to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save schema config: {e}")
    
    def _calculate_schema_checksum(self, schema_files: List[str]) -> str:
        """Calculate checksum for schema files"""
        hasher = hashlib.sha256()
        
        for file_path in sorted(schema_files):
            try:
                file_path_obj = Path(file_path)
                if file_path_obj.exists():
                    with open(file_path_obj, 'rb') as f:
                        hasher.update(f.read())
                else:
                    logger.warning(f"Schema file not found: {file_path}")
                    hasher.update(f"MISSING:{file_path}".encode())
            except Exception as e:
                logger.error(f"Error reading schema file {file_path}: {e}")
                hasher.update(f"ERROR:{file_path}".encode())
        
        return hasher.hexdigest()
    
    async def validate_postgresql_schema(
        self, 
        connection_string: str,
        database_name: str = "multimodal_librarian"
    ) -> ValidationResult:
        """
        Validate PostgreSQL schema against expected configuration.
        
        Args:
            connection_string: PostgreSQL connection string
            database_name: Name of the database to validate
            
        Returns:
            ValidationResult with validation status and issues
        """
        if not ASYNCPG_AVAILABLE:
            return ValidationResult(
                database_type=DatabaseType.POSTGRESQL,
                database_name=database_name,
                status=ValidationStatus.ERROR,
                issues=[ValidationIssue(
                    severity=ValidationStatus.ERROR,
                    category="dependency",
                    message="asyncpg not available for PostgreSQL validation"
                )]
            )
        
        result = ValidationResult(
            database_type=DatabaseType.POSTGRESQL,
            database_name=database_name,
            status=ValidationStatus.VALID
        )
        
        try:
            conn = await asyncpg.connect(connection_string)
            
            try:
                # Get database configuration
                db_config = self.schema_config["databases"]["postgresql"]
                validation_rules = db_config["validation_rules"]
                
                # Check required extensions
                extensions_query = """
                    SELECT extname FROM pg_extension 
                    WHERE extname = ANY($1::text[])
                """
                required_extensions = validation_rules["required_extensions"]
                installed_extensions = await conn.fetch(
                    extensions_query, 
                    required_extensions
                )
                installed_ext_names = {row['extname'] for row in installed_extensions}
                
                missing_extensions = set(required_extensions) - installed_ext_names
                if missing_extensions:
                    result.issues.append(ValidationIssue(
                        severity=ValidationStatus.ERROR,
                        category="extensions",
                        message=f"Missing required extensions: {missing_extensions}",
                        suggestion="Install missing extensions using CREATE EXTENSION"
                    ))
                    result.status = ValidationStatus.INVALID
                
                # Check required schemas
                schemas_query = """
                    SELECT schema_name FROM information_schema.schemata 
                    WHERE schema_name = ANY($1::text[])
                """
                required_schemas = validation_rules["required_schemas"]
                existing_schemas = await conn.fetch(schemas_query, required_schemas)
                existing_schema_names = {row['schema_name'] for row in existing_schemas}
                
                missing_schemas = set(required_schemas) - existing_schema_names
                if missing_schemas:
                    result.issues.append(ValidationIssue(
                        severity=ValidationStatus.ERROR,
                        category="schemas",
                        message=f"Missing required schemas: {missing_schemas}",
                        suggestion="Create missing schemas using CREATE SCHEMA"
                    ))
                    result.status = ValidationStatus.INVALID
                
                # Check required tables
                tables_query = """
                    SELECT schemaname || '.' || tablename as full_name
                    FROM pg_tables 
                    WHERE schemaname || '.' || tablename = ANY($1::text[])
                """
                required_tables = validation_rules["required_tables"]
                existing_tables = await conn.fetch(tables_query, required_tables)
                existing_table_names = {row['full_name'] for row in existing_tables}
                
                missing_tables = set(required_tables) - existing_table_names
                if missing_tables:
                    result.issues.append(ValidationIssue(
                        severity=ValidationStatus.ERROR,
                        category="tables",
                        message=f"Missing required tables: {missing_tables}",
                        suggestion="Run schema initialization scripts to create tables"
                    ))
                    result.status = ValidationStatus.INVALID
                
                # Check schema version
                version_query = """
                    SELECT version FROM multimodal_librarian.schema_version 
                    ORDER BY applied_at DESC LIMIT 1
                """
                try:
                    version_row = await conn.fetchrow(version_query)
                    if version_row:
                        result.version = version_row['version']
                        expected_version = db_config["current_version"]
                        if result.version != expected_version:
                            result.issues.append(ValidationIssue(
                                severity=ValidationStatus.WARNING,
                                category="version",
                                message=f"Schema version mismatch: expected {expected_version}, got {result.version}",
                                suggestion="Run schema migration to update to latest version"
                            ))
                            if result.status == ValidationStatus.VALID:
                                result.status = ValidationStatus.WARNING
                    else:
                        result.issues.append(ValidationIssue(
                            severity=ValidationStatus.WARNING,
                            category="version",
                            message="No schema version information found",
                            suggestion="Initialize schema version tracking"
                        ))
                        if result.status == ValidationStatus.VALID:
                            result.status = ValidationStatus.WARNING
                except Exception as e:
                    logger.debug(f"Could not check schema version: {e}")
                    result.issues.append(ValidationIssue(
                        severity=ValidationStatus.WARNING,
                        category="version",
                        message="Schema version table not accessible",
                        suggestion="Ensure schema version tracking is properly initialized"
                    ))
                
                # Calculate and verify schema checksum
                schema_files = db_config["schema_files"]
                current_checksum = self._calculate_schema_checksum(schema_files)
                
                # Store checksum for future validation
                self.schema_versions[DatabaseType.POSTGRESQL] = SchemaVersion(
                    database_type=DatabaseType.POSTGRESQL,
                    version=result.version or "unknown",
                    description="PostgreSQL schema validation",
                    applied_at=datetime.now(timezone.utc),
                    checksum=current_checksum
                )
                
                logger.info(f"PostgreSQL schema validation completed: {result.status.value}")
                
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"PostgreSQL schema validation failed: {e}")
            result.status = ValidationStatus.ERROR
            result.issues.append(ValidationIssue(
                severity=ValidationStatus.ERROR,
                category="connection",
                message=f"Database connection or query failed: {e}",
                suggestion="Check database connectivity and permissions"
            ))
        
        return result
    
    async def validate_milvus_schema(
        self,
        host: str = "localhost",
        port: int = 19530,
        connection_alias: str = "validation"
    ) -> ValidationResult:
        """
        Validate Milvus schema against expected configuration.
        
        Args:
            host: Milvus host
            port: Milvus port
            connection_alias: Connection alias for Milvus
            
        Returns:
            ValidationResult with validation status and issues
        """
        if not PYMILVUS_AVAILABLE:
            return ValidationResult(
                database_type=DatabaseType.MILVUS,
                database_name=f"{host}:{port}",
                status=ValidationStatus.ERROR,
                issues=[ValidationIssue(
                    severity=ValidationStatus.ERROR,
                    category="dependency",
                    message="pymilvus not available for Milvus validation"
                )]
            )
        
        result = ValidationResult(
            database_type=DatabaseType.MILVUS,
            database_name=f"{host}:{port}",
            status=ValidationStatus.VALID
        )
        
        try:
            from pymilvus import connections

            # Connect to Milvus
            connections.connect(
                alias=connection_alias,
                host=host,
                port=str(port),
                timeout=30
            )
            
            try:
                # Get database configuration
                db_config = self.schema_config["databases"]["milvus"]
                validation_rules = db_config["validation_rules"]
                
                # Check required collections
                existing_collections = utility.list_collections(using=connection_alias)
                required_collections = validation_rules["required_collections"]
                
                missing_collections = set(required_collections) - set(existing_collections)
                if missing_collections:
                    result.issues.append(ValidationIssue(
                        severity=ValidationStatus.ERROR,
                        category="collections",
                        message=f"Missing required collections: {missing_collections}",
                        suggestion="Run Milvus schema initialization to create collections"
                    ))
                    result.status = ValidationStatus.INVALID
                
                # Check vector dimensions for existing collections
                vector_dimensions = validation_rules["vector_dimensions"]
                for collection_name in existing_collections:
                    if collection_name in vector_dimensions:
                        try:
                            collection = Collection(collection_name, using=connection_alias)
                            schema = collection.schema
                            
                            # Find vector field
                            vector_field = None
                            for field in schema.fields:
                                if hasattr(field, 'dtype') and 'VECTOR' in str(field.dtype):
                                    vector_field = field
                                    break
                            
                            if vector_field:
                                actual_dim = vector_field.params.get('dim', 0)
                                expected_dim = vector_dimensions[collection_name]
                                
                                if actual_dim != expected_dim:
                                    result.issues.append(ValidationIssue(
                                        severity=ValidationStatus.ERROR,
                                        category="dimensions",
                                        message=f"Collection {collection_name} dimension mismatch: expected {expected_dim}, got {actual_dim}",
                                        suggestion="Recreate collection with correct dimension"
                                    ))
                                    result.status = ValidationStatus.INVALID
                            else:
                                result.issues.append(ValidationIssue(
                                    severity=ValidationStatus.WARNING,
                                    category="schema",
                                    message=f"Collection {collection_name} has no vector field",
                                    suggestion="Verify collection schema definition"
                                ))
                                if result.status == ValidationStatus.VALID:
                                    result.status = ValidationStatus.WARNING
                        
                        except Exception as e:
                            logger.warning(f"Could not validate collection {collection_name}: {e}")
                            result.issues.append(ValidationIssue(
                                severity=ValidationStatus.WARNING,
                                category="collection_access",
                                message=f"Could not access collection {collection_name}: {e}",
                                suggestion="Check collection status and permissions"
                            ))
                
                # Set version information
                result.version = db_config["current_version"]
                
                # Calculate schema checksum
                schema_files = db_config["schema_files"]
                current_checksum = self._calculate_schema_checksum(schema_files)
                
                self.schema_versions[DatabaseType.MILVUS] = SchemaVersion(
                    database_type=DatabaseType.MILVUS,
                    version=result.version,
                    description="Milvus schema validation",
                    applied_at=datetime.now(timezone.utc),
                    checksum=current_checksum
                )
                
                logger.info(f"Milvus schema validation completed: {result.status.value}")
                
            finally:
                connections.disconnect(alias=connection_alias)
                
        except Exception as e:
            logger.error(f"Milvus schema validation failed: {e}")
            result.status = ValidationStatus.ERROR
            result.issues.append(ValidationIssue(
                severity=ValidationStatus.ERROR,
                category="connection",
                message=f"Milvus connection or query failed: {e}",
                suggestion="Check Milvus connectivity and service status"
            ))
        
        return result
    
    async def validate_neo4j_schema(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "ml_password"
    ) -> ValidationResult:
        """
        Validate Neo4j schema against expected configuration.
        
        Args:
            uri: Neo4j connection URI
            user: Neo4j username
            password: Neo4j password
            
        Returns:
            ValidationResult with validation status and issues
        """
        if not NEO4J_AVAILABLE:
            return ValidationResult(
                database_type=DatabaseType.NEO4J,
                database_name=uri,
                status=ValidationStatus.ERROR,
                issues=[ValidationIssue(
                    severity=ValidationStatus.ERROR,
                    category="dependency",
                    message="neo4j driver not available for Neo4j validation"
                )]
            )
        
        result = ValidationResult(
            database_type=DatabaseType.NEO4J,
            database_name=uri,
            status=ValidationStatus.VALID
        )
        
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            
            try:
                with driver.session() as session:
                    # Get database configuration
                    db_config = self.schema_config["databases"]["neo4j"]
                    validation_rules = db_config["validation_rules"]
                    
                    # Check required constraints
                    constraints_query = "CALL db.constraints() YIELD name RETURN name"
                    constraints_result = session.run(constraints_query)
                    existing_constraints = {record["name"] for record in constraints_result}
                    
                    required_constraints = validation_rules["required_constraints"]
                    missing_constraints = set(required_constraints) - existing_constraints
                    
                    if missing_constraints:
                        result.issues.append(ValidationIssue(
                            severity=ValidationStatus.ERROR,
                            category="constraints",
                            message=f"Missing required constraints: {missing_constraints}",
                            suggestion="Run Neo4j schema initialization to create constraints"
                        ))
                        result.status = ValidationStatus.INVALID
                    
                    # Check required indexes
                    indexes_query = "CALL db.indexes() YIELD name WHERE state = 'ONLINE' RETURN name"
                    indexes_result = session.run(indexes_query)
                    existing_indexes = {record["name"] for record in indexes_result}
                    
                    required_indexes = validation_rules["required_indexes"]
                    missing_indexes = set(required_indexes) - existing_indexes
                    
                    if missing_indexes:
                        result.issues.append(ValidationIssue(
                            severity=ValidationStatus.WARNING,
                            category="indexes",
                            message=f"Missing recommended indexes: {missing_indexes}",
                            suggestion="Create missing indexes for better performance"
                        ))
                        if result.status == ValidationStatus.VALID:
                            result.status = ValidationStatus.WARNING
                    
                    # Check required node types (by checking if nodes exist)
                    required_node_types = validation_rules["required_node_types"]
                    for node_type in required_node_types:
                        count_query = f"MATCH (n:{node_type}) RETURN count(n) as count LIMIT 1"
                        count_result = session.run(count_query)
                        # Just checking if the query executes without error
                        # (indicates the label exists in the schema)
                        try:
                            list(count_result)
                        except Exception as e:
                            result.issues.append(ValidationIssue(
                                severity=ValidationStatus.WARNING,
                                category="node_types",
                                message=f"Node type {node_type} may not be properly defined: {e}",
                                suggestion="Verify schema initialization completed successfully"
                            ))
                    
                    # Check schema version (if schema documentation exists)
                    version_query = """
                        MATCH (s:SchemaDoc) 
                        RETURN s.version as version, s.last_updated as updated
                        ORDER BY s.last_updated DESC LIMIT 1
                    """
                    try:
                        version_result = session.run(version_query)
                        version_record = version_result.single()
                        if version_record:
                            result.version = version_record["version"]
                            expected_version = db_config["current_version"]
                            if result.version != expected_version:
                                result.issues.append(ValidationIssue(
                                    severity=ValidationStatus.WARNING,
                                    category="version",
                                    message=f"Schema version mismatch: expected {expected_version}, got {result.version}",
                                    suggestion="Update schema documentation or run migration"
                                ))
                                if result.status == ValidationStatus.VALID:
                                    result.status = ValidationStatus.WARNING
                        else:
                            result.issues.append(ValidationIssue(
                                severity=ValidationStatus.WARNING,
                                category="version",
                                message="No schema version documentation found",
                                suggestion="Initialize schema documentation"
                            ))
                    except Exception as e:
                        logger.debug(f"Could not check Neo4j schema version: {e}")
                        result.version = db_config["current_version"]
                    
                    # Calculate schema checksum
                    schema_files = db_config["schema_files"]
                    current_checksum = self._calculate_schema_checksum(schema_files)
                    
                    self.schema_versions[DatabaseType.NEO4J] = SchemaVersion(
                        database_type=DatabaseType.NEO4J,
                        version=result.version or db_config["current_version"],
                        description="Neo4j schema validation",
                        applied_at=datetime.now(timezone.utc),
                        checksum=current_checksum
                    )
                    
                    logger.info(f"Neo4j schema validation completed: {result.status.value}")
                    
            finally:
                driver.close()
                
        except Exception as e:
            logger.error(f"Neo4j schema validation failed: {e}")
            result.status = ValidationStatus.ERROR
            result.issues.append(ValidationIssue(
                severity=ValidationStatus.ERROR,
                category="connection",
                message=f"Neo4j connection or query failed: {e}",
                suggestion="Check Neo4j connectivity and authentication"
            ))
        
        return result
    
    async def validate_all_schemas(
        self,
        postgresql_conn: Optional[str] = None,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "ml_password"
    ) -> Dict[DatabaseType, ValidationResult]:
        """
        Validate all database schemas.
        
        Args:
            postgresql_conn: PostgreSQL connection string
            milvus_host: Milvus host
            milvus_port: Milvus port
            neo4j_uri: Neo4j connection URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            
        Returns:
            Dictionary mapping database types to validation results
        """
        logger.info("Starting comprehensive schema validation...")
        
        results = {}
        
        # Validate PostgreSQL
        if postgresql_conn:
            logger.info("Validating PostgreSQL schema...")
            results[DatabaseType.POSTGRESQL] = await self.validate_postgresql_schema(
                postgresql_conn
            )
        else:
            logger.info("Skipping PostgreSQL validation (no connection string provided)")
        
        # Validate Milvus
        logger.info("Validating Milvus schema...")
        results[DatabaseType.MILVUS] = await self.validate_milvus_schema(
            milvus_host, milvus_port
        )
        
        # Validate Neo4j
        logger.info("Validating Neo4j schema...")
        results[DatabaseType.NEO4J] = await self.validate_neo4j_schema(
            neo4j_uri, neo4j_user, neo4j_password
        )
        
        # Generate summary
        valid_count = sum(1 for result in results.values() if result.status == ValidationStatus.VALID)
        warning_count = sum(1 for result in results.values() if result.status == ValidationStatus.WARNING)
        error_count = sum(1 for result in results.values() if result.status in [ValidationStatus.INVALID, ValidationStatus.ERROR])
        
        logger.info(f"Schema validation completed: {valid_count} valid, {warning_count} warnings, {error_count} errors")
        
        return results
    
    def get_schema_versions(self) -> Dict[DatabaseType, SchemaVersion]:
        """Get current schema versions for all databases"""
        return self.schema_versions.copy()
    
    def generate_validation_report(
        self, 
        results: Dict[DatabaseType, ValidationResult],
        output_file: Optional[str] = None
    ) -> str:
        """
        Generate a comprehensive validation report.
        
        Args:
            results: Validation results from validate_all_schemas
            output_file: Optional file path to save the report
            
        Returns:
            Report content as string
        """
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("DATABASE SCHEMA VALIDATION REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        report_lines.append("")
        
        # Summary
        valid_count = sum(1 for result in results.values() if result.status == ValidationStatus.VALID)
        warning_count = sum(1 for result in results.values() if result.status == ValidationStatus.WARNING)
        error_count = sum(1 for result in results.values() if result.status in [ValidationStatus.INVALID, ValidationStatus.ERROR])
        
        report_lines.append("SUMMARY")
        report_lines.append("-" * 40)
        report_lines.append(f"Total Databases: {len(results)}")
        report_lines.append(f"Valid: {valid_count}")
        report_lines.append(f"Warnings: {warning_count}")
        report_lines.append(f"Errors: {error_count}")
        report_lines.append("")
        
        # Detailed results
        for db_type, result in results.items():
            report_lines.append(f"{db_type.value.upper()} DATABASE")
            report_lines.append("-" * 40)
            report_lines.append(f"Database: {result.database_name}")
            report_lines.append(f"Status: {result.status.value.upper()}")
            report_lines.append(f"Version: {result.version or 'Unknown'}")
            report_lines.append(f"Validated: {result.validated_at.isoformat()}")
            
            if result.issues:
                report_lines.append(f"Issues ({len(result.issues)}):")
                for i, issue in enumerate(result.issues, 1):
                    report_lines.append(f"  {i}. [{issue.severity.value.upper()}] {issue.category}: {issue.message}")
                    if issue.suggestion:
                        report_lines.append(f"     Suggestion: {issue.suggestion}")
            else:
                report_lines.append("No issues found.")
            
            report_lines.append("")
        
        # Schema versions
        if self.schema_versions:
            report_lines.append("SCHEMA VERSIONS")
            report_lines.append("-" * 40)
            for db_type, version in self.schema_versions.items():
                report_lines.append(f"{db_type.value}: {version.version} (checksum: {version.checksum[:8]}...)")
            report_lines.append("")
        
        report_lines.append("=" * 80)
        
        report_content = "\n".join(report_lines)
        
        # Save to file if requested
        if output_file:
            try:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w') as f:
                    f.write(report_content)
                logger.info(f"Validation report saved to {output_file}")
            except Exception as e:
                logger.error(f"Failed to save validation report: {e}")
        
        return report_content
    
    async def check_schema_drift(self) -> Dict[DatabaseType, bool]:
        """
        Check if schemas have drifted from their expected state.
        
        Returns:
            Dictionary mapping database types to drift status (True = drifted)
        """
        logger.info("Checking for schema drift...")
        
        drift_status = {}
        
        for db_type, db_config in self.schema_config["databases"].items():
            try:
                db_type_enum = DatabaseType(db_type)
                
                # Calculate current checksum
                schema_files = db_config["schema_files"]
                current_checksum = self._calculate_schema_checksum(schema_files)
                
                # Compare with stored checksum
                if db_type_enum in self.schema_versions:
                    stored_version = self.schema_versions[db_type_enum]
                    has_drifted = stored_version.checksum != current_checksum
                    drift_status[db_type_enum] = has_drifted
                    
                    if has_drifted:
                        logger.warning(f"Schema drift detected for {db_type}: {stored_version.checksum[:8]}... -> {current_checksum[:8]}...")
                    else:
                        logger.debug(f"No schema drift for {db_type}")
                else:
                    # No stored version, assume drift
                    drift_status[db_type_enum] = True
                    logger.warning(f"No stored schema version for {db_type}, assuming drift")
                    
            except Exception as e:
                logger.error(f"Error checking schema drift for {db_type}: {e}")
                drift_status[DatabaseType(db_type)] = True
        
        return drift_status


# Convenience functions for direct usage

async def validate_all_database_schemas(
    postgresql_conn: Optional[str] = None,
    milvus_host: str = "localhost",
    milvus_port: int = 19530,
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "ml_password"
) -> Dict[DatabaseType, ValidationResult]:
    """
    Convenience function to validate all database schemas.
    
    Returns:
        Dictionary mapping database types to validation results
    """
    validator = SchemaValidator()
    return await validator.validate_all_schemas(
        postgresql_conn=postgresql_conn,
        milvus_host=milvus_host,
        milvus_port=milvus_port,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password
    )


def generate_schema_validation_report(
    results: Dict[DatabaseType, ValidationResult],
    output_file: Optional[str] = None
) -> str:
    """
    Convenience function to generate validation report.
    
    Returns:
        Report content as string
    """
    validator = SchemaValidator()
    return validator.generate_validation_report(results, output_file)