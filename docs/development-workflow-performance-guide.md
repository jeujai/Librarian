# Development Workflow Performance Guide

## Overview

This guide focuses on optimizing the development workflow performance for the local development environment. It covers hot reload optimization, testing performance, debugging efficiency, and overall developer productivity while maintaining the performance requirements of the local-development-conversion spec.

## Hot Reload Performance Optimization

### File Watching Optimization

#### Intelligent File Watcher Configuration

```python
# src/multimodal_librarian/development/optimized_file_watcher.py
import os
import time
from pathlib import Path
from typing import Set, List, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

class OptimizedFileWatcher:
    """Optimized file watcher for development hot reload."""
    
    def __init__(self):
        self.ignore_patterns = {
            # Python cache files
            "*.pyc", "__pycache__", "*.pyo", "*.pyd",
            # Version control
            ".git", ".gitignore", ".gitmodules",
            # IDE files
            ".vscode", ".idea", "*.swp", "*.swo",
            # Logs and temporary files
            "*.log", "*.tmp", "*.temp", ".DS_Store",
            # Test artifacts
            ".pytest_cache", ".coverage", "htmlcov",
            # Node modules (if any)
            "node_modules", "*.lock",
            # Docker files
            "Dockerfile*", "docker-compose*",
            # Documentation (unless specifically watched)
            "*.md", "docs/",
        }
        
        self.debounce_delay = 0.3  # 300ms debounce
        self.batch_delay = 0.1     # 100ms batch delay
        self.last_modified = {}
        self.pending_changes = set()
        self.batch_timer = None
        
    def should_ignore_file(self, file_path: str) -> bool:
        """Check if file should be ignored based on patterns."""
        path = Path(file_path)
        
        # Check ignore patterns
        for pattern in self.ignore_patterns:
            if pattern.startswith("*."):
                if path.suffix == pattern[1:]:
                    return True
            elif pattern.endswith("/"):
                if pattern[:-1] in path.parts:
                    return True
            elif pattern in path.name or pattern in str(path):
                return True
                
        return False
    
    def debounce_file_change(self, file_path: str) -> bool:
        """Debounce file changes to avoid excessive reloads."""
        now = time.time()
        
        if file_path in self.last_modified:
            if now - self.last_modified[file_path] < self.debounce_delay:
                return False
                
        self.last_modified[file_path] = now
        return True
    
    def batch_file_changes(self, file_path: str, callback: Callable):
        """Batch multiple file changes together."""
        self.pending_changes.add(file_path)
        
        # Cancel existing timer
        if self.batch_timer:
            self.batch_timer.cancel()
        
        # Start new timer
        import threading
        self.batch_timer = threading.Timer(
            self.batch_delay,
            lambda: self.process_batched_changes(callback)
        )
        self.batch_timer.start()
    
    def process_batched_changes(self, callback: Callable):
        """Process all batched file changes."""
        if self.pending_changes:
            changed_files = list(self.pending_changes)
            self.pending_changes.clear()
            callback(changed_files)

class DevelopmentFileHandler(FileSystemEventHandler):
    """Optimized file system event handler for development."""
    
    def __init__(self, reload_callback: Callable, watcher: OptimizedFileWatcher):
        self.reload_callback = reload_callback
        self.watcher = watcher
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        file_path = event.src_path
        
        # Skip ignored files
        if self.watcher.should_ignore_file(file_path):
            return
            
        # Debounce changes
        if not self.watcher.debounce_file_change(file_path):
            return
            
        # Batch changes
        self.watcher.batch_file_changes(file_path, self.reload_callback)

# Usage in FastAPI application
def setup_optimized_hot_reload():
    """Setup optimized hot reload for development."""
    watcher = OptimizedFileWatcher()
    
    def reload_application(changed_files: List[str]):
        print(f"Reloading application due to changes in: {changed_files}")
        # Trigger application reload
        
    handler = DevelopmentFileHandler(reload_application, watcher)
    observer = Observer()
    
    # Watch source directories
    observer.schedule(handler, "src/", recursive=True)
    observer.schedule(handler, "tests/", recursive=True)
    
    observer.start()
    return observer
```

#### Docker Volume Mount Optimization

```yaml
# docker-compose.local.yml - Optimized volume mounts for hot reload
services:
  multimodal-librarian:
    volumes:
      # Source code with optimized caching
      - ./src:/app/src:ro,cached
      - ./tests:/app/tests:ro,cached
      
      # Configuration files
      - ./.env.local:/app/.env:ro
      - ./pyproject.toml:/app/pyproject.toml:ro
      
      # Exclude cache directories to avoid conflicts
      - /app/src/**/__pycache__
      - /app/tests/**/__pycache__
      
      # Persistent directories with delegated caching
      - ./uploads:/app/uploads:rw,delegated
      - ./logs:/app/logs:rw,delegated
      
      # Temporary cache (in-memory for speed)
      - cache_volume:/app/.cache:rw
      
    environment:
      # Python optimization for development
      - PYTHONDONTWRITEBYTECODE=1  # Prevent .pyc files
      - PYTHONUNBUFFERED=1         # Immediate output
      - PYTHONPATH=/app/src        # Module path
      - WATCHDOG_POLLING=false     # Use native file events
      
volumes:
  cache_volume:
    driver: local
    driver_opts:
      type: tmpfs
      device: tmpfs
      o: size=512m,uid=1000,gid=1000
```

### Application Startup Optimization

#### Fast Development Server Configuration

```python
# src/multimodal_librarian/development/fast_server.py
import asyncio
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

class FastDevelopmentServer:
    """Optimized development server for fast startup and reload."""
    
    def __init__(self):
        self.app = None
        self.server = None
        self.reload_dirs = ["src", "tests"]
        self.reload_excludes = [
            "*.pyc", "__pycache__", "*.log", "*.tmp",
            ".git", ".pytest_cache", "htmlcov"
        ]
    
    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """Optimized lifespan for development."""
        # Fast startup - only initialize essential components
        await self.initialize_essential_components()
        
        yield
        
        # Fast shutdown
        await self.cleanup_components()
    
    async def initialize_essential_components(self):
        """Initialize only essential components for fast startup."""
        # Skip heavy initialization in development
        # Load models lazily when needed
        pass
    
    async def cleanup_components(self):
        """Fast cleanup for development."""
        # Minimal cleanup for fast restart
        pass
    
    def create_app(self) -> FastAPI:
        """Create optimized FastAPI app for development."""
        app = FastAPI(
            title="Multimodal Librarian (Development)",
            debug=True,
            lifespan=self.lifespan,
            # Disable OpenAPI generation for faster startup
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_url="/openapi.json",
        )
        
        # Add development-specific middleware
        self.add_development_middleware(app)
        
        # Add routes
        self.add_routes(app)
        
        return app
    
    def add_development_middleware(self, app: FastAPI):
        """Add development-specific middleware."""
        from fastapi.middleware.cors import CORSMiddleware
        
        # Permissive CORS for development
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Development request logging
        @app.middleware("http")
        async def log_requests(request, call_next):
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            
            if process_time > 0.1:  # Log slow requests
                print(f"Slow request: {request.method} {request.url} - {process_time:.3f}s")
            
            return response
    
    def add_routes(self, app: FastAPI):
        """Add application routes."""
        # Import routes lazily to speed up startup
        from multimodal_librarian.api.routers import (
            health, chat, documents
        )
        
        app.include_router(health.router, prefix="/health", tags=["health"])
        app.include_router(chat.router, prefix="/chat", tags=["chat"])
        app.include_router(documents.router, prefix="/documents", tags=["documents"])
    
    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Run the development server with optimized settings."""
        config = uvicorn.Config(
            app=self.create_app(),
            host=host,
            port=port,
            reload=True,
            reload_dirs=self.reload_dirs,
            reload_excludes=self.reload_excludes,
            # Performance optimizations
            loop="asyncio",
            http="httptools",
            ws="websockets",
            # Development settings
            log_level="info",
            access_log=True,
            use_colors=True,
            # Reload optimization
            reload_delay=0.25,  # 250ms delay before reload
        )
        
        server = uvicorn.Server(config)
        server.run()

# Development server entry point
if __name__ == "__main__":
    server = FastDevelopmentServer()
    server.run()
```

## Testing Performance Optimization

### Parallel Test Execution

#### Optimized pytest Configuration

```ini
# pytest.ini - Optimized for performance
[tool:pytest]
minversion = 6.0
addopts = 
    # Parallel execution
    -n auto
    --dist worksteal
    --maxfail=5
    
    # Output optimization
    --tb=short
    --strict-markers
    --disable-warnings
    
    # Coverage (optional, can slow down tests)
    --cov=multimodal_librarian
    --cov-report=term-missing:skip-covered
    --cov-report=html:htmlcov
    --cov-fail-under=80
    
    # Performance optimization
    --durations=10
    --durations-min=1.0

testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    performance: marks tests as performance tests
    unit: marks tests as unit tests (fast)
    database: marks tests that require database
    
# Parallel execution configuration
[tool:pytest-xdist]
# Use all available CPU cores
workers = auto
# Distribute tests efficiently
distribution = worksteal
```

#### Fast Test Database Setup

```python
# tests/conftest.py - Optimized test configuration
import pytest
import asyncio
import asyncpg
from typing import AsyncGenerator
from multimodal_librarian.config.local_config import LocalDatabaseConfig

class FastTestDatabase:
    """Fast test database setup for development."""
    
    def __init__(self):
        self.test_db_name = "test_multimodal_librarian"
        self.template_db_name = "template_multimodal_librarian"
        self.config = LocalDatabaseConfig()
        
    async def create_template_database(self):
        """Create a template database with schema for fast test setup."""
        # Connect to postgres database
        conn = await asyncpg.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            database="postgres"
        )
        
        try:
            # Drop existing template if exists
            await conn.execute(f"DROP DATABASE IF EXISTS {self.template_db_name}")
            
            # Create template database
            await conn.execute(f"CREATE DATABASE {self.template_db_name}")
            
        finally:
            await conn.close()
        
        # Connect to template database and set up schema
        template_conn = await asyncpg.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            database=self.template_db_name
        )
        
        try:
            # Run schema setup
            await self.setup_database_schema(template_conn)
        finally:
            await template_conn.close()
    
    async def setup_database_schema(self, conn):
        """Set up database schema in template database."""
        # Read and execute schema files
        schema_files = [
            "database/postgresql/init/01_schema.sql",
            "database/postgresql/init/02_indexes.sql",
            "database/postgresql/init/03_performance_tuning.sql",
        ]
        
        for schema_file in schema_files:
            if os.path.exists(schema_file):
                with open(schema_file, 'r') as f:
                    schema_sql = f.read()
                    await conn.execute(schema_sql)
    
    async def create_test_database(self, test_id: str):
        """Create test database from template for fast setup."""
        test_db_name = f"{self.test_db_name}_{test_id}"
        
        # Connect to postgres database
        conn = await asyncpg.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            database="postgres"
        )
        
        try:
            # Drop existing test database if exists
            await conn.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
            
            # Create test database from template (very fast)
            await conn.execute(
                f"CREATE DATABASE {test_db_name} WITH TEMPLATE {self.template_db_name}"
            )
            
        finally:
            await conn.close()
        
        return test_db_name
    
    async def cleanup_test_database(self, test_db_name: str):
        """Clean up test database."""
        conn = await asyncpg.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            database="postgres"
        )
        
        try:
            # Terminate connections to test database
            await conn.execute(f"""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = '{test_db_name}' AND pid <> pg_backend_pid()
            """)
            
            # Drop test database
            await conn.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
            
        finally:
            await conn.close()

# Global test database manager
test_db_manager = FastTestDatabase()

@pytest.fixture(scope="session", autouse=True)
async def setup_test_template():
    """Set up template database once per test session."""
    await test_db_manager.create_template_database()

@pytest.fixture
async def test_database() -> AsyncGenerator[str, None]:
    """Provide a fresh test database for each test."""
    import uuid
    test_id = str(uuid.uuid4())[:8]
    
    test_db_name = await test_db_manager.create_test_database(test_id)
    
    try:
        yield test_db_name
    finally:
        await test_db_manager.cleanup_test_database(test_db_name)

@pytest.fixture
async def fast_app_client(test_database):
    """Fast test client with minimal setup."""
    from fastapi.testclient import TestClient
    from multimodal_librarian.development.fast_server import FastDevelopmentServer
    
    # Create app with test database
    server = FastDevelopmentServer()
    app = server.create_app()
    
    # Override database configuration
    app.dependency_overrides[get_database_config] = lambda: LocalDatabaseConfig(
        postgres_db=test_database
    )
    
    with TestClient(app) as client:
        yield client
    
    # Clean up overrides
    app.dependency_overrides.clear()
```

### Test Performance Optimization

#### Smart Test Selection

```python
# tests/performance/test_selection.py
import pytest
import time
from typing import List, Dict

class SmartTestSelector:
    """Smart test selection based on file changes and test performance."""
    
    def __init__(self):
        self.test_performance_cache = {}
        self.file_test_mapping = {}
        
    def get_affected_tests(self, changed_files: List[str]) -> List[str]:
        """Get tests affected by file changes."""
        affected_tests = set()
        
        for file_path in changed_files:
            # Direct test file
            if file_path.startswith("tests/"):
                affected_tests.add(file_path)
            
            # Source file - find related tests
            elif file_path.startswith("src/"):
                related_tests = self.find_related_tests(file_path)
                affected_tests.update(related_tests)
        
        return list(affected_tests)
    
    def find_related_tests(self, source_file: str) -> List[str]:
        """Find tests related to a source file."""
        # Convert source file path to test file path
        test_patterns = [
            source_file.replace("src/", "tests/").replace(".py", "_test.py"),
            source_file.replace("src/", "tests/test_"),
            # Integration tests
            f"tests/integration/test_{Path(source_file).stem}.py",
            # Component tests
            f"tests/components/test_{Path(source_file).stem}.py",
        ]
        
        existing_tests = []
        for pattern in test_patterns:
            if os.path.exists(pattern):
                existing_tests.append(pattern)
        
        return existing_tests
    
    def prioritize_tests(self, test_files: List[str]) -> List[str]:
        """Prioritize tests based on performance and importance."""
        test_priorities = []
        
        for test_file in test_files:
            # Get cached performance data
            performance = self.test_performance_cache.get(test_file, {})
            avg_duration = performance.get("avg_duration", 1.0)
            
            # Calculate priority (lower is higher priority)
            priority = avg_duration
            
            # Boost priority for unit tests
            if "unit" in test_file or "test_" in test_file:
                priority *= 0.5
            
            # Lower priority for slow integration tests
            if "integration" in test_file:
                priority *= 2.0
            
            test_priorities.append((priority, test_file))
        
        # Sort by priority (lowest first)
        test_priorities.sort(key=lambda x: x[0])
        
        return [test_file for _, test_file in test_priorities]

# Pytest plugin for smart test selection
class SmartTestPlugin:
    def __init__(self):
        self.selector = SmartTestSelector()
        
    def pytest_collection_modifyitems(self, config, items):
        """Modify test collection based on smart selection."""
        if config.getoption("--smart-select"):
            # Get changed files from git
            changed_files = self.get_changed_files()
            
            if changed_files:
                # Get affected tests
                affected_tests = self.selector.get_affected_tests(changed_files)
                
                # Filter items to only affected tests
                selected_items = []
                for item in items:
                    if any(test_path in str(item.fspath) for test_path in affected_tests):
                        selected_items.append(item)
                
                items[:] = selected_items
                print(f"Smart selection: Running {len(selected_items)} affected tests")
    
    def get_changed_files(self) -> List[str]:
        """Get changed files from git."""
        import subprocess
        
        try:
            # Get changed files in working directory
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            
            changed_files = result.stdout.strip().split('\n')
            return [f for f in changed_files if f.endswith('.py')]
            
        except subprocess.CalledProcessError:
            return []

# Register plugin
def pytest_configure(config):
    config.pluginmanager.register(SmartTestPlugin(), "smart_test_plugin")

def pytest_addoption(parser):
    parser.addoption(
        "--smart-select",
        action="store_true",
        default=False,
        help="Run only tests affected by changed files"
    )
```

## Debugging Performance Optimization

### Fast Debugging Setup

#### Optimized Debug Configuration

```python
# src/multimodal_librarian/development/debug_config.py
import logging
import sys
from typing import Optional

class FastDebugger:
    """Optimized debugger for development performance."""
    
    def __init__(self):
        self.debug_enabled = True
        self.log_level = logging.DEBUG
        self.performance_logging = True
        
    def setup_fast_logging(self):
        """Set up fast logging for development."""
        # Create custom formatter for development
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Console handler with optimized settings
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(self.log_level)
        
        # Root logger configuration
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        root_logger.addHandler(console_handler)
        
        # Optimize specific loggers
        self.optimize_logger_performance()
    
    def optimize_logger_performance(self):
        """Optimize logger performance for development."""
        # Reduce verbosity of noisy loggers
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        
        # Enable performance-critical loggers
        logging.getLogger("multimodal_librarian").setLevel(logging.DEBUG)
        logging.getLogger("performance").setLevel(logging.INFO)
    
    def setup_performance_profiling(self):
        """Set up performance profiling for development."""
        import cProfile
        import pstats
        from functools import wraps
        
        def profile_function(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not self.performance_logging:
                    return func(*args, **kwargs)
                
                profiler = cProfile.Profile()
                profiler.enable()
                
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    profiler.disable()
                    
                    # Log slow functions
                    stats = pstats.Stats(profiler)
                    stats.sort_stats('cumulative')
                    
                    # Get function stats
                    for stat in stats.get_stats_profile().func_profiles:
                        if stat.cumulative > 0.1:  # Log functions taking > 100ms
                            logging.getLogger("performance").warning(
                                f"Slow function: {func.__name__} took {stat.cumulative:.3f}s"
                            )
            
            return wrapper
        
        return profile_function
    
    def setup_memory_profiling(self):
        """Set up memory profiling for development."""
        import tracemalloc
        
        if self.performance_logging:
            tracemalloc.start()
            
            def log_memory_usage():
                current, peak = tracemalloc.get_traced_memory()
                logging.getLogger("performance").info(
                    f"Memory usage: {current / 1024 / 1024:.1f}MB "
                    f"(peak: {peak / 1024 / 1024:.1f}MB)"
                )
            
            return log_memory_usage
        
        return lambda: None

# Global debugger instance
fast_debugger = FastDebugger()

# Decorators for performance monitoring
def profile_performance(func):
    """Decorator to profile function performance."""
    return fast_debugger.setup_performance_profiling()(func)

def log_memory_usage(func):
    """Decorator to log memory usage."""
    memory_logger = fast_debugger.setup_memory_profiling()
    
    def wrapper(*args, **kwargs):
        memory_logger()
        result = func(*args, **kwargs)
        memory_logger()
        return result
    
    return wrapper
```

#### Interactive Debugging Tools

```python
# src/multimodal_librarian/development/interactive_debug.py
import asyncio
import json
from typing import Any, Dict
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/debug", tags=["debug"])

class InteractiveDebugger:
    """Interactive debugging tools for development."""
    
    def __init__(self):
        self.debug_data = {}
        self.performance_metrics = {}
        
    async def capture_request_data(self, request_data: Dict[str, Any]):
        """Capture request data for debugging."""
        self.debug_data[f"request_{len(self.debug_data)}"] = {
            "timestamp": time.time(),
            "data": request_data
        }
        
        # Keep only last 100 requests
        if len(self.debug_data) > 100:
            oldest_key = min(self.debug_data.keys())
            del self.debug_data[oldest_key]
    
    async def measure_performance(self, operation_name: str, duration: float):
        """Measure and store performance metrics."""
        if operation_name not in self.performance_metrics:
            self.performance_metrics[operation_name] = []
        
        self.performance_metrics[operation_name].append({
            "timestamp": time.time(),
            "duration": duration
        })
        
        # Keep only last 1000 measurements per operation
        if len(self.performance_metrics[operation_name]) > 1000:
            self.performance_metrics[operation_name] = \
                self.performance_metrics[operation_name][-1000:]

# Global debugger instance
interactive_debugger = InteractiveDebugger()

@router.get("/performance")
async def get_performance_metrics():
    """Get current performance metrics."""
    summary = {}
    
    for operation, measurements in interactive_debugger.performance_metrics.items():
        if measurements:
            durations = [m["duration"] for m in measurements]
            summary[operation] = {
                "count": len(durations),
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "recent_duration": durations[-1] if durations else 0
            }
    
    return JSONResponse(summary)

@router.get("/requests")
async def get_recent_requests():
    """Get recent request data for debugging."""
    return JSONResponse(interactive_debugger.debug_data)

@router.post("/clear")
async def clear_debug_data():
    """Clear all debug data."""
    interactive_debugger.debug_data.clear()
    interactive_debugger.performance_metrics.clear()
    return {"message": "Debug data cleared"}

@router.get("/system")
async def get_system_info():
    """Get system information for debugging."""
    import psutil
    import platform
    
    return JSONResponse({
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "memory_total": psutil.virtual_memory().total,
        "memory_available": psutil.virtual_memory().available,
        "disk_usage": psutil.disk_usage('/').percent,
        "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
    })
```

## Code Quality and Performance

### Fast Code Quality Checks

#### Optimized Pre-commit Hooks

```yaml
# .pre-commit-config.yaml - Fast code quality checks
repos:
  # Fast Python formatting
  - repo: https://github.com/psf/black
    rev: 23.1.0
    hooks:
      - id: black
        args: [--fast, --line-length=88]
        
  # Fast import sorting
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: [--profile=black, --fast]
        
  # Fast linting (essential rules only)
  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: [--select=E9,F63,F7,F82, --max-line-length=88]
        
  # Fast security checks
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.4
    hooks:
      - id: bandit
        args: [-ll, --skip=B101,B601]
        
  # Fast type checking (essential only)
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.0.1
    hooks:
      - id: mypy
        args: [--ignore-missing-imports, --fast-parser]
        additional_dependencies: [types-all]
```

#### Incremental Code Analysis

```python
# scripts/fast-code-analysis.py
import os
import subprocess
import time
from pathlib import Path
from typing import List, Set

class IncrementalCodeAnalyzer:
    """Fast incremental code analysis for development."""
    
    def __init__(self):
        self.cache_dir = Path(".code_analysis_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
    def get_changed_files(self) -> List[str]:
        """Get changed Python files since last analysis."""
        try:
            # Get changed files from git
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            
            changed_files = result.stdout.strip().split('\n')
            return [f for f in changed_files if f.endswith('.py') and os.path.exists(f)]
            
        except subprocess.CalledProcessError:
            # Fallback: analyze all Python files
            return list(Path("src").rglob("*.py"))
    
    def run_fast_analysis(self, files: List[str]) -> Dict[str, Any]:
        """Run fast code analysis on specified files."""
        results = {
            "formatting": self.check_formatting(files),
            "imports": self.check_imports(files),
            "basic_linting": self.check_basic_linting(files),
            "type_hints": self.check_type_hints(files),
        }
        
        return results
    
    def check_formatting(self, files: List[str]) -> Dict[str, Any]:
        """Fast formatting check with black."""
        try:
            result = subprocess.run(
                ["black", "--check", "--fast", "--diff"] + files,
                capture_output=True,
                text=True
            )
            
            return {
                "passed": result.returncode == 0,
                "output": result.stdout if result.returncode != 0 else None
            }
        except FileNotFoundError:
            return {"passed": True, "output": "Black not installed"}
    
    def check_imports(self, files: List[str]) -> Dict[str, Any]:
        """Fast import sorting check with isort."""
        try:
            result = subprocess.run(
                ["isort", "--check-only", "--diff", "--fast"] + files,
                capture_output=True,
                text=True
            )
            
            return {
                "passed": result.returncode == 0,
                "output": result.stdout if result.returncode != 0 else None
            }
        except FileNotFoundError:
            return {"passed": True, "output": "isort not installed"}
    
    def check_basic_linting(self, files: List[str]) -> Dict[str, Any]:
        """Fast basic linting with flake8."""
        try:
            result = subprocess.run(
                ["flake8", "--select=E9,F63,F7,F82"] + files,
                capture_output=True,
                text=True
            )
            
            return {
                "passed": result.returncode == 0,
                "output": result.stdout if result.returncode != 0 else None
            }
        except FileNotFoundError:
            return {"passed": True, "output": "flake8 not installed"}
    
    def check_type_hints(self, files: List[str]) -> Dict[str, Any]:
        """Fast type hint checking with mypy."""
        try:
            result = subprocess.run(
                ["mypy", "--fast-parser", "--ignore-missing-imports"] + files,
                capture_output=True,
                text=True
            )
            
            return {
                "passed": result.returncode == 0,
                "output": result.stdout if result.returncode != 0 else None
            }
        except FileNotFoundError:
            return {"passed": True, "output": "mypy not installed"}

def main():
    """Run fast incremental code analysis."""
    analyzer = IncrementalCodeAnalyzer()
    
    print("Running fast code analysis...")
    start_time = time.time()
    
    # Get changed files
    changed_files = analyzer.get_changed_files()
    
    if not changed_files:
        print("No Python files changed.")
        return
    
    print(f"Analyzing {len(changed_files)} changed files...")
    
    # Run analysis
    results = analyzer.run_fast_analysis(changed_files)
    
    # Report results
    all_passed = True
    for check_name, result in results.items():
        status = "✓" if result["passed"] else "✗"
        print(f"{status} {check_name}")
        
        if not result["passed"]:
            all_passed = False
            if result["output"]:
                print(f"  {result['output']}")
    
    duration = time.time() - start_time
    print(f"\nAnalysis completed in {duration:.2f}s")
    
    if not all_passed:
        exit(1)

if __name__ == "__main__":
    main()
```

## Performance Monitoring Integration

### Development Performance Dashboard

```python
# src/multimodal_librarian/development/performance_dashboard.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import json
import time

router = APIRouter(prefix="/dev", tags=["development"])

class DevelopmentPerformanceDashboard:
    """Real-time performance dashboard for development."""
    
    def __init__(self):
        self.metrics = {
            "requests": [],
            "database_queries": [],
            "cache_hits": [],
            "memory_usage": [],
        }
        
    def record_request(self, request: Request, duration: float):
        """Record request performance."""
        self.metrics["requests"].append({
            "timestamp": time.time(),
            "method": request.method,
            "path": str(request.url.path),
            "duration": duration,
        })
        
        # Keep only last 1000 requests
        if len(self.metrics["requests"]) > 1000:
            self.metrics["requests"] = self.metrics["requests"][-1000:]
    
    def record_database_query(self, query_type: str, duration: float):
        """Record database query performance."""
        self.metrics["database_queries"].append({
            "timestamp": time.time(),
            "type": query_type,
            "duration": duration,
        })
        
        # Keep only last 1000 queries
        if len(self.metrics["database_queries"]) > 1000:
            self.metrics["database_queries"] = self.metrics["database_queries"][-1000:]
    
    def get_performance_summary(self) -> dict:
        """Get performance summary for dashboard."""
        now = time.time()
        last_minute = now - 60
        
        # Recent requests
        recent_requests = [
            r for r in self.metrics["requests"] 
            if r["timestamp"] > last_minute
        ]
        
        # Recent queries
        recent_queries = [
            q for q in self.metrics["database_queries"]
            if q["timestamp"] > last_minute
        ]
        
        return {
            "requests_per_minute": len(recent_requests),
            "avg_request_duration": (
                sum(r["duration"] for r in recent_requests) / len(recent_requests)
                if recent_requests else 0
            ),
            "queries_per_minute": len(recent_queries),
            "avg_query_duration": (
                sum(q["duration"] for q in recent_queries) / len(recent_queries)
                if recent_queries else 0
            ),
            "slow_requests": [
                r for r in recent_requests if r["duration"] > 1.0
            ],
            "slow_queries": [
                q for q in recent_queries if q["duration"] > 0.1
            ],
        }

# Global dashboard instance
dashboard = DevelopmentPerformanceDashboard()

@router.get("/dashboard", response_class=HTMLResponse)
async def performance_dashboard():
    """Development performance dashboard."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Development Performance Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .metric { display: inline-block; margin: 10px; padding: 10px; border: 1px solid #ccc; }
            .chart-container { width: 400px; height: 300px; display: inline-block; margin: 10px; }
        </style>
    </head>
    <body>
        <h1>Development Performance Dashboard</h1>
        
        <div id="metrics"></div>
        
        <div class="chart-container">
            <canvas id="requestChart"></canvas>
        </div>
        
        <div class="chart-container">
            <canvas id="queryChart"></canvas>
        </div>
        
        <script>
            async function updateDashboard() {
                const response = await fetch('/dev/metrics');
                const data = await response.json();
                
                // Update metrics
                document.getElementById('metrics').innerHTML = `
                    <div class="metric">
                        <h3>Requests/min</h3>
                        <p>${data.requests_per_minute}</p>
                    </div>
                    <div class="metric">
                        <h3>Avg Request Time</h3>
                        <p>${data.avg_request_duration.toFixed(3)}s</p>
                    </div>
                    <div class="metric">
                        <h3>Queries/min</h3>
                        <p>${data.queries_per_minute}</p>
                    </div>
                    <div class="metric">
                        <h3>Avg Query Time</h3>
                        <p>${data.avg_query_duration.toFixed(3)}s</p>
                    </div>
                `;
            }
            
            // Update every 5 seconds
            setInterval(updateDashboard, 5000);
            updateDashboard();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@router.get("/metrics")
async def get_metrics():
    """Get current performance metrics."""
    return dashboard.get_performance_summary()
```

## Makefile Integration

### Performance-Optimized Development Commands

```makefile
# Development workflow performance targets
.PHONY: dev-fast dev-test-fast dev-lint-fast dev-format-fast

# Fast development startup
dev-fast:
	@echo "Starting fast development environment..."
	@./scripts/optimize-development-performance.sh
	docker-compose -f docker-compose.local.yml up -d --build
	@echo "Development environment ready!"
	@echo "Performance dashboard: http://localhost:8000/dev/dashboard"

# Fast testing with smart selection
dev-test-fast:
	@echo "Running fast tests with smart selection..."
	pytest --smart-select -x -v --tb=short

# Fast linting (changed files only)
dev-lint-fast:
	@echo "Running fast linting on changed files..."
	python scripts/fast-code-analysis.py

# Fast formatting (changed files only)
dev-format-fast:
	@echo "Formatting changed files..."
	@git diff --name-only HEAD~1 HEAD | grep '\.py$$' | xargs black --fast
	@git diff --name-only HEAD~1 HEAD | grep '\.py$$' | xargs isort --fast

# Complete fast development workflow
dev-workflow-fast: dev-format-fast dev-lint-fast dev-test-fast
	@echo "Fast development workflow completed!"

# Performance monitoring
dev-monitor:
	@echo "Starting development performance monitoring..."
	python scripts/monitor-development-performance.py

# Hot reload optimization
dev-hot-reload-optimize:
	@echo "Optimizing hot reload performance..."
	@./scripts/optimize-hot-reload.sh

# Clean up development artifacts
dev-clean-fast:
	@echo "Fast cleanup of development artifacts..."
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name ".pytest_cache" -type d -exec rm -rf {} +
	docker system prune -f
```

## Best Practices

### Development Workflow Optimization
1. **Use smart test selection**: Run only affected tests during development
2. **Optimize hot reload**: Use efficient file watching and volume mounts
3. **Fast feedback loops**: Minimize time between code change and feedback
4. **Incremental analysis**: Run code quality checks on changed files only
5. **Performance monitoring**: Track development workflow performance

### Testing Performance
1. **Parallel execution**: Use pytest-xdist for parallel test execution
2. **Fast test databases**: Use template databases for quick setup
3. **Smart fixtures**: Use appropriate fixture scopes
4. **Test categorization**: Mark tests by speed and type
5. **Performance regression detection**: Monitor test execution times

### Debugging Efficiency
1. **Fast logging setup**: Optimize logging for development
2. **Interactive debugging**: Use development-specific debug endpoints
3. **Performance profiling**: Profile slow functions automatically
4. **Memory monitoring**: Track memory usage during development
5. **Real-time dashboards**: Use performance dashboards for monitoring

### Code Quality Performance
1. **Incremental checks**: Run quality checks on changed files only
2. **Fast tools**: Use fast versions of linting and formatting tools
3. **Pre-commit optimization**: Use optimized pre-commit hooks
4. **Parallel processing**: Run multiple checks in parallel
5. **Caching**: Cache analysis results when possible

## Conclusion

This development workflow performance guide provides comprehensive strategies for optimizing the development experience while maintaining code quality and performance. By following these guidelines, you can achieve:

- **Fast feedback loops**: Minimize time between code changes and results
- **Efficient testing**: Run tests quickly with smart selection
- **Optimized debugging**: Debug efficiently with performance monitoring
- **Quality maintenance**: Maintain code quality without sacrificing speed
- **Performance awareness**: Monitor and optimize development workflow performance

Regular monitoring and incremental optimization of the development workflow will help maintain productivity as the application grows and evolves.