#!/usr/bin/env python3
"""
Validation Script for Database Reset and Cleanup Functionality

This script validates that the database reset and cleanup scripts work correctly
by testing them in a safe environment with sample data.

Features:
- Creates test data in databases
- Tests reset functionality
- Tests cleanup functionality
- Validates results
- Provides comprehensive reporting

Usage:
    python scripts/validate-reset-cleanup.py [options]
"""

import asyncio
import argparse
import logging
import os
import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from multimodal_librarian.config.config_factory import get_database_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    NC = '\033[0m'

def colored_print(message: str, color: str = Colors.NC) -> None:
    """Print colored message to terminal."""
    print(f"{color}{message}{Colors.NC}")

def log_info(message: str) -> None:
    colored_print(f"[INFO] {message}", Colors.BLUE)

def log_success(message: str) -> None:
    colored_print(f"[SUCCESS] {message}", Colors.GREEN)

def log_warning(message: str) -> None:
    colored_print(f"[WARNING] {message}", Colors.YELLOW)

def log_error(message: str) -> None:
    colored_print(f"[ERROR] {message}", Colors.RED)

class ResetCleanupValidator:
    """Validates database reset and cleanup functionality."""
    
    def __init__(self, config: Any):
        self.config = config
        self.factory: Optional[DatabaseClientFactory] = None
        self.test_results: Dict[str, Any] = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": []
        }
        
    async def initialize(self) -> None:
        """Initialize database connections."""
        self.factory = DatabaseClientFactory(self.config)
        log_info(f"Initialized for {self.config.database_type} environment")
    
    async def cleanup(self) -> None:
        """Clean up connections."""
        if self.factory:
            await self.factory.close()
    
    async def create_test_data(self) -> bool:
        """Create test data in databases."""
        try:
            log_info("Creating test data...")
            
            # PostgreSQL test data
            try:
                client = await self.factory.get_relational_client()
                
                # Create test table if it doesn't exist
                await client.execute_command("""
                    CREATE TABLE IF NOT EXISTS test_validation_data (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100),
                        created_at TIMESTAMP DEFAULT NOW(),
                        data_type VARCHAR(50)
                    )
                """)
                
                # Insert test records
                for i in range(10):
                    await client.execute_command(
                        "INSERT INTO test_validation_data (name, data_type) VALUES (%s, %s)",
                        [f"test_record_{i}", "validation"]
                    )
                
                log_success("PostgreSQL test data created")
                
            except Exception as e:
                log_warning(f"Could not create PostgreSQL test data: {e}")
            
            # Neo4j test data
            try:
                client = await self.factory.get_graph_client()
                
                # Create test nodes
                for i in range(5):
                    await client.execute_query(
                        f"CREATE (n:TestNode {{id: {i}, name: 'test_node_{i}', type: 'validation'}})"
                    )
                
                log_success("Neo4j test data created")
                
            except Exception as e:
                log_warning(f"Could not create Neo4j test data: {e}")
            
            # Milvus test data (simplified)
            try:
                client = await self.factory.get_vector_client()
                
                # Create test collection
                await client.create_collection("test_validation", dimension=128)
                log_success("Milvus test data created")
                
            except Exception as e:
                log_warning(f"Could not create Milvus test data: {e}")
            
            return True
            
        except Exception as e:
            log_error(f"Failed to create test data: {e}")
            return False
    
    async def validate_data_exists(self) -> Dict[str, int]:
        """Validate that test data exists."""
        counts = {}
        
        # PostgreSQL
        try:
            client = await self.factory.get_relational_client()
            result = await client.execute_query(
                "SELECT COUNT(*) as count FROM test_validation_data WHERE data_type = 'validation'"
            )
            counts["postgresql"] = result[0]["count"] if result else 0
        except Exception:
            counts["postgresql"] = 0
        
        # Neo4j
        try:
            client = await self.factory.get_graph_client()
            result = await client.execute_query(
                "MATCH (n:TestNode {type: 'validation'}) RETURN count(n) as count"
            )
            counts["neo4j"] = result[0]["count"] if result else 0
        except Exception:
            counts["neo4j"] = 0
        
        # Milvus
        try:
            client = await self.factory.get_vector_client()
            collections = await client.list_collections()
            counts["milvus"] = 1 if "test_validation" in collections else 0
        except Exception:
            counts["milvus"] = 0
        
        return counts
    
    async def test_reset_functionality(self) -> bool:
        """Test database reset functionality."""
        try:
            log_info("Testing reset functionality...")
            
            # Create test data
            await self.create_test_data()
            
            # Validate data exists
            counts_before = await self.validate_data_exists()
            log_info(f"Data before reset: {counts_before}")
            
            # Test dry run first
            log_info("Testing dry run mode...")
            import subprocess
            result = subprocess.run([
                sys.executable, 
                str(Path(__file__).parent / "reset-all-databases.py"),
                "--all", "--dry-run"
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
            
            if result.returncode == 0:
                log_success("Dry run completed successfully")
                self.test_results["tests_passed"] += 1
            else:
                log_error(f"Dry run failed: {result.stderr}")
                self.test_results["tests_failed"] += 1
                self.test_results["errors"].append(f"Dry run failed: {result.stderr}")
            
            self.test_results["tests_run"] += 1
            
            # Test actual reset (only if we have test data)
            if any(count > 0 for count in counts_before.values()):
                log_info("Testing actual reset...")
                result = subprocess.run([
                    sys.executable,
                    str(Path(__file__).parent / "reset-all-databases.py"),
                    "--databases", "postgresql,neo4j,milvus", "--force"
                ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
                
                if result.returncode == 0:
                    log_success("Reset completed successfully")
                    
                    # Validate data was reset
                    counts_after = await self.validate_data_exists()
                    log_info(f"Data after reset: {counts_after}")
                    
                    # Check if data was actually reset
                    reset_successful = True
                    for db, count in counts_after.items():
                        if db in counts_before and counts_before[db] > 0 and count >= counts_before[db]:
                            log_warning(f"{db} data was not reset properly")
                            reset_successful = False
                    
                    if reset_successful:
                        log_success("Reset validation passed")
                        self.test_results["tests_passed"] += 1
                    else:
                        log_error("Reset validation failed")
                        self.test_results["tests_failed"] += 1
                        self.test_results["errors"].append("Reset did not clear data properly")
                else:
                    log_error(f"Reset failed: {result.stderr}")
                    self.test_results["tests_failed"] += 1
                    self.test_results["errors"].append(f"Reset failed: {result.stderr}")
                
                self.test_results["tests_run"] += 1
            
            return True
            
        except Exception as e:
            log_error(f"Reset functionality test failed: {e}")
            self.test_results["tests_failed"] += 1
            self.test_results["errors"].append(f"Reset test exception: {str(e)}")
            return False
    
    async def test_cleanup_functionality(self) -> bool:
        """Test database cleanup functionality."""
        try:
            log_info("Testing cleanup functionality...")
            
            # Create test data with different ages
            await self.create_test_data()
            
            # Test cleanup dry run
            log_info("Testing cleanup dry run...")
            import subprocess
            result = subprocess.run([
                sys.executable,
                str(Path(__file__).parent / "cleanup-database-data.py"),
                "--age", "1", "--dry-run"
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
            
            if result.returncode == 0:
                log_success("Cleanup dry run completed successfully")
                self.test_results["tests_passed"] += 1
            else:
                log_error(f"Cleanup dry run failed: {result.stderr}")
                self.test_results["tests_failed"] += 1
                self.test_results["errors"].append(f"Cleanup dry run failed: {result.stderr}")
            
            self.test_results["tests_run"] += 1
            
            return True
            
        except Exception as e:
            log_error(f"Cleanup functionality test failed: {e}")
            self.test_results["tests_failed"] += 1
            self.test_results["errors"].append(f"Cleanup test exception: {str(e)}")
            return False
    
    async def test_database_management_script(self) -> bool:
        """Test the unified database management script."""
        try:
            log_info("Testing database management script...")
            
            # Test health check
            import subprocess
            result = subprocess.run([
                str(Path(__file__).parent / "database-management.sh"),
                "health"
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
            
            if result.returncode == 0:
                log_success("Database management health check passed")
                self.test_results["tests_passed"] += 1
            else:
                log_warning(f"Database management health check failed: {result.stderr}")
                self.test_results["tests_failed"] += 1
                self.test_results["errors"].append(f"Management script health check failed: {result.stderr}")
            
            self.test_results["tests_run"] += 1
            
            # Test status command
            result = subprocess.run([
                str(Path(__file__).parent / "database-management.sh"),
                "status"
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
            
            if result.returncode == 0:
                log_success("Database management status check passed")
                self.test_results["tests_passed"] += 1
            else:
                log_warning(f"Database management status check failed: {result.stderr}")
                self.test_results["tests_failed"] += 1
                self.test_results["errors"].append(f"Management script status check failed: {result.stderr}")
            
            self.test_results["tests_run"] += 1
            
            return True
            
        except Exception as e:
            log_error(f"Database management script test failed: {e}")
            self.test_results["tests_failed"] += 1
            self.test_results["errors"].append(f"Management script test exception: {str(e)}")
            return False
    
    def print_validation_summary(self) -> None:
        """Print validation summary."""
        print("\n" + "="*60)
        colored_print("RESET & CLEANUP VALIDATION SUMMARY", Colors.BLUE)
        print("="*60)
        
        print(f"Environment: {self.config.database_type}")
        print(f"Tests run: {self.test_results['tests_run']}")
        print(f"Tests passed: {self.test_results['tests_passed']}")
        print(f"Tests failed: {self.test_results['tests_failed']}")
        
        if self.test_results["errors"]:
            print("\nErrors encountered:")
            for error in self.test_results["errors"]:
                colored_print(f"  ✗ {error}", Colors.RED)
        
        print()
        
        success_rate = (self.test_results["tests_passed"] / self.test_results["tests_run"] * 100) if self.test_results["tests_run"] > 0 else 0
        
        if success_rate == 100:
            log_success(f"All tests passed! ({success_rate:.1f}%)")
        elif success_rate >= 80:
            log_warning(f"Most tests passed ({success_rate:.1f}%)")
        else:
            log_error(f"Many tests failed ({success_rate:.1f}%)")
        
        print("="*60)

async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Validate database reset and cleanup functionality"
    )
    
    parser.add_argument(
        "--environment",
        choices=["local", "aws"],
        help="Override environment detection"
    )
    parser.add_argument(
        "--skip-reset",
        action="store_true",
        help="Skip reset functionality tests"
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip cleanup functionality tests"
    )
    parser.add_argument(
        "--skip-management",
        action="store_true",
        help="Skip management script tests"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Get configuration
        if args.environment:
            os.environ["ML_ENVIRONMENT"] = args.environment
        
        config = get_database_config()
        log_info(f"Validating in {config.database_type} environment")
        
        # Initialize validator
        validator = ResetCleanupValidator(config)
        await validator.initialize()
        
        try:
            # Run tests
            if not args.skip_reset:
                await validator.test_reset_functionality()
            
            if not args.skip_cleanup:
                await validator.test_cleanup_functionality()
            
            if not args.skip_management:
                await validator.test_database_management_script()
            
            # Print summary
            validator.print_validation_summary()
            
            # Return appropriate exit code
            if validator.test_results["tests_failed"] == 0:
                return 0
            else:
                return 1
                
        finally:
            await validator.cleanup()
            
    except KeyboardInterrupt:
        log_warning("Validation cancelled by user")
        return 1
    except Exception as e:
        log_error(f"Validation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))