#!/usr/bin/env python3
"""
Local Development Resource Cleanup Automation

This script provides automated cleanup of local development resources including:
- Docker containers, images, volumes, and networks
- Temporary files and logs
- Database data and backups
- Application cache and uploads
"""

import os
import sys
import subprocess
import shutil
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LocalResourceCleaner:
    """Automated cleanup for local development resources."""
    
    def __init__(self, dry_run: bool = False, force: bool = False):
        self.dry_run = dry_run
        self.force = force
        self.project_root = Path(__file__).parent.parent
        self.compose_file = self.project_root / "docker-compose.local.yml"
        
    def run_command(self, command: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run a command with optional dry-run mode."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would execute: {' '.join(command)}")
            return subprocess.CompletedProcess(command, 0, "", "")
        
        try:
            result = subprocess.run(
                command,
                capture_output=capture_output,
                text=True,
                check=False
            )
            if result.returncode != 0 and result.stderr:
                logger.warning(f"Command failed: {' '.join(command)}")
                logger.warning(f"Error: {result.stderr}")
            return result
        except Exception as e:
            logger.error(f"Failed to execute command {' '.join(command)}: {e}")
            return subprocess.CompletedProcess(command, 1, "", str(e))
    
    def cleanup_docker_containers(self) -> bool:
        """Stop and remove all local development containers."""
        logger.info("Cleaning up Docker containers...")
        
        # Stop and remove containers using docker-compose
        if self.compose_file.exists():
            result = self.run_command([
                "docker-compose", "-f", str(self.compose_file), "down", "-v"
            ])
            if result.returncode == 0:
                logger.info("Successfully stopped and removed containers")
            else:
                logger.error("Failed to stop containers with docker-compose")
                return False
        
        # Remove any orphaned containers
        result = self.run_command([
            "docker", "ps", "-a", "--filter", "label=com.docker.compose.project=multimodal-librarian-local",
            "--format", "{{.ID}}"
        ])
        
        if result.stdout.strip():
            container_ids = result.stdout.strip().split('\n')
            logger.info(f"Found {len(container_ids)} orphaned containers")
            
            # Stop containers
            stop_result = self.run_command(["docker", "stop"] + container_ids)
            if stop_result.returncode == 0:
                logger.info("Stopped orphaned containers")
            
            # Remove containers
            rm_result = self.run_command(["docker", "rm"] + container_ids)
            if rm_result.returncode == 0:
                logger.info("Removed orphaned containers")
        
        return True
    
    def cleanup_docker_volumes(self) -> bool:
        """Remove Docker volumes for local development."""
        logger.info("Cleaning up Docker volumes...")
        
        # Get volumes associated with the project
        result = self.run_command([
            "docker", "volume", "ls", "--filter", "label=com.docker.compose.project=multimodal-librarian-local",
            "--format", "{{.Name}}"
        ])
        
        if result.stdout.strip():
            volume_names = result.stdout.strip().split('\n')
            logger.info(f"Found {len(volume_names)} project volumes")
            
            if not self.force:
                response = input(f"Remove {len(volume_names)} volumes? This will delete all database data! (y/N): ")
                if response.lower() != 'y':
                    logger.info("Skipping volume cleanup")
                    return True
            
            # Remove volumes
            rm_result = self.run_command(["docker", "volume", "rm"] + volume_names)
            if rm_result.returncode == 0:
                logger.info("Removed project volumes")
            else:
                logger.error("Failed to remove some volumes")
                return False
        
        # Clean up dangling volumes
        result = self.run_command(["docker", "volume", "prune", "-f"])
        if result.returncode == 0:
            logger.info("Cleaned up dangling volumes")
        
        return True
    
    def cleanup_docker_images(self) -> bool:
        """Remove unused Docker images."""
        logger.info("Cleaning up Docker images...")
        
        # Remove dangling images
        result = self.run_command(["docker", "image", "prune", "-f"])
        if result.returncode == 0:
            logger.info("Removed dangling images")
        
        # Optionally remove all unused images
        if self.force:
            result = self.run_command(["docker", "image", "prune", "-a", "-f"])
            if result.returncode == 0:
                logger.info("Removed all unused images")
        
        return True
    
    def cleanup_docker_networks(self) -> bool:
        """Remove unused Docker networks."""
        logger.info("Cleaning up Docker networks...")
        
        result = self.run_command(["docker", "network", "prune", "-f"])
        if result.returncode == 0:
            logger.info("Removed unused networks")
            return True
        
        return False
    
    def cleanup_application_files(self) -> bool:
        """Clean up application-generated files."""
        logger.info("Cleaning up application files...")
        
        cleanup_paths = [
            self.project_root / "uploads",
            self.project_root / "logs",
            self.project_root / "cache",
            self.project_root / "test_uploads",
            self.project_root / "test_data" / "generated",
            self.project_root / "__pycache__",
            self.project_root / ".pytest_cache",
        ]
        
        for path in cleanup_paths:
            if path.exists():
                if path.is_dir():
                    if not self.dry_run:
                        shutil.rmtree(path)
                    logger.info(f"Removed directory: {path}")
                else:
                    if not self.dry_run:
                        path.unlink()
                    logger.info(f"Removed file: {path}")
        
        # Clean up Python cache files recursively
        for root, dirs, files in os.walk(self.project_root):
            # Remove __pycache__ directories
            if '__pycache__' in dirs:
                pycache_path = Path(root) / '__pycache__'
                if not self.dry_run:
                    shutil.rmtree(pycache_path)
                logger.info(f"Removed __pycache__: {pycache_path}")
                dirs.remove('__pycache__')
            
            # Remove .pyc files
            for file in files:
                if file.endswith('.pyc'):
                    pyc_path = Path(root) / file
                    if not self.dry_run:
                        pyc_path.unlink()
                    logger.info(f"Removed .pyc file: {pyc_path}")
        
        return True
    
    def cleanup_log_files(self, days_old: int = 7) -> bool:
        """Clean up old log files."""
        logger.info(f"Cleaning up log files older than {days_old} days...")
        
        log_directories = [
            self.project_root / "logs",
            self.project_root / "monitoring" / "logs",
            Path("/tmp") / "multimodal-librarian-logs",
        ]
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        for log_dir in log_directories:
            if not log_dir.exists():
                continue
            
            for log_file in log_dir.glob("**/*.log"):
                try:
                    file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if file_mtime < cutoff_date:
                        if not self.dry_run:
                            log_file.unlink()
                        logger.info(f"Removed old log file: {log_file}")
                except Exception as e:
                    logger.warning(f"Failed to process log file {log_file}: {e}")
        
        return True
    
    def cleanup_backup_files(self, days_old: int = 30) -> bool:
        """Clean up old backup files."""
        logger.info(f"Cleaning up backup files older than {days_old} days...")
        
        backup_directories = [
            self.project_root / "backups",
            self.project_root / "database" / "backups",
        ]
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        for backup_dir in backup_directories:
            if not backup_dir.exists():
                continue
            
            for backup_file in backup_dir.glob("**/*"):
                if backup_file.is_file():
                    try:
                        file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                        if file_mtime < cutoff_date:
                            if not self.dry_run:
                                backup_file.unlink()
                            logger.info(f"Removed old backup file: {backup_file}")
                    except Exception as e:
                        logger.warning(f"Failed to process backup file {backup_file}: {e}")
        
        return True
    
    def cleanup_test_artifacts(self) -> bool:
        """Clean up test-generated artifacts."""
        logger.info("Cleaning up test artifacts...")
        
        test_artifacts = [
            self.project_root / "test_exports",
            self.project_root / "test_media",
            self.project_root / ".coverage",
            self.project_root / "htmlcov",
            self.project_root / ".pytest_cache",
            self.project_root / "test-results.xml",
        ]
        
        for artifact in test_artifacts:
            if artifact.exists():
                if artifact.is_dir():
                    if not self.dry_run:
                        shutil.rmtree(artifact)
                    logger.info(f"Removed test directory: {artifact}")
                else:
                    if not self.dry_run:
                        artifact.unlink()
                    logger.info(f"Removed test file: {artifact}")
        
        return True
    
    def get_resource_usage_report(self) -> Dict[str, str]:
        """Generate a report of current resource usage."""
        report = {}
        
        # Docker resource usage
        containers_result = self.run_command(["docker", "ps", "-a", "--format", "table {{.Names}}\t{{.Status}}\t{{.Size}}"])
        report["containers"] = containers_result.stdout if containers_result.returncode == 0 else "Failed to get container info"
        
        volumes_result = self.run_command(["docker", "volume", "ls", "--format", "table {{.Name}}\t{{.Driver}}\t{{.Size}}"])
        report["volumes"] = volumes_result.stdout if volumes_result.returncode == 0 else "Failed to get volume info"
        
        images_result = self.run_command(["docker", "images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"])
        report["images"] = images_result.stdout if images_result.returncode == 0 else "Failed to get image info"
        
        # Disk usage
        if self.project_root.exists():
            try:
                total_size = sum(f.stat().st_size for f in self.project_root.rglob('*') if f.is_file())
                report["project_disk_usage"] = f"{total_size / (1024**3):.2f} GB"
            except Exception as e:
                report["project_disk_usage"] = f"Failed to calculate: {e}"
        
        return report
    
    def run_full_cleanup(self, include_data: bool = False) -> bool:
        """Run complete cleanup process."""
        logger.info("Starting full resource cleanup...")
        
        success = True
        
        # Always clean up containers and networks
        success &= self.cleanup_docker_containers()
        success &= self.cleanup_docker_networks()
        success &= self.cleanup_docker_images()
        
        # Clean up application files
        success &= self.cleanup_application_files()
        success &= self.cleanup_test_artifacts()
        success &= self.cleanup_log_files()
        success &= self.cleanup_backup_files()
        
        # Optionally clean up data volumes
        if include_data:
            success &= self.cleanup_docker_volumes()
        
        if success:
            logger.info("Full cleanup completed successfully")
        else:
            logger.error("Some cleanup operations failed")
        
        return success


def main():
    parser = argparse.ArgumentParser(description="Local Development Resource Cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be cleaned without actually doing it")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--include-data", action="store_true", help="Also clean up database volumes (destructive)")
    parser.add_argument("--report-only", action="store_true", help="Only generate resource usage report")
    parser.add_argument("--containers-only", action="store_true", help="Only clean up containers")
    parser.add_argument("--files-only", action="store_true", help="Only clean up application files")
    parser.add_argument("--logs-days", type=int, default=7, help="Days to keep log files (default: 7)")
    parser.add_argument("--backup-days", type=int, default=30, help="Days to keep backup files (default: 30)")
    
    args = parser.parse_args()
    
    cleaner = LocalResourceCleaner(dry_run=args.dry_run, force=args.force)
    
    if args.report_only:
        logger.info("Generating resource usage report...")
        report = cleaner.get_resource_usage_report()
        
        print("\n" + "="*60)
        print("LOCAL DEVELOPMENT RESOURCE USAGE REPORT")
        print("="*60)
        
        for section, content in report.items():
            print(f"\n{section.upper().replace('_', ' ')}:")
            print("-" * 40)
            print(content)
        
        return
    
    if args.containers_only:
        success = cleaner.cleanup_docker_containers()
        success &= cleaner.cleanup_docker_networks()
        sys.exit(0 if success else 1)
    
    if args.files_only:
        success = cleaner.cleanup_application_files()
        success &= cleaner.cleanup_test_artifacts()
        success &= cleaner.cleanup_log_files(args.logs_days)
        success &= cleaner.cleanup_backup_files(args.backup_days)
        sys.exit(0 if success else 1)
    
    # Run full cleanup
    success = cleaner.run_full_cleanup(include_data=args.include_data)
    
    if not args.dry_run:
        # Generate final report
        print("\n" + "="*60)
        print("CLEANUP COMPLETED - FINAL RESOURCE STATUS")
        print("="*60)
        
        report = cleaner.get_resource_usage_report()
        for section, content in report.items():
            print(f"\n{section.upper().replace('_', ' ')}:")
            print("-" * 40)
            print(content)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()