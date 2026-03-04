#!/usr/bin/env python3
"""
Debug Manager

Unified debugging manager that orchestrates all debugging tools and provides
a single entry point for comprehensive system diagnostics.
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DebugManager:
    """Unified debugging manager."""
    
    def __init__(self):
        self.debug_dir = Path(__file__).parent
        self.output_dir = Path("debug_output")
        self.output_dir.mkdir(exist_ok=True)
        
        # Available debug tools
        self.tools = {
            "local-debug-cli": self.debug_dir / "local-debug-cli.py",
            "database-debug-tool": self.debug_dir / "database-debug-tool.py",
            "container-inspector": self.debug_dir / "container-inspector.py",
            "log-analyzer": self.debug_dir / "log-analyzer.py",
            "network-diagnostics": self.debug_dir / "network-diagnostics.py"
        }
    
    def run_tool(self, tool_name: str, args: List[str]) -> Dict[str, Any]:
        """Run a specific debug tool with arguments."""
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        tool_path = self.tools[tool_name]
        cmd = [sys.executable, str(tool_path)] + args
        
        logger.info(f"🔧 Running {tool_name}: {' '.join(args)}")
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            execution_time = time.time() - start_time
            
            return {
                "tool": tool_name,
                "args": args,
                "success": True,
                "execution_time": execution_time,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        
        except subprocess.CalledProcessError as e:
            return {
                "tool": tool_name,
                "args": args,
                "success": False,
                "execution_time": time.time() - start_time,
                "stdout": e.stdout,
                "stderr": e.stderr,
                "returncode": e.returncode,
                "error": str(e)
            }
    
    def quick_health_check(self) -> Dict[str, Any]:
        """Run a quick health check of the system."""
        logger.info("🏥 Running quick health check...")
        
        health_check = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "overall_status": "unknown",
            "issues": [],
            "recommendations": []
        }
        
        # Check Docker services
        logger.info("  Checking Docker services...")
        services_result = self.run_tool("local-debug-cli", ["services"])
        health_check["checks"]["docker_services"] = {
            "success": services_result["success"],
            "details": "Docker services check completed"
        }
        
        if not services_result["success"]:
            health_check["issues"].append("Docker services check failed")
            health_check["recommendations"].append("Check Docker daemon and service configuration")
        
        # Check database connections
        logger.info("  Checking database connections...")
        db_result = self.run_tool("database-debug-tool", ["diagnostics"])
        health_check["checks"]["database_connections"] = {
            "success": db_result["success"],
            "details": "Database connections check completed"
        }
        
        if not db_result["success"]:
            health_check["issues"].append("Database connections check failed")
            health_check["recommendations"].append("Verify database services are running and accessible")
        
        # Check network connectivity
        logger.info("  Checking network connectivity...")
        network_result = self.run_tool("network-diagnostics", ["ports"])
        health_check["checks"]["network_connectivity"] = {
            "success": network_result["success"],
            "details": "Network connectivity check completed"
        }
        
        if not network_result["success"]:
            health_check["issues"].append("Network connectivity check failed")
            health_check["recommendations"].append("Check port availability and network configuration")
        
        # Determine overall status
        failed_checks = sum(1 for check in health_check["checks"].values() if not check["success"])
        
        if failed_checks == 0:
            health_check["overall_status"] = "healthy"
        elif failed_checks <= 1:
            health_check["overall_status"] = "degraded"
        else:
            health_check["overall_status"] = "critical"
        
        logger.info(f"🏥 Health check complete: {health_check['overall_status']}")
        
        return health_check
    
    def comprehensive_diagnostics(self) -> Dict[str, Any]:
        """Run comprehensive system diagnostics."""
        logger.info("🔬 Running comprehensive diagnostics...")
        
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "tools_executed": [],
            "results": {},
            "summary": {
                "total_tools": 0,
                "successful_tools": 0,
                "failed_tools": 0,
                "total_execution_time": 0
            }
        }
        
        # Define diagnostic tasks
        diagnostic_tasks = [
            ("local-debug-cli", ["status"]),
            ("database-debug-tool", ["diagnostics"]),
            ("container-inspector", ["inspect"]),
            ("log-analyzer", ["analyze", "--lines", "500"]),
            ("network-diagnostics", ["report"])
        ]
        
        start_time = time.time()
        
        for tool_name, args in diagnostic_tasks:
            logger.info(f"🔧 Running {tool_name}...")
            
            result = self.run_tool(tool_name, args)
            diagnostics["results"][tool_name] = result
            diagnostics["tools_executed"].append(tool_name)
            diagnostics["summary"]["total_tools"] += 1
            
            if result["success"]:
                diagnostics["summary"]["successful_tools"] += 1
                logger.info(f"  ✅ {tool_name} completed successfully")
            else:
                diagnostics["summary"]["failed_tools"] += 1
                logger.error(f"  ❌ {tool_name} failed")
        
        diagnostics["summary"]["total_execution_time"] = time.time() - start_time
        
        # Save comprehensive report
        report_file = self.output_dir / f"comprehensive_diagnostics_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(diagnostics, f, indent=2, default=str)
        
        logger.info(f"📄 Comprehensive diagnostics saved to: {report_file}")
        logger.info(f"📊 Summary: {diagnostics['summary']['successful_tools']}/{diagnostics['summary']['total_tools']} tools successful")
        
        return diagnostics
    
    def monitor_system(self, duration: int = 300) -> Dict[str, Any]:
        """Monitor system for a specified duration."""
        logger.info(f"📊 Monitoring system for {duration} seconds...")
        
        monitoring = {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration,
            "monitoring_tasks": [],
            "results": {}
        }
        
        # Start monitoring tasks
        tasks = [
            ("local-debug-cli", ["monitor", "--duration", str(duration)]),
            ("database-debug-tool", ["performance", "--duration", str(duration)])
        ]
        
        for tool_name, args in tasks:
            logger.info(f"🔧 Starting {tool_name} monitoring...")
            result = self.run_tool(tool_name, args)
            monitoring["results"][tool_name] = result
            monitoring["monitoring_tasks"].append(tool_name)
        
        # Save monitoring report
        report_file = self.output_dir / f"system_monitoring_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(monitoring, f, indent=2, default=str)
        
        logger.info(f"📄 Monitoring report saved to: {report_file}")
        
        return monitoring
    
    def troubleshoot_issue(self, issue_type: str) -> Dict[str, Any]:
        """Run targeted troubleshooting for specific issue types."""
        logger.info(f"🔍 Troubleshooting issue: {issue_type}")
        
        troubleshooting = {
            "issue_type": issue_type,
            "timestamp": datetime.now().isoformat(),
            "steps": [],
            "results": {},
            "recommendations": []
        }
        
        if issue_type == "service_not_starting":
            steps = [
                ("container-inspector", ["inspect"]),
                ("log-analyzer", ["search", "ERROR|CRITICAL|FATAL"]),
                ("network-diagnostics", ["ports"])
            ]
            troubleshooting["recommendations"] = [
                "Check container logs for startup errors",
                "Verify port availability",
                "Check resource limits and dependencies"
            ]
        
        elif issue_type == "database_connection":
            steps = [
                ("database-debug-tool", ["diagnostics"]),
                ("network-diagnostics", ["connectivity"]),
                ("log-analyzer", ["search", "connection.*failed|timeout"])
            ]
            troubleshooting["recommendations"] = [
                "Verify database services are running",
                "Check network connectivity",
                "Validate connection credentials"
            ]
        
        elif issue_type == "performance":
            steps = [
                ("local-debug-cli", ["monitor", "--duration", "60"]),
                ("database-debug-tool", ["performance", "--duration", "60"]),
                ("log-analyzer", ["search", "slow|timeout|performance"])
            ]
            troubleshooting["recommendations"] = [
                "Monitor resource usage",
                "Check for slow queries",
                "Analyze performance patterns"
            ]
        
        elif issue_type == "network":
            steps = [
                ("network-diagnostics", ["report"]),
                ("container-inspector", ["inspect"]),
                ("log-analyzer", ["search", "connection.*refused|network"])
            ]
            troubleshooting["recommendations"] = [
                "Check Docker network configuration",
                "Verify port mappings",
                "Test inter-service connectivity"
            ]
        
        else:
            logger.error(f"Unknown issue type: {issue_type}")
            return troubleshooting
        
        # Execute troubleshooting steps
        for tool_name, args in steps:
            logger.info(f"🔧 Running {tool_name}...")
            result = self.run_tool(tool_name, args)
            troubleshooting["results"][tool_name] = result
            troubleshooting["steps"].append(f"{tool_name}: {' '.join(args)}")
        
        # Save troubleshooting report
        report_file = self.output_dir / f"troubleshooting_{issue_type}_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(troubleshooting, f, indent=2, default=str)
        
        logger.info(f"📄 Troubleshooting report saved to: {report_file}")
        
        return troubleshooting
    
    def cleanup_debug_outputs(self, days_old: int = 7) -> Dict[str, Any]:
        """Clean up old debug output files."""
        logger.info(f"🧹 Cleaning up debug outputs older than {days_old} days...")
        
        cleanup_result = {
            "timestamp": datetime.now().isoformat(),
            "days_old": days_old,
            "files_removed": [],
            "total_size_freed": 0,
            "errors": []
        }
        
        cutoff_time = time.time() - (days_old * 24 * 60 * 60)
        
        try:
            for file_path in self.output_dir.rglob("*"):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        cleanup_result["files_removed"].append(str(file_path))
                        cleanup_result["total_size_freed"] += file_size
                        logger.info(f"  🗑️ Removed: {file_path}")
                    except Exception as e:
                        cleanup_result["errors"].append(f"Failed to remove {file_path}: {e}")
                        logger.error(f"  ❌ Failed to remove {file_path}: {e}")
        
        except Exception as e:
            cleanup_result["errors"].append(f"Cleanup failed: {e}")
            logger.error(f"Cleanup failed: {e}")
        
        size_mb = cleanup_result["total_size_freed"] / 1024 / 1024
        logger.info(f"🧹 Cleanup complete: {len(cleanup_result['files_removed'])} files, {size_mb:.1f}MB freed")
        
        return cleanup_result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Debug Manager - Unified debugging interface")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Quick health check
    health_parser = subparsers.add_parser("health", help="Run quick health check")
    
    # Comprehensive diagnostics
    diag_parser = subparsers.add_parser("diagnostics", help="Run comprehensive diagnostics")
    
    # System monitoring
    monitor_parser = subparsers.add_parser("monitor", help="Monitor system")
    monitor_parser.add_argument("--duration", "-d", type=int, default=300, help="Monitoring duration in seconds")
    
    # Troubleshooting
    trouble_parser = subparsers.add_parser("troubleshoot", help="Run targeted troubleshooting")
    trouble_parser.add_argument("issue_type", choices=["service_not_starting", "database_connection", "performance", "network"], help="Type of issue to troubleshoot")
    
    # Tool execution
    tool_parser = subparsers.add_parser("tool", help="Run specific debug tool")
    tool_parser.add_argument("tool_name", help="Name of the tool to run")
    tool_parser.add_argument("args", nargs="*", help="Arguments to pass to the tool")
    
    # Cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old debug outputs")
    cleanup_parser.add_argument("--days", type=int, default=7, help="Remove files older than N days")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize manager
    manager = DebugManager()
    
    # Execute command
    if args.command == "health":
        result = manager.quick_health_check()
        
        print("\n" + "="*50)
        print("SYSTEM HEALTH CHECK")
        print("="*50)
        print(f"Overall Status: {result['overall_status'].upper()}")
        
        print("\nChecks:")
        for check_name, check_result in result["checks"].items():
            status_icon = "✅" if check_result["success"] else "❌"
            print(f"  {status_icon} {check_name}: {check_result['details']}")
        
        if result["issues"]:
            print("\nIssues Found:")
            for issue in result["issues"]:
                print(f"  ⚠️ {issue}")
        
        if result["recommendations"]:
            print("\nRecommendations:")
            for rec in result["recommendations"]:
                print(f"  💡 {rec}")
    
    elif args.command == "diagnostics":
        manager.comprehensive_diagnostics()
    
    elif args.command == "monitor":
        manager.monitor_system(args.duration)
    
    elif args.command == "troubleshoot":
        result = manager.troubleshoot_issue(args.issue_type)
        
        print("\n" + "="*50)
        print(f"TROUBLESHOOTING: {args.issue_type.upper()}")
        print("="*50)
        
        print("Steps Executed:")
        for step in result["steps"]:
            print(f"  🔧 {step}")
        
        print("\nRecommendations:")
        for rec in result["recommendations"]:
            print(f"  💡 {rec}")
    
    elif args.command == "tool":
        result = manager.run_tool(args.tool_name, args.args)
        
        if result["success"]:
            print(result["stdout"])
        else:
            print(f"Tool failed: {result.get('error', 'Unknown error')}")
            if result["stderr"]:
                print(f"Error output: {result['stderr']}")
    
    elif args.command == "cleanup":
        manager.cleanup_debug_outputs(args.days)


if __name__ == "__main__":
    main()