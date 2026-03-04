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
