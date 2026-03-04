#!/usr/bin/env python3
"""
Tests for Data Integrity Validation

This module tests the comprehensive data integrity validation functionality
to ensure it correctly identifies issues and provides appropriate suggestions.
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Import the modules we're testing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.data_validation_utils import (
    DataValidationUtils, ValidationResult, DataConsistencyReport
)
from scripts.validate_backup_restore_integrity import BackupRestoreValidator
from scripts.validate_data_integrity_comprehensive import ComprehensiveDataValidator


class TestDataValidationUtils:
    """Test the DataValidationUtils class."""
    
    @pytest.fixture
    async def mock_config(self):
        """Create a mock configuration."""
        config = MagicMock()
        config.database_type = "local"
        return config
    
    @pytest.fixture
    async def mock_factory(self):
        """Create a mock database factory."""
        factory = AsyncMock()
        
        # Mock relational client
        relational_client = AsyncMock()
        relational_client.get_database_info.return_value = {"table_count": 5, "size": 1024}
        relational_client.execute_query.return_value = [{"count": 10}]
        factory.get_relational_client.return_value = relational_client
        
        # Mock graph client
        graph_client = AsyncMock()
        graph_client.execute_query.return_value = [{"count": 8}]
        factory.get_graph_client.return_value = graph_client
        
        # Mock vector client
        vector_client = AsyncMock()
        vector_client.list_collections.return_value = ["test_collection"]
        vector_client.get_collection_stats.return_value = {"vector_count": 100}
        factory.get_vector_client.return_value = vector_client
        
        return factory
    
    @pytest.fixture
    async def validator(self, mock_config, mock_factory):
        """Create a DataValidationUtils instance with mocked dependencies."""
        validator = DataValidationUtils(mock_config)
        
        # Mock the factory initialization
        with patch.object(validator, 'factory', mock_factory):
            yield validator
    
    @pytest.mark.asyncio
    async def test_validate_database_connectivity_success(self, validator, mock_factory):
        """Test successful database connectivity validation."""
        validator.factory = mock_factory
        
        results = await validator.validate_database_connectivity()
        
        assert len(results) == 3
        assert "postgresql" in results
        assert "neo4j" in results
        assert "milvus" in results
        
        # All should be successful
        for result in results.values():
            assert result.success
            assert "connection successful" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_validate_database_connectivity_failure(self, validator, mock_factory):
        """Test database connectivity validation with failures."""
        validator.factory = mock_factory
        
        # Make PostgreSQL fail
        mock_factory.get_relational_client.side_effect = Exception("Connection refused")
        
        results = await validator.validate_database_connectivity()
        
        assert not results["postgresql"].success
        assert "connection refused" in results["postgresql"].message.lower()
        assert len(results["postgresql"].suggestions) > 0
    
    @pytest.mark.asyncio
    async def test_validate_user_data_consistency_match(self, validator, mock_factory):
        """Test user data consistency validation with matching counts."""
        validator.factory = mock_factory
        
        # Mock matching user counts
        relational_client = await mock_factory.get_relational_client()
        relational_client.execute_query.return_value = [{"count": 10}]
        
        graph_client = await mock_factory.get_graph_client()
        graph_client.execute_query.return_value = [{"count": 10}]
        
        result = await validator.validate_user_data_consistency()
        
        assert result.success
        assert "consistent" in result.message.lower()
        assert result.details["difference"] == 0
    
    @pytest.mark.asyncio
    async def test_validate_user_data_consistency_mismatch(self, validator, mock_factory):
        """Test user data consistency validation with mismatched counts."""
        validator.factory = mock_factory
        
        # Mock mismatched user counts
        relational_client = await mock_factory.get_relational_client()
        relational_client.execute_query.return_value = [{"count": 10}]
        
        graph_client = await mock_factory.get_graph_client()
        graph_client.execute_query.return_value = [{"count": 20}]
        
        result = await validator.validate_user_data_consistency()
        
        assert not result.success
        assert "inconsistent" in result.message.lower()
        assert result.details["difference"] == 10
        assert len(result.suggestions) > 0
    
    @pytest.mark.asyncio
    async def test_validate_document_data_consistency(self, validator, mock_factory):
        """Test document data consistency validation."""
        validator.factory = mock_factory
        
        # Mock document counts
        relational_client = await mock_factory.get_relational_client()
        relational_client.execute_query.return_value = [{"count": 5}]
        
        graph_client = await mock_factory.get_graph_client()
        graph_client.execute_query.return_value = [{"count": 5}]
        
        vector_client = await mock_factory.get_vector_client()
        vector_client.list_collections.return_value = ["docs"]
        vector_client.get_collection_stats.return_value = {"vector_count": 50}
        
        result = await validator.validate_document_data_consistency()
        
        assert result.success
        assert result.details["postgresql_documents"] == 5
        assert result.details["neo4j_documents"] == 5
        assert result.details["milvus_vectors"] == 50
    
    @pytest.mark.asyncio
    async def test_validate_referential_integrity(self, validator, mock_factory):
        """Test referential integrity validation."""
        validator.factory = mock_factory
        
        # Mock no violations
        relational_client = await mock_factory.get_relational_client()
        relational_client.execute_query.return_value = [{"count": 0}]
        
        graph_client = await mock_factory.get_graph_client()
        graph_client.execute_query.return_value = [{"count": 0}]
        
        results = await validator.validate_referential_integrity()
        
        assert "postgresql" in results
        assert "neo4j" in results
        assert results["postgresql"].success
        assert results["neo4j"].success
    
    @pytest.mark.asyncio
    async def test_generate_data_consistency_report(self, validator, mock_factory):
        """Test comprehensive data consistency report generation."""
        validator.factory = mock_factory
        
        # Mock all validation methods to return success
        with patch.object(validator, 'validate_user_data_consistency') as mock_user, \
             patch.object(validator, 'validate_document_data_consistency') as mock_doc, \
             patch.object(validator, 'validate_conversation_data_consistency') as mock_conv, \
             patch.object(validator, 'validate_vector_data_consistency') as mock_vec:
            
            # All successful
            mock_user.return_value = ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc))
            mock_doc.return_value = ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc))
            mock_conv.return_value = ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc))
            mock_vec.return_value = ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc))
            
            report = await validator.generate_data_consistency_report()
            
            assert isinstance(report, DataConsistencyReport)
            assert report.overall_status == "healthy"
            assert report.total_issues == 0


class TestBackupRestoreValidator:
    """Test the BackupRestoreValidator class."""
    
    @pytest.fixture
    async def mock_config(self):
        """Create a mock configuration."""
        config = MagicMock()
        config.database_type = "local"
        return config
    
    @pytest.fixture
    async def validator(self, mock_config):
        """Create a BackupRestoreValidator instance."""
        validator = BackupRestoreValidator(mock_config)
        
        # Mock the validation utils
        validator.validation_utils = AsyncMock()
        
        return validator
    
    @pytest.mark.asyncio
    async def test_validate_pre_backup_success(self, validator):
        """Test successful pre-backup validation."""
        # Mock all validation methods to return success
        validator.validation_utils.validate_database_connectivity.return_value = {
            "postgresql": ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            "neo4j": ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            "milvus": ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc))
        }
        
        mock_report = DataConsistencyReport(
            user_consistency=ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            document_consistency=ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            conversation_consistency=ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            vector_consistency=ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            overall_status="healthy",
            total_issues=0
        )
        validator.validation_utils.generate_data_consistency_report.return_value = mock_report
        
        validator.validation_utils.validate_referential_integrity.return_value = {
            "postgresql": ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc))
        }
        
        validator.validation_utils.validate_data_quality.return_value = {
            "postgresql": ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc))
        }
        
        result = await validator.validate_pre_backup()
        
        assert result["backup_recommended"] is True
        assert result["connectivity"]["status"] == "ok"
        assert result["consistency"]["status"] == "healthy"
        assert "System is ready for backup operation" in result["recommendations"]
    
    @pytest.mark.asyncio
    async def test_validate_pre_backup_failure(self, validator):
        """Test pre-backup validation with failures."""
        # Mock connectivity failure
        validator.validation_utils.validate_database_connectivity.return_value = {
            "postgresql": ValidationResult(False, "Failed", {}, [], datetime.now(timezone.utc))
        }
        
        mock_report = DataConsistencyReport(
            user_consistency=ValidationResult(False, "Failed", {}, [], datetime.now(timezone.utc)),
            document_consistency=ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            conversation_consistency=ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            vector_consistency=ValidationResult(True, "OK", {}, [], datetime.now(timezone.utc)),
            overall_status="critical",
            total_issues=5
        )
        validator.validation_utils.generate_data_consistency_report.return_value = mock_report
        
        validator.validation_utils.validate_referential_integrity.return_value = {}
        validator.validation_utils.validate_data_quality.return_value = {}
        
        result = await validator.validate_pre_backup()
        
        assert result["backup_recommended"] is False
        assert result["connectivity"]["status"] == "failed"
        assert result["consistency"]["status"] == "critical"
        assert "Backup not recommended" in result["recommendations"]
    
    @pytest.mark.asyncio
    async def test_validate_backup_integrity_missing_directory(self, validator):
        """Test backup integrity validation with missing directory."""
        result = await validator.validate_backup_integrity("/nonexistent/path")
        
        assert result["backup_valid"] is False
        assert "does not exist" in result["error"]
        assert "Check backup path" in result["recommendations"]
    
    @pytest.mark.asyncio
    async def test_validate_backup_integrity_valid_backup(self, validator):
        """Test backup integrity validation with valid backup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_dir = Path(temp_dir)
            
            # Create mock backup structure
            (backup_dir / "postgresql").mkdir()
            (backup_dir / "neo4j").mkdir()
            (backup_dir / "milvus").mkdir()
            (backup_dir / "system").mkdir()
            
            # Create mock backup files
            (backup_dir / "postgresql" / "backup.sql").write_text("CREATE TABLE test;")
            (backup_dir / "neo4j" / "backup.cypher").write_text("CREATE (n:Test);")
            (backup_dir / "milvus" / "backup.json").write_text('{"test": "data"}')
            (backup_dir / "system" / "backup_metadata_123.json").write_text('{"backup_timestamp": "2024-01-01"}')
            
            # Mock the backup integrity check
            validator.validation_utils.check_backup_integrity.return_value = ValidationResult(
                True, "OK", {}, [], datetime.now(timezone.utc)
            )
            
            result = await validator.validate_backup_integrity(str(backup_dir))
            
            assert result["backup_valid"] is True
            assert result["database_backups"]["postgresql"]["valid"] is True
            assert result["database_backups"]["neo4j"]["valid"] is True
            assert result["database_backups"]["milvus"]["valid"] is True
            assert result["system_metadata_valid"] is True


class TestComprehensiveDataValidator:
    """Test the ComprehensiveDataValidator class."""
    
    @pytest.fixture
    async def mock_config(self):
        """Create a mock configuration."""
        config = MagicMock()
        config.database_type = "local"
        return config
    
    @pytest.fixture
    async def validator(self, mock_config):
        """Create a ComprehensiveDataValidator instance."""
        validator = ComprehensiveDataValidator(mock_config)
        
        # Mock the factory
        validator.factory = AsyncMock()
        
        return validator
    
    @pytest.mark.asyncio
    async def test_check_database_connectivity(self, validator):
        """Test database connectivity check."""
        # Mock successful connections
        relational_client = AsyncMock()
        relational_client.get_database_info.return_value = {"tables": 5}
        validator.factory.get_relational_client.return_value = relational_client
        
        graph_client = AsyncMock()
        graph_client.execute_query.return_value = [{"test": 1}]
        validator.factory.get_graph_client.return_value = graph_client
        
        vector_client = AsyncMock()
        vector_client.list_collections.return_value = ["test"]
        validator.factory.get_vector_client.return_value = vector_client
        
        result = await validator._check_database_connectivity(suggest_fixes=True)
        
        assert result.success
        assert result.check_name == "Database Connectivity"
        assert result.issues_found == 0
    
    @pytest.mark.asyncio
    async def test_check_schema_integrity(self, validator):
        """Test schema integrity check."""
        # Mock clients
        relational_client = AsyncMock()
        relational_client.get_table_list.return_value = ["users", "documents", "conversations"]
        validator.factory.get_relational_client.return_value = relational_client
        
        graph_client = AsyncMock()
        graph_client.execute_query.return_value = [
            {"label": "User"}, {"label": "Document"}, {"label": "Concept"}
        ]
        validator.factory.get_graph_client.return_value = graph_client
        
        vector_client = AsyncMock()
        vector_client.list_collections.return_value = ["knowledge_chunks"]
        validator.factory.get_vector_client.return_value = vector_client
        
        result = await validator._check_schema_integrity(suggest_fixes=True)
        
        assert result.check_name == "Schema Integrity"
        # Should have some missing tables/collections
        assert result.issues_found > 0
    
    @pytest.mark.asyncio
    async def test_comprehensive_validation_quick_mode(self, validator):
        """Test comprehensive validation in quick mode."""
        # Mock all check methods
        with patch.object(validator, '_check_database_connectivity') as mock_conn, \
             patch.object(validator, '_check_schema_integrity') as mock_schema, \
             patch.object(validator, '_check_data_consistency') as mock_data, \
             patch.object(validator, '_check_referential_integrity') as mock_ref, \
             patch.object(validator, '_check_cross_database_sync') as mock_sync:
            
            # Mock successful results
            from scripts.validate_data_integrity_comprehensive import IntegrityCheckResult
            
            mock_result = IntegrityCheckResult(
                check_name="Test",
                success=True,
                issues_found=0,
                execution_time=0.1,
                details={},
                suggestions=[]
            )
            
            mock_conn.return_value = mock_result
            mock_schema.return_value = mock_result
            mock_data.return_value = mock_result
            mock_ref.return_value = mock_result
            mock_sync.return_value = mock_result
            
            report = await validator.run_comprehensive_validation(quick_mode=True)
            
            assert report.total_checks == 5  # Only basic checks in quick mode
            assert report.successful_checks == 5
            assert report.failed_checks == 0


@pytest.mark.asyncio
async def test_integration_validation_workflow():
    """Test the complete validation workflow integration."""
    # This test would require actual database connections
    # For now, we'll test the workflow structure
    
    mock_config = MagicMock()
    mock_config.database_type = "local"
    
    # Test that we can create all validator instances
    data_validator = DataValidationUtils(mock_config)
    backup_validator = BackupRestoreValidator(mock_config)
    comprehensive_validator = ComprehensiveDataValidator(mock_config)
    
    # Test that they have the expected methods
    assert hasattr(data_validator, 'validate_database_connectivity')
    assert hasattr(data_validator, 'generate_data_consistency_report')
    assert hasattr(backup_validator, 'validate_pre_backup')
    assert hasattr(backup_validator, 'validate_backup_integrity')
    assert hasattr(backup_validator, 'validate_post_restore')
    assert hasattr(comprehensive_validator, 'run_comprehensive_validation')


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])