#!/usr/bin/env python3
"""
Tests for Database Schema Validation System

This module tests the schema validation and versioning functionality
for all database systems used in the Multimodal Librarian application.
"""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone

# Import the modules to test
try:
    from database.schema_validator import (
        SchemaValidator, DatabaseType, ValidationStatus, ValidationResult,
        ValidationIssue, SchemaVersion
    )
    from database.schema_version_manager import (
        SchemaVersionManager, Migration, MigrationStatus, MigrationDirection
    )
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Schema validation modules not available")
class TestSchemaValidator:
    """Test cases for SchemaValidator"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.config_path = self.temp_config.name
        
        # Create test configuration
        test_config = {
            "version": "1.0.0",
            "databases": {
                "postgresql": {
                    "current_version": "1.0.0",
                    "schema_files": ["test_schema.sql"],
                    "validation_rules": {
                        "required_extensions": ["uuid-ossp"],
                        "required_schemas": ["test_schema"],
                        "required_tables": ["test_schema.test_table"]
                    }
                },
                "milvus": {
                    "current_version": "1.0.0",
                    "schema_files": ["test_schema.py"],
                    "validation_rules": {
                        "required_collections": ["test_collection"],
                        "vector_dimensions": {"test_collection": 384}
                    }
                },
                "neo4j": {
                    "current_version": "1.0.0",
                    "schema_files": ["test_schema.cypher"],
                    "validation_rules": {
                        "required_constraints": ["test_constraint"],
                        "required_indexes": ["test_index"],
                        "required_node_types": ["TestNode"]
                    }
                }
            }
        }
        
        json.dump(test_config, self.temp_config)
        self.temp_config.close()
        
        self.validator = SchemaValidator(self.config_path)
    
    def teardown_method(self):
        """Clean up test fixtures"""
        Path(self.config_path).unlink(missing_ok=True)
    
    def test_validator_initialization(self):
        """Test validator initialization with config"""
        assert self.validator.config_path == self.config_path
        assert "databases" in self.validator.schema_config
        assert "postgresql" in self.validator.schema_config["databases"]
    
    def test_default_config_creation(self):
        """Test creation of default configuration"""
        # Test with non-existent config file
        temp_path = "/tmp/nonexistent_config.json"
        validator = SchemaValidator(temp_path)
        
        assert validator.schema_config is not None
        assert "databases" in validator.schema_config
        assert "postgresql" in validator.schema_config["databases"]
        assert "milvus" in validator.schema_config["databases"]
        assert "neo4j" in validator.schema_config["databases"]
    
    def test_schema_checksum_calculation(self):
        """Test schema checksum calculation"""
        # Create temporary schema files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("CREATE TABLE test (id INTEGER);")
            schema_file = f.name
        
        try:
            checksum = self.validator._calculate_schema_checksum([schema_file])
            assert isinstance(checksum, str)
            assert len(checksum) == 64  # SHA256 hex digest length
            
            # Same content should produce same checksum
            checksum2 = self.validator._calculate_schema_checksum([schema_file])
            assert checksum == checksum2
        finally:
            Path(schema_file).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_postgresql_validation_success(self):
        """Test successful PostgreSQL schema validation"""
        # Mock asyncpg connection
        mock_conn = AsyncMock()
        
        # Mock successful extension check
        mock_conn.fetch.side_effect = [
            [{'extname': 'uuid-ossp'}],  # extensions
            [{'schema_name': 'test_schema'}],  # schemas
            [{'full_name': 'test_schema.test_table'}],  # tables
        ]
        
        # Mock version check
        mock_conn.fetchrow.return_value = {'version': '1.0.0'}
        
        with patch('asyncpg.connect', return_value=mock_conn):
            result = await self.validator.validate_postgresql_schema(
                "postgresql://test:test@localhost/test"
            )
        
        assert result.database_type == DatabaseType.POSTGRESQL
        assert result.status == ValidationStatus.VALID
        assert result.version == "1.0.0"
        assert len(result.issues) == 0
    
    @pytest.mark.asyncio
    async def test_postgresql_validation_missing_extensions(self):
        """Test PostgreSQL validation with missing extensions"""
        mock_conn = AsyncMock()
        
        # Mock missing extensions
        mock_conn.fetch.side_effect = [
            [],  # no extensions found
            [{'schema_name': 'test_schema'}],  # schemas
            [{'full_name': 'test_schema.test_table'}],  # tables
        ]
        
        with patch('asyncpg.connect', return_value=mock_conn):
            result = await self.validator.validate_postgresql_schema(
                "postgresql://test:test@localhost/test"
            )
        
        assert result.status == ValidationStatus.INVALID
        assert len(result.issues) > 0
        assert any("Missing required extensions" in issue.message for issue in result.issues)
    
    @pytest.mark.asyncio
    async def test_milvus_validation_success(self):
        """Test successful Milvus schema validation"""
        # Mock pymilvus components
        mock_connections = Mock()
        mock_utility = Mock()
        mock_collection = Mock()
        
        # Mock successful collection check
        mock_utility.list_collections.return_value = ["test_collection"]
        
        # Mock collection schema
        mock_field = Mock()
        mock_field.dtype = "FLOAT_VECTOR"
        mock_field.params = {"dim": 384}
        
        mock_schema = Mock()
        mock_schema.fields = [mock_field]
        
        mock_collection.schema = mock_schema
        
        with patch.multiple(
            'database.schema_validator',
            connections=mock_connections,
            utility=mock_utility,
            Collection=Mock(return_value=mock_collection)
        ):
            result = await self.validator.validate_milvus_schema()
        
        assert result.database_type == DatabaseType.MILVUS
        assert result.status == ValidationStatus.VALID
    
    @pytest.mark.asyncio
    async def test_neo4j_validation_success(self):
        """Test successful Neo4j schema validation"""
        # Mock Neo4j driver and session
        mock_driver = Mock()
        mock_session = Mock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        
        # Mock successful constraint and index checks
        mock_session.run.side_effect = [
            [{"name": "test_constraint"}],  # constraints
            [{"name": "test_index"}],       # indexes
            [],  # node type check (no error means success)
            [{"version": "1.0.0", "updated": datetime.now()}]  # version check
        ]
        
        with patch('neo4j.GraphDatabase.driver', return_value=mock_driver):
            result = await self.validator.validate_neo4j_schema()
        
        assert result.database_type == DatabaseType.NEO4J
        assert result.status == ValidationStatus.VALID
        assert result.version == "1.0.0"
    
    @pytest.mark.asyncio
    async def test_validate_all_schemas(self):
        """Test validation of all schemas"""
        # Mock all database validations to return success
        with patch.object(self.validator, 'validate_postgresql_schema') as mock_pg, \
             patch.object(self.validator, 'validate_milvus_schema') as mock_milvus, \
             patch.object(self.validator, 'validate_neo4j_schema') as mock_neo4j:
            
            mock_pg.return_value = ValidationResult(
                DatabaseType.POSTGRESQL, "test_db", ValidationStatus.VALID
            )
            mock_milvus.return_value = ValidationResult(
                DatabaseType.MILVUS, "localhost:19530", ValidationStatus.VALID
            )
            mock_neo4j.return_value = ValidationResult(
                DatabaseType.NEO4J, "bolt://localhost:7687", ValidationStatus.VALID
            )
            
            results = await self.validator.validate_all_schemas(
                postgresql_conn="postgresql://test:test@localhost/test"
            )
        
        assert len(results) == 3
        assert DatabaseType.POSTGRESQL in results
        assert DatabaseType.MILVUS in results
        assert DatabaseType.NEO4J in results
        
        for result in results.values():
            assert result.status == ValidationStatus.VALID
    
    def test_validation_report_generation(self):
        """Test validation report generation"""
        # Create test results
        results = {
            DatabaseType.POSTGRESQL: ValidationResult(
                DatabaseType.POSTGRESQL,
                "test_db",
                ValidationStatus.VALID,
                version="1.0.0"
            ),
            DatabaseType.MILVUS: ValidationResult(
                DatabaseType.MILVUS,
                "localhost:19530",
                ValidationStatus.WARNING,
                issues=[ValidationIssue(
                    ValidationStatus.WARNING,
                    "performance",
                    "Index not optimized"
                )]
            )
        }
        
        report = self.validator.generate_validation_report(results)
        
        assert "DATABASE SCHEMA VALIDATION REPORT" in report
        assert "POSTGRESQL DATABASE" in report
        assert "MILVUS DATABASE" in report
        assert "Valid: 1" in report
        assert "Warnings: 1" in report
    
    @pytest.mark.asyncio
    async def test_schema_drift_detection(self):
        """Test schema drift detection"""
        # Mock schema files with different content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write("CREATE TABLE modified (id INTEGER);")
            modified_file = f.name
        
        try:
            # Update config to use the modified file
            self.validator.schema_config["databases"]["postgresql"]["schema_files"] = [modified_file]
            
            # Store a different checksum to simulate drift
            self.validator.schema_versions[DatabaseType.POSTGRESQL] = SchemaVersion(
                database_type=DatabaseType.POSTGRESQL,
                version="1.0.0",
                description="Test version",
                checksum="different_checksum"
            )
            
            drift_status = await self.validator.check_schema_drift()
            
            assert DatabaseType.POSTGRESQL in drift_status
            assert drift_status[DatabaseType.POSTGRESQL] is True  # Should detect drift
        finally:
            Path(modified_file).unlink(missing_ok=True)


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Schema validation modules not available")
class TestSchemaVersionManager:
    """Test cases for SchemaVersionManager"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.config_path = self.temp_config.name
        
        # Create test migration configuration
        test_config = {
            "version": "1.0.0",
            "migration_settings": {
                "auto_backup": True,
                "migration_timeout": 3600,
                "rollback_on_failure": True
            },
            "database_connections": {
                "postgresql": {
                    "connection_string": "postgresql://test:test@localhost/test"
                },
                "milvus": {
                    "host": "localhost",
                    "port": 19530
                },
                "neo4j": {
                    "uri": "bolt://localhost:7687",
                    "user": "neo4j",
                    "password": "password"
                }
            },
            "version_history": {},
            "migration_dependencies": {
                "postgresql": [],
                "milvus": ["postgresql"],
                "neo4j": ["postgresql"]
            }
        }
        
        json.dump(test_config, self.temp_config)
        self.temp_config.close()
        
        # Create temporary migrations directory
        self.temp_migrations_dir = tempfile.mkdtemp()
        
        self.manager = SchemaVersionManager(self.config_path)
        self.manager.migrations_dir = Path(self.temp_migrations_dir)
    
    def teardown_method(self):
        """Clean up test fixtures"""
        Path(self.config_path).unlink(missing_ok=True)
        import shutil
        shutil.rmtree(self.temp_migrations_dir, ignore_errors=True)
    
    def test_manager_initialization(self):
        """Test version manager initialization"""
        assert self.manager.config_path == self.config_path
        assert "migration_settings" in self.manager.config
        assert "database_connections" in self.manager.config
    
    def test_version_parsing(self):
        """Test version string parsing"""
        assert self.manager._parse_version("1.0.0") == (1, 0, 0)
        assert self.manager._parse_version("2.1.3") == (2, 1, 3)
        assert self.manager._parse_version("invalid") == (0, 0, 0)
    
    def test_version_comparison(self):
        """Test version comparison"""
        assert self.manager._compare_versions("1.0.0", "1.0.1") == -1
        assert self.manager._compare_versions("1.0.1", "1.0.0") == 1
        assert self.manager._compare_versions("1.0.0", "1.0.0") == 0
    
    def test_migration_discovery(self):
        """Test migration file discovery"""
        # Create test migration files
        pg_dir = Path(self.temp_migrations_dir) / "postgresql"
        pg_dir.mkdir(parents=True)
        
        migration_file = pg_dir / "1.0.1_test_migration.sql"
        with open(migration_file, 'w') as f:
            f.write("CREATE TABLE test (id INTEGER);")
        
        rollback_file = pg_dir / "1.0.1_test_migration_rollback.sql"
        with open(rollback_file, 'w') as f:
            f.write("DROP TABLE test;")
        
        # Rediscover migrations
        self.manager._discover_migrations()
        
        pg_migrations = self.manager.available_migrations[DatabaseType.POSTGRESQL]
        assert len(pg_migrations) == 1
        
        migration = pg_migrations[0]
        assert migration.version == "1.0.1"
        assert migration.description == "Test Migration"
        assert migration.up_script == "CREATE TABLE test (id INTEGER);"
        assert migration.down_script == "DROP TABLE test;"
    
    def test_migration_plan_creation(self):
        """Test migration plan creation"""
        # Create test migrations
        test_migration = Migration(
            id="test_migration_1_0_1",
            database_type=DatabaseType.POSTGRESQL,
            version="1.0.1",
            description="Test migration",
            up_script="CREATE TABLE test (id INTEGER);"
        )
        
        self.manager.available_migrations[DatabaseType.POSTGRESQL] = [test_migration]
        
        # Test upgrade plan
        target_versions = {DatabaseType.POSTGRESQL: "1.0.1"}
        current_versions = {DatabaseType.POSTGRESQL: "1.0.0"}
        
        plans = self.manager.create_migration_plan(target_versions, current_versions)
        
        assert DatabaseType.POSTGRESQL in plans
        plan = plans[DatabaseType.POSTGRESQL]
        assert plan.target_version == "1.0.1"
        assert plan.direction == MigrationDirection.UP
        assert len(plan.migrations) == 1
        assert plan.migrations[0].version == "1.0.1"
    
    def test_execution_order_with_dependencies(self):
        """Test migration execution order based on dependencies"""
        databases = [DatabaseType.NEO4J, DatabaseType.POSTGRESQL, DatabaseType.MILVUS]
        
        execution_order = self.manager._get_execution_order(databases)
        
        # PostgreSQL should come first (no dependencies)
        assert execution_order[0] == DatabaseType.POSTGRESQL
        
        # Milvus and Neo4j should come after PostgreSQL
        pg_index = execution_order.index(DatabaseType.POSTGRESQL)
        milvus_index = execution_order.index(DatabaseType.MILVUS)
        neo4j_index = execution_order.index(DatabaseType.NEO4J)
        
        assert milvus_index > pg_index
        assert neo4j_index > pg_index
    
    @pytest.mark.asyncio
    async def test_migration_validation(self):
        """Test migration script validation"""
        test_migration = Migration(
            id="test_migration",
            database_type=DatabaseType.POSTGRESQL,
            version="1.0.1",
            description="Test migration",
            up_script="CREATE TABLE test (id INTEGER);"
        )
        
        # Mock validation to return success
        with patch.object(self.manager, '_validate_migration', return_value=True):
            result = await self.manager._validate_migration(test_migration, DatabaseType.POSTGRESQL)
            assert result is True
    
    def test_migration_status_tracking(self):
        """Test migration status and history tracking"""
        test_migration = Migration(
            id="test_migration",
            database_type=DatabaseType.POSTGRESQL,
            version="1.0.1",
            description="Test migration",
            up_script="CREATE TABLE test (id INTEGER);",
            status=MigrationStatus.COMPLETED,
            applied_at=datetime.now(timezone.utc)
        )
        
        self.manager._update_migration_history(test_migration)
        
        # Check that version history was updated
        version_history = self.manager.config["version_history"]
        assert "postgresql" in version_history
        assert version_history["postgresql"]["current"] == "1.0.1"
        assert len(version_history["postgresql"]["migrations"]) == 1
    
    def test_get_migration_status(self):
        """Test migration status reporting"""
        status = self.manager.get_migration_status()
        
        assert "available_migrations" in status
        assert "version_history" in status
        assert "migration_settings" in status
        assert "last_updated" in status


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Schema validation modules not available")
class TestIntegration:
    """Integration tests for schema validation and versioning"""
    
    @pytest.mark.asyncio
    async def test_validation_and_migration_workflow(self):
        """Test complete validation and migration workflow"""
        # This would be a more comprehensive test that combines
        # validation and migration in a realistic scenario
        
        validator = SchemaValidator()
        manager = SchemaVersionManager()
        
        # Mock successful validation
        with patch.object(validator, 'validate_all_schemas') as mock_validate:
            mock_validate.return_value = {
                DatabaseType.POSTGRESQL: ValidationResult(
                    DatabaseType.POSTGRESQL,
                    "test_db",
                    ValidationStatus.VALID,
                    version="1.0.0"
                )
            }
            
            results = await validator.validate_all_schemas()
            assert len(results) == 1
            assert results[DatabaseType.POSTGRESQL].status == ValidationStatus.VALID
        
        # Test that manager can get status
        status = manager.get_migration_status()
        assert isinstance(status, dict)
        assert "available_migrations" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])