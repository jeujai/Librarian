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
