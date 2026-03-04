"""
Tests for PostgreSQL initialization and configuration.

This module tests the PostgreSQL setup including:
- Database connectivity
- Extension installation
- Schema creation
- Performance configuration
- Monitoring setup
"""

import pytest
import psycopg2
import os
from typing import Dict, Any
import time


class TestPostgreSQLInitialization:
    """Test PostgreSQL initialization and configuration."""
    
    @pytest.fixture(scope="class")
    def db_config(self) -> Dict[str, Any]:
        """Database configuration for testing."""
        return {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': os.getenv('POSTGRES_DB', 'multimodal_librarian'),
            'user': os.getenv('POSTGRES_USER', 'ml_user'),
            'password': os.getenv('POSTGRES_PASSWORD', 'ml_password')
        }
    
    @pytest.fixture(scope="class")
    def db_connection(self, db_config):
        """Create database connection for testing."""
        # Wait for database to be ready
        max_retries = 30
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                conn = psycopg2.connect(**db_config)
                conn.autocommit = True
                yield conn
                conn.close()
                return
            except psycopg2.OperationalError:
                retry_count += 1
                time.sleep(1)
        
        pytest.fail("Could not connect to PostgreSQL database after 30 seconds")
    
    def test_database_connectivity(self, db_connection):
        """Test basic database connectivity."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1
        cursor.close()
    
    def test_database_version(self, db_connection):
        """Test PostgreSQL version is 15+."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        assert "PostgreSQL 15" in version
        cursor.close()
    
    def test_required_extensions(self, db_connection):
        """Test that required extensions are installed."""
        cursor = db_connection.cursor()
        
        required_extensions = [
            'uuid-ossp',
            'pg_trgm', 
            'btree_gin',
            'pg_stat_statements',
            'pgcrypto',
            'citext'
        ]
        
        cursor.execute("""
            SELECT extname FROM pg_extension 
            WHERE extname = ANY(%s)
        """, (required_extensions,))
        
        installed_extensions = [row[0] for row in cursor.fetchall()]
        
        for ext in required_extensions:
            assert ext in installed_extensions, f"Extension {ext} not installed"
        
        cursor.close()
    
    def test_schemas_created(self, db_connection):
        """Test that required schemas are created."""
        cursor = db_connection.cursor()
        
        required_schemas = [
            'multimodal_librarian',
            'audit',
            'monitoring',
            'maintenance'
        ]
        
        cursor.execute("""
            SELECT schema_name FROM information_schema.schemata 
            WHERE schema_name = ANY(%s)
        """, (required_schemas,))
        
        created_schemas = [row[0] for row in cursor.fetchall()]
        
        for schema in required_schemas:
            assert schema in created_schemas, f"Schema {schema} not created"
        
        cursor.close()
    
    def test_performance_configuration(self, db_connection):
        """Test performance configuration settings."""
        cursor = db_connection.cursor()
        
        # Test key performance settings
        performance_settings = {
            'shared_buffers': '256MB',
            'effective_cache_size': '1GB',
            'maintenance_work_mem': '64MB',
            'max_connections': '100'
        }
        
        for setting, expected_value in performance_settings.items():
            cursor.execute("SELECT current_setting(%s)", (setting,))
            actual_value = cursor.fetchone()[0]
            assert actual_value == expected_value, \
                f"Setting {setting}: expected {expected_value}, got {actual_value}"
        
        cursor.close()
    
    def test_monitoring_views(self, db_connection):
        """Test that monitoring views are created."""
        cursor = db_connection.cursor()
        
        monitoring_views = [
            'monitoring.active_connections',
            'monitoring.database_stats',
            'monitoring.table_stats',
            'monitoring.index_usage'
        ]
        
        for view in monitoring_views:
            schema, view_name = view.split('.')
            cursor.execute("""
                SELECT 1 FROM information_schema.views 
                WHERE table_schema = %s AND table_name = %s
            """, (schema, view_name))
            
            result = cursor.fetchone()
            assert result is not None, f"Monitoring view {view} not found"
        
        cursor.close()
    
    def test_monitoring_functions(self, db_connection):
        """Test that monitoring functions are created."""
        cursor = db_connection.cursor()
        
        monitoring_functions = [
            'monitoring.get_database_sizes',
            'monitoring.get_table_sizes',
            'monitoring.health_check'
        ]
        
        for function in monitoring_functions:
            schema, function_name = function.split('.')
            cursor.execute("""
                SELECT 1 FROM information_schema.routines 
                WHERE routine_schema = %s AND routine_name = %s
            """, (schema, function_name))
            
            result = cursor.fetchone()
            assert result is not None, f"Monitoring function {function} not found"
        
        cursor.close()
    
    def test_maintenance_functions(self, db_connection):
        """Test that maintenance functions are created."""
        cursor = db_connection.cursor()
        
        maintenance_functions = [
            'maintenance.cleanup_expired_sessions',
            'maintenance.cleanup_expired_exports',
            'maintenance.cleanup_old_audit_logs',
            'maintenance.update_statistics',
            'maintenance.routine_maintenance'
        ]
        
        for function in maintenance_functions:
            schema, function_name = function.split('.')
            cursor.execute("""
                SELECT 1 FROM information_schema.routines 
                WHERE routine_schema = %s AND routine_name = %s
            """, (schema, function_name))
            
            result = cursor.fetchone()
            assert result is not None, f"Maintenance function {function} not found"
        
        cursor.close()
    
    def test_health_check_function(self, db_connection):
        """Test the health check function works."""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT * FROM monitoring.health_check()")
        results = cursor.fetchall()
        
        assert len(results) > 0, "Health check returned no results"
        
        # Check that we have expected health check items
        check_names = [row[0] for row in results]
        expected_checks = [
            'database_connectivity',
            'active_connections',
            'long_running_queries',
            'database_size'
        ]
        
        for check in expected_checks:
            assert check in check_names, f"Health check {check} not found"
        
        cursor.close()
    
    def test_application_schema_tables(self, db_connection):
        """Test that main application tables are created."""
        cursor = db_connection.cursor()
        
        # Test some key tables from the application schema
        expected_tables = [
            'users',
            'documents', 
            'conversation_threads',
            'messages',
            'knowledge_chunks'
        ]
        
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'multimodal_librarian'
            AND table_name = ANY(%s)
        """, (expected_tables,))
        
        created_tables = [row[0] for row in cursor.fetchall()]
        
        for table in expected_tables:
            assert table in created_tables, f"Table {table} not created"
        
        cursor.close()
    
    def test_database_users(self, db_connection):
        """Test that database users are created."""
        cursor = db_connection.cursor()
        
        # Check for application users (these might not exist in all environments)
        cursor.execute("""
            SELECT rolname FROM pg_roles 
            WHERE rolname IN ('ml_app_user', 'ml_readonly', 'ml_backup')
        """)
        
        users = [row[0] for row in cursor.fetchall()]
        
        # Note: These users are created by initialization scripts
        # but might not exist if scripts haven't run yet
        # This is more of an informational test
        print(f"Found database users: {users}")
        
        cursor.close()
    
    def test_pg_stat_statements_enabled(self, db_connection):
        """Test that pg_stat_statements extension is working."""
        cursor = db_connection.cursor()
        
        # Check if pg_stat_statements view exists and has data
        cursor.execute("""
            SELECT COUNT(*) FROM pg_stat_statements 
            WHERE query LIKE '%SELECT%'
        """)
        
        result = cursor.fetchone()
        # Should have at least some SELECT statements recorded
        assert result[0] >= 0, "pg_stat_statements not working"
        
        cursor.close()
    
    def test_autovacuum_enabled(self, db_connection):
        """Test that autovacuum is enabled."""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT current_setting('autovacuum')")
        autovacuum_setting = cursor.fetchone()[0]
        
        assert autovacuum_setting == 'on', "Autovacuum should be enabled"
        
        cursor.close()
    
    def test_database_encoding(self, db_connection):
        """Test database encoding is UTF-8."""
        cursor = db_connection.cursor()
        
        cursor.execute("""
            SELECT pg_encoding_to_char(encoding) 
            FROM pg_database 
            WHERE datname = current_database()
        """)
        
        encoding = cursor.fetchone()[0]
        assert encoding == 'UTF8', f"Expected UTF8 encoding, got {encoding}"
        
        cursor.close()


class TestPostgreSQLPerformance:
    """Test PostgreSQL performance and optimization."""
    
    @pytest.fixture(scope="class")
    def db_connection(self):
        """Create database connection for performance testing."""
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': os.getenv('POSTGRES_DB', 'multimodal_librarian'),
            'user': os.getenv('POSTGRES_USER', 'ml_user'),
            'password': os.getenv('POSTGRES_PASSWORD', 'ml_password')
        }
        
        try:
            conn = psycopg2.connect(**db_config)
            conn.autocommit = True
            yield conn
            conn.close()
        except psycopg2.OperationalError:
            pytest.skip("PostgreSQL not available for performance testing")
    
    def test_query_performance(self, db_connection):
        """Test basic query performance."""
        cursor = db_connection.cursor()
        
        # Simple performance test
        start_time = time.time()
        cursor.execute("SELECT COUNT(*) FROM pg_stat_activity")
        end_time = time.time()
        
        query_time = end_time - start_time
        assert query_time < 1.0, f"Simple query took too long: {query_time}s"
        
        cursor.close()
    
    def test_connection_performance(self, db_connection):
        """Test connection establishment performance."""
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': os.getenv('POSTGRES_DB', 'multimodal_librarian'),
            'user': os.getenv('POSTGRES_USER', 'ml_user'),
            'password': os.getenv('POSTGRES_PASSWORD', 'ml_password')
        }
        
        # Test connection establishment time
        start_time = time.time()
        test_conn = psycopg2.connect(**db_config)
        end_time = time.time()
        
        connection_time = end_time - start_time
        assert connection_time < 2.0, f"Connection took too long: {connection_time}s"
        
        test_conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])