#!/usr/bin/env python3
"""
Comprehensive Schema Validation Script

This script validates all database schemas used by the Multimodal Librarian
application and generates detailed validation reports.

Usage:
    # Validate all schemas with default connections
    python scripts/validate-all-schemas.py
    
    # Validate with custom connections
    python scripts/validate-all-schemas.py --postgresql-conn "postgresql://user:pass@host:port/db"
    
    # Generate detailed report
    python scripts/validate-all-schemas.py --report-file validation_report.txt
    
    # Check for schema drift
    python scripts/validate-all-schemas.py --check-drift
    
    # Validate specific databases only
    python scripts/validate-all-schemas.py --databases postgresql milvus
"""

import sys
import asyncio
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from database.schema_validator import (
        SchemaValidator, DatabaseType, ValidationStatus,
        validate_all_database_schemas, generate_schema_validation_report
    )
    from database.schema_version_manager import SchemaVersionManager
    MODULES_AVAILABLE = True
except ImportError as e:
    MODULES_AVAILABLE = False
    IMPORT_ERROR = str(e)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_validation_summary(results: Dict[DatabaseType, any]) -> None:
    """Print a colorized summary of validation results"""
    
    # ANSI color codes
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'
    
    print(f"\n{BOLD}{'='*80}{END}")
    print(f"{BOLD}{BLUE}DATABASE SCHEMA VALIDATION SUMMARY{END}")
    print(f"{BOLD}{'='*80}{END}")
    
    total_databases = len(results)
    valid_count = 0
    warning_count = 0
    error_count = 0
    
    for db_type, result in results.items():
        status_color = GREEN
        status_symbol = "✅"
        
        if result.status == ValidationStatus.VALID:
            valid_count += 1
            status_color = GREEN
            status_symbol = "✅"
        elif result.status == ValidationStatus.WARNING:
            warning_count += 1
            status_color = YELLOW
            status_symbol = "⚠️ "
        else:
            error_count += 1
            status_color = RED
            status_symbol = "❌"
        
        print(f"\n{BOLD}{db_type.value.upper()}{END}")
        print(f"  Status: {status_color}{status_symbol} {result.status.value.upper()}{END}")
        print(f"  Database: {result.database_name}")
        print(f"  Version: {result.version or 'Unknown'}")
        print(f"  Issues: {len(result.issues)}")
        
        if result.issues:
            for issue in result.issues[:3]:  # Show first 3 issues
                severity_color = RED if issue.severity in [ValidationStatus.ERROR, ValidationStatus.INVALID] else YELLOW
                print(f"    {severity_color}• {issue.message}{END}")
            
            if len(result.issues) > 3:
                print(f"    ... and {len(result.issues) - 3} more issues")
    
    print(f"\n{BOLD}OVERALL SUMMARY{END}")
    print(f"  Total Databases: {total_databases}")
    print(f"  {GREEN}Valid: {valid_count}{END}")
    print(f"  {YELLOW}Warnings: {warning_count}{END}")
    print(f"  {RED}Errors: {error_count}{END}")
    
    if error_count == 0 and warning_count == 0:
        print(f"\n{GREEN}{BOLD}🎉 All schemas are valid!{END}")
    elif error_count == 0:
        print(f"\n{YELLOW}{BOLD}⚠️  All schemas are functional with minor warnings{END}")
    else:
        print(f"\n{RED}{BOLD}❌ Some schemas have critical issues that need attention{END}")
    
    print(f"{BOLD}{'='*80}{END}\n")


async def check_schema_drift(validator: SchemaValidator) -> None:
    """Check and report schema drift"""
    logger.info("Checking for schema drift...")
    
    drift_status = await validator.check_schema_drift()
    
    print(f"\n{'='*60}")
    print("SCHEMA DRIFT ANALYSIS")
    print(f"{'='*60}")
    
    has_drift = False
    for db_type, drifted in drift_status.items():
        status = "DRIFTED" if drifted else "STABLE"
        color = '\033[91m' if drifted else '\033[92m'
        print(f"{db_type.value}: {color}{status}\033[0m")
        
        if drifted:
            has_drift = True
    
    if has_drift:
        print(f"\n\033[93m⚠️  Schema drift detected! Consider running migrations.\033[0m")
    else:
        print(f"\n\033[92m✅ No schema drift detected.\033[0m")
    
    print(f"{'='*60}\n")


async def validate_with_version_check(
    postgresql_conn: Optional[str] = None,
    milvus_host: str = "localhost",
    milvus_port: int = 19530,
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "ml_password"
) -> Dict[DatabaseType, any]:
    """Validate schemas and check versions"""
    
    # Initialize validator and version manager
    validator = SchemaValidator()
    version_manager = SchemaVersionManager()
    
    # Validate all schemas
    logger.info("Starting comprehensive schema validation...")
    results = await validate_all_database_schemas(
        postgresql_conn=postgresql_conn,
        milvus_host=milvus_host,
        milvus_port=milvus_port,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password
    )
    
    # Get current and latest versions
    try:
        current_versions = await version_manager.get_current_versions()
        latest_versions = version_manager.get_latest_versions()
        
        # Add version information to results
        for db_type, result in results.items():
            current_version = current_versions.get(db_type)
            latest_version = latest_versions.get(db_type)
            
            if current_version and latest_version:
                if version_manager._compare_versions(current_version, latest_version) < 0:
                    result.issues.append(type(result.issues[0])(
                        severity=ValidationStatus.WARNING,
                        category="version",
                        message=f"Schema version outdated: {current_version} < {latest_version}",
                        suggestion="Run schema migration to update to latest version"
                    ))
                    if result.status == ValidationStatus.VALID:
                        result.status = ValidationStatus.WARNING
    
    except Exception as e:
        logger.warning(f"Could not check schema versions: {e}")
    
    return results


def parse_database_list(db_list: List[str]) -> List[DatabaseType]:
    """Parse database list from command line arguments"""
    databases = []
    for db_name in db_list:
        try:
            db_type = DatabaseType(db_name.lower())
            databases.append(db_type)
        except ValueError:
            logger.error(f"Unknown database type: {db_name}")
            logger.info(f"Available types: {[dt.value for dt in DatabaseType]}")
            sys.exit(1)
    return databases


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Validate database schemas for Multimodal Librarian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic validation
  python scripts/validate-all-schemas.py
  
  # Custom PostgreSQL connection
  python scripts/validate-all-schemas.py --postgresql-conn "postgresql://user:pass@host/db"
  
  # Generate detailed report
  python scripts/validate-all-schemas.py --report-file validation_report.txt
  
  # Check for schema drift
  python scripts/validate-all-schemas.py --check-drift
  
  # Validate specific databases
  python scripts/validate-all-schemas.py --databases postgresql milvus
  
  # Quiet mode (errors only)
  python scripts/validate-all-schemas.py --quiet
        """
    )
    
    # Connection arguments
    parser.add_argument(
        "--postgresql-conn",
        help="PostgreSQL connection string"
    )
    parser.add_argument(
        "--milvus-host",
        default="localhost",
        help="Milvus host (default: localhost)"
    )
    parser.add_argument(
        "--milvus-port",
        type=int,
        default=19530,
        help="Milvus port (default: 19530)"
    )
    parser.add_argument(
        "--neo4j-uri",
        default="bolt://localhost:7687",
        help="Neo4j URI (default: bolt://localhost:7687)"
    )
    parser.add_argument(
        "--neo4j-user",
        default="neo4j",
        help="Neo4j username (default: neo4j)"
    )
    parser.add_argument(
        "--neo4j-password",
        default="ml_password",
        help="Neo4j password (default: ml_password)"
    )
    
    # Validation options
    parser.add_argument(
        "--databases",
        nargs="+",
        help="Specific databases to validate (postgresql, milvus, neo4j)"
    )
    parser.add_argument(
        "--report-file",
        help="Generate detailed report to file"
    )
    parser.add_argument(
        "--check-drift",
        action="store_true",
        help="Check for schema drift"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Quiet mode (errors only)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check module availability
    if not MODULES_AVAILABLE:
        logger.error(f"Required modules not available: {IMPORT_ERROR}")
        sys.exit(1)
    
    try:
        # Validate schemas
        results = await validate_with_version_check(
            postgresql_conn=args.postgresql_conn,
            milvus_host=args.milvus_host,
            milvus_port=args.milvus_port,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password
        )
        
        # Filter results if specific databases requested
        if args.databases:
            requested_dbs = parse_database_list(args.databases)
            results = {db_type: result for db_type, result in results.items() if db_type in requested_dbs}
        
        # Print summary
        if not args.quiet:
            print_validation_summary(results)
        
        # Check schema drift if requested
        if args.check_drift:
            validator = SchemaValidator()
            await check_schema_drift(validator)
        
        # Generate detailed report if requested
        if args.report_file:
            report_content = generate_schema_validation_report(results, args.report_file)
            if not args.quiet:
                logger.info(f"Detailed report saved to: {args.report_file}")
        
        # Determine exit code
        error_count = sum(
            1 for result in results.values() 
            if result.status in [ValidationStatus.ERROR, ValidationStatus.INVALID]
        )
        
        if error_count > 0:
            logger.error(f"Validation failed with {error_count} database(s) having critical issues")
            sys.exit(1)
        else:
            if not args.quiet:
                logger.info("Schema validation completed successfully")
            sys.exit(0)
    
    except KeyboardInterrupt:
        logger.info("Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Validation failed with error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())