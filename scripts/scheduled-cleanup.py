#!/usr/bin/env python3
"""
Scheduled Resource Cleanup Service

This service runs automated cleanup tasks on a schedule to maintain
a clean local development environment.
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# Optional import for schedule module
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False
    schedule = None

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import the cleanup script as a module
cleanup_script_path = project_root / "scripts" / "cleanup-local-resources.py"
if cleanup_script_path.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cleanup_local_resources", cleanup_script_path)
    cleanup_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cleanup_module)
    LocalResourceCleaner = cleanup_module.LocalResourceCleaner
else:
    # Fallback for testing
    class LocalResourceCleaner:
        def __init__(self, force=False):
            self.force = force
        def cleanup_log_files(self, days_old=7): return True
        def cleanup_application_files(self): return True
        def cleanup_test_artifacts(self): return True
        def cleanup_docker_images(self): return True
        def cleanup_backup_files(self, days_old=30): return True
        def cleanup_docker_networks(self): return True
        def cleanup_docker_volumes(self): return True
        def get_resource_usage_report(self): return {"status": "mock"}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(project_root / 'logs' / 'scheduled-cleanup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ScheduledCleanupService:
    """Service for running scheduled cleanup tasks."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or self.get_default_config()
        self.cleaner = LocalResourceCleaner(force=True)  # Auto-confirm for scheduled runs
        self.running = False
        self.cleanup_thread = None
        
        # Ensure logs directory exists
        logs_dir = project_root / 'logs'
        logs_dir.mkdir(exist_ok=True)
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for scheduled cleanup."""
        return {
            # Daily cleanup tasks
            'daily_cleanup': {
                'enabled': True,
                'time': '02:00',  # 2 AM
                'tasks': ['logs', 'temp_files', 'test_artifacts']
            },
            
            # Weekly cleanup tasks
            'weekly_cleanup': {
                'enabled': True,
                'day': 'sunday',
                'time': '03:00',  # 3 AM on Sunday
                'tasks': ['docker_images', 'old_backups', 'cache_files']
            },
            
            # Monthly cleanup tasks
            'monthly_cleanup': {
                'enabled': False,  # Disabled by default due to destructive nature
                'day': 1,  # First day of month
                'time': '04:00',  # 4 AM
                'tasks': ['docker_volumes', 'all_backups']
            },
            
            # Cleanup thresholds
            'thresholds': {
                'log_retention_days': 7,
                'backup_retention_days': 30,
                'temp_file_retention_hours': 24,
                'max_disk_usage_gb': 10
            },
            
            # Monitoring
            'monitoring': {
                'enabled': True,
                'report_interval_hours': 24,
                'alert_on_failure': True
            }
        }
    
    def daily_cleanup_task(self):
        """Run daily cleanup tasks."""
        logger.info("Starting daily cleanup task...")
        
        try:
            # Clean up log files
            self.cleaner.cleanup_log_files(
                days_old=self.config['thresholds']['log_retention_days']
            )
            
            # Clean up application files
            self.cleaner.cleanup_application_files()
            
            # Clean up test artifacts
            self.cleaner.cleanup_test_artifacts()
            
            logger.info("Daily cleanup task completed successfully")
            
        except Exception as e:
            logger.error(f"Daily cleanup task failed: {e}")
            if self.config['monitoring']['alert_on_failure']:
                self.send_alert(f"Daily cleanup failed: {e}")
    
    def weekly_cleanup_task(self):
        """Run weekly cleanup tasks."""
        logger.info("Starting weekly cleanup task...")
        
        try:
            # Clean up Docker images
            self.cleaner.cleanup_docker_images()
            
            # Clean up old backups
            self.cleaner.cleanup_backup_files(
                days_old=self.config['thresholds']['backup_retention_days']
            )
            
            # Clean up Docker networks
            self.cleaner.cleanup_docker_networks()
            
            logger.info("Weekly cleanup task completed successfully")
            
        except Exception as e:
            logger.error(f"Weekly cleanup task failed: {e}")
            if self.config['monitoring']['alert_on_failure']:
                self.send_alert(f"Weekly cleanup failed: {e}")
    
    def monthly_cleanup_task(self):
        """Run monthly cleanup tasks (destructive)."""
        logger.info("Starting monthly cleanup task...")
        
        try:
            # This is destructive - only run if explicitly enabled
            if not self.config['monthly_cleanup']['enabled']:
                logger.info("Monthly cleanup is disabled - skipping")
                return
            
            # Clean up Docker volumes (destructive!)
            logger.warning("Running destructive monthly cleanup - this will remove all data!")
            self.cleaner.cleanup_docker_volumes()
            
            logger.info("Monthly cleanup task completed successfully")
            
        except Exception as e:
            logger.error(f"Monthly cleanup task failed: {e}")
            if self.config['monitoring']['alert_on_failure']:
                self.send_alert(f"Monthly cleanup failed: {e}")
    
    def disk_usage_check(self):
        """Check disk usage and clean up if necessary."""
        try:
            # Get project disk usage
            total_size = sum(f.stat().st_size for f in project_root.rglob('*') if f.is_file())
            size_gb = total_size / (1024**3)
            
            max_size = self.config['thresholds']['max_disk_usage_gb']
            
            if size_gb > max_size:
                logger.warning(f"Disk usage ({size_gb:.2f} GB) exceeds threshold ({max_size} GB)")
                
                # Run emergency cleanup
                self.emergency_cleanup()
                
                # Check again
                total_size = sum(f.stat().st_size for f in project_root.rglob('*') if f.is_file())
                new_size_gb = total_size / (1024**3)
                
                logger.info(f"Emergency cleanup reduced disk usage from {size_gb:.2f} GB to {new_size_gb:.2f} GB")
                
                if new_size_gb > max_size:
                    self.send_alert(f"Disk usage still high after cleanup: {new_size_gb:.2f} GB")
            
        except Exception as e:
            logger.error(f"Disk usage check failed: {e}")
    
    def emergency_cleanup(self):
        """Run emergency cleanup when disk usage is high."""
        logger.info("Running emergency cleanup due to high disk usage...")
        
        # Clean up everything except data volumes
        self.cleaner.cleanup_application_files()
        self.cleaner.cleanup_test_artifacts()
        self.cleaner.cleanup_log_files(days_old=1)  # More aggressive
        self.cleaner.cleanup_backup_files(days_old=7)  # More aggressive
        self.cleaner.cleanup_docker_images()
        self.cleaner.cleanup_docker_networks()
    
    def generate_status_report(self):
        """Generate and log status report."""
        logger.info("Generating status report...")
        
        try:
            report = self.cleaner.get_resource_usage_report()
            
            logger.info("=== SCHEDULED CLEANUP STATUS REPORT ===")
            for section, content in report.items():
                logger.info(f"{section.upper()}:")
                for line in content.split('\n')[:5]:  # Limit output
                    if line.strip():
                        logger.info(f"  {line}")
            
        except Exception as e:
            logger.error(f"Failed to generate status report: {e}")
    
    def send_alert(self, message: str):
        """Send alert notification (placeholder for actual implementation)."""
        logger.error(f"ALERT: {message}")
        
        # In a real implementation, this could:
        # - Send email notifications
        # - Post to Slack/Discord
        # - Write to monitoring system
        # - Create system notifications
        
        # For now, just log the alert
        alert_file = project_root / 'logs' / 'cleanup-alerts.log'
        with open(alert_file, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - {message}\n")
    
    def schedule_tasks(self):
        """Schedule all cleanup tasks."""
        if not SCHEDULE_AVAILABLE:
            logger.error("Schedule module not available. Install with: pip install schedule")
            return False
            
        logger.info("Scheduling cleanup tasks...")
        
        # Daily tasks
        if self.config['daily_cleanup']['enabled']:
            schedule.every().day.at(self.config['daily_cleanup']['time']).do(self.daily_cleanup_task)
            logger.info(f"Scheduled daily cleanup at {self.config['daily_cleanup']['time']}")
        
        # Weekly tasks
        if self.config['weekly_cleanup']['enabled']:
            day = self.config['weekly_cleanup']['day']
            time = self.config['weekly_cleanup']['time']
            getattr(schedule.every(), day).at(time).do(self.weekly_cleanup_task)
            logger.info(f"Scheduled weekly cleanup on {day} at {time}")
        
        # Monthly tasks
        if self.config['monthly_cleanup']['enabled']:
            # Note: schedule library doesn't support monthly, so we'll check daily
            schedule.every().day.at(self.config['monthly_cleanup']['time']).do(self.check_monthly_cleanup)
            logger.info(f"Scheduled monthly cleanup check at {self.config['monthly_cleanup']['time']}")
        
        # Monitoring tasks
        if self.config['monitoring']['enabled']:
            # Disk usage check every hour
            schedule.every().hour.do(self.disk_usage_check)
            
            # Status report
            interval = self.config['monitoring']['report_interval_hours']
            schedule.every(interval).hours.do(self.generate_status_report)
            
            logger.info(f"Scheduled monitoring tasks (disk check: hourly, report: every {interval}h)")
        
        return True
    
    def check_monthly_cleanup(self):
        """Check if it's time for monthly cleanup."""
        if datetime.now().day == self.config['monthly_cleanup']['day']:
            self.monthly_cleanup_task()
    
    def start(self):
        """Start the scheduled cleanup service."""
        if not SCHEDULE_AVAILABLE:
            logger.error("Cannot start scheduled service: schedule module not available")
            logger.error("Install with: pip install schedule")
            return False
            
        logger.info("Starting scheduled cleanup service...")
        
        if not self.schedule_tasks():
            return False
            
        self.running = True
        
        # Run initial status report
        self.generate_status_report()
        
        # Start the scheduler thread
        self.cleanup_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.cleanup_thread.start()
        
        logger.info("Scheduled cleanup service started")
        return True
    
    def stop(self):
        """Stop the scheduled cleanup service."""
        logger.info("Stopping scheduled cleanup service...")
        self.running = False
        
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
        
        logger.info("Scheduled cleanup service stopped")
    
    def _run_scheduler(self):
        """Run the scheduler in a separate thread."""
        if not SCHEDULE_AVAILABLE:
            logger.error("Scheduler cannot run: schedule module not available")
            return
            
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Scheduled Resource Cleanup Service")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--test", action="store_true", help="Run test cleanup and exit")
    
    args = parser.parse_args()
    
    # Load configuration if provided
    config = None
    if args.config:
        import json
        with open(args.config) as f:
            config = json.load(f)
    
    service = ScheduledCleanupService(config)
    
    if args.test:
        logger.info("Running test cleanup...")
        service.daily_cleanup_task()
        service.generate_status_report()
        return
    
    try:
        service.start()
        
        if args.daemon:
            # Run as daemon
            while True:
                time.sleep(60)
        else:
            # Interactive mode
            print("Scheduled cleanup service is running. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        service.stop()


if __name__ == "__main__":
    main()