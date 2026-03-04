#!/usr/bin/env python3
"""
PostgreSQL Setup Validation Script for Multimodal Librarian

This script validates that the PostgreSQL database is properly initialized
and all required components are in place for local development.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import structlog
from typing import Dict, List, Any
import json
from datetime import datetime

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class PostgreSQLValidator:
    """Validates PostgreSQL setup for Multimodal Librarian."""
    
    def __init__(self):
        """Initialize the validator with database connection parameters."""
        self.host = os.getenv('POSTGRES_HOST', 'localhost')
        self.port = int(os.getenv('POSTGRES_PORT', 5432))
        self.database = os.getenv('POSTGRES_DB', 'multimodal_librarian')
        self.user = os.getenv('POSTGRES_USER', 'ml_user')
        self.password = os.getenv('POSTGRES_PASSWORD', 'ml_password')
        
        self.connection = None
        self.validation_results = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'UNKNOWN',
            'checks': {},
            'errors': [],
            'warnings': []
        }
    
    def connect(self) -> bool:
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                cursor_factory=RealDictCursor
            )
            logger.info("Database connection established")
            return True
        except Exception as e:
            logger.error("Failed to connect to database", error=str(e))
            self.validation_results['errors'].append(f"Database connection failed: {str(e)}")
            return False
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
    
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute a query and return results."""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                return cursor.fetchall()
        except Exception as e:
            logger.error("Query execution failed", query=query, error=str(e))
            raise
    
    def check_database_connectivity(self) -> bool:
        """Check basic database connectivity."""
        try:
            result = self.execute_query("SELECT version(), current_database(), current_user")
            if result:
                self.validation_results['checks']['connectivity'] = {
                    'status': 'PASS',
                    'details': {
                        'version': result[0]['version'],
                        'database': result[0]['current_database'],
                        'user': result[0]['current_user']
                    }
                }
                return True
        except Exception as e:
            self.validation_results['checks']['connectivity'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def check_extensions(self) -> bool:
        """Check that required PostgreSQL extensions are installed."""
        required_extensions = [
            'uuid-ossp', 'pg_trgm', 'btree_gin', 
            'pg_stat_statements', 'pgcrypto', 'citext'
        ]
        
        try:
            result = self.execute_query("""
                SELECT extname, extversion 
                FROM pg_extension 
                WHERE extname = ANY(%s)
            """, (required_extensions,))
            
            installed_extensions = {row['extname']: row['extversion'] for row in result}
            missing_extensions = set(required_extensions) - set(installed_extensions.keys())
            
            self.validation_results['checks']['extensions'] = {
                'status': 'PASS' if not missing_extensions else 'FAIL',
                'installed': installed_extensions,
                'missing': list(missing_extensions)
            }
            
            if missing_extensions:
                self.validation_results['errors'].append(f"Missing extensions: {missing_extensions}")
                return False
            
            return True
        except Exception as e:
            self.validation_results['checks']['extensions'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def check_schemas(self) -> bool:
        """Check that required schemas exist."""
        required_schemas = ['multimodal_librarian', 'audit', 'monitoring', 'maintenance']
        
        try:
            result = self.execute_query("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name = ANY(%s)
            """, (required_schemas,))
            
            existing_schemas = [row['schema_name'] for row in result]
            missing_schemas = set(required_schemas) - set(existing_schemas)
            
            self.validation_results['checks']['schemas'] = {
                'status': 'PASS' if not missing_schemas else 'FAIL',
                'existing': existing_schemas,
                'missing': list(missing_schemas)
            }
            
            if missing_schemas:
                self.validation_results['errors'].append(f"Missing schemas: {missing_schemas}")
                return False
            
            return True
        except Exception as e:
            self.validation_results['checks']['schemas'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def check_tables(self) -> bool:
        """Check that required tables exist."""
        required_tables = [
            ('multimodal_librarian', 'users'),
            ('multimodal_librarian', 'user_sessions'),
            ('multimodal_librarian', 'documents'),
            ('multimodal_librarian', 'conversation_threads'),
            ('multimodal_librarian', 'messages'),
            ('multimodal_librarian', 'knowledge_chunks'),
            ('multimodal_librarian', 'domain_configurations'),
            ('audit', 'audit_log')
        ]
        
        try:
            result = self.execute_query("""
                SELECT table_schema, table_name 
                FROM information_schema.tables 
                WHERE (table_schema, table_name) = ANY(%s)
            """, (required_tables,))
            
            existing_tables = [(row['table_schema'], row['table_name']) for row in result]
            missing_tables = set(required_tables) - set(existing_tables)
            
            self.validation_results['checks']['tables'] = {
                'status': 'PASS' if not missing_tables else 'FAIL',
                'existing': [f"{schema}.{table}" for schema, table in existing_tables],
                'missing': [f"{schema}.{table}" for schema, table in missing_tables]
            }
            
            if missing_tables:
                self.validation_results['errors'].append(f"Missing tables: {missing_tables}")
                return False
            
            return True
        except Exception as e:
            self.validation_results['checks']['tables'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def check_users_and_permissions(self) -> bool:
        """Check that required database users exist."""
        required_users = ['ml_app_user', 'ml_readonly', 'ml_backup']
        
        try:
            result = self.execute_query("""
                SELECT rolname, rolcanlogin, rolsuper 
                FROM pg_roles 
                WHERE rolname = ANY(%s)
            """, (required_users,))
            
            existing_users = {row['rolname']: {
                'can_login': row['rolcanlogin'],
                'is_superuser': row['rolsuper']
            } for row in result}
            
            missing_users = set(required_users) - set(existing_users.keys())
            
            self.validation_results['checks']['users'] = {
                'status': 'PASS' if not missing_users else 'FAIL',
                'existing': existing_users,
                'missing': list(missing_users)
            }
            
            if missing_users:
                self.validation_results['warnings'].append(f"Missing users: {missing_users}")
                # Don't fail for missing users, just warn
            
            return True
        except Exception as e:
            self.validation_results['checks']['users'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def check_functions(self) -> bool:
        """Check that required functions exist."""
        required_functions = [
            ('monitoring', 'health_check'),
            ('monitoring', 'get_table_sizes'),
            ('maintenance', 'cleanup_expired_sessions'),
            ('maintenance', 'routine_maintenance'),
            ('public', 'record_migration'),
            ('public', 'is_migration_applied')
        ]
        
        try:
            result = self.execute_query("""
                SELECT routine_schema, routine_name 
                FROM information_schema.routines 
                WHERE (routine_schema, routine_name) = ANY(%s)
                AND routine_type = 'FUNCTION'
            """, (required_functions,))
            
            existing_functions = [(row['routine_schema'], row['routine_name']) for row in result]
            missing_functions = set(required_functions) - set(existing_functions)
            
            self.validation_results['checks']['functions'] = {
                'status': 'PASS' if not missing_functions else 'FAIL',
                'existing': [f"{schema}.{func}" for schema, func in existing_functions],
                'missing': [f"{schema}.{func}" for schema, func in missing_functions]
            }
            
            if missing_functions:
                self.validation_results['errors'].append(f"Missing functions: {missing_functions}")
                return False
            
            return True
        except Exception as e:
            self.validation_results['checks']['functions'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def check_indexes(self) -> bool:
        """Check that important indexes exist."""
        try:
            result = self.execute_query("""
                SELECT schemaname, tablename, indexname 
                FROM pg_indexes 
                WHERE schemaname IN ('multimodal_librarian', 'audit', 'public')
                AND indexname LIKE 'idx_%'
            """)
            
            indexes = [f"{row['schemaname']}.{row['tablename']}.{row['indexname']}" for row in result]
            
            self.validation_results['checks']['indexes'] = {
                'status': 'PASS',
                'count': len(indexes),
                'indexes': indexes[:10]  # Show first 10 for brevity
            }
            
            return True
        except Exception as e:
            self.validation_results['checks']['indexes'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def check_migration_tracking(self) -> bool:
        """Check migration tracking tables."""
        try:
            # Check if migration_history table exists and has records
            result = self.execute_query("""
                SELECT COUNT(*) as count 
                FROM public.migration_history 
                WHERE success = true
            """)
            
            migration_count = result[0]['count'] if result else 0
            
            self.validation_results['checks']['migrations'] = {
                'status': 'PASS',
                'applied_migrations': migration_count
            }
            
            return True
        except Exception as e:
            self.validation_results['checks']['migrations'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def test_basic_operations(self) -> bool:
        """Test basic database operations."""
        try:
            # Test insert/select/delete on a simple table
            test_user_id = 'test-validation-user'
            
            # Insert test user
            self.execute_query("""
                INSERT INTO multimodal_librarian.users (username, email, password_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            """, (test_user_id, f"{test_user_id}@test.local", "test_hash"))
            
            # Select test user
            result = self.execute_query("""
                SELECT id, username FROM multimodal_librarian.users 
                WHERE username = %s
            """, (test_user_id,))
            
            if not result:
                raise Exception("Test user not found after insert")
            
            # Delete test user
            self.execute_query("""
                DELETE FROM multimodal_librarian.users 
                WHERE username = %s
            """, (test_user_id,))
            
            self.connection.commit()
            
            self.validation_results['checks']['basic_operations'] = {
                'status': 'PASS',
                'operations_tested': ['INSERT', 'SELECT', 'DELETE']
            }
            
            return True
        except Exception as e:
            self.connection.rollback()
            self.validation_results['checks']['basic_operations'] = {
                'status': 'FAIL',
                'error': str(e)
            }
            return False
    
    def run_validation(self) -> Dict[str, Any]:
        """Run all validation checks."""
        logger.info("Starting PostgreSQL validation")
        
        if not self.connect():
            self.validation_results['overall_status'] = 'FAIL'
            return self.validation_results
        
        try:
            checks = [
                self.check_database_connectivity,
                self.check_extensions,
                self.check_schemas,
                self.check_tables,
                self.check_users_and_permissions,
                self.check_functions,
                self.check_indexes,
                self.check_migration_tracking,
                self.test_basic_operations
            ]
            
            passed_checks = 0
            total_checks = len(checks)
            
            for check in checks:
                try:
                    if check():
                        passed_checks += 1
                except Exception as e:
                    logger.error("Check failed", check=check.__name__, error=str(e))
                    self.validation_results['errors'].append(f"{check.__name__}: {str(e)}")
            
            # Determine overall status
            if passed_checks == total_checks:
                self.validation_results['overall_status'] = 'PASS'
            elif passed_checks >= total_checks * 0.8:  # 80% pass rate
                self.validation_results['overall_status'] = 'WARN'
            else:
                self.validation_results['overall_status'] = 'FAIL'
            
            self.validation_results['summary'] = {
                'passed_checks': passed_checks,
                'total_checks': total_checks,
                'pass_rate': round((passed_checks / total_checks) * 100, 2)
            }
            
        finally:
            self.disconnect()
        
        logger.info("PostgreSQL validation completed", 
                   status=self.validation_results['overall_status'],
                   pass_rate=self.validation_results.get('summary', {}).get('pass_rate', 0))
        
        return self.validation_results


def main():
    """Main validation function."""
    validator = PostgreSQLValidator()
    results = validator.run_validation()
    
    # Print results
    print("\n" + "="*60)
    print("PostgreSQL Setup Validation Results")
    print("="*60)
    print(f"Overall Status: {results['overall_status']}")
    print(f"Timestamp: {results['timestamp']}")
    
    if 'summary' in results:
        summary = results['summary']
        print(f"Checks Passed: {summary['passed_checks']}/{summary['total_checks']} ({summary['pass_rate']}%)")
    
    print("\nDetailed Results:")
    for check_name, check_result in results['checks'].items():
        status = check_result['status']
        print(f"  {check_name}: {status}")
        if status == 'FAIL' and 'error' in check_result:
            print(f"    Error: {check_result['error']}")
    
    if results['errors']:
        print("\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")
    
    if results['warnings']:
        print("\nWarnings:")
        for warning in results['warnings']:
            print(f"  - {warning}")
    
    # Save results to file
    results_file = 'postgresql_validation_results.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {results_file}")
    
    # Exit with appropriate code
    if results['overall_status'] == 'FAIL':
        sys.exit(1)
    elif results['overall_status'] == 'WARN':
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()