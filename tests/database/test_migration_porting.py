"""
Tests for migration porting functionality.

This module tests the migration porting system that adapts existing
AWS-focused migrations to work with local PostgreSQL setup.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from src.multimodal_librarian.database.local_migration_manager import (
    LocalMigrationManager,
    get_local_migration_status,
    port_migrations_to_local,
)


class TestLocalMigrationManager:
    """Test cases for LocalMigrationManager."""
    
    @pytest.fixture
    def migration_manager(self):
        """Create a LocalMigrationManager instance for testing."""
        return LocalMigrationManager("postgresql://test:test@localhost:5432/test_db")
    
    @pytest.mark.asyncio
    async def test_initialization(self, migration_manager):
        """Test LocalMigrationManager initialization."""
        assert migration_manager.database_url == "postgresql://test:test@localhost:5432/test_db"
        assert migration_manager.migration_manager is not None
        assert migration_manager.migrations_dir.exists()
    
    @pytest.mark.asyncio
    async def test_is_porting_complete_true(self, migration_manager):
        """Test checking porting status when complete."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            # Mock the query result
            mock_result = MagicMock()
            mock_result.scalar.return_value = True
            mock_session_instance.execute.return_value = mock_result
            
            result = await migration_manager._is_porting_complete()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_is_porting_complete_false(self, migration_manager):
        """Test checking porting status when not complete."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            # Mock the query result
            mock_result = MagicMock()
            mock_result.scalar.return_value = False
            mock_session_instance.execute.return_value = mock_result
            
            result = await migration_manager._is_porting_complete()
            assert result is False
    
    @pytest.mark.asyncio
    async def test_is_porting_complete_exception(self, migration_manager):
        """Test checking porting status when exception occurs."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session.return_value.__aenter__.side_effect = Exception("Database error")
            
            result = await migration_manager._is_porting_complete()
            assert result is False
    
    def test_split_sql_statements_basic(self, migration_manager):
        """Test SQL statement splitting with basic statements."""
        sql_content = """
        -- Comment
        CREATE TABLE test1 (id INTEGER);
        
        INSERT INTO test1 VALUES (1);
        
        -- Another comment
        CREATE TABLE test2 (name VARCHAR(50));
        """
        
        statements = migration_manager._split_sql_statements(sql_content)
        
        # Filter out empty statements
        non_empty_statements = [s for s in statements if s.strip()]
        
        assert len(non_empty_statements) == 3
        assert "CREATE TABLE test1" in non_empty_statements[0]
        assert "INSERT INTO test1" in non_empty_statements[1]
        assert "CREATE TABLE test2" in non_empty_statements[2]
    
    def test_split_sql_statements_with_functions(self, migration_manager):
        """Test SQL statement splitting with function definitions."""
        sql_content = """
        CREATE OR REPLACE FUNCTION test_function()
        RETURNS INTEGER AS $
        BEGIN
            RETURN 1;
        END;
        $ LANGUAGE plpgsql;
        
        CREATE TABLE test_table (id INTEGER);
        """
        
        statements = migration_manager._split_sql_statements(sql_content)
        
        # Filter out empty statements
        non_empty_statements = [s for s in statements if s.strip()]
        
        assert len(non_empty_statements) == 2
        assert "CREATE OR REPLACE FUNCTION" in non_empty_statements[0]
        assert "CREATE TABLE test_table" in non_empty_statements[1]
    
    def test_split_sql_statements_with_do_blocks(self, migration_manager):
        """Test SQL statement splitting with DO blocks."""
        sql_content = """
        DO $
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'test') THEN
                CREATE TABLE test (id INTEGER);
            END IF;
        END $;
        
        INSERT INTO test VALUES (1);
        """
        
        statements = migration_manager._split_sql_statements(sql_content)
        
        # Filter out empty statements
        non_empty_statements = [s for s in statements if s.strip()]
        
        assert len(non_empty_statements) == 2
        assert "DO $" in non_empty_statements[0]
        assert "INSERT INTO test" in non_empty_statements[1]
    
    @pytest.mark.asyncio
    async def test_is_migration_applied_true(self, migration_manager):
        """Test checking if migration is applied when true."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            # Mock the query result
            mock_result = MagicMock()
            mock_result.scalar.return_value = True
            mock_session_instance.execute.return_value = mock_result
            
            result = await migration_manager._is_migration_applied("test_migration")
            assert result is True
    
    @pytest.mark.asyncio
    async def test_is_migration_applied_false(self, migration_manager):
        """Test checking if migration is applied when false."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            # Mock the query result
            mock_result = MagicMock()
            mock_result.scalar.return_value = False
            mock_session_instance.execute.return_value = mock_result
            
            result = await migration_manager._is_migration_applied("test_migration")
            assert result is False
    
    @pytest.mark.asyncio
    async def test_record_migration_success(self, migration_manager):
        """Test recording a migration successfully."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            # Should not raise an exception
            await migration_manager._record_migration("test_migration")
            
            # Verify the execute was called
            mock_session_instance.execute.assert_called_once()
            mock_session_instance.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_record_migration_exception(self, migration_manager):
        """Test recording a migration when exception occurs."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session_instance.execute.side_effect = Exception("Database error")
            
            # Should not raise an exception (error is logged)
            await migration_manager._record_migration("test_migration")
    
    @pytest.mark.asyncio
    async def test_get_migration_status_success(self, migration_manager):
        """Test getting migration status successfully."""
        from datetime import datetime
        
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            # Mock porting status query
            mock_result1 = MagicMock()
            mock_result1.scalar.return_value = True
            
            # Mock migration history query - use datetime objects since code calls .isoformat()
            mock_result2 = MagicMock()
            mock_result2.fetchall.return_value = [
                ("test_migration", datetime(2023, 1, 1, 0, 0, 0), True),
                ("another_migration", datetime(2023, 1, 2, 0, 0, 0), True)
            ]
            
            # Mock table counts query
            mock_result3 = MagicMock()
            mock_result3.fetchone.return_value = (5, 10, 100, 50)
            
            mock_session_instance.execute.side_effect = [mock_result1, mock_result2, mock_result3]
            
            status = await migration_manager.get_migration_status()
            
            assert status["porting_complete"] is True
            assert len(status["migration_history"]) == 2
            assert status["table_counts"]["users"] == 5
            assert status["table_counts"]["documents"] == 10
            assert status["table_counts"]["knowledge_chunks"] == 100
            assert status["table_counts"]["chat_messages"] == 50
    
    @pytest.mark.asyncio
    async def test_get_migration_status_exception(self, migration_manager):
        """Test getting migration status when exception occurs."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session.return_value.__aenter__.side_effect = Exception("Database error")
            
            status = await migration_manager.get_migration_status()
            
            assert status["porting_complete"] is False
            assert "error" in status
            assert status["error"] == "Database error"
    
    @pytest.mark.asyncio
    async def test_reset_migrations_success(self, migration_manager):
        """Test resetting migrations successfully."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            
            result = await migration_manager.reset_migrations()
            
            assert result is True
            # Verify DELETE statements were executed
            assert mock_session_instance.execute.call_count == 2
            mock_session_instance.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_reset_migrations_exception(self, migration_manager):
        """Test resetting migrations when exception occurs."""
        with patch('src.multimodal_librarian.database.local_migration_manager.get_async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_instance
            mock_session_instance.execute.side_effect = Exception("Database error")
            
            result = await migration_manager.reset_migrations()
            
            assert result is False


class TestMigrationPortingFunctions:
    """Test cases for module-level functions."""
    
    @pytest.mark.asyncio
    async def test_port_migrations_to_local_success(self):
        """Test successful migration porting."""
        with patch('src.multimodal_librarian.database.local_migration_manager.LocalMigrationManager') as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager.port_existing_migrations.return_value = True
            mock_manager_class.return_value = mock_manager
            
            result = await port_migrations_to_local()
            
            assert result is True
            mock_manager.port_existing_migrations.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_port_migrations_to_local_failure(self):
        """Test failed migration porting."""
        with patch('src.multimodal_librarian.database.local_migration_manager.LocalMigrationManager') as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager.port_existing_migrations.return_value = False
            mock_manager_class.return_value = mock_manager
            
            result = await port_migrations_to_local()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_get_local_migration_status_success(self):
        """Test getting local migration status successfully."""
        with patch('src.multimodal_librarian.database.local_migration_manager.LocalMigrationManager') as mock_manager_class:
            mock_manager = AsyncMock()
            expected_status = {
                "porting_complete": True,
                "migration_history": [],
                "table_counts": {}
            }
            mock_manager.get_migration_status.return_value = expected_status
            mock_manager_class.return_value = mock_manager
            
            result = await get_local_migration_status()
            
            assert result == expected_status
            mock_manager.get_migration_status.assert_called_once()


class TestMigrationPortingIntegration:
    """Integration tests for migration porting (requires database)."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_migration_porting_flow(self):
        """Test the complete migration porting flow."""
        # This test would require a real database connection
        # Skip if not in integration test mode
        pytest.skip("Integration test requires database setup")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_migration_verification(self):
        """Test migration verification after porting."""
        # This test would verify that all expected tables exist
        # Skip if not in integration test mode
        pytest.skip("Integration test requires database setup")


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])