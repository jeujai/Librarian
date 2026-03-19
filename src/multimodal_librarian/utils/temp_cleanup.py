"""
Temporary File Cleanup Utility

Provides proactive cleanup of temporary files created by the Multimodal Librarian
to prevent disk space issues that can destabilize the application.

Key directories managed:
- /tmp/multimodal_librarian_model_transfer - Model transfer files
- /tmp/model_compression_cache - Model compression cache
- /tmp/pycache - Python bytecode cache
- /tmp/multimodal_librarian_alerts - Alert logs
- /tmp/multimodal_librarian_errors - Error logs
"""

import asyncio
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Directories to clean up with their max age in hours
TEMP_DIRECTORIES: Dict[str, int] = {
    "multimodal_librarian_model_transfer": 24,  # Model transfer files - 24 hours
    "model_compression_cache": 72,  # Compression cache - 3 days
    "pycache": 168,  # Python cache - 1 week
    "multimodal_librarian_alerts": 168,  # Alert logs - 1 week
    "multimodal_librarian_errors": 168,  # Error logs - 1 week
}

# File patterns to clean up (with max age in hours)
TEMP_FILE_PATTERNS: Dict[str, int] = {
    "*.pkl": 24,  # Pickle files from model transfer
    "*_config.json": 24,  # Config files from model transfer
    "*.pyc": 168,  # Compiled Python files
}


class TempCleanupService:
    """Service for managing temporary file cleanup."""
    
    def __init__(
        self,
        temp_base: str = "/tmp",
        cleanup_interval_seconds: int = 3600,  # 1 hour
        max_temp_size_mb: int = 500,  # Trigger cleanup if temp exceeds this
    ):
        self.temp_base = Path(temp_base)
        self.cleanup_interval = cleanup_interval_seconds
        self.max_temp_size_mb = max_temp_size_mb
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._last_cleanup: Optional[datetime] = None
        self._cleanup_stats: Dict[str, int] = {
            "total_cleanups": 0,
            "files_removed": 0,
            "bytes_freed": 0,
            "errors": 0,
        }
    
    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is not None:
            logger.warning("Temp cleanup service already running")
            return
        
        logger.info("Starting temp cleanup service")
        
        # Run initial cleanup
        await self.cleanup_now()
        
        # Start background task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"Temp cleanup service started (interval: {self.cleanup_interval}s)")
    
    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task is None:
            return
        
        logger.info("Stopping temp cleanup service")
        self._shutdown_event.set()
        self._cleanup_task.cancel()
        
        try:
            await self._cleanup_task
        except asyncio.CancelledError:
            pass
        
        self._cleanup_task = None
        logger.info("Temp cleanup service stopped")
    
    async def _cleanup_loop(self) -> None:
        """Background loop for periodic cleanup."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                if self._shutdown_event.is_set():
                    break
                
                # Check if cleanup is needed
                if self._should_cleanup():
                    await self.cleanup_now()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in temp cleanup loop: {e}")
                self._cleanup_stats["errors"] += 1
    
    def _should_cleanup(self) -> bool:
        """Check if cleanup should run based on size or time."""
        # Always cleanup if temp is too large
        try:
            total_size = self._get_temp_size_mb()
            if total_size > self.max_temp_size_mb:
                logger.info(f"Temp size ({total_size:.1f} MB) exceeds threshold ({self.max_temp_size_mb} MB)")
                return True
        except Exception:
            pass
        
        return True  # Always run on schedule
    
    def _get_temp_size_mb(self) -> float:
        """Get total size of managed temp directories in MB."""
        total_bytes = 0
        
        for dir_name in TEMP_DIRECTORIES:
            dir_path = self.temp_base / dir_name
            if dir_path.exists():
                try:
                    for item in dir_path.rglob("*"):
                        if item.is_file():
                            total_bytes += item.stat().st_size
                except Exception:
                    pass
        
        return total_bytes / (1024 * 1024)
    
    async def cleanup_now(self) -> Dict[str, int]:
        """Run cleanup immediately and return stats."""
        logger.info("Running temp cleanup...")
        start_time = time.time()
        
        files_removed = 0
        bytes_freed = 0
        errors = 0
        
        # Clean up managed directories
        for dir_name, max_age_hours in TEMP_DIRECTORIES.items():
            dir_path = self.temp_base / dir_name
            
            if not dir_path.exists():
                continue
            
            try:
                result = await asyncio.to_thread(
                    self._cleanup_directory,
                    dir_path,
                    max_age_hours
                )
                files_removed += result["files"]
                bytes_freed += result["bytes"]
            except Exception as e:
                logger.warning(f"Error cleaning {dir_path}: {e}")
                errors += 1
        
        # Update stats
        self._cleanup_stats["total_cleanups"] += 1
        self._cleanup_stats["files_removed"] += files_removed
        self._cleanup_stats["bytes_freed"] += bytes_freed
        self._cleanup_stats["errors"] += errors
        self._last_cleanup = datetime.now()
        
        duration = time.time() - start_time
        logger.info(
            f"Temp cleanup completed in {duration:.2f}s: "
            f"{files_removed} files removed, {bytes_freed / 1024 / 1024:.1f} MB freed"
        )
        
        return {
            "files_removed": files_removed,
            "bytes_freed": bytes_freed,
            "errors": errors,
            "duration_seconds": duration,
        }
    
    def _cleanup_directory(self, dir_path: Path, max_age_hours: int) -> Dict[str, int]:
        """Clean up old files in a directory (runs in thread)."""
        files_removed = 0
        bytes_freed = 0
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cutoff_timestamp = cutoff_time.timestamp()
        
        try:
            for item in dir_path.iterdir():
                try:
                    if item.is_file():
                        # Check file age
                        mtime = item.stat().st_mtime
                        if mtime < cutoff_timestamp:
                            size = item.stat().st_size
                            item.unlink()
                            files_removed += 1
                            bytes_freed += size
                    elif item.is_dir():
                        # Recursively clean subdirectories
                        result = self._cleanup_directory(item, max_age_hours)
                        files_removed += result["files"]
                        bytes_freed += result["bytes"]
                        
                        # Remove empty directories
                        if not any(item.iterdir()):
                            item.rmdir()
                except Exception as e:
                    logger.debug(f"Could not clean {item}: {e}")
        except Exception as e:
            logger.warning(f"Error iterating {dir_path}: {e}")
        
        return {"files": files_removed, "bytes": bytes_freed}
    
    def get_stats(self) -> Dict:
        """Get cleanup statistics."""
        return {
            **self._cleanup_stats,
            "last_cleanup": self._last_cleanup.isoformat() if self._last_cleanup else None,
            "current_temp_size_mb": self._get_temp_size_mb(),
            "max_temp_size_mb": self.max_temp_size_mb,
            "cleanup_interval_seconds": self.cleanup_interval,
        }


# Global instance
_cleanup_service: Optional[TempCleanupService] = None


def get_temp_cleanup_service() -> TempCleanupService:
    """Get or create the temp cleanup service singleton."""
    global _cleanup_service
    if _cleanup_service is None:
        _cleanup_service = TempCleanupService()
    return _cleanup_service


async def start_temp_cleanup() -> TempCleanupService:
    """Start the temp cleanup service."""
    service = get_temp_cleanup_service()
    await service.start()
    return service


async def stop_temp_cleanup() -> None:
    """Stop the temp cleanup service."""
    global _cleanup_service
    if _cleanup_service is not None:
        await _cleanup_service.stop()


async def cleanup_temp_now() -> Dict[str, int]:
    """Run temp cleanup immediately."""
    service = get_temp_cleanup_service()
    return await service.cleanup_now()
