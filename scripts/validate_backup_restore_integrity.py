#!/usr/bin/env python3
"""
Backup and Restore Integrity Validation

This script provides comprehensive validation for backup and restore operations,
ensuring data integrity throughout the backup/restore lifecycle. It integrates
with existing backup and restore scripts to provide validation checkpoints.

Features:
- Pre-backup validation
- Backup integrity verification
- Post-restore validation
- Data consistency checks
- Automated fix suggestions

Usage:
    # Validate before backup
    python scripts/validate-backup-restore-integrity.py --pre-backup

    # Validate backup files
    python scripts/validate-backup-restore-integrity.py --validate-backup ./backups/20240101_120000

    # Validate after restore
    python scripts/validate-backup-restore-integrity.py --post-restore

    # Full validation cycle
    python scripts/validate-backup-restore-integrity.py --full-cycle
"""

import asyncio
import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.multimodal_librarian.config.config_factory import get_database_config
from scripts.data_validation_utils import (
    DataValidationUtils, ValidationResult, DataConsistencyReport,
    validate_before_backup, validate_after_restore
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackupRestoreValidator:
    """
    Comprehensive validator for backup and restore operations.
    
    This class provides validation at different stages of the backup/restore
    lifecycle to ensure data integrity and consistency.
    """
    
    def __init__(self, config: Any):
        """Initialize the validator."""
        self.config = config
        self.validation_utils = DataValidationUtils(config)
        
    async def initialize(self) -> None:
        """Initialize the validator."""
        await self.validation_utils.initialize()
        
    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.validation_utils.cleanup()
    
    async def validate_pre_backup(self) -> Dict[str, Any]:
        """
        Validate system state before backup operation.
        
        Returns:
            Validation report with recommendations
        """
        logger.info("Running pre-backup validation...")
        
        start_time = time.time()
        
        # Check database connectivity
        connectivity_results = await self.validation_utils.validate_database_connectivity()
        
        # Check data consistency
        consistency_report = await self.validation_utils.generate_data_consistency_report()
        
        # Check referential integrity
        referential_results = await self.validation_utils.validate_referential_integrity()
        
        # Check data quality
        quality_results = await self.validation_utils.validate_data_quality()
        
        execution_time = time.time() - start_time
        
        # Determine if backup should proceed
        connectivity_ok = all(result.success for result in connectivity_results.values())
        consistency_ok = consistency_report.overall_status != "critical"
        referential_ok = all(result.success for result in referential_results.values())
        
        backup_recommended = connectivity_ok and consistency_ok
        
        # Generate recommendations
        recommendations = []
        if not connectivity_ok:
            recommendations.append("Fix database connectivity issues before backup")
        if not consistency_ok:
            recommendations.append("Resolve critical data consistency issues before backup")
        if not referential_ok:
            recommendations.append("Consider fixing referential integrity issues")
        
        if backup_recommended:
            recommendations.append("System is ready for backup operation")
        else:
            recommendations.append("Backup not recommended due to critical issues")
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation_type": "pre_backup",
            "execution_time": execution_time,
            "backup_recommended": backup_recommended,
            "connectivity": {
                "status": "ok" if connectivity_ok else "failed",
                "results": {k: {"success": v.success, "message": v.message} for k, v in connectivity_results.items()}
            },
            "consistency": {
                "status": consistency_report.overall_status,
                "total_issues": consistency_report.total_issues,
                "details": {
                    "users": {"success": consistency_report.user_consistency.success, "message": consistency_report.user_consistency.message},
                    "documents": {"success": consistency_report.document_consistency.success, "message": consistency_report.document_consistency.message},
                    "conversations": {"success": consistency_report.conversation_consistency.success, "message": consistency_report.conversation_consistency.message},
                    "vectors": {"success": consistency_report.vector_consistency.success, "message": consistency_report.vector_consistency.message}
                }
            },
            "referential_integrity": {
                "status": "ok" if referential_ok else "issues_found",
                "results": {k: {"success": v.success, "message": v.message} for k, v in referential_results.items()}
            },
            "data_quality": {
                "results": {k: {"success": v.success, "message": v.message} for k, v in quality_results.items()}
            },
            "recommendations": recommendations
        }
    
    async def validate_backup_integrity(self, backup_path: str) -> Dict[str, Any]:
        """
        Validate integrity of backup files.
        
        Args:
            backup_path: Path to backup directory
            
        Returns:
            Validation report for backup files
        """
        logger.info(f"Validating backup integrity: {backup_path}")
        
        start_time = time.time()
        backup_dir = Path(backup_path)
        
        if not backup_dir.exists():
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "validation_type": "backup_integrity",
                "execution_time": 0,
                "backup_valid": False,
                "error": f"Backup directory does not exist: {backup_path}",
                "recommendations": ["Check backup path", "Run backup operation"]
            }
        
        # Check backup file integrity
        backup_integrity = await self.validation_utils.check_backup_integrity(backup_path)
        
        # Check individual database backups
        database_backups = {}
        
        # PostgreSQL backup validation
        pg_backup_dir = backup_dir / "postgresql"
        if pg_backup_dir.exists():
            pg_files = list(pg_backup_dir.glob("*.sql"))
            pg_valid = len(pg_files) > 0 and all(f.stat().st_size > 0 for f in pg_files)
            
            # Basic SQL file validation
            if pg_files:
                try:
                    with open(pg_files[0], 'r') as f:
                        content = f.read(1000)  # Read first 1KB
                        pg_valid = pg_valid and ("CREATE" in content or "INSERT" in content or "COPY" in content)
                except Exception:
                    pg_valid = False
            
            database_backups["postgresql"] = {
                "files_found": len(pg_files),
                "valid": pg_valid,
                "total_size": sum(f.stat().st_size for f in pg_files)
            }
        
        # Neo4j backup validation
        neo4j_backup_dir = backup_dir / "neo4j"
        if neo4j_backup_dir.exists():
            neo4j_files = list(neo4j_backup_dir.glob("*.cypher")) + list(neo4j_backup_dir.glob("*.json"))
            neo4j_valid = len(neo4j_files) > 0 and all(f.stat().st_size > 0 for f in neo4j_files)
            
            database_backups["neo4j"] = {
                "files_found": len(neo4j_files),
                "valid": neo4j_valid,
                "total_size": sum(f.stat().st_size for f in neo4j_files)
            }
        
        # Milvus backup validation
        milvus_backup_dir = backup_dir / "milvus"
        if milvus_backup_dir.exists():
            milvus_files = list(milvus_backup_dir.glob("*.json"))
            milvus_valid = len(milvus_files) > 0
            
            # Validate JSON format
            if milvus_files:
                try:
                    with open(milvus_files[0], 'r') as f:
                        json.load(f)
                except Exception:
                    milvus_valid = False
            
            database_backups["milvus"] = {
                "files_found": len(milvus_files),
                "valid": milvus_valid,
                "total_size": sum(f.stat().st_size for f in milvus_files)
            }
        
        # Check system metadata
        system_backup_dir = backup_dir / "system"
        system_metadata_valid = False
        if system_backup_dir.exists():
            metadata_files = list(system_backup_dir.glob("backup_metadata_*.json"))
            if metadata_files:
                try:
                    with open(metadata_files[0], 'r') as f:
                        metadata = json.load(f)
                        system_metadata_valid = "backup_timestamp" in metadata
                except Exception:
                    pass
        
        execution_time = time.time() - start_time
        
        # Determine overall backup validity
        backup_valid = (
            backup_integrity.success and
            len(database_backups) > 0 and
            all(db["valid"] for db in database_backups.values())
        )
        
        # Generate recommendations
        recommendations = []
        if not backup_valid:
            recommendations.append("Backup files appear to be corrupted or incomplete")
            recommendations.append("Re-run backup operation")
        else:
            recommendations.append("Backup files appear to be valid")
        
        if not system_metadata_valid:
            recommendations.append("System metadata missing or invalid")
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation_type": "backup_integrity",
            "execution_time": execution_time,
            "backup_path": str(backup_dir),
            "backup_valid": backup_valid,
            "backup_integrity": {
                "success": backup_integrity.success,
                "message": backup_integrity.message,
                "details": backup_integrity.details
            },
            "database_backups": database_backups,
            "system_metadata_valid": system_metadata_valid,
            "recommendations": recommendations
        }
    
    async def validate_post_restore(self) -> Dict[str, Any]:
        """
        Validate system state after restore operation.
        
        Returns:
            Validation report for post-restore state
        """
        logger.info("Running post-restore validation...")
        
        start_time = time.time()
        
        # Wait a moment for services to stabilize
        await asyncio.sleep(2)
        
        # Check database connectivity
        connectivity_results = await self.validation_utils.validate_database_connectivity()
        
        # Check data consistency
        consistency_report = await self.validation_utils.generate_data_consistency_report()
        
        # Check referential integrity
        referential_results = await self.validation_utils.validate_referential_integrity()
        
        # Check data quality
        quality_results = await self.validation_utils.validate_data_quality()
        
        execution_time = time.time() - start_time
        
        # Determine restore success
        connectivity_ok = all(result.success for result in connectivity_results.values())
        consistency_ok = consistency_report.overall_status != "critical"
        referential_ok = all(result.success for result in referential_results.values())
        
        restore_successful = connectivity_ok and consistency_ok
        
        # Generate recommendations
        recommendations = []
        if not connectivity_ok:
            recommendations.append("Database connectivity issues detected after restore")
            recommendations.append("Check service status and configuration")
        
        if not consistency_ok:
            recommendations.append("Data consistency issues detected after restore")
            recommendations.append("Investigate data synchronization problems")
        
        if not referential_ok:
            recommendations.append("Referential integrity issues detected")
            recommendations.append("Run data cleanup procedures")
        
        if restore_successful:
            recommendations.append("Restore operation appears successful")
            recommendations.append("System is ready for use")
        else:
            recommendations.append("Restore operation may have failed")
            recommendations.append("Consider re-running restore or investigating issues")
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation_type": "post_restore",
            "execution_time": execution_time,
            "restore_successful": restore_successful,
            "connectivity": {
                "status": "ok" if connectivity_ok else "failed",
                "results": {k: {"success": v.success, "message": v.message} for k, v in connectivity_results.items()}
            },
            "consistency": {
                "status": consistency_report.overall_status,
                "total_issues": consistency_report.total_issues,
                "details": {
                    "users": {"success": consistency_report.user_consistency.success, "message": consistency_report.user_consistency.message},
                    "documents": {"success": consistency_report.document_consistency.success, "message": consistency_report.document_consistency.message},
                    "conversations": {"success": consistency_report.conversation_consistency.success, "message": consistency_report.conversation_consistency.message},
                    "vectors": {"success": consistency_report.vector_consistency.success, "message": consistency_report.vector_consistency.message}
                }
            },
            "referential_integrity": {
                "status": "ok" if referential_ok else "issues_found",
                "results": {k: {"success": v.success, "message": v.message} for k, v in referential_results.items()}
            },
            "data_quality": {
                "results": {k: {"success": v.success, "message": v.message} for k, v in quality_results.items()}
            },
            "recommendations": recommendations
        }
    
    async def run_full_validation_cycle(self, backup_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Run complete validation cycle: pre-backup, backup integrity, and post-restore simulation.
        
        Args:
            backup_path: Optional path to existing backup to validate
            
        Returns:
            Complete validation cycle report
        """
        logger.info("Running full validation cycle...")
        
        cycle_start = time.time()
        results = {}
        
        # Pre-backup validation
        try:
            results["pre_backup"] = await self.validate_pre_backup()
        except Exception as e:
            results["pre_backup"] = {
                "error": str(e),
                "backup_recommended": False
            }
        
        # Backup integrity validation (if path provided)
        if backup_path:
            try:
                results["backup_integrity"] = await self.validate_backup_integrity(backup_path)
            except Exception as e:
                results["backup_integrity"] = {
                    "error": str(e),
                    "backup_valid": False
                }
        
        # Current state validation (simulates post-restore)
        try:
            results["current_state"] = await self.validate_post_restore()
        except Exception as e:
            results["current_state"] = {
                "error": str(e),
                "restore_successful": False
            }
        
        cycle_time = time.time() - cycle_start
        
        # Overall assessment
        pre_backup_ok = results.get("pre_backup", {}).get("backup_recommended", False)
        backup_ok = results.get("backup_integrity", {}).get("backup_valid", True)  # True if not tested
        current_ok = results.get("current_state", {}).get("restore_successful", False)
        
        overall_status = "healthy" if all([pre_backup_ok, backup_ok, current_ok]) else "issues_detected"
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation_type": "full_cycle",
            "total_execution_time": cycle_time,
            "overall_status": overall_status,
            "results": results,
            "summary": {
                "pre_backup_ready": pre_backup_ok,
                "backup_integrity_ok": backup_ok,
                "current_state_healthy": current_ok
            }
        }


def print_validation_report(report: Dict[str, Any]) -> None:
    """Print formatted validation report."""
    print("\n" + "="*80)
    print(f"BACKUP/RESTORE VALIDATION REPORT - {report['validation_type'].upper()}")
    print("="*80)
    
    print(f"Timestamp: {report['timestamp']}")
    print(f"Execution Time: {report.get('execution_time', 0):.2f} seconds")
    
    if report['validation_type'] == 'pre_backup':
        print(f"Backup Recommended: {'YES' if report['backup_recommended'] else 'NO'}")
        print(f"Connectivity: {report['connectivity']['status'].upper()}")
        print(f"Consistency: {report['consistency']['status'].upper()}")
        print(f"Total Issues: {report['consistency']['total_issues']}")
        
    elif report['validation_type'] == 'backup_integrity':
        print(f"Backup Path: {report.get('backup_path', 'N/A')}")
        print(f"Backup Valid: {'YES' if report['backup_valid'] else 'NO'}")
        
        if 'database_backups' in report:
            print("\nDatabase Backup Status:")
            for db, info in report['database_backups'].items():
                status = "✓" if info['valid'] else "✗"
                print(f"  {status} {db:12} {info['files_found']} files, {info['total_size']:,} bytes")
        
    elif report['validation_type'] == 'post_restore':
        print(f"Restore Successful: {'YES' if report['restore_successful'] else 'NO'}")
        print(f"Connectivity: {report['connectivity']['status'].upper()}")
        print(f"Consistency: {report['consistency']['status'].upper()}")
        
    elif report['validation_type'] == 'full_cycle':
        print(f"Overall Status: {report['overall_status'].upper()}")
        print(f"Total Execution Time: {report['total_execution_time']:.2f} seconds")
        
        summary = report['summary']
        print(f"\nSummary:")
        print(f"  Pre-backup Ready: {'YES' if summary['pre_backup_ready'] else 'NO'}")
        print(f"  Backup Integrity: {'OK' if summary['backup_integrity_ok'] else 'ISSUES'}")
        print(f"  Current State: {'HEALTHY' if summary['current_state_healthy'] else 'ISSUES'}")
    
    # Print recommendations
    if 'recommendations' in report and report['recommendations']:
        print(f"\nRecommendations:")
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"  {i}. {rec}")
    
    print("="*80)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Validate backup and restore operations",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Validation modes
    parser.add_argument(
        "--pre-backup",
        action="store_true",
        help="Validate system state before backup"
    )
    parser.add_argument(
        "--validate-backup",
        type=str,
        metavar="PATH",
        help="Validate backup integrity at specified path"
    )
    parser.add_argument(
        "--post-restore",
        action="store_true",
        help="Validate system state after restore"
    )
    parser.add_argument(
        "--full-cycle",
        action="store_true",
        help="Run complete validation cycle"
    )
    
    # Options
    parser.add_argument(
        "--backup-path",
        type=str,
        help="Backup path for full cycle validation"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save report to JSON file"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate arguments
    if not any([args.pre_backup, args.validate_backup, args.post_restore, args.full_cycle]):
        parser.error("Must specify one validation mode")
    
    try:
        # Get configuration
        config = get_database_config()
        
        # Initialize validator
        validator = BackupRestoreValidator(config)
        await validator.initialize()
        
        try:
            report = None
            
            # Run requested validation
            if args.pre_backup:
                report = await validator.validate_pre_backup()
            elif args.validate_backup:
                report = await validator.validate_backup_integrity(args.validate_backup)
            elif args.post_restore:
                report = await validator.validate_post_restore()
            elif args.full_cycle:
                report = await validator.run_full_validation_cycle(args.backup_path)
            
            # Print report
            if report:
                print_validation_report(report)
                
                # Save to file if requested
                if args.output:
                    output_path = Path(args.output)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(output_path, 'w') as f:
                        json.dump(report, f, indent=2, default=str)
                    
                    print(f"\nReport saved to: {output_path}")
                
                # Return appropriate exit code
                if report['validation_type'] == 'pre_backup':
                    return 0 if report['backup_recommended'] else 1
                elif report['validation_type'] == 'backup_integrity':
                    return 0 if report['backup_valid'] else 1
                elif report['validation_type'] == 'post_restore':
                    return 0 if report['restore_successful'] else 1
                elif report['validation_type'] == 'full_cycle':
                    return 0 if report['overall_status'] == 'healthy' else 1
            
            return 0
            
        finally:
            await validator.cleanup()
            
    except KeyboardInterrupt:
        print("\nValidation cancelled by user")
        return 1
    except Exception as e:
        print(f"Validation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))