#!/usr/bin/env python3
"""
Optimized Hot Reload System for Local Development

This script provides highly optimized hot reload functionality with:
- Intelligent file filtering to reduce CPU usage
- Advanced debouncing to prevent restart storms
- Selective module reloading where possible
- Memory-efficient file watching
- Fast startup optimizations
"""

import os
import sys
import time
import signal
import subprocess
import threading
import hashlib
from pathlib import Path
from typing import Dict, Set, Optional, List, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent


@dataclass
class FileChangeEvent:
    """Represents a file change event with metadata."""
    path: str
    event_type: str
    timestamp: float
    file_hash: Optional[str] = None


class OptimizedHotReloadConfig:
    """Optimized configuration for hot reload functionality."""
    
    def __init__(self):
        # Core directories to monitor (reduced set for performance)
        self.watch_dirs = [
            "/app/src/multimodal_librarian",  # Only watch main source
        ]
        
        # Configuration files to watch separately
        self.config_files = [
            "/app/pyproject.toml",
            "/app/.env.local"
        ]
        
        # High-priority file patterns (trigger immediate reload)
        self.high_priority_patterns = {
            "*/main.py",
            "*/config*.py", 
            "*/dependencies/*.py",
            "*/routers/*.py"
        }
        
        # Medium-priority file patterns (can be batched)
        self.medium_priority_patterns = {
            "*/services/*.py",
            "*/components/*.py",
            "*/models/*.py"
        }
        
        # Low-priority file patterns (batch with longer delay)
        self.low_priority_patterns = {
            "*/utils/*.py",
            "*/monitoring/*.py",
            "*/logging/*.py"
        }
        
        # File patterns to include in monitoring
        self.include_patterns = {
            "*.py",
            "*.yaml", 
            "*.yml",
            "*.json",
            "*.toml"
        }
        
        # Optimized exclude patterns (more specific)
        self.exclude_patterns = {
            "__pycache__/*",
            "*.pyc",
            "*.pyo", 
            "*.pyd",
            ".git/*",
            ".pytest_cache/*",
            ".mypy_cache/*",
            "*.log",
            "*.tmp",
            ".DS_Store",
            "Thumbs.db",
            "*.swp",
            "*.swo",
            "*~"
        }
        
        # Directories to exclude completely (performance optimization)
        self.exclude_dirs = {
            "__pycache__",
            ".git",
            ".pytest_cache", 
            ".mypy_cache",
            "node_modules",
            ".venv",
            "venv",
            ".tox",
            "dist",
            "build",
            ".eggs",
            "*.egg-info"
        }
        
        # Debounce delays by priority (seconds)
        self.debounce_delays = {
            'high': 0.5,      # High priority: fast restart
            'medium': 1.0,    # Medium priority: moderate delay
            'low': 2.0,       # Low priority: longer delay
            'config': 0.2     # Config changes: immediate
        }
        
        # Maximum number of changes to batch
        self.max_batch_size = 10
        
        # File hash cache size (for change detection)
        self.hash_cache_size = 1000
        
        # Server restart command (optimized)
        self.server_command = [
            "python", "-m", "uvicorn", 
            "multimodal_librarian.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
            "--reload-dir", "/app/src/multimodal_librarian",  # More specific
            "--reload-include", "*.py",
            "--reload-exclude", "__pycache__",
            "--reload-exclude", "*.pyc",
            "--reload-exclude", ".git",
            "--log-level", "info",  # Reduce log verbosity
            "--access-log",
            "--use-colors",
            "--loop", "uvloop",  # Use faster event loop
            "--http", "httptools",  # Use faster HTTP parser
            "--ws", "websockets"  # Use optimized WebSocket implementation
        ]


class FileHashCache:
    """Efficient file hash cache for change detection."""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: Dict[str, Tuple[float, str]] = {}  # path -> (mtime, hash)
        self.access_order = deque()  # For LRU eviction
    
    def get_file_hash(self, file_path: str) -> Optional[str]:
        """Get file hash, using cache when possible."""
        try:
            stat = os.stat(file_path)
            mtime = stat.st_mtime
            
            # Check cache
            if file_path in self.cache:
                cached_mtime, cached_hash = self.cache[file_path]
                if cached_mtime == mtime:
                    # Move to end of access order
                    self.access_order.remove(file_path)
                    self.access_order.append(file_path)
                    return cached_hash
            
            # Calculate new hash
            with open(file_path, 'rb') as f:
                content = f.read()
                file_hash = hashlib.md5(content).hexdigest()
            
            # Update cache
            self._update_cache(file_path, mtime, file_hash)
            return file_hash
            
        except (OSError, IOError):
            return None
    
    def _update_cache(self, file_path: str, mtime: float, file_hash: str):
        """Update cache with LRU eviction."""
        # Remove from old position if exists
        if file_path in self.cache:
            self.access_order.remove(file_path)
        
        # Add to cache
        self.cache[file_path] = (mtime, file_hash)
        self.access_order.append(file_path)
        
        # Evict if over size limit
        while len(self.cache) > self.max_size:
            oldest = self.access_order.popleft()
            del self.cache[oldest]
    
    def has_changed(self, file_path: str, current_hash: str) -> bool:
        """Check if file has changed based on hash."""
        if file_path not in self.cache:
            return True
        
        _, cached_hash = self.cache[file_path]
        return cached_hash != current_hash


class OptimizedHotReloadHandler(FileSystemEventHandler):
    """Optimized file system event handler for hot reload."""
    
    def __init__(self, config: OptimizedHotReloadConfig):
        self.config = config
        self.hash_cache = FileHashCache(config.hash_cache_size)
        self.pending_changes: Dict[str, deque] = defaultdict(deque)  # priority -> changes
        self.last_restart_time = 0
        self.server_process: Optional[subprocess.Popen] = None
        self.restart_lock = threading.Lock()
        self.change_processor_thread = None
        self.running = True
        
        # Start background change processor
        self._start_change_processor()
    
    def _start_change_processor(self):
        """Start background thread to process file changes."""
        def process_changes():
            while self.running:
                try:
                    self._process_pending_changes()
                    time.sleep(0.1)  # Check every 100ms
                except Exception as e:
                    print(f"❌ Error in change processor: {e}")
        
        self.change_processor_thread = threading.Thread(target=process_changes, daemon=True)
        self.change_processor_thread.start()
    
    def _get_file_priority(self, file_path: str) -> str:
        """Determine the priority of a file change."""
        path = Path(file_path)
        
        # Check if it's a config file
        if str(path) in self.config.config_files:
            return 'config'
        
        # Check priority patterns
        for pattern in self.config.high_priority_patterns:
            if path.match(pattern):
                return 'high'
        
        for pattern in self.config.medium_priority_patterns:
            if path.match(pattern):
                return 'medium'
        
        for pattern in self.config.low_priority_patterns:
            if path.match(pattern):
                return 'low'
        
        # Default to medium priority
        return 'medium'
    
    def should_handle_event(self, event_path: str) -> bool:
        """Optimized check if the file change event should trigger a reload."""
        path = Path(event_path)
        
        # Quick directory exclusion check
        path_str = str(path)
        for exclude_dir in self.config.exclude_dirs:
            if f"/{exclude_dir}/" in path_str or path_str.endswith(f"/{exclude_dir}"):
                return False
        
        # Check file extension against include patterns
        for pattern in self.config.include_patterns:
            if path.match(pattern):
                # Check against exclude patterns
                for exclude_pattern in self.config.exclude_patterns:
                    if path.match(exclude_pattern):
                        return False
                return True
        
        return False
    
    def _has_file_actually_changed(self, file_path: str) -> bool:
        """Check if file has actually changed using hash comparison."""
        current_hash = self.hash_cache.get_file_hash(file_path)
        if current_hash is None:
            return False
        
        return self.hash_cache.has_changed(file_path, current_hash)
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory and self.should_handle_event(event.src_path):
            # Only process if file actually changed (not just touched)
            if self._has_file_actually_changed(event.src_path):
                self._queue_change(event.src_path, "modified")
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory and self.should_handle_event(event.src_path):
            self._queue_change(event.src_path, "created")
    
    def on_deleted(self, event):
        """Handle file deletion events."""
        if not event.is_directory and self.should_handle_event(event.src_path):
            self._queue_change(event.src_path, "deleted")
    
    def _queue_change(self, file_path: str, event_type: str):
        """Queue a file change for processing."""
        priority = self._get_file_priority(file_path)
        change_event = FileChangeEvent(
            path=file_path,
            event_type=event_type,
            timestamp=time.time()
        )
        
        self.pending_changes[priority].append(change_event)
        
        # Limit queue size to prevent memory issues
        if len(self.pending_changes[priority]) > self.config.max_batch_size:
            self.pending_changes[priority].popleft()
    
    def _process_pending_changes(self):
        """Process pending file changes with intelligent batching."""
        current_time = time.time()
        
        # Process changes by priority
        for priority in ['config', 'high', 'medium', 'low']:
            if not self.pending_changes[priority]:
                continue
            
            # Check if enough time has passed for this priority
            debounce_delay = self.config.debounce_delays[priority]
            oldest_change = self.pending_changes[priority][0]
            
            if current_time - oldest_change.timestamp >= debounce_delay:
                # Collect all changes for this priority
                changes = list(self.pending_changes[priority])
                self.pending_changes[priority].clear()
                
                # Trigger restart with change information
                self._trigger_restart(priority, changes)
                break  # Only process one priority level at a time
    
    def _trigger_restart(self, priority: str, changes: List[FileChangeEvent]):
        """Trigger server restart with change information."""
        with self.restart_lock:
            current_time = time.time()
            
            # Additional debouncing for rapid restarts
            if current_time - self.last_restart_time < 0.5:
                return
            
            change_summary = self._summarize_changes(changes)
            print(f"🔄 Hot reload triggered ({priority} priority): {change_summary}")
            
            self._restart_server()
            self.last_restart_time = current_time
    
    def _summarize_changes(self, changes: List[FileChangeEvent]) -> str:
        """Create a summary of file changes."""
        if len(changes) == 1:
            change = changes[0]
            return f"{change.event_type} {Path(change.path).name}"
        else:
            change_types = defaultdict(int)
            for change in changes:
                change_types[change.event_type] += 1
            
            summary_parts = []
            for change_type, count in change_types.items():
                summary_parts.append(f"{count} {change_type}")
            
            return f"{len(changes)} files ({', '.join(summary_parts)})"
    
    def _restart_server(self):
        """Restart the application server with optimizations."""
        # Stop existing server process
        if self.server_process and self.server_process.poll() is None:
            print("🛑 Stopping server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=3)  # Reduced timeout
            except subprocess.TimeoutExpired:
                print("⚠️  Force killing server...")
                self.server_process.kill()
                self.server_process.wait()
        
        # Start new server process with optimizations
        print("🚀 Starting server...")
        try:
            env = dict(os.environ)
            env.update({
                'PYTHONPATH': '/app/src:/app',
                'PYTHONOPTIMIZE': '1',  # Enable Python optimizations
                'PYTHONDONTWRITEBYTECODE': '1',  # Don't write .pyc files
                'UVLOOP_ENABLED': '1'  # Enable uvloop if available
            })
            
            self.server_process = subprocess.Popen(
                self.config.server_command,
                cwd="/app",
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True
            )
            print(f"✅ Server started with PID {self.server_process.pid}")
            
            # Start log monitoring in background
            self._start_log_monitoring()
            
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
    
    def _start_log_monitoring(self):
        """Start background log monitoring for server output."""
        def monitor_logs():
            if not self.server_process:
                return
            
            try:
                for line in iter(self.server_process.stdout.readline, ''):
                    if not line:
                        break
                    
                    # Filter and display relevant log messages
                    line = line.strip()
                    if any(keyword in line.lower() for keyword in ['error', 'exception', 'failed', 'started']):
                        print(f"📋 {line}")
                        
            except Exception as e:
                print(f"❌ Log monitoring error: {e}")
        
        log_thread = threading.Thread(target=monitor_logs, daemon=True)
        log_thread.start()
    
    def start_server(self):
        """Start the initial server process."""
        print("🚀 Starting initial server...")
        self._restart_server()
    
    def stop_server(self):
        """Stop the server process and cleanup."""
        self.running = False
        
        if self.server_process and self.server_process.poll() is None:
            print("🛑 Stopping server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()


class OptimizedHotReloadManager:
    """Optimized hot reload manager with performance enhancements."""
    
    def __init__(self):
        self.config = OptimizedHotReloadConfig()
        self.handler = OptimizedHotReloadHandler(self.config)
        self.observer = Observer()
        self.running = False
        
        # Performance monitoring
        self.start_time = time.time()
        self.restart_count = 0
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            print(f"\n📡 Received signal {signum}, shutting down...")
            self._print_performance_stats()
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def _print_performance_stats(self):
        """Print performance statistics."""
        uptime = time.time() - self.start_time
        print(f"\n📊 Performance Stats:")
        print(f"   Uptime: {uptime:.1f}s")
        print(f"   Restarts: {self.restart_count}")
        print(f"   Cache size: {len(self.handler.hash_cache.cache)}")
    
    def start(self):
        """Start the optimized hot reload manager."""
        print("🔥 Starting Optimized Hot Reload Manager")
        print("=" * 60)
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Start initial server
        self.handler.start_server()
        
        # Setup file system monitoring with optimizations
        for watch_dir in self.config.watch_dirs:
            if os.path.exists(watch_dir):
                # Use recursive=False for better performance, manually handle subdirs
                self.observer.schedule(self.handler, watch_dir, recursive=True)
                print(f"👀 Watching: {watch_dir}")
            else:
                print(f"⚠️  Watch directory not found: {watch_dir}")
        
        # Watch config files separately
        for config_file in self.config.config_files:
            if os.path.exists(config_file):
                config_dir = os.path.dirname(config_file)
                self.observer.schedule(self.handler, config_dir, recursive=False)
                print(f"⚙️  Watching config: {config_file}")
        
        # Start observer with optimizations
        self.observer.start()
        self.running = True
        
        print("=" * 60)
        print("✅ Optimized hot reload is active!")
        print("📝 Edit files to trigger intelligent reloads")
        print("🎯 High priority files reload faster")
        print("🛑 Press Ctrl+C to stop")
        print("=" * 60)
        
        try:
            while self.running:
                time.sleep(1)
                
                # Periodic cleanup
                if time.time() % 60 < 1:  # Every minute
                    self._periodic_cleanup()
        
        except KeyboardInterrupt:
            self.stop()
    
    def _periodic_cleanup(self):
        """Perform periodic cleanup tasks."""
        # Clean up hash cache if it's getting too large
        if len(self.handler.hash_cache.cache) > self.config.hash_cache_size * 0.9:
            # Remove 10% of oldest entries
            cleanup_count = int(self.config.hash_cache_size * 0.1)
            for _ in range(cleanup_count):
                if self.handler.hash_cache.access_order:
                    oldest = self.handler.hash_cache.access_order.popleft()
                    self.handler.hash_cache.cache.pop(oldest, None)
    
    def stop(self):
        """Stop the optimized hot reload manager."""
        if self.running:
            print("\n🛑 Stopping optimized hot reload manager...")
            self.running = False
            
            # Stop file system observer
            self.observer.stop()
            self.observer.join()
            
            # Stop server
            self.handler.stop_server()
            
            print("✅ Optimized hot reload manager stopped")


def main():
    """Main entry point."""
    # Check if we're in development mode
    if os.getenv("ML_ENVIRONMENT") != "local":
        print("⚠️  Optimized hot reload is only available in local development mode")
        print("   Set ML_ENVIRONMENT=local to enable hot reload")
        sys.exit(1)
    
    # Check if required directories exist
    if not os.path.exists("/app/src"):
        print("❌ Source directory /app/src not found")
        print("   Make sure you're running this from the correct container")
        sys.exit(1)
    
    # Install uvloop for better performance if available
    try:
        import uvloop
        uvloop.install()
        print("🚀 Using uvloop for enhanced performance")
    except ImportError:
        print("💡 Install uvloop for better performance: pip install uvloop")
    
    # Start optimized hot reload manager
    manager = OptimizedHotReloadManager()
    manager.start()


if __name__ == "__main__":
    main()