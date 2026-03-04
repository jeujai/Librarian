#!/usr/bin/env python3
"""
Development Optimization Manager

This script provides a command-line interface for managing development-specific
optimizations in the Multimodal Librarian local development environment.
"""

import os
import sys
import time
import json
import argparse
import asyncio
from pathlib import Path
from typing import Dict, List, Any
import requests


class DevOptimizationManager:
    """Manager for development optimizations."""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.api_base = f"{self.base_url}/dev"
        
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to the development API."""
        url = f"{self.api_base}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=30, **kwargs)
            elif method.upper() == "POST":
                response = requests.post(url, timeout=30, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.ConnectionError:
            print("❌ Error: Cannot connect to development server")
            print("   Make sure the development environment is running:")
            print("   make dev-local-optimized")
            sys.exit(1)
        except requests.exceptions.Timeout:
            print("❌ Error: Request timed out")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            print(f"❌ Error: HTTP {e.response.status_code}")
            if e.response.text:
                try:
                    error_data = e.response.json()
                    print(f"   {error_data.get('detail', 'Unknown error')}")
                except:
                    print(f"   {e.response.text}")
            sys.exit(1)
    
    def get_status(self) -> Dict[str, Any]:
        """Get optimization status."""
        return self._make_request("GET", "/optimization/status")
    
    def apply_optimizations(self) -> Dict[str, Any]:
        """Apply all optimizations."""
        return self._make_request("POST", "/optimization/apply")
    
    def get_recommendations(self) -> Dict[str, Any]:
        """Get optimization recommendations."""
        return self._make_request("GET", "/optimization/recommendations")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return self._make_request("GET", "/performance/metrics")
    
    def monitor_performance(self, duration: int) -> Dict[str, Any]:
        """Monitor performance for specified duration."""
        return self._make_request("POST", f"/performance/monitor?duration={duration}")
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Get environment information."""
        return self._make_request("GET", "/environment/info")
    
    def clear_cache(self) -> Dict[str, Any]:
        """Clear development cache."""
        return self._make_request("POST", "/cache/clear")
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information."""
        return self._make_request("GET", "/debug/info")
    
    def reset_optimizations(self) -> Dict[str, Any]:
        """Reset optimizations to defaults."""
        return self._make_request("POST", "/optimization/reset")


def print_status(data: Dict[str, Any]):
    """Print optimization status in a formatted way."""
    print("🚀 Development Optimization Status")
    print("=" * 50)
    
    if not data.get("enabled"):
        print("❌ Development optimization is disabled")
        return
    
    status = data.get("status", {})
    enabled_opts = status.get("enabled_optimizations", {})
    applied_opts = status.get("applied_optimizations", {})
    
    print("✅ Development optimization is enabled")
    print()
    
    print("📊 Enabled Optimizations:")
    for opt_name, enabled in enabled_opts.items():
        status_icon = "✅" if enabled else "❌"
        print(f"  {status_icon} {opt_name.replace('_', ' ').title()}")
    
    print()
    print("🔧 Applied Optimizations:")
    for category, opts in applied_opts.items():
        if opts:
            print(f"  {category.title()}:")
            for opt_name, applied in opts.items():
                status_icon = "✅" if applied else "❌"
                print(f"    {status_icon} {opt_name.replace('_', ' ').title()}")
    
    # System metrics
    system_metrics = data.get("system_metrics", {})
    if system_metrics and "memory" in system_metrics:
        print()
        print("💾 System Metrics:")
        memory = system_metrics["memory"]
        cpu = system_metrics["cpu"]
        
        print(f"  Memory: {memory.get('used_mb', 0):.0f}MB / {memory.get('total_mb', 0):.0f}MB ({memory.get('percent_used', 0):.1f}%)")
        print(f"  CPU: {cpu.get('percent_used', 0):.1f}% ({cpu.get('count', 0)} cores)")


def print_recommendations(data: Dict[str, Any]):
    """Print optimization recommendations."""
    print("🎯 Optimization Recommendations")
    print("=" * 50)
    
    recommendations = data.get("recommendations", [])
    if not recommendations:
        print("✅ No recommendations - system appears well optimized!")
        return
    
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. {rec}")
    
    # System metrics summary
    system_metrics = data.get("system_metrics", {})
    if system_metrics and "memory" in system_metrics:
        print()
        print("📊 Current System State:")
        memory = system_metrics["memory"]
        cpu = system_metrics["cpu"]
        disk = system_metrics.get("disk", {})
        
        print(f"  Memory Usage: {memory.get('percent_used', 0):.1f}%")
        print(f"  CPU Usage: {cpu.get('percent_used', 0):.1f}%")
        if disk:
            print(f"  Disk Usage: {disk.get('percent_used', 0):.1f}%")


def print_performance_metrics(data: Dict[str, Any]):
    """Print performance metrics."""
    print("📊 Performance Metrics")
    print("=" * 50)
    
    metrics = data.get("metrics", {})
    if not metrics:
        print("❌ No metrics available")
        return
    
    # Memory metrics
    memory = metrics.get("memory", {})
    if memory:
        print("💾 Memory:")
        print(f"  Total: {memory.get('total_mb', 0):.0f} MB")
        print(f"  Used: {memory.get('used_mb', 0):.0f} MB ({memory.get('percent_used', 0):.1f}%)")
        print(f"  Available: {memory.get('available_mb', 0):.0f} MB")
    
    # CPU metrics
    cpu = metrics.get("cpu", {})
    if cpu:
        print()
        print("🖥️  CPU:")
        print(f"  Usage: {cpu.get('percent_used', 0):.1f}%")
        print(f"  Cores: {cpu.get('count', 0)}")
        if cpu.get('load_average'):
            load_avg = cpu['load_average']
            print(f"  Load Average: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}")
    
    # Disk metrics
    disk = metrics.get("disk", {})
    if disk:
        print()
        print("💿 Disk:")
        print(f"  Total: {disk.get('total_gb', 0):.1f} GB")
        print(f"  Used: {disk.get('used_gb', 0):.1f} GB ({disk.get('percent_used', 0):.1f}%)")
        print(f"  Free: {disk.get('free_gb', 0):.1f} GB")


def print_environment_info(data: Dict[str, Any]):
    """Print environment information."""
    print("🌍 Development Environment Information")
    print("=" * 50)
    
    env = data.get("environment", {})
    
    # System info
    print("🖥️  System:")
    print(f"  Python: {env.get('python_version', 'Unknown').split()[0]}")
    print(f"  Platform: {env.get('platform', 'Unknown')}")
    print(f"  Architecture: {env.get('architecture', ['Unknown'])[0]}")
    
    # Environment variables
    env_vars = env.get("environment_variables", {})
    print()
    print("🔧 Environment Variables:")
    for key, value in env_vars.items():
        if value is not None:
            print(f"  {key}: {value}")
    
    # Optimization status
    opt_status = env.get("optimization_status", {})
    print()
    print("⚡ Optimization Status:")
    for key, value in opt_status.items():
        status_icon = "✅" if value else "❌"
        print(f"  {status_icon} {key.replace('_', ' ').title()}: {value}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Development Optimization Manager for Multimodal Librarian"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Status command
    subparsers.add_parser("status", help="Show optimization status")
    
    # Apply command
    subparsers.add_parser("apply", help="Apply all optimizations")
    
    # Recommendations command
    subparsers.add_parser("recommendations", help="Get optimization recommendations")
    
    # Metrics command
    subparsers.add_parser("metrics", help="Show performance metrics")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor performance")
    monitor_parser.add_argument(
        "--duration", "-d", type=int, default=60,
        help="Monitoring duration in seconds (default: 60)"
    )
    
    # Environment command
    subparsers.add_parser("env", help="Show environment information")
    
    # Cache command
    subparsers.add_parser("clear-cache", help="Clear development cache")
    
    # Debug command
    subparsers.add_parser("debug", help="Show debug information")
    
    # Reset command
    subparsers.add_parser("reset", help="Reset optimizations to defaults")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = DevOptimizationManager()
    
    try:
        if args.command == "status":
            data = manager.get_status()
            print_status(data)
            
        elif args.command == "apply":
            print("🔧 Applying development optimizations...")
            data = manager.apply_optimizations()
            if data.get("success"):
                print("✅ Optimizations applied successfully!")
                result = data.get("result", {})
                applied = result.get("applied", [])
                failed = result.get("failed", [])
                
                if applied:
                    print(f"   Applied: {', '.join(applied)}")
                if failed:
                    print(f"   Failed: {', '.join(failed)}")
            else:
                print("❌ Failed to apply optimizations")
                
        elif args.command == "recommendations":
            data = manager.get_recommendations()
            print_recommendations(data)
            
        elif args.command == "metrics":
            data = manager.get_performance_metrics()
            print_performance_metrics(data)
            
        elif args.command == "monitor":
            print(f"📊 Monitoring performance for {args.duration} seconds...")
            data = manager.monitor_performance(args.duration)
            
            impact = data.get("performance_impact", {})
            print()
            print("📈 Performance Impact:")
            print(f"  Memory Change: {impact.get('memory_change_mb', 0):+.1f} MB")
            print(f"  Average CPU: {impact.get('cpu_average', 0):.1f}%")
            print(f"  Effectiveness: {impact.get('optimization_effectiveness', 'unknown').title()}")
            
        elif args.command == "env":
            data = manager.get_environment_info()
            print_environment_info(data)
            
        elif args.command == "clear-cache":
            print("🧹 Clearing development cache...")
            data = manager.clear_cache()
            if data.get("success"):
                print(f"✅ {data.get('message', 'Cache cleared successfully')}")
            else:
                print("❌ Failed to clear cache")
                
        elif args.command == "debug":
            data = manager.get_debug_info()
            print("🐛 Debug Information")
            print("=" * 50)
            print(json.dumps(data, indent=2))
            
        elif args.command == "reset":
            print("🔄 Resetting optimizations to defaults...")
            data = manager.reset_optimizations()
            if data.get("success"):
                print("✅ Optimizations reset successfully!")
            else:
                print("❌ Failed to reset optimizations")
    
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()