#!/usr/bin/env python3
"""
Demo script to show CLI help and available options.
"""

import subprocess
import sys

def show_cli_help():
    """Show CLI help and available options."""
    print("🚀 Production Deployment Validation CLI - Help Demo")
    print("=" * 60)
    
    # Show help
    result = subprocess.run([
        sys.executable, '-m', 'multimodal_librarian.validation.cli', '--help'
    ], capture_output=True, text=True, cwd='src')
    
    if result.returncode == 0:
        print("CLI Help Output:")
        print("-" * 40)
        print(result.stdout)
    else:
        print(f"Error getting help: {result.stderr}")

if __name__ == '__main__':
    show_cli_help()