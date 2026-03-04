#!/bin/bash
#
# Development Workflow Optimizer
#
# This script provides workflow-specific optimizations for local development,
# including IDE integration, debugging enhancements, and productivity tools.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
OPTIMIZATION_LEVEL="standard"
ENABLE_IDE_INTEGRATION=true
ENABLE_DEBUG_TOOLS=true
ENABLE_PRODUCTIVITY_TOOLS=true
ENABLE_TESTING_OPTIMIZATION=true

# Function to print colored output
print_status() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} ✅ $1"
}

print_warning() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} ⚠️  $1"
}

print_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} ❌ $1"
}

print_info() {
    echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} 💡 $1"
}

# Function to show help
show_help() {
    echo "Development Workflow Optimizer"
    echo
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Commands:"
    echo "  optimize      Apply all workflow optimizations"
    echo "  ide           Set up IDE integration"
    echo "  debug         Set up debugging tools"
    echo "  productivity  Set up productivity tools"
    echo "  testing       Optimize testing workflow"
    echo "  status        Show optimization status"
    echo "  clean         Clean up optimization artifacts"
    echo
    echo "Options:"
    echo "  --level LEVEL         Optimization level: standard, advanced (default: standard)"
    echo "  --no-ide             Disable IDE integration"
    echo "  --no-debug           Disable debugging tools"
    echo "  --no-productivity    Disable productivity tools"
    echo "  --no-testing         Disable testing optimization"
    echo "  --help               Show this help message"
    echo
    echo "Examples:"
    echo "  $0 optimize                    # Apply all optimizations"
    echo "  $0 --level advanced optimize   # Advanced optimizations"
    echo "  $0 ide                         # Set up IDE integration only"
}

# Function to set up IDE integration
setup_ide_integration() {
    print_status "Setting up IDE integration..."
    
    # Create VS Code settings
    if [[ "$ENABLE_IDE_INTEGRATION" == "true" ]]; then
        mkdir -p .vscode
        
        # VS Code settings
        cat > .vscode/settings.json << 'EOF'
{
    "python.defaultInterpreterPath": "/app/venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "python.formatting.blackArgs": ["--line-length", "88"],
    "python.sortImports.args": ["--profile", "black"],
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": [
        "tests/",
        "-v",
        "--tb=short"
    ],
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        "**/.pytest_cache": true,
        "**/.mypy_cache": true,
        "**/node_modules": true,
        "**/.git": true,
        "**/.DS_Store": true
    },
    "files.watcherExclude": {
        "**/__pycache__/**": true,
        "**/.pytest_cache/**": true,
        "**/.mypy_cache/**": true,
        "**/node_modules/**": true,
        "**/.git/**": true
    },
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "terminal.integrated.env.linux": {
        "PYTHONPATH": "/app/src:/app"
    },
    "terminal.integrated.env.osx": {
        "PYTHONPATH": "/app/src:/app"
    },
    "docker.defaultRegistryPath": "multimodal-librarian",
    "remote.containers.defaultExtensions": [
        "ms-python.python",
        "ms-python.flake8",
        "ms-python.mypy-type-checker",
        "ms-python.black-formatter",
        "ms-python.isort"
    ]
}
EOF
        
        # VS Code launch configuration
        cat > .vscode/launch.json << 'EOF'
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: FastAPI",
            "type": "python",
            "request": "launch",
            "program": "/usr/local/bin/uvicorn",
            "args": [
                "multimodal_librarian.main:app",
                "--host", "0.0.0.0",
                "--port", "8000",
                "--reload"
            ],
            "cwd": "/app",
            "env": {
                "PYTHONPATH": "/app/src:/app",
                "ML_ENVIRONMENT": "local",
                "DATABASE_TYPE": "local",
                "DEBUG": "true"
            },
            "console": "integratedTerminal",
            "justMyCode": false
        },
        {
            "name": "Python: Debug Tests",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": [
                "tests/",
                "-v",
                "--tb=short"
            ],
            "cwd": "/app",
            "env": {
                "PYTHONPATH": "/app/src:/app",
                "ML_ENVIRONMENT": "local",
                "DATABASE_TYPE": "local"
            },
            "console": "integratedTerminal",
            "justMyCode": false
        },
        {
            "name": "Python: Attach to Container",
            "type": "python",
            "request": "attach",
            "connect": {
                "host": "localhost",
                "port": 5678
            },
            "pathMappings": [
                {
                    "localRoot": "${workspaceFolder}",
                    "remoteRoot": "/app"
                }
            ]
        }
    ]
}
EOF
        
        # VS Code tasks
        cat > .vscode/tasks.json << 'EOF'
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "Start Development Environment",
            "type": "shell",
            "command": "make",
            "args": ["dev-local-optimized"],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "shared"
            },
            "problemMatcher": []
        },
        {
            "label": "Run Tests",
            "type": "shell",
            "command": "make",
            "args": ["test-local-optimized"],
            "group": "test",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "shared"
            },
            "problemMatcher": []
        },
        {
            "label": "Format Code",
            "type": "shell",
            "command": "make",
            "args": ["format"],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "silent",
                "focus": false,
                "panel": "shared"
            },
            "problemMatcher": []
        },
        {
            "label": "Lint Code",
            "type": "shell",
            "command": "make",
            "args": ["lint"],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "shared"
            },
            "problemMatcher": []
        }
    ]
}
EOF
        
        # VS Code extensions recommendations
        cat > .vscode/extensions.json << 'EOF'
{
    "recommendations": [
        "ms-python.python",
        "ms-python.flake8",
        "ms-python.mypy-type-checker",
        "ms-python.black-formatter",
        "ms-python.isort",
        "ms-vscode-remote.remote-containers",
        "ms-azuretools.vscode-docker",
        "redhat.vscode-yaml",
        "ms-vscode.makefile-tools",
        "ms-python.debugpy",
        "charliermarsh.ruff"
    ]
}
EOF
        
        print_success "VS Code integration configured"
    fi
    
    # Create PyCharm/IntelliJ configuration
    if [[ -d ".idea" ]] || command -v pycharm >/dev/null 2>&1; then
        mkdir -p .idea
        
        # PyCharm run configuration
        mkdir -p .idea/runConfigurations
        cat > .idea/runConfigurations/FastAPI_Development.xml << 'EOF'
<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="FastAPI Development" type="PythonConfigurationType" factoryName="Python">
    <module name="multimodal-librarian" />
    <option name="INTERPRETER_OPTIONS" value="" />
    <option name="PARENT_ENVS" value="true" />
    <envs>
      <env name="PYTHONPATH" value="/app/src:/app" />
      <env name="ML_ENVIRONMENT" value="local" />
      <env name="DATABASE_TYPE" value="local" />
      <env name="DEBUG" value="true" />
    </envs>
    <option name="SDK_HOME" value="/app/venv/bin/python" />
    <option name="WORKING_DIRECTORY" value="/app" />
    <option name="IS_MODULE_SDK" value="false" />
    <option name="ADD_CONTENT_ROOTS" value="true" />
    <option name="ADD_SOURCE_ROOTS" value="true" />
    <option name="SCRIPT_NAME" value="uvicorn" />
    <option name="PARAMETERS" value="multimodal_librarian.main:app --host 0.0.0.0 --port 8000 --reload" />
    <option name="SHOW_COMMAND_LINE" value="false" />
    <option name="EMULATE_TERMINAL" value="false" />
    <option name="MODULE_MODE" value="true" />
    <option name="REDIRECT_INPUT" value="false" />
    <option name="INPUT_FILE" value="" />
    <method v="2" />
  </configuration>
</component>
EOF
        
        print_success "PyCharm/IntelliJ integration configured"
    fi
    
    # Create development environment file
    cat > .env.development << 'EOF'
# Development Environment Configuration
# This file contains IDE-specific and development workflow optimizations

# IDE Integration
ENABLE_IDE_INTEGRATION=true
IDE_DEBUG_PORT=5678
IDE_PROFILER_PORT=8089

# Development Workflow
DEVELOPMENT_MODE=true
SHOW_ERROR_DETAILS=true
ENABLE_DEBUG_TOOLBAR=true
AUTO_RELOAD_STATIC=true
STATIC_FILE_CACHE_DISABLED=true

# Debugging
ENABLE_DEBUGGER=true
DEBUGGER_PORT=5678
ENABLE_PROFILING=true
PROFILE_OUTPUT_DIR=/app/profiles

# Testing
TEST_DB_FAST_SETUP=true
PYTEST_CACHE_ENABLED=true
PYTEST_WORKERS=4

# Logging
LOG_FORMAT=development
LOG_COLORS=true
LOG_LEVEL=DEBUG

# Performance
DEV_OPTIMIZATION_ENABLED=true
DEV_MEMORY_OPTIMIZATION=true
DEV_CACHE_OPTIMIZATION=true
DEV_WORKFLOW_OPTIMIZATION=true
EOF
    
    print_success "IDE integration setup completed"
}

# Function to set up debugging tools
setup_debug_tools() {
    print_status "Setting up debugging tools..."
    
    if [[ "$ENABLE_DEBUG_TOOLS" == "true" ]]; then
        # Create debugging scripts
        mkdir -p scripts/debug
        
        # Debug server script
        cat > scripts/debug/debug-server.py << 'EOF'
#!/usr/bin/env python3
"""
Debug Server for Development

This script starts the application with debugging enabled,
including remote debugging capabilities and profiling.
"""

import os
import sys
import debugpy

# Enable remote debugging
debugpy.listen(("0.0.0.0", 5678))
print("🐛 Debug server listening on port 5678")
print("   Attach your debugger to localhost:5678")

# Set development environment
os.environ.update({
    'PYTHONPATH': '/app/src:/app',
    'ML_ENVIRONMENT': 'local',
    'DATABASE_TYPE': 'local',
    'DEBUG': 'true',
    'DEVELOPMENT_MODE': 'true',
    'ENABLE_DEBUGGER': 'true'
})

# Start the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "multimodal_librarian.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["/app/src"],
        log_level="debug"
    )
EOF
        
        chmod +x scripts/debug/debug-server.py
        
        # Performance profiler script
        cat > scripts/debug/profile-server.py << 'EOF'
#!/usr/bin/env python3
"""
Performance Profiler for Development

This script starts the application with performance profiling enabled.
"""

import os
import sys
import cProfile
import pstats
from pathlib import Path

# Set up profiling
profile_dir = Path("/app/profiles")
profile_dir.mkdir(exist_ok=True)

# Set environment
os.environ.update({
    'PYTHONPATH': '/app/src:/app',
    'ML_ENVIRONMENT': 'local',
    'DATABASE_TYPE': 'local',
    'ENABLE_PROFILING': 'true',
    'PROFILE_OUTPUT_DIR': str(profile_dir)
})

def run_with_profiling():
    """Run the application with profiling."""
    import uvicorn
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    try:
        uvicorn.run(
            "multimodal_librarian.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,  # Disable reload for accurate profiling
            log_level="info"
        )
    finally:
        profiler.disable()
        
        # Save profile results
        profile_file = profile_dir / f"profile_{int(time.time())}.prof"
        profiler.dump_stats(str(profile_file))
        
        # Generate text report
        with open(profile_dir / "profile_report.txt", "w") as f:
            stats = pstats.Stats(profiler, stream=f)
            stats.sort_stats('cumulative')
            stats.print_stats(50)  # Top 50 functions
        
        print(f"📊 Profile saved to: {profile_file}")
        print(f"📄 Report saved to: {profile_dir}/profile_report.txt")

if __name__ == "__main__":
    import time
    run_with_profiling()
EOF
        
        chmod +x scripts/debug/profile-server.py
        
        # Memory profiler script
        cat > scripts/debug/memory-profiler.py << 'EOF'
#!/usr/bin/env python3
"""
Memory Profiler for Development

This script monitors memory usage during development.
"""

import os
import sys
import time
import psutil
import threading
from pathlib import Path

def monitor_memory(duration=300, interval=5):
    """Monitor memory usage for specified duration."""
    print(f"🔍 Monitoring memory usage for {duration} seconds...")
    
    log_file = Path("/app/profiles/memory_usage.log")
    log_file.parent.mkdir(exist_ok=True)
    
    start_time = time.time()
    
    with open(log_file, "w") as f:
        f.write("timestamp,memory_mb,memory_percent,cpu_percent\n")
        
        while time.time() - start_time < duration:
            memory = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.1)
            
            timestamp = time.time()
            memory_mb = (memory.total - memory.available) / 1024 / 1024
            memory_percent = memory.percent
            
            f.write(f"{timestamp},{memory_mb:.1f},{memory_percent:.1f},{cpu:.1f}\n")
            f.flush()
            
            print(f"Memory: {memory_mb:.1f}MB ({memory_percent:.1f}%), CPU: {cpu:.1f}%")
            time.sleep(interval)
    
    print(f"📊 Memory usage log saved to: {log_file}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Memory profiler for development")
    parser.add_argument("--duration", "-d", type=int, default=300, help="Monitoring duration in seconds")
    parser.add_argument("--interval", "-i", type=int, default=5, help="Monitoring interval in seconds")
    
    args = parser.parse_args()
    monitor_memory(args.duration, args.interval)
EOF
        
        chmod +x scripts/debug/memory-profiler.py
        
        # Request tracer script
        cat > scripts/debug/request-tracer.py << 'EOF'
#!/usr/bin/env python3
"""
Request Tracer for Development

This script traces HTTP requests for debugging purposes.
"""

import time
import json
from pathlib import Path

class RequestTracer:
    """Simple request tracer for development."""
    
    def __init__(self):
        self.trace_file = Path("/app/profiles/request_traces.jsonl")
        self.trace_file.parent.mkdir(exist_ok=True)
    
    def trace_request(self, method, path, headers, body=None):
        """Trace an HTTP request."""
        trace_data = {
            "timestamp": time.time(),
            "method": method,
            "path": path,
            "headers": dict(headers) if headers else {},
            "body": body,
            "trace_id": f"trace_{int(time.time() * 1000)}"
        }
        
        with open(self.trace_file, "a") as f:
            f.write(json.dumps(trace_data) + "\n")
    
    def trace_response(self, status_code, headers, body=None, duration=None):
        """Trace an HTTP response."""
        trace_data = {
            "timestamp": time.time(),
            "type": "response",
            "status_code": status_code,
            "headers": dict(headers) if headers else {},
            "body": body,
            "duration_ms": duration * 1000 if duration else None
        }
        
        with open(self.trace_file, "a") as f:
            f.write(json.dumps(trace_data) + "\n")

# Global tracer instance
tracer = RequestTracer()

def enable_request_tracing():
    """Enable request tracing middleware."""
    print("🔍 Request tracing enabled")
    print(f"   Traces will be saved to: {tracer.trace_file}")
    
    # This would be integrated with FastAPI middleware
    # For now, it's a placeholder for the tracing infrastructure

if __name__ == "__main__":
    enable_request_tracing()
EOF
        
        chmod +x scripts/debug/request-tracer.py
        
        print_success "Debugging tools setup completed"
    fi
}

# Function to set up productivity tools
setup_productivity_tools() {
    print_status "Setting up productivity tools..."
    
    if [[ "$ENABLE_PRODUCTIVITY_TOOLS" == "true" ]]; then
        # Create productivity scripts
        mkdir -p scripts/productivity
        
        # Quick development commands
        cat > scripts/productivity/dev-commands.sh << 'EOF'
#!/bin/bash
#
# Quick Development Commands
#
# This script provides shortcuts for common development tasks.
#

# Quick restart
dev-restart() {
    echo "🔄 Quick restart..."
    make restart-optimized
}

# Quick test
dev-test() {
    echo "🧪 Running tests..."
    make test-local-optimized
}

# Quick format
dev-format() {
    echo "✨ Formatting code..."
    make format
}

# Quick lint
dev-lint() {
    echo "🔍 Linting code..."
    make lint
}

# Quick status
dev-status() {
    echo "📊 Development status..."
    make status-optimized
}

# Quick logs
dev-logs() {
    echo "📋 Showing logs..."
    make logs-optimized
}

# Quick health check
dev-health() {
    echo "🏥 Health check..."
    curl -s http://localhost:8000/health/simple | jq .
}

# Quick performance check
dev-perf() {
    echo "⚡ Performance check..."
    python scripts/dev-optimization-manager.py metrics
}

# Export functions
export -f dev-restart dev-test dev-format dev-lint dev-status dev-logs dev-health dev-perf

echo "🚀 Development commands loaded:"
echo "  dev-restart  - Quick restart"
echo "  dev-test     - Run tests"
echo "  dev-format   - Format code"
echo "  dev-lint     - Lint code"
echo "  dev-status   - Show status"
echo "  dev-logs     - Show logs"
echo "  dev-health   - Health check"
echo "  dev-perf     - Performance check"
EOF
        
        # Development dashboard
        cat > scripts/productivity/dev-dashboard.py << 'EOF'
#!/usr/bin/env python3
"""
Development Dashboard

This script provides a simple dashboard for monitoring development metrics.
"""

import time
import json
import requests
from datetime import datetime

class DevDashboard:
    """Simple development dashboard."""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
    
    def get_health_status(self):
        """Get application health status."""
        try:
            response = requests.get(f"{self.base_url}/health/simple", timeout=5)
            return response.json() if response.status_code == 200 else None
        except:
            return None
    
    def get_dev_metrics(self):
        """Get development metrics."""
        try:
            response = requests.get(f"{self.base_url}/dev/performance/metrics", timeout=5)
            return response.json() if response.status_code == 200 else None
        except:
            return None
    
    def display_dashboard(self):
        """Display the development dashboard."""
        print("🚀 Development Dashboard")
        print("=" * 50)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Health status
        health = self.get_health_status()
        if health:
            print("🏥 Health Status: ✅ Healthy")
        else:
            print("🏥 Health Status: ❌ Unhealthy")
        
        # Development metrics
        metrics = self.get_dev_metrics()
        if metrics and "metrics" in metrics:
            m = metrics["metrics"]
            
            if "memory" in m:
                memory = m["memory"]
                print(f"💾 Memory: {memory.get('used_mb', 0):.0f}MB ({memory.get('percent_used', 0):.1f}%)")
            
            if "cpu" in m:
                cpu = m["cpu"]
                print(f"🖥️  CPU: {cpu.get('percent_used', 0):.1f}%")
            
            if "disk" in m:
                disk = m["disk"]
                print(f"💿 Disk: {disk.get('used_gb', 0):.1f}GB ({disk.get('percent_used', 0):.1f}%)")
        
        print()
        print("📊 Quick Commands:")
        print("  make status-optimized    - Detailed status")
        print("  make logs-optimized      - View logs")
        print("  make test-local-optimized - Run tests")

if __name__ == "__main__":
    dashboard = DevDashboard()
    dashboard.display_dashboard()
EOF
        
        chmod +x scripts/productivity/dev-dashboard.py
        
        # Code quality checker
        cat > scripts/productivity/quality-check.sh << 'EOF'
#!/bin/bash
#
# Code Quality Checker
#
# This script runs comprehensive code quality checks.
#

set -e

echo "🔍 Running code quality checks..."

# Format check
echo "📝 Checking code formatting..."
if command -v black >/dev/null 2>&1; then
    black --check --diff src/ tests/ || {
        echo "❌ Code formatting issues found. Run 'make format' to fix."
        exit 1
    }
    echo "✅ Code formatting is good"
else
    echo "⚠️  Black not found, skipping format check"
fi

# Import sorting check
echo "📦 Checking import sorting..."
if command -v isort >/dev/null 2>&1; then
    isort --check-only --diff src/ tests/ || {
        echo "❌ Import sorting issues found. Run 'make format' to fix."
        exit 1
    }
    echo "✅ Import sorting is good"
else
    echo "⚠️  isort not found, skipping import check"
fi

# Linting
echo "🔍 Running linter..."
if command -v flake8 >/dev/null 2>&1; then
    flake8 src/ tests/ || {
        echo "❌ Linting issues found. Fix the issues above."
        exit 1
    }
    echo "✅ Linting passed"
else
    echo "⚠️  flake8 not found, skipping lint check"
fi

# Type checking
echo "🔬 Running type checker..."
if command -v mypy >/dev/null 2>&1; then
    mypy src/ || {
        echo "❌ Type checking issues found. Fix the issues above."
        exit 1
    }
    echo "✅ Type checking passed"
else
    echo "⚠️  mypy not found, skipping type check"
fi

echo "🎉 All code quality checks passed!"
EOF
        
        chmod +x scripts/productivity/quality-check.sh
        
        print_success "Productivity tools setup completed"
    fi
}

# Function to optimize testing workflow
optimize_testing_workflow() {
    print_status "Optimizing testing workflow..."
    
    if [[ "$ENABLE_TESTING_OPTIMIZATION" == "true" ]]; then
        # Create testing configuration
        cat > pytest.ini << 'EOF'
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --color=yes
    --durations=10
    --cache-clear
markers =
    unit: Unit tests
    integration: Integration tests
    performance: Performance tests
    slow: Slow tests (use -m "not slow" to skip)
    dev: Development-specific tests
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
EOF
        
        # Create test configuration
        mkdir -p tests/config
        cat > tests/config/test_settings.py << 'EOF'
"""
Test Configuration

This module provides configuration for testing in the development environment.
"""

import os
from pathlib import Path

# Test environment settings
TEST_ENV = {
    'ML_ENVIRONMENT': 'local',
    'DATABASE_TYPE': 'local',
    'DEBUG': 'true',
    'LOG_LEVEL': 'WARNING',  # Reduce log noise in tests
    'TEST_MODE': 'true',
    'DISABLE_TELEMETRY': 'true',
    'DISABLE_ANALYTICS': 'true'
}

# Test database settings
TEST_DB_SETTINGS = {
    'TEST_DB_FAST_SETUP': 'true',
    'TEST_DB_IN_MEMORY': 'true',
    'POSTGRES_POOL_SIZE': '2',  # Smaller pool for tests
    'POSTGRES_MAX_CONNECTIONS': '10'
}

# Performance test settings
PERFORMANCE_TEST_SETTINGS = {
    'PERFORMANCE_TEST_DURATION': '10',  # Shorter for development
    'PERFORMANCE_TEST_CONCURRENT_USERS': '5',
    'PERFORMANCE_TEST_TIMEOUT': '30'
}

def setup_test_environment():
    """Set up the test environment."""
    # Apply test environment variables
    for key, value in TEST_ENV.items():
        os.environ[key] = value
    
    for key, value in TEST_DB_SETTINGS.items():
        os.environ[key] = value
    
    # Create test directories
    test_dirs = [
        Path('/app/test_data'),
        Path('/app/test_uploads'),
        Path('/app/test_exports')
    ]
    
    for test_dir in test_dirs:
        test_dir.mkdir(exist_ok=True)

def cleanup_test_environment():
    """Clean up the test environment."""
    import shutil
    
    # Clean up test directories
    test_dirs = [
        Path('/app/test_data'),
        Path('/app/test_uploads'),
        Path('/app/test_exports')
    ]
    
    for test_dir in test_dirs:
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)
EOF
        
        # Create test utilities
        cat > tests/utils/test_helpers.py << 'EOF'
"""
Test Helpers

This module provides utility functions for testing.
"""

import time
import asyncio
from typing import Any, Dict, Optional
from contextlib import asynccontextmanager

class TestTimer:
    """Simple timer for performance testing."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
    
    def start(self):
        """Start the timer."""
        self.start_time = time.time()
    
    def stop(self):
        """Stop the timer."""
        self.end_time = time.time()
    
    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time

@asynccontextmanager
async def async_timer():
    """Async context manager for timing operations."""
    timer = TestTimer()
    timer.start()
    try:
        yield timer
    finally:
        timer.stop()

def assert_performance(timer: TestTimer, max_duration: float, operation: str = "operation"):
    """Assert that an operation completed within the expected time."""
    assert timer.elapsed <= max_duration, (
        f"{operation} took {timer.elapsed:.2f}s, expected <= {max_duration}s"
    )

def wait_for_condition(condition_func, timeout: float = 10.0, interval: float = 0.1):
    """Wait for a condition to become true."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition_func():
            return True
        time.sleep(interval)
    return False

async def async_wait_for_condition(condition_func, timeout: float = 10.0, interval: float = 0.1):
    """Async version of wait_for_condition."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if await condition_func() if asyncio.iscoroutinefunction(condition_func) else condition_func():
            return True
        await asyncio.sleep(interval)
    return False
EOF
        
        # Create test runner script
        cat > scripts/productivity/run-tests.sh << 'EOF'
#!/bin/bash
#
# Optimized Test Runner
#
# This script runs tests with optimizations for development workflow.
#

set -e

# Configuration
TEST_TYPE="all"
PARALLEL_WORKERS=4
COVERAGE_ENABLED=false
PERFORMANCE_TESTS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --type)
            TEST_TYPE="$2"
            shift 2
            ;;
        --parallel)
            PARALLEL_WORKERS="$2"
            shift 2
            ;;
        --coverage)
            COVERAGE_ENABLED=true
            shift
            ;;
        --performance)
            PERFORMANCE_TESTS=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --type TYPE          Test type: unit, integration, performance, all"
            echo "  --parallel WORKERS   Number of parallel workers (default: 4)"
            echo "  --coverage           Enable coverage reporting"
            echo "  --performance        Include performance tests"
            echo "  --help               Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "🧪 Running optimized tests..."
echo "   Type: $TEST_TYPE"
echo "   Parallel workers: $PARALLEL_WORKERS"
echo "   Coverage: $COVERAGE_ENABLED"
echo "   Performance tests: $PERFORMANCE_TESTS"

# Set up test environment
export ML_ENVIRONMENT=local
export DATABASE_TYPE=local
export TEST_MODE=true
export PYTEST_WORKERS=$PARALLEL_WORKERS

# Build pytest command
PYTEST_CMD="pytest"

# Add parallel execution
if [[ $PARALLEL_WORKERS -gt 1 ]]; then
    PYTEST_CMD="$PYTEST_CMD -n $PARALLEL_WORKERS"
fi

# Add coverage
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    PYTEST_CMD="$PYTEST_CMD --cov=multimodal_librarian --cov-report=html --cov-report=term"
fi

# Add test type filter
case $TEST_TYPE in
    unit)
        PYTEST_CMD="$PYTEST_CMD -m unit"
        ;;
    integration)
        PYTEST_CMD="$PYTEST_CMD -m integration"
        ;;
    performance)
        PYTEST_CMD="$PYTEST_CMD -m performance"
        ;;
    all)
        if [[ "$PERFORMANCE_TESTS" == "false" ]]; then
            PYTEST_CMD="$PYTEST_CMD -m 'not performance'"
        fi
        ;;
esac

# Run tests
echo "🚀 Executing: $PYTEST_CMD"
$PYTEST_CMD tests/

echo "✅ Tests completed successfully!"

# Show coverage report location if enabled
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    echo "📊 Coverage report available at: htmlcov/index.html"
fi
EOF
        
        chmod +x scripts/productivity/run-tests.sh
        
        print_success "Testing workflow optimization completed"
    fi
}

# Function to show optimization status
show_optimization_status() {
    print_status "Development Workflow Optimization Status"
    echo
    
    # Check IDE integration
    if [[ -f ".vscode/settings.json" ]]; then
        print_success "VS Code integration: Configured"
    else
        print_warning "VS Code integration: Not configured"
    fi
    
    if [[ -f ".idea/runConfigurations/FastAPI_Development.xml" ]]; then
        print_success "PyCharm integration: Configured"
    else
        print_warning "PyCharm integration: Not configured"
    fi
    
    # Check debugging tools
    if [[ -f "scripts/debug/debug-server.py" ]]; then
        print_success "Debugging tools: Available"
    else
        print_warning "Debugging tools: Not available"
    fi
    
    # Check productivity tools
    if [[ -f "scripts/productivity/dev-commands.sh" ]]; then
        print_success "Productivity tools: Available"
    else
        print_warning "Productivity tools: Not available"
    fi
    
    # Check testing optimization
    if [[ -f "pytest.ini" ]]; then
        print_success "Testing optimization: Configured"
    else
        print_warning "Testing optimization: Not configured"
    fi
    
    echo
    print_info "Use '$0 optimize' to apply all optimizations"
}

# Function to clean up optimization artifacts
cleanup_optimizations() {
    print_status "Cleaning up workflow optimization artifacts..."
    
    # Remove IDE configurations
    rm -rf .vscode .idea
    
    # Remove debug scripts
    rm -rf scripts/debug scripts/productivity
    
    # Remove test configurations
    rm -f pytest.ini .env.development
    rm -rf tests/config tests/utils
    
    print_success "Cleanup completed"
}

# Parse command line arguments
COMMAND=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --level)
            OPTIMIZATION_LEVEL="$2"
            shift 2
            ;;
        --no-ide)
            ENABLE_IDE_INTEGRATION=false
            shift
            ;;
        --no-debug)
            ENABLE_DEBUG_TOOLS=false
            shift
            ;;
        --no-productivity)
            ENABLE_PRODUCTIVITY_TOOLS=false
            shift
            ;;
        --no-testing)
            ENABLE_TESTING_OPTIMIZATION=false
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        optimize|ide|debug|productivity|testing|status|clean)
            COMMAND="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set default command
COMMAND="${COMMAND:-optimize}"

# Main execution
main() {
    print_status "🛠️  Development Workflow Optimizer"
    print_info "Optimization level: $OPTIMIZATION_LEVEL"
    print_info "Command: $COMMAND"
    echo
    
    case $COMMAND in
        optimize)
            setup_ide_integration
            setup_debug_tools
            setup_productivity_tools
            optimize_testing_workflow
            
            print_success "🎉 Development workflow optimization completed!"
            print_info "Available tools:"
            print_info "  • IDE integration (VS Code, PyCharm)"
            print_info "  • Debugging tools (remote debugging, profiling)"
            print_info "  • Productivity shortcuts (dev-* commands)"
            print_info "  • Optimized testing workflow"
            ;;
        ide)
            setup_ide_integration
            ;;
        debug)
            setup_debug_tools
            ;;
        productivity)
            setup_productivity_tools
            ;;
        testing)
            optimize_testing_workflow
            ;;
        status)
            show_optimization_status
            ;;
        clean)
            cleanup_optimizations
            ;;
        *)
            print_error "Unknown command: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"