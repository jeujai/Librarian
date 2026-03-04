#!/usr/bin/env python3
"""
Hot Reload Configuration for Local Development

This script provides enhanced hot reload functionality for the Multimodal Librarian
application during local development. It monitors file changes and automatically
restarts the application server when changes are detected.

Features:
- Configurable file patterns for monitoring
- Intelligent exclusion of cache and temporary files
- Graceful server restart with minimal downtime
- Support for configuration file changes
- Development-specific optimizations
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from typing import List, Set, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent


class HotReloadConfig:
    """Configuration for hot reload functionality."""
    
    def __init__(self):
        # Directories to monitor for changes
        self.watch_dirs = [
            "/app/src",
            "/app/pyproject.toml",
            "/app/.env.local"
        ]
        
        # File patterns to include in monitoring
        self.include_patterns = {
            "*.py",
            "*.yaml", 
            "*.yml",
            "*.json",
            "*.toml",
            "*.env*"
        }
        
        # File patterns to exclude from monitoring
        self.exclude_patterns = {
            "__pycache__",
            "*.pyc",
            "*.pyo", 
            "*.pyd",
            ".git",
            ".pytest_cache",
            ".mypy_cache",
            "*.log",
            "*.tmp",
            ".DS_Store",
            "Thumbs.db"
        }
        
        # Directories to exclude completely
        self.exclude_dirs = {
            "__pycache__",
            ".git",
            ".pytest_cache", 
            ".mypy_cache",
            "node_modules",
            ".venv",
            "venv",
            ".tox"
        }
        
        # Debounce delay (seconds) to avoid multiple restarts for rapid changes
        self.debounce_delay = 1.0
        
        # Server restart command
        self.server_command = [
            "python", "-m", "uvicorn", 
            "multimodal_librarian.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
            "--reload-dir", "/app/src",
            "--reload-include", "*.py",
            "--reload-include", "*.yaml",
            "--reload-include", "*.yml", 
            "--reload-include", "*.json",
            "--reload-exclude", "__pycache__",
            "--reload-exclude", "*.pyc",
            "--reload-exclude", "*.pyo",
            "--reload-exclude", "*.pyd",
            "--reload-exclude", ".git"
        ]


class HotReloadHandler(FileSystemEventHandler):
    """File system event handler for hot reload functionality."""
    
    def __init__(self, config: HotReloadConfig):
        self.config = config
        self.last_restart_time = 0
        self.server_process: Optional[subprocess.Popen] = None
        self.pending_restart = False
        
    def should_handle_event(self, event_path: str) -> bool:
        """Check if the file change event should trigger a reload."""
        path = Path(event_path)
        
        # Skip directories in exclude list
        for part in path.parts:
            if part in self.config.exclude_dirs:
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
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory and self.should_handle_event(event.src_path):
            self.schedule_restart(f"File modified: {event.src_path}")
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory and self.should_handle_event(event.src_path):
            self.schedule_restart(f"File created: {event.src_path}")
    
    def on_deleted(self, event):
        """Handle file deletion events."""
        if not event.is_directory and self.should_handle_event(event.src_path):
            self.schedule_restart(f"File deleted: {event.src_path}")
    
    def schedule_restart(self, reason: str):
        """Schedule a server restart with debouncing."""
        current_time = time.time()
        
        # Debounce rapid changes
        if current_time - self.last_restart_time < self.config.debounce_delay:
            self.pending_restart = True
            return
        
        print(f"🔄 Hot reload triggered: {reason}")
        self.restart_server()
        self.last_restart_time = current_time
        self.pending_restart = False
    
    def restart_server(self):
        """Restart the application server."""
        # Stop existing server process
        if self.server_process and self.server_process.poll() is None:
            print("🛑 Stopping server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("⚠️  Force killing server...")
                self.server_process.kill()
                self.server_process.wait()
        
        # Start new server process
        print("🚀 Starting server...")
        try:
            self.server_process = subprocess.Popen(
                self.config.server_command,
                cwd="/app",
                env=dict(os.environ, PYTHONPATH="/app/src:/app")
            )
            print(f"✅ Server started with PID {self.server_process.pid}")
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
    
    def start_server(self):
        """Start the initial server process."""
        print("🚀 Starting initial server...")
        self.restart_server()
    
    def stop_server(self):
        """Stop the server process."""
        if self.server_process and self.server_process.poll() is None:
            print("🛑 Stopping server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()


class HotReloadManager:
    """Main hot reload manager."""
    
    def __init__(self):
        self.config = HotReloadConfig()
        self.handler = HotReloadHandler(self.config)
        self.observer = Observer()
        self.running = False
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            print(f"\n📡 Received signal {signum}, shutting down...")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def start(self):
        """Start the hot reload manager."""
        print("🔥 Starting Hot Reload Manager for Multimodal Librarian")
        print("=" * 60)
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Start initial server
        self.handler.start_server()
        
        # Setup file system monitoring
        for watch_dir in self.config.watch_dirs:
            if os.path.exists(watch_dir):
                self.observer.schedule(self.handler, watch_dir, recursive=True)
                print(f"👀 Watching: {watch_dir}")
            else:
                print(f"⚠️  Watch directory not found: {watch_dir}")
        
        # Start observer
        self.observer.start()
        self.running = True
        
        print("=" * 60)
        print("✅ Hot reload is active!")
        print("📝 Edit files in /app/src to trigger automatic reloads")
        print("🛑 Press Ctrl+C to stop")
        print("=" * 60)
        
        try:
            while self.running:
                time.sleep(1)
                
                # Handle pending restarts
                if self.handler.pending_restart:
                    current_time = time.time()
                    if current_time - self.handler.last_restart_time >= self.config.debounce_delay:
                        self.handler.schedule_restart("Pending restart")
        
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Stop the hot reload manager."""
        if self.running:
            print("\n🛑 Stopping hot reload manager...")
            self.running = False
            
            # Stop file system observer
            self.observer.stop()
            self.observer.join()
            
            # Stop server
            self.handler.stop_server()
            
            print("✅ Hot reload manager stopped")


def main():
    """Main entry point."""
    # Check if we're in development mode
    if os.getenv("ML_ENVIRONMENT") != "local":
        print("⚠️  Hot reload is only available in local development mode")
        print("   Set ML_ENVIRONMENT=local to enable hot reload")
        sys.exit(1)
    
    # Check if required directories exist
    if not os.path.exists("/app/src"):
        print("❌ Source directory /app/src not found")
        print("   Make sure you're running this from the correct container")
        sys.exit(1)
    
    # Start hot reload manager
    manager = HotReloadManager()
    manager.start()


if __name__ == "__main__":
    main()