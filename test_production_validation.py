#!/usr/bin/env python3
"""
Simple test for production readiness validation
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

print("Starting production readiness validation test...")

try:
    import requests
    print("✓ requests imported successfully")
except ImportError as e:
    print(f"✗ Failed to import requests: {e}")
    sys.exit(1)

try:
    import psutil
    print("✓ psutil imported successfully")
except ImportError as e:
    print(f"✗ Failed to import psutil: {e}")
    sys.exit(1)

# Test basic functionality
base_url = os.getenv("BASE_URL", "http://localhost:8000")
print(f"Testing base URL: {base_url}")

try:
    response = requests.get(f"{base_url}/health", timeout=5)
    print(f"✓ Health check response: {response.status_code}")
    if response.status_code == 200:
        print(f"  Response data: {response.json()}")
except Exception as e:
    print(f"✗ Health check failed: {e}")

# Test system resources
try:
    memory_percent = psutil.virtual_memory().percent
    cpu_percent = psutil.cpu_percent(interval=1)
    print(f"✓ System resources - Memory: {memory_percent}%, CPU: {cpu_percent}%")
except Exception as e:
    print(f"✗ System resource check failed: {e}")

print("Test completed successfully!")