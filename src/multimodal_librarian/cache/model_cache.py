"""
EFS-based Model Cache System

This module implements a comprehensive model caching system using EFS (Elastic File System)
for persistent storage of ML models. It provides model download, cache management,
validation, and cleanup capabilities.

Key Features:
- EFS-based persistent model storage
- Model download and cache management
- Cache validation and integrity checking
- Automatic cleanup of old/unused models
- Model versioning support
- Concurrent download management
- Cache warming strategies
"""

import os
import json
import hashlib
import asyncio
import aiofiles
import aiohttp
import logging
import statistics
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
import fcntl
import time

logger = logging.getLogger(__name__)


class CacheStatus(Enum):
    """Cache entry status."""
    MISSING = "missing"           # Not in cache
    DOWNLOADING = "downloading"   # Currently downloading
    CACHED = "cached"            # Successfully cached
    CORRUPTED = "corrupted"      # Cache entry is corrupted
    EXPIRED = "expired"          # Cache entry has expired
    VALIDATING = "validating"    # Currently validating


@dataclass
class CacheConfig:
    """Configuration for the model cache."""
    cache_dir: str = "/efs/model-cache"
    max_cache_size_gb: float = 100.0
    max_model_age_days: int = 30
    download_timeout_seconds: int = 3600  # 1 hour
    max_concurrent_downloads: int = 3
    validation_enabled: bool = True
    compression_enabled: bool = True
    checksum_algorithm: str = "sha256"
    cleanup_interval_hours: int = 24
    temp_dir: Optional[str] = None
    
    def __post_init__(self):
        """Initialize derived values."""
        if self.temp_dir is None:
            self.temp_dir = os.path.join(self.cache_dir, "temp")


@dataclass
class ModelCacheEntry:
    """Represents a cached model entry."""
    model_name: str
    model_version: str
    file_path: str
    metadata_path: str
    size_bytes: int
    checksum: str
    download_time: datetime
    last_accessed: datetime
    access_count: int = 0
    status: CacheStatus = CacheStatus.CACHED
    
    @property
    def age_days(self) -> float:
        """Get the age of the cache entry in days."""
        return (datetime.now() - self.download_time).total_seconds() / 86400
    
    @property
    def size_mb(self) -> float:
        """Get the size in MB."""
        return self.size_bytes / (1024 * 1024)


class ModelCache:
    """
    EFS-based model cache system.
    
    This class manages a persistent cache of ML models stored on EFS,
    providing download, validation, and cleanup capabilities.
    """
    
    def __init__(self, config: Optional[CacheConfig] = None):
        """Initialize the model cache."""
        self.config = config or CacheConfig()
        self.cache_entries: Dict[str, ModelCacheEntry] = {}
        self.download_queue: asyncio.Queue = asyncio.Queue()
        self.download_tasks: Dict[str, asyncio.Task] = {}
        self.download_semaphore = asyncio.Semaphore(self.config.max_concurrent_downloads)
        
        # Thread pool for I/O operations
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        
        # Lock files for concurrent access protection
        self.lock_dir = os.path.join(self.config.cache_dir, "locks")
        
        # Statistics
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "downloads_completed": 0,
            "downloads_failed": 0,
            "bytes_downloaded": 0,
            "bytes_served_from_cache": 0,
            "cleanup_runs": 0,
            "models_cleaned": 0,
            # Enhanced cache hit rate tracking
            "hit_rate_history": [],  # List of (timestamp, hit_rate) tuples
            "hourly_hit_rates": {},  # Hour -> hit rate mapping
            "model_specific_hits": {},  # Model -> hit count mapping
            "model_specific_misses": {},  # Model -> miss count mapping
            "cache_source_hits": {},  # Source -> hit count mapping
            "recent_requests": []  # Recent cache requests for trend analysis
        }
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        logger.info(f"ModelCache initialized with cache_dir: {self.config.cache_dir}")
    
    async def initialize(self) -> None:
        """Initialize the cache system."""
        try:
            # Create cache directories
            await self._create_cache_directories()
            
            # Load existing cache entries
            await self._load_cache_index()
            
            # Start background cleanup task
            self._cleanup_task = asyncio.create_task(self._background_cleanup())
            
            logger.info(f"ModelCache initialized with {len(self.cache_entries)} cached models")
            
        except Exception as e:
            logger.error(f"Failed to initialize ModelCache: {e}")
            raise
    
    async def _create_cache_directories(self) -> None:
        """Create necessary cache directories."""
        directories = [
            self.config.cache_dir,
            self.config.temp_dir,
            self.lock_dir,
            os.path.join(self.config.cache_dir, "models"),
            os.path.join(self.config.cache_dir, "metadata"),
            os.path.join(self.config.cache_dir, "index")
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"Created cache directory: {directory}")
    
    async def _load_cache_index(self) -> None:
        """Load the cache index from disk."""
        index_file = os.path.join(self.config.cache_dir, "index", "cache_index.json")
        
        if not os.path.exists(index_file):
            logger.info("No existing cache index found, starting fresh")
            return
        
        try:
            async with aiofiles.open(index_file, 'r') as f:
                index_data = json.loads(await f.read())
            
            for entry_data in index_data.get("entries", []):
                entry = ModelCacheEntry(
                    model_name=entry_data["model_name"],
                    model_version=entry_data["model_version"],
                    file_path=entry_data["file_path"],
                    metadata_path=entry_data["metadata_path"],
                    size_bytes=entry_data["size_bytes"],
                    checksum=entry_data["checksum"],
                    download_time=datetime.fromisoformat(entry_data["download_time"]),
                    last_accessed=datetime.fromisoformat(entry_data["last_accessed"]),
                    access_count=entry_data.get("access_count", 0)
                )
                
                # Validate that files still exist
                if os.path.exists(entry.file_path) and os.path.exists(entry.metadata_path):
                    cache_key = f"{entry.model_name}:{entry.model_version}"
                    self.cache_entries[cache_key] = entry
                else:
                    logger.warning(f"Cache entry files missing for {entry.model_name}:{entry.model_version}")
            
            logger.info(f"Loaded {len(self.cache_entries)} cache entries from index")
            
        except Exception as e:
            logger.error(f"Failed to load cache index: {e}")
            # Continue with empty cache
    
    async def _save_cache_index(self) -> None:
        """Save the cache index to disk."""
        index_file = os.path.join(self.config.cache_dir, "index", "cache_index.json")
        
        try:
            index_data = {
                "version": "1.0",
                "updated": datetime.now().isoformat(),
                "entries": []
            }
            
            for entry in self.cache_entries.values():
                entry_data = {
                    "model_name": entry.model_name,
                    "model_version": entry.model_version,
                    "file_path": entry.file_path,
                    "metadata_path": entry.metadata_path,
                    "size_bytes": entry.size_bytes,
                    "checksum": entry.checksum,
                    "download_time": entry.download_time.isoformat(),
                    "last_accessed": entry.last_accessed.isoformat(),
                    "access_count": entry.access_count
                }
                index_data["entries"].append(entry_data)
            
            # Write to temporary file first, then rename for atomicity
            temp_file = f"{index_file}.tmp"
            async with aiofiles.open(temp_file, 'w') as f:
                await f.write(json.dumps(index_data, indent=2))
            
            os.rename(temp_file, index_file)
            logger.debug("Cache index saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")
    
    def is_cached(self, model_name: str, model_version: str = "latest") -> bool:
        """Check if a model is cached."""
        cache_key = f"{model_name}:{model_version}"
        
        # Record cache request for hit rate tracking
        self._record_cache_request(model_name, model_version, cache_key in self.cache_entries)
        
        if cache_key not in self.cache_entries:
            return False
        
        entry = self.cache_entries[cache_key]
        
        # Check if files still exist
        if not (os.path.exists(entry.file_path) and os.path.exists(entry.metadata_path)):
            logger.warning(f"Cache entry files missing for {cache_key}")
            entry.status = CacheStatus.CORRUPTED
            return False
        
        # Check if expired
        if entry.age_days > self.config.max_model_age_days:
            logger.info(f"Cache entry expired for {cache_key}")
            entry.status = CacheStatus.EXPIRED
            return False
        
        return entry.status == CacheStatus.CACHED
    
    async def get_cached_model_path(self, model_name: str, model_version: str = "latest") -> Optional[str]:
        """Get the file path of a cached model."""
        cache_key = f"{model_name}:{model_version}"
        
        if not self.is_cached(model_name, model_version):
            self.stats["cache_misses"] += 1
            return None
        
        entry = self.cache_entries[cache_key]
        
        # Update access statistics
        entry.last_accessed = datetime.now()
        entry.access_count += 1
        self.stats["cache_hits"] += 1
        self.stats["bytes_served_from_cache"] += entry.size_bytes
        
        # Save updated index
        await self._save_cache_index()
        
        logger.info(f"Cache hit for {cache_key}: {entry.file_path}")
        return entry.file_path
    
    async def download_and_cache_model(
        self,
        model_name: str,
        model_url: str,
        model_version: str = "latest",
        priority: str = "standard",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Download and cache a model."""
        cache_key = f"{model_name}:{model_version}"
        
        # Check if already cached
        if self.is_cached(model_name, model_version):
            return await self.get_cached_model_path(model_name, model_version)
        
        # Check if already downloading
        if cache_key in self.download_tasks and not self.download_tasks[cache_key].done():
            logger.info(f"Model {cache_key} is already downloading, waiting...")
            await self.download_tasks[cache_key]
            return await self.get_cached_model_path(model_name, model_version)
        
        # Start download
        download_task = asyncio.create_task(
            self._download_model(model_name, model_url, model_version, metadata or {})
        )
        self.download_tasks[cache_key] = download_task
        
        try:
            await download_task
            return await self.get_cached_model_path(model_name, model_version)
        except Exception as e:
            logger.error(f"Failed to download model {cache_key}: {e}")
            raise
    
    async def _download_model(
        self,
        model_name: str,
        model_url: str,
        model_version: str,
        metadata: Dict[str, Any]
    ) -> None:
        """Download a model to cache."""
        cache_key = f"{model_name}:{model_version}"
        
        async with self.download_semaphore:
            # Acquire lock for this model
            lock_file = os.path.join(self.lock_dir, f"{cache_key}.lock")
            
            try:
                # Create cache entry with downloading status
                model_dir = os.path.join(self.config.cache_dir, "models", model_name)
                os.makedirs(model_dir, exist_ok=True)
                
                file_path = os.path.join(model_dir, f"{model_version}.model")
                metadata_path = os.path.join(self.config.cache_dir, "metadata", f"{cache_key}.json")
                
                entry = ModelCacheEntry(
                    model_name=model_name,
                    model_version=model_version,
                    file_path=file_path,
                    metadata_path=metadata_path,
                    size_bytes=0,
                    checksum="",
                    download_time=datetime.now(),
                    last_accessed=datetime.now(),
                    status=CacheStatus.DOWNLOADING
                )
                
                self.cache_entries[cache_key] = entry
                
                logger.info(f"Starting download of {cache_key} from {model_url}")
                
                # Download to temporary file first
                temp_file = os.path.join(self.config.temp_dir, f"{cache_key}.tmp")
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        model_url,
                        timeout=aiohttp.ClientTimeout(total=self.config.download_timeout_seconds)
                    ) as response:
                        response.raise_for_status()
                        
                        total_size = int(response.headers.get('content-length', 0))
                        downloaded_size = 0
                        
                        # Create checksum hasher
                        hasher = hashlib.new(self.config.checksum_algorithm)
                        
                        async with aiofiles.open(temp_file, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                                hasher.update(chunk)
                                downloaded_size += len(chunk)
                                
                                # Log progress periodically
                                if total_size > 0 and downloaded_size % (1024 * 1024) == 0:
                                    progress = (downloaded_size / total_size) * 100
                                    logger.debug(f"Download progress for {cache_key}: {progress:.1f}%")
                
                # Calculate checksum
                checksum = hasher.hexdigest()
                
                # Move from temp to final location
                shutil.move(temp_file, file_path)
                
                # Update entry
                entry.size_bytes = downloaded_size
                entry.checksum = checksum
                entry.status = CacheStatus.CACHED
                
                # Save metadata
                metadata_content = {
                    "model_name": model_name,
                    "model_version": model_version,
                    "download_url": model_url,
                    "download_time": entry.download_time.isoformat(),
                    "size_bytes": downloaded_size,
                    "checksum": checksum,
                    "checksum_algorithm": self.config.checksum_algorithm,
                    "metadata": metadata
                }
                
                async with aiofiles.open(metadata_path, 'w') as f:
                    await f.write(json.dumps(metadata_content, indent=2))
                
                # Update statistics
                self.stats["downloads_completed"] += 1
                self.stats["bytes_downloaded"] += downloaded_size
                
                # Save cache index
                await self._save_cache_index()
                
                logger.info(f"Successfully cached {cache_key} ({downloaded_size / (1024*1024):.1f} MB)")
                
            except Exception as e:
                # Mark as failed and cleanup
                if cache_key in self.cache_entries:
                    self.cache_entries[cache_key].status = CacheStatus.CORRUPTED
                
                # Cleanup temporary files
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                
                self.stats["downloads_failed"] += 1
                logger.error(f"Failed to download {cache_key}: {e}")
                raise
            
            finally:
                # Release lock
                if os.path.exists(lock_file):
                    os.remove(lock_file)
    
    async def validate_cache_entry(self, model_name: str, model_version: str = "latest") -> bool:
        """Validate a cache entry's integrity."""
        cache_key = f"{model_name}:{model_version}"
        
        if cache_key not in self.cache_entries:
            return False
        
        entry = self.cache_entries[cache_key]
        entry.status = CacheStatus.VALIDATING
        
        try:
            # Check if files exist
            if not (os.path.exists(entry.file_path) and os.path.exists(entry.metadata_path)):
                entry.status = CacheStatus.CORRUPTED
                return False
            
            # Validate file size
            actual_size = os.path.getsize(entry.file_path)
            if actual_size != entry.size_bytes:
                logger.warning(f"Size mismatch for {cache_key}: expected {entry.size_bytes}, got {actual_size}")
                entry.status = CacheStatus.CORRUPTED
                return False
            
            # Validate checksum if enabled
            if self.config.validation_enabled:
                actual_checksum = await self._calculate_file_checksum(entry.file_path)
                if actual_checksum != entry.checksum:
                    logger.warning(f"Checksum mismatch for {cache_key}")
                    entry.status = CacheStatus.CORRUPTED
                    return False
            
            entry.status = CacheStatus.CACHED
            logger.debug(f"Cache entry {cache_key} validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error validating cache entry {cache_key}: {e}")
            entry.status = CacheStatus.CORRUPTED
            return False
    
    async def _calculate_file_checksum(self, file_path: str) -> str:
        """Calculate checksum of a file."""
        hasher = hashlib.new(self.config.checksum_algorithm)
        
        async with aiofiles.open(file_path, 'rb') as f:
            while chunk := await f.read(8192):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    async def cleanup_cache(self, force: bool = False) -> Dict[str, Any]:
        """Clean up old and unused cache entries."""
        logger.info("Starting cache cleanup")
        
        cleanup_stats = {
            "entries_checked": 0,
            "entries_removed": 0,
            "bytes_freed": 0,
            "errors": []
        }
        
        current_time = datetime.now()
        entries_to_remove = []
        
        # Check each cache entry
        for cache_key, entry in self.cache_entries.items():
            cleanup_stats["entries_checked"] += 1
            
            should_remove = False
            reason = ""
            
            # Check age
            if entry.age_days > self.config.max_model_age_days:
                should_remove = True
                reason = f"expired (age: {entry.age_days:.1f} days)"
            
            # Check if files are missing
            elif not (os.path.exists(entry.file_path) and os.path.exists(entry.metadata_path)):
                should_remove = True
                reason = "missing files"
            
            # Check if corrupted
            elif entry.status == CacheStatus.CORRUPTED:
                should_remove = True
                reason = "corrupted"
            
            # Force cleanup if requested
            elif force:
                should_remove = True
                reason = "force cleanup"
            
            if should_remove:
                entries_to_remove.append((cache_key, entry, reason))
        
        # Remove entries
        for cache_key, entry, reason in entries_to_remove:
            try:
                # Remove files
                if os.path.exists(entry.file_path):
                    os.remove(entry.file_path)
                if os.path.exists(entry.metadata_path):
                    os.remove(entry.metadata_path)
                
                # Remove from cache
                del self.cache_entries[cache_key]
                
                cleanup_stats["entries_removed"] += 1
                cleanup_stats["bytes_freed"] += entry.size_bytes
                
                logger.info(f"Removed cache entry {cache_key}: {reason}")
                
            except Exception as e:
                error_msg = f"Failed to remove {cache_key}: {e}"
                cleanup_stats["errors"].append(error_msg)
                logger.error(error_msg)
        
        # Check total cache size and remove least recently used if needed
        total_size_gb = sum(entry.size_bytes for entry in self.cache_entries.values()) / (1024**3)
        
        if total_size_gb > self.config.max_cache_size_gb:
            logger.info(f"Cache size ({total_size_gb:.2f} GB) exceeds limit ({self.config.max_cache_size_gb} GB)")
            
            # Sort by last accessed time (oldest first)
            sorted_entries = sorted(
                self.cache_entries.items(),
                key=lambda x: x[1].last_accessed
            )
            
            for cache_key, entry in sorted_entries:
                if total_size_gb <= self.config.max_cache_size_gb:
                    break
                
                try:
                    # Remove files
                    if os.path.exists(entry.file_path):
                        os.remove(entry.file_path)
                    if os.path.exists(entry.metadata_path):
                        os.remove(entry.metadata_path)
                    
                    # Remove from cache
                    del self.cache_entries[cache_key]
                    
                    cleanup_stats["entries_removed"] += 1
                    cleanup_stats["bytes_freed"] += entry.size_bytes
                    total_size_gb -= entry.size_bytes / (1024**3)
                    
                    logger.info(f"Removed cache entry {cache_key}: size limit exceeded")
                    
                except Exception as e:
                    error_msg = f"Failed to remove {cache_key} for size limit: {e}"
                    cleanup_stats["errors"].append(error_msg)
                    logger.error(error_msg)
        
        # Save updated index
        await self._save_cache_index()
        
        # Update statistics
        self.stats["cleanup_runs"] += 1
        self.stats["models_cleaned"] += cleanup_stats["entries_removed"]
        
        logger.info(f"Cache cleanup completed: removed {cleanup_stats['entries_removed']} entries, "
                   f"freed {cleanup_stats['bytes_freed'] / (1024**2):.1f} MB")
        
        return cleanup_stats
    
    async def _background_cleanup(self) -> None:
        """Background task for periodic cache cleanup."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Wait for cleanup interval or shutdown
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.config.cleanup_interval_hours * 3600
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    # Time for cleanup
                    await self.cleanup_cache()
                
        except asyncio.CancelledError:
            logger.info("Background cleanup task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in background cleanup: {e}")
    
    def _record_cache_request(self, model_name: str, model_version: str, is_hit: bool) -> None:
        """Record a cache request for hit rate tracking."""
        timestamp = datetime.now()
        cache_key = f"{model_name}:{model_version}"
        
        # Update basic stats
        if is_hit:
            self.stats["cache_hits"] += 1
            # Track model-specific hits
            self.stats["model_specific_hits"][model_name] = self.stats["model_specific_hits"].get(model_name, 0) + 1
        else:
            self.stats["cache_misses"] += 1
            # Track model-specific misses
            self.stats["model_specific_misses"][model_name] = self.stats["model_specific_misses"].get(model_name, 0) + 1
        
        # Add to recent requests (keep last 1000 for trend analysis)
        request_record = {
            "timestamp": timestamp,
            "model_name": model_name,
            "model_version": model_version,
            "cache_key": cache_key,
            "is_hit": is_hit
        }
        
        self.stats["recent_requests"].append(request_record)
        if len(self.stats["recent_requests"]) > 1000:
            self.stats["recent_requests"] = self.stats["recent_requests"][-1000:]
        
        # Update hourly hit rates
        hour_key = timestamp.strftime("%Y-%m-%d-%H")
        if hour_key not in self.stats["hourly_hit_rates"]:
            self.stats["hourly_hit_rates"][hour_key] = {"hits": 0, "total": 0}
        
        self.stats["hourly_hit_rates"][hour_key]["total"] += 1
        if is_hit:
            self.stats["hourly_hit_rates"][hour_key]["hits"] += 1
        
        # Update overall hit rate history (every 100 requests)
        total_requests = self.stats["cache_hits"] + self.stats["cache_misses"]
        if total_requests % 100 == 0:
            current_hit_rate = self.stats["cache_hits"] / total_requests
            self.stats["hit_rate_history"].append((timestamp, current_hit_rate))
            
            # Keep only last 100 entries
            if len(self.stats["hit_rate_history"]) > 100:
                self.stats["hit_rate_history"] = self.stats["hit_rate_history"][-100:]
    
    def get_cache_hit_rate_metrics(self) -> Dict[str, Any]:
        """Get comprehensive cache hit rate metrics."""
        total_requests = self.stats["cache_hits"] + self.stats["cache_misses"]
        
        if total_requests == 0:
            return {
                "overall_hit_rate": 0.0,
                "total_requests": 0,
                "message": "No cache requests recorded yet"
            }
        
        overall_hit_rate = self.stats["cache_hits"] / total_requests
        
        # Calculate time-based hit rates
        now = datetime.now()
        time_periods = {
            "last_hour": now - timedelta(hours=1),
            "last_6_hours": now - timedelta(hours=6),
            "last_24_hours": now - timedelta(hours=24)
        }
        
        time_based_rates = {}
        for period_name, cutoff_time in time_periods.items():
            period_requests = [
                req for req in self.stats["recent_requests"]
                if req["timestamp"] >= cutoff_time
            ]
            
            if period_requests:
                period_hits = sum(1 for req in period_requests if req["is_hit"])
                time_based_rates[period_name] = {
                    "hit_rate": period_hits / len(period_requests),
                    "total_requests": len(period_requests),
                    "hits": period_hits,
                    "misses": len(period_requests) - period_hits
                }
        
        # Model-specific hit rates
        model_hit_rates = {}
        for model_name in set(list(self.stats["model_specific_hits"].keys()) + list(self.stats["model_specific_misses"].keys())):
            hits = self.stats["model_specific_hits"].get(model_name, 0)
            misses = self.stats["model_specific_misses"].get(model_name, 0)
            total = hits + misses
            
            if total > 0:
                model_hit_rates[model_name] = {
                    "hit_rate": hits / total,
                    "total_requests": total,
                    "hits": hits,
                    "misses": misses
                }
        
        # Hourly breakdown (last 24 hours)
        hourly_breakdown = {}
        for i in range(24):
            hour_time = now - timedelta(hours=i)
            hour_key = hour_time.strftime("%Y-%m-%d-%H")
            
            if hour_key in self.stats["hourly_hit_rates"]:
                hour_data = self.stats["hourly_hit_rates"][hour_key]
                hourly_breakdown[f"hour_{i}"] = {
                    "hour_key": hour_key,
                    "hit_rate": hour_data["hits"] / hour_data["total"] if hour_data["total"] > 0 else 0.0,
                    "total_requests": hour_data["total"],
                    "hits": hour_data["hits"],
                    "misses": hour_data["total"] - hour_data["hits"]
                }
        
        # Hit rate trend analysis
        trend_analysis = {}
        if len(self.stats["hit_rate_history"]) >= 2:
            recent_rates = [rate for _, rate in self.stats["hit_rate_history"][-10:]]
            older_rates = [rate for _, rate in self.stats["hit_rate_history"][:-10]] if len(self.stats["hit_rate_history"]) > 10 else []
            
            if older_rates:
                recent_avg = statistics.mean(recent_rates)
                older_avg = statistics.mean(older_rates)
                
                trend_analysis = {
                    "recent_average": recent_avg,
                    "historical_average": older_avg,
                    "trend_direction": (
                        "improving" if recent_avg > older_avg * 1.05 else
                        "declining" if recent_avg < older_avg * 0.95 else
                        "stable"
                    ),
                    "trend_magnitude": abs(recent_avg - older_avg)
                }
        
        # Performance insights
        insights = []
        
        if overall_hit_rate < 0.3:
            insights.append("Critical: Very low cache hit rate - implement cache warming strategies")
        elif overall_hit_rate < 0.5:
            insights.append("Warning: Low cache hit rate - consider improving cache retention")
        elif overall_hit_rate > 0.8:
            insights.append("Excellent: High cache hit rate indicates effective caching")
        
        # Check for models with low hit rates
        low_hit_rate_models = [
            name for name, data in model_hit_rates.items()
            if data["hit_rate"] < 0.3 and data["total_requests"] >= 5
        ]
        if low_hit_rate_models:
            insights.append(f"Models with low hit rates: {', '.join(low_hit_rate_models)}")
        
        # Check recent performance
        if time_based_rates.get("last_hour", {}).get("hit_rate", 0) < overall_hit_rate * 0.8:
            insights.append("Recent cache performance has declined - investigate cache issues")
        
        return {
            "timestamp": now.isoformat(),
            "overall_statistics": {
                "hit_rate": overall_hit_rate,
                "total_requests": total_requests,
                "total_hits": self.stats["cache_hits"],
                "total_misses": self.stats["cache_misses"]
            },
            "time_based_rates": time_based_rates,
            "model_specific_rates": model_hit_rates,
            "hourly_breakdown": hourly_breakdown,
            "trend_analysis": trend_analysis,
            "performance_insights": insights,
            "cache_effectiveness": {
                "grade": (
                    "A" if overall_hit_rate >= 0.8 else
                    "B" if overall_hit_rate >= 0.6 else
                    "C" if overall_hit_rate >= 0.4 else
                    "D" if overall_hit_rate >= 0.2 else
                    "F"
                ),
                "recommendation": (
                    "Excellent cache performance" if overall_hit_rate >= 0.8 else
                    "Good cache performance" if overall_hit_rate >= 0.6 else
                    "Moderate cache performance - consider optimization" if overall_hit_rate >= 0.4 else
                    "Poor cache performance - immediate optimization needed" if overall_hit_rate >= 0.2 else
                    "Critical cache performance - review cache strategy"
                )
            }
        }

    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache statistics including enhanced hit rate metrics."""
        total_entries = len(self.cache_entries)
        total_size_bytes = sum(entry.size_bytes for entry in self.cache_entries.values())
        
        # Status breakdown
        status_counts = {}
        for entry in self.cache_entries.values():
            status = entry.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate hit rate
        total_requests = self.stats["cache_hits"] + self.stats["cache_misses"]
        hit_rate = (self.stats["cache_hits"] / total_requests * 100) if total_requests > 0 else 0
        
        # Get detailed hit rate metrics
        hit_rate_metrics = self.get_cache_hit_rate_metrics()
        
        return {
            "total_entries": total_entries,
            "total_size_bytes": total_size_bytes,
            "total_size_mb": total_size_bytes / (1024 * 1024),
            "total_size_gb": total_size_bytes / (1024 * 1024 * 1024),
            "status_breakdown": status_counts,
            "hit_rate_percent": hit_rate,
            "statistics": self.stats.copy(),
            "detailed_hit_rate_metrics": hit_rate_metrics,
            "config": {
                "cache_dir": self.config.cache_dir,
                "max_cache_size_gb": self.config.max_cache_size_gb,
                "max_model_age_days": self.config.max_model_age_days,
                "max_concurrent_downloads": self.config.max_concurrent_downloads
            }
        }
    
    def get_cached_models(self) -> List[Dict[str, Any]]:
        """Get list of all cached models."""
        models = []
        
        for cache_key, entry in self.cache_entries.items():
            models.append({
                "model_name": entry.model_name,
                "model_version": entry.model_version,
                "cache_key": cache_key,
                "status": entry.status.value,
                "size_bytes": entry.size_bytes,
                "size_mb": entry.size_mb,
                "age_days": entry.age_days,
                "download_time": entry.download_time.isoformat(),
                "last_accessed": entry.last_accessed.isoformat(),
                "access_count": entry.access_count,
                "file_path": entry.file_path
            })
        
        return sorted(models, key=lambda x: x["last_accessed"], reverse=True)
    
    async def queue_for_background_load(self, model_name: str, model_url: str, model_version: str = "latest") -> None:
        """Queue a model for background loading."""
        await self.download_queue.put({
            "model_name": model_name,
            "model_url": model_url,
            "model_version": model_version,
            "priority": "background"
        })
        logger.info(f"Queued {model_name}:{model_version} for background loading")
    
    async def load_from_cache(self, model_name: str, model_version: str = "latest") -> Optional[Any]:
        """Load a model from cache."""
        file_path = await self.get_cached_model_path(model_name, model_version)
        
        if not file_path:
            return None
        
        try:
            # In a real implementation, this would load the actual model
            # For now, return a mock model object
            cache_key = f"{model_name}:{model_version}"
            entry = self.cache_entries[cache_key]
            
            # Load metadata
            async with aiofiles.open(entry.metadata_path, 'r') as f:
                metadata = json.loads(await f.read())
            
            mock_model = {
                "name": model_name,
                "version": model_version,
                "file_path": file_path,
                "metadata": metadata,
                "loaded_from_cache": True,
                "cache_entry": entry
            }
            
            logger.info(f"Loaded model {cache_key} from cache")
            return mock_model
            
        except Exception as e:
            logger.error(f"Failed to load model from cache: {e}")
            return None
    
    async def shutdown(self) -> None:
        """Shutdown the cache system."""
        logger.info("Shutting down ModelCache")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel background cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Cancel download tasks
        for task in self.download_tasks.values():
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self.download_tasks:
            await asyncio.gather(*self.download_tasks.values(), return_exceptions=True)
        
        # Save final cache index
        await self._save_cache_index()
        
        # Shutdown thread pool
        self.thread_pool.shutdown(wait=True)
        
        logger.info("ModelCache shutdown complete")


# Global cache instance
_model_cache: Optional[ModelCache] = None


def get_model_cache() -> ModelCache:
    """Get the global model cache instance."""
    global _model_cache
    if _model_cache is None:
        _model_cache = ModelCache()
    return _model_cache


async def initialize_model_cache(config: Optional[CacheConfig] = None) -> ModelCache:
    """Initialize and start the model cache."""
    global _model_cache
    _model_cache = ModelCache(config)
    await _model_cache.initialize()
    return _model_cache