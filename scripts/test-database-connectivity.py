#!/usr/bin/env python3
"""
Test Database Connectivity

This script verifies that the application can successfully connect to the PostgreSQL database.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import psycopg2
from sqlalchemy import create_engine, text
import structlog

logger = structlog.get_logger(__name__)


def test_raw_psycopg2_connection():
    """Test raw psycopg2 connection."""
    print("\n" + "="*80)
    print("TEST 1: Raw psycopg2 Connection")
    print("="*80)
    
    try:
        # Get connection parameters from environment
        host = os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost"))
        port = os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))
        database = os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "multimodal_librarian"))
        user = os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres"))
        password = os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "postgres"))
        
        print(f"\nConnection Parameters:")
        print(f"  Host: {host}")
        print(f"  Port: {port}")
        print(f"  Database: {database}")
        print(f"  User: {user}")
        print(f"  Password: {'*' * len(password) if password else '(not set)'}")
        
        print("\nAttempting connection...")
        conn = psycopg2.connect(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
            connect_timeout=10
        )
        
        print("✓ Connection successful!")
        
        # Test query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"\n✓ PostgreSQL Version: {version}")
        
        # Test database name
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()[0]
        print(f"✓ Connected to database: {db_name}")
        
        # Test user
        cursor.execute("SELECT current_user;")
        current_user = cursor.fetchone()[0]
        print(f"✓ Connected as user: {current_user}")
        
        cursor.close()
        conn.close()
        
        print("\n✓ TEST 1 PASSED: Raw psycopg2 connection successful")
        return True
        
    except Exception as e:
        print(f"\n✗ TEST 1 FAILED: {str(e)}")
        return False


def test_sqlalchemy_connection():
    """Test SQLAlchemy connection."""
    print("\n" + "="*80)
    print("TEST 2: SQLAlchemy Connection")
    print("="*80)
    
    try:
        # Get connection parameters from environment
        host = os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost"))
        port = os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))
        database = os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "multimodal_librarian"))
        user = os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres"))
        password = os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "postgres"))
        
        database_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        
        print(f"\nDatabase URL: postgresql://{user}:***@{host}:{port}/{database}")
        
        print("\nCreating SQLAlchemy engine...")
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10}
        )
        
        print("✓ Engine created successfully!")
        
        # Test connection
        print("\nTesting connection...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            test_value = result.fetchone()[0]
            print(f"✓ Test query successful: SELECT 1 returned {test_value}")
            
            # Get database info
            result = conn.execute(text("SELECT current_database(), current_user, version()"))
            db_name, user_name, version = result.fetchone()
            print(f"\n✓ Database: {db_name}")
            print(f"✓ User: {user_name}")
            print(f"✓ Version: {version}")
        
        engine.dispose()
        
        print("\n✓ TEST 2 PASSED: SQLAlchemy connection successful")
        return True
        
    except Exception as e:
        print(f"\n✗ TEST 2 FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_application_database_manager():
    """Test the application's DatabaseManager."""
    print("\n" + "="*80)
    print("TEST 3: Application DatabaseManager")
    print("="*80)
    
    try:
        from multimodal_librarian.database.connection import DatabaseManager
        
        print("\nInitializing DatabaseManager...")
        db_manager = DatabaseManager()
        
        print("✓ DatabaseManager created")
        
        print("\nInitializing database connection...")
        db_manager.initialize()
        
        print("✓ Database initialized")
        
        # Test session
        print("\nTesting database session...")
        with db_manager.get_session() as session:
            result = session.execute(text("SELECT 1 as test"))
            test_value = result.fetchone()[0]
            print(f"✓ Session test query successful: {test_value}")
        
        print("✓ Session management working")
        
        # Cleanup
        db_manager.close()
        print("✓ Database connections closed")
        
        print("\n✓ TEST 3 PASSED: Application DatabaseManager working correctly")
        return True
        
    except Exception as e:
        print(f"\n✗ TEST 3 FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all database connectivity tests."""
    print("\n" + "="*80)
    print("DATABASE CONNECTIVITY TEST SUITE")
    print("="*80)
    
    # Load environment variables from .env if it exists
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        print(f"\nLoading environment from: {env_file}")
        from dotenv import load_dotenv
        load_dotenv(env_file)
    else:
        print(f"\nNo .env file found at: {env_file}")
        print("Using environment variables or defaults")
    
    results = []
    
    # Run tests
    results.append(("Raw psycopg2 Connection", test_raw_psycopg2_connection()))
    results.append(("SQLAlchemy Connection", test_sqlalchemy_connection()))
    results.append(("Application DatabaseManager", test_application_database_manager()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)
    
    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\n✓ ALL TESTS PASSED - Database connectivity confirmed!")
        return 0
    else:
        print(f"\n✗ {total_tests - passed_tests} TEST(S) FAILED - Database connectivity issues detected")
        return 1


if __name__ == "__main__":
    sys.exit(main())
