#!/usr/bin/env python3
"""
Hot Reload Setup Validation

This script validates that the hot reload setup is correctly configured
for local development. It checks files, configurations, and provides
recommendations for optimal development experience.

Usage:
    python scripts/validate-hot-reload-setup.py
    python scripts/validate-hot-reload-setup.py --verbose
    python scripts/validate-hot-reload-setup.py --fix
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Any


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color


class HotReloadValidator:
    """Validates hot reload setup and configuration."""
    
    def __init__(self, verbose: bool = False, fix: bool = False):
        self.verbose = verbose
        self.fix = fix
        self.issues: List[Tuple[str, str, str]] = []  # (level, category, message)
        self.checks_passed = 0
        self.checks_total = 0
    
    def print_status(self, message: str):
        """Print status message."""
        print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")
    
    def print_success(self, message: str):
        """Print success message."""
        print(f"{Colors.GREEN}[PASS]{Colors.NC} {message}")
        self.checks_passed += 1
    
    def print_warning(self, message: str):
        """Print warning message."""
        print(f"{Colors.YELLOW}[WARN]{Colors.NC} {message}")
        self.issues.append(("warning", "configuration", message))
    
    def print_error(self, message: str):
        """Print error message."""
        print(f"{Colors.RED}[FAIL]{Colors.NC} {message}")
        self.issues.append(("error", "configuration", message))
    
    def print_info(self, message: str):
        """Print info message."""
        if self.verbose:
            print(f"{Colors.CYAN}[INFO]{Colors.NC} {message}")
    
    def check_file_exists(self, file_path: str, description: str, required: bool = True) -> bool:
        """Check if a file exists."""
        self.checks_total += 1
        path = Path(file_path)
        
        if path.exists():
            self.print_success(f"{description}: {file_path}")
            return True
        else:
            if required:
                self.print_error(f"{description} not found: {file_path}")
            else:
                self.print_warning(f"{description} not found (optional): {file_path}")
            return False
    
    def check_file_executable(self, file_path: str, description: str) -> bool:
        """Check if a file is executable."""
        self.checks_total += 1
        path = Path(file_path)
        
        if path.exists() and os.access(path, os.X_OK):
            self.print_success(f"{description} is executable: {file_path}")
            return True
        else:
            self.print_error(f"{description} is not executable: {file_path}")
            return False
    
    def check_directory_exists(self, dir_path: str, description: str, create: bool = False) -> bool:
        """Check if a directory exists, optionally create it."""
        self.checks_total += 1
        path = Path(dir_path)
        
        if path.exists() and path.is_dir():
            self.print_success(f"{description}: {dir_path}")
            return True
        else:
            if create and self.fix:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    self.print_success(f"Created {description}: {dir_path}")
                    return True
                except Exception as e:
                    self.print_error(f"Failed to create {description}: {dir_path} - {e}")
                    return False
            else:
                self.print_error(f"{description} not found: {dir_path}")
                return False
    
    def check_file_content(self, file_path: str, expected_content: List[str], description: str) -> bool:
        """Check if a file contains expected content."""
        self.checks_total += 1
        path = Path(file_path)
        
        if not path.exists():
            self.print_error(f"{description} file not found: {file_path}")
            return False
        
        try:
            content = path.read_text()
            missing_content = []
            
            for expected in expected_content:
                if expected not in content:
                    missing_content.append(expected)
            
            if not missing_content:
                self.print_success(f"{description} contains all expected content")
                return True
            else:
                self.print_error(f"{description} missing content: {', '.join(missing_content)}")
                return False
        
        except Exception as e:
            self.print_error(f"Failed to read {description}: {e}")
            return False
    
    def validate_required_files(self):
        """Validate that all required files exist."""
        self.print_status("Checking required files...")
        
        required_files = [
            ("Dockerfile", "Docker configuration"),
            ("docker-compose.local.yml", "Local Docker Compose configuration"),
            (".env.local.example", "Environment template"),
            ("Makefile", "Build automation"),
            ("src/multimodal_librarian/main.py", "Main application file"),
        ]
        
        for file_path, description in required_files:
            self.check_file_exists(file_path, description, required=True)
    
    def validate_hot_reload_scripts(self):
        """Validate hot reload scripts."""
        self.print_status("Checking hot reload scripts...")
        
        scripts = [
            ("scripts/dev-with-hot-reload.sh", "Hot reload development script"),
            ("scripts/hot-reload-config.py", "Hot reload configuration script"),
            ("scripts/wait-for-services.sh", "Service wait script"),
            ("scripts/setup-development-directories.sh", "Directory setup script"),
        ]
        
        for script_path, description in scripts:
            if self.check_file_exists(script_path, description, required=True):
                self.check_file_executable(script_path, description)
    
    def validate_development_directories(self):
        """Validate development directories."""
        self.print_status("Checking development directories...")
        
        directories = [
            ("uploads", "Uploads directory", True),
            ("media", "Media directory", True),
            ("exports", "Exports directory", True),
            ("logs", "Logs directory", True),
            ("cache", "Cache directory", True),
            ("data", "Data directory", True),
            ("backups", "Backups directory", True),
        ]
        
        for dir_path, description, create in directories:
            self.check_directory_exists(dir_path, description, create=create)
    
    def validate_docker_configuration(self):
        """Validate Docker configuration for hot reload."""
        self.print_status("Checking Docker configuration...")
        
        # Check Dockerfile
        dockerfile_content = [
            "CMD [\"python\", \"-m\", \"uvicorn\"",
            "--reload",
            "--reload-dir",
            "--reload-include",
            "--reload-exclude"
        ]
        self.check_file_content("Dockerfile", dockerfile_content, "Dockerfile hot reload configuration")
        
        # Check docker-compose.local.yml
        compose_content = [
            "./src:/app/src:rw",
            "WATCHDOG_ENABLED=true",
            "RELOAD_DIRS=/app/src",
            "UVICORN_RELOAD=true"
        ]
        self.check_file_content("docker-compose.local.yml", compose_content, "Docker Compose hot reload configuration")
    
    def validate_makefile_targets(self):
        """Validate Makefile targets for hot reload."""
        self.print_status("Checking Makefile targets...")
        
        makefile_targets = [
            "dev-hot-reload:",
            "logs-hot-reload:",
            "restart-app:",
            "watch-files:",
            "dev-local-setup:"
        ]
        self.check_file_content("Makefile", makefile_targets, "Makefile hot reload targets")
    
    def validate_environment_template(self):
        """Validate environment template."""
        self.print_status("Checking environment template...")
        
        env_content = [
            "ENABLE_HOT_RELOAD=true",
            "WATCHDOG_ENABLED=true",
            "UVICORN_RELOAD=true",
            "RELOAD_DIRS=/app/src",
            "RELOAD_INCLUDES=",
            "RELOAD_EXCLUDES="
        ]
        self.check_file_content(".env.local.example", env_content, "Environment template hot reload configuration")
    
    def validate_python_dependencies(self):
        """Validate Python dependencies for hot reload."""
        self.print_status("Checking Python dependencies...")
        
        try:
            import uvicorn
            self.print_success("uvicorn is available")
        except ImportError:
            self.print_error("uvicorn not available - required for hot reload")
        
        try:
            import watchdog
            self.print_success("watchdog is available")
        except ImportError:
            self.print_warning("watchdog not available - file watching may not work optimally")
    
    def validate_git_configuration(self):
        """Validate Git configuration for development."""
        self.print_status("Checking Git configuration...")
        
        gitignore_path = Path(".gitignore")
        if gitignore_path.exists():
            gitignore_content = gitignore_path.read_text()
            
            # Check for important exclusions
            important_exclusions = [
                ".env.local",
                "/data/",
                "/cache/",
                "/logs/",
                "__pycache__"
            ]
            
            missing_exclusions = []
            for exclusion in important_exclusions:
                if exclusion not in gitignore_content:
                    missing_exclusions.append(exclusion)
            
            if not missing_exclusions:
                self.print_success("Git ignore configuration is complete")
            else:
                self.print_warning(f"Git ignore missing exclusions: {', '.join(missing_exclusions)}")
        else:
            self.print_warning(".gitignore file not found")
    
    def provide_recommendations(self):
        """Provide recommendations for improvement."""
        if not self.issues:
            return
        
        print(f"\n{Colors.YELLOW}📋 Recommendations:{Colors.NC}")
        print("=" * 50)
        
        # Group issues by category
        issues_by_category: Dict[str, List[Tuple[str, str]]] = {}
        for level, category, message in self.issues:
            if category not in issues_by_category:
                issues_by_category[category] = []
            issues_by_category[category].append((level, message))
        
        for category, category_issues in issues_by_category.items():
            print(f"\n{Colors.CYAN}{category.title()}:{Colors.NC}")
            for level, message in category_issues:
                color = Colors.RED if level == "error" else Colors.YELLOW
                print(f"  {color}•{Colors.NC} {message}")
        
        print(f"\n{Colors.BLUE}💡 Quick fixes:{Colors.NC}")
        print("  • Run with --fix to automatically create missing directories")
        print("  • Run 'make dev-hot-reload' to start development environment")
        print("  • Check documentation: docs/local-development-hot-reload.md")
    
    def run_validation(self):
        """Run all validation checks."""
        print(f"{Colors.PURPLE}🔥 Hot Reload Setup Validation{Colors.NC}")
        print("=" * 50)
        
        # Run all validation checks
        self.validate_required_files()
        self.validate_hot_reload_scripts()
        self.validate_development_directories()
        self.validate_docker_configuration()
        self.validate_makefile_targets()
        self.validate_environment_template()
        self.validate_python_dependencies()
        self.validate_git_configuration()
        
        # Print summary
        print(f"\n{Colors.BLUE}📊 Validation Summary:{Colors.NC}")
        print("=" * 30)
        
        success_rate = (self.checks_passed / self.checks_total * 100) if self.checks_total > 0 else 0
        color = Colors.GREEN if success_rate >= 80 else Colors.YELLOW if success_rate >= 60 else Colors.RED
        
        print(f"Checks passed: {color}{self.checks_passed}/{self.checks_total} ({success_rate:.1f}%){Colors.NC}")
        
        if self.issues:
            error_count = sum(1 for level, _, _ in self.issues if level == "error")
            warning_count = sum(1 for level, _, _ in self.issues if level == "warning")
            
            if error_count > 0:
                print(f"Errors: {Colors.RED}{error_count}{Colors.NC}")
            if warning_count > 0:
                print(f"Warnings: {Colors.YELLOW}{warning_count}{Colors.NC}")
            
            self.provide_recommendations()
        else:
            print(f"{Colors.GREEN}✅ All checks passed! Hot reload setup is ready.{Colors.NC}")
        
        return len([issue for issue in self.issues if issue[0] == "error"]) == 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate hot reload setup")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--fix", "-f", action="store_true", help="Automatically fix issues where possible")
    
    args = parser.parse_args()
    
    validator = HotReloadValidator(verbose=args.verbose, fix=args.fix)
    success = validator.run_validation()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()