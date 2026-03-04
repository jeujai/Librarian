#!/usr/bin/env python3
import requests

urls_to_test = [
    "http://localhost:8000/health",
    "http://127.0.0.1:8000/health"
]

for url in urls_to_test:
    try:
        print(f"Testing {url}...")
        response = requests.get(url, timeout=5)
        print(f"✓ Success: {response.status_code} - {response.json()}")
        break
    except Exception as e:
        print(f"✗ Failed: {e}")