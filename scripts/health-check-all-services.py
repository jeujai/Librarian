#!/usr/bin/env python3
"""
All Services Health Check Orchestrator

Orchestrates health checks for all local development services using dedicated
health check scripts. Provides comprehensive reporting and status aggregation.
"""

import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

class ServiceHealthOrchestrator:
    """Orchestrates health checks for all services."""
    
    def __init__(self, scripts_dir: str = "scripts"):
        self.scripts_dir = scripts_dir
        self.service_scripts = {
            "postgresql": "health-check-postgresql.py",
            "neo4j": "health-check-neo4j.py", 
            "milvus": "health-check-milvus.py",
            "redis": "health-check-redis.py"
        }
        
    def run_service_health_check(self, service: str, timeout: int = 60) -> Dict[str, Any]:
        """Run health check for a specific service."""
        script_name = self.service_scripts.get(service)
        if not script_name:
            return {
                "service": service,
                "status": "CRITICAL",
                "message": f"No health check script found for {service}",
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": 0,
                "checks": {}
            }
        
        script_path = os.path.join(self.scripts_dir, script_name)
        if not os.path.exists(script_path):
            return {
                "service": service,
                "status": "CRITICAL", 
                "message": f"Health check script not found: {script_path}",
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": 0,
                "checks": {}
            }
        
        start_time = time.time()
        
        try:
            # Run the health check script
            result = subprocess.run(
                [sys.executable, script_path, "--json"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                # Parse JSON output
                try:
                    health_data = json.loads(result.stdout)
                    health_data["script_exit_code"] = result.returncode
                    return health_data
                except json.JSONDecodeError as e:
                    return {
                        "service": service,
                        "status": "CRITICAL",
                        "message": f"Failed to parse health check output: {str(e)}",
                        "timestamp": datetime.now().isoformat(),
                        "duration_seconds": duration,
                        "script_exit_code": result.returncode,
                        "raw_output": result.stdout,
                        "checks": {}
                    }
            else:
                # Health check failed
                try:
                    # Try to parse JSON even on failure
                    health_data = json.loads(result.stdout)
                    health_data["script_exit_code"] = result.returncode
                    if result.stderr:
                        health_data["stderr"] = result.stderr
                    return health_data
                except json.JSONDecodeError:
                    return {
                        "service": service,
                        "status": "CRITICAL",
                        "message": f"Health check script failed (exit code: {result.returncode})",
                        "timestamp": datetime.now().isoformat(),
                        "duration_seconds": duration,
                        "script_exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "checks": {}
                    }
                    
        except subprocess.TimeoutExpired:
            return {
                "service": service,
                "status": "CRITICAL",
                "message": f"Health check timed out after {timeout}s",
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": timeout,
                "script_exit_code": -1,
                "checks": {}
            }
        except Exception as e:
            return {
                "service": service,
                "status": "CRITICAL",
                "message": f"Health check execution failed: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": time.time() - start_time,
                "script_exit_code": -1,
                "checks": {}
            }
    
    def run_parallel_health_checks(self, services: List[str], max_workers: int = 4, timeout: int = 60) -> Dict[str, Any]:
        """Run health checks for multiple services in parallel."""
        start_time = datetime.now()
        results = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all health check tasks
            future_to_service = {
                executor.submit(self.run_service_health_check, service, timeout): service
                for service in services
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_service):
                service = future_to_service[future]
                try:
                    result = future.result()
                    results[service] = result
                except Exception as e:
                    results[service] = {
                        "service": service,
                        "status": "CRITICAL",
                        "message": f"Health check execution failed: {str(e)}",
                        "timestamp": datetime.now().isoformat(),
                        "duration_seconds": 0,
                        "checks": {}
                    }
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        return self._aggregate_results(results, total_duration, end_time)
    
    def run_sequential_health_checks(self, services: List[str], timeout: int = 60) -> Dict[str, Any]:
        """Run health checks for multiple services sequentially."""
        start_time = datetime.now()
        results = {}
        
        for service in services:
            results[service] = self.run_service_health_check(service, timeout)
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        return self._aggregate_results(results, total_duration, end_time)
    
    def _aggregate_results(self, results: Dict[str, Any], total_duration: float, end_time: datetime) -> Dict[str, Any]:
        """Aggregate individual service results into overall summary."""
        # Count statuses
        status_counts = {"OK": 0, "WARNING": 0, "CRITICAL": 0, "INFO": 0}
        total_checks = 0
        
        for service_result in results.values():
            service_status = service_result.get("status", "CRITICAL")
            status_counts[service_status] = status_counts.get(service_status, 0) + 1
            
            # Count individual checks
            checks = service_result.get("checks", {})
            for check in checks.values():
                check_status = check.get("status", "CRITICAL")
                status_counts[check_status] = status_counts.get(check_status, 0) + 1
                total_checks += 1
        
        # Determine overall status
        if status_counts["CRITICAL"] > 0:
            overall_status = "CRITICAL"
        elif status_counts["WARNING"] > 0:
            overall_status = "WARNING"
        else:
            overall_status = "OK"
        
        # Calculate service-level summary
        total_services = len(results)
        healthy_services = sum(1 for r in results.values() if r.get("status") == "OK")
        warning_services = sum(1 for r in results.values() if r.get("status") == "WARNING")
        critical_services = sum(1 for r in results.values() if r.get("status") == "CRITICAL")
        
        return {
            "overall_status": overall_status,
            "message": f"Health check completed for {total_services} services",
            "timestamp": end_time.isoformat(),
            "duration_seconds": round(total_duration, 2),
            "summary": {
                "services": {
                    "total": total_services,
                    "healthy": healthy_services,
                    "warning": warning_services,
                    "critical": critical_services
                },
                "checks": {
                    "total": total_checks,
                    "ok": status_counts["OK"],
                    "warning": status_counts["WARNING"],
                    "critical": status_counts["CRITICAL"],
                    "info": status_counts["INFO"]
                }
            },
            "services": results
        }
    
    def check_docker_compose_status(self) -> Dict[str, Any]:
        """Check Docker Compose service status."""
        try:
            result = subprocess.run(
                ["docker-compose", "-f", "docker-compose.local.yml", "ps", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                try:
                    services = json.loads(result.stdout) if result.stdout.strip() else []
                    if not isinstance(services, list):
                        services = [services]  # Handle single service case
                    
                    running_services = [s for s in services if s.get("State") == "running"]
                    
                    return {
                        "status": "OK" if len(running_services) == len(services) else "WARNING",
                        "message": f"{len(running_services)}/{len(services)} services running",
                        "details": {
                            "total_services": len(services),
                            "running_services": len(running_services),
                            "services": services
                        }
                    }
                except json.JSONDecodeError:
                    # Fallback to text parsing
                    lines = result.stdout.strip().split('\n')
                    running_count = sum(1 for line in lines if 'Up' in line)
                    total_count = len([line for line in lines if line.strip()])
                    
                    return {
                        "status": "OK" if running_count == total_count else "WARNING",
                        "message": f"{running_count}/{total_count} services running (text format)",
                        "details": {
                            "total_services": total_count,
                            "running_services": running_count
                        }
                    }
            else:
                return {
                    "status": "CRITICAL",
                    "message": f"Docker Compose status check failed: {result.stderr}",
                    "details": {"exit_code": result.returncode}
                }
                
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Docker Compose status check failed: {str(e)}",
                "details": {}
            }


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="All Services Health Check")
    parser.add_argument("--services", help="Comma-separated list of services to check (postgresql,neo4j,milvus,redis)")
    parser.add_argument("--parallel", action="store_true", help="Run health checks in parallel")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout per service health check")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum parallel workers")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--include-docker", action="store_true", help="Include Docker Compose status check")
    
    args = parser.parse_args()
    
    orchestrator = ServiceHealthOrchestrator()
    
    # Determine which services to check
    if args.services:
        services = [s.strip() for s in args.services.split(",")]
        # Validate service names
        valid_services = list(orchestrator.service_scripts.keys())
        invalid_services = [s for s in services if s not in valid_services]
        if invalid_services:
            print(f"Error: Invalid services: {invalid_services}", file=sys.stderr)
            print(f"Valid services: {valid_services}", file=sys.stderr)
            sys.exit(1)
    else:
        services = list(orchestrator.service_scripts.keys())
    
    # Run health checks
    if args.parallel:
        results = orchestrator.run_parallel_health_checks(services, args.max_workers, args.timeout)
    else:
        results = orchestrator.run_sequential_health_checks(services, args.timeout)
    
    # Add Docker Compose status if requested
    if args.include_docker:
        docker_status = orchestrator.check_docker_compose_status()
        results["docker_compose_status"] = docker_status
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Human-readable output
        status_emoji = {
            "OK": "✅",
            "WARNING": "⚠️",
            "CRITICAL": "❌",
            "INFO": "ℹ️"
        }
        
        print(f"\n{'='*70}")
        print(f"ALL SERVICES HEALTH CHECK RESULTS")
        print(f"{'='*70}")
        print(f"Overall Status: {status_emoji.get(results['overall_status'], '?')} {results['overall_status']}")
        print(f"Duration: {results['duration_seconds']}s")
        print(f"Timestamp: {results['timestamp']}")
        
        # Service summary
        service_summary = results['summary']['services']
        print(f"\nServices: {service_summary['healthy']}/{service_summary['total']} healthy")
        if service_summary['warning'] > 0:
            print(f"Warnings: {service_summary['warning']}")
        if service_summary['critical'] > 0:
            print(f"Critical: {service_summary['critical']}")
        
        # Check summary
        check_summary = results['summary']['checks']
        print(f"Total Checks: {check_summary['total']} ({check_summary['ok']} OK, {check_summary['warning']} Warning, {check_summary['critical']} Critical)")
        
        if not args.quiet:
            # Individual service results
            for service_name, service_data in results['services'].items():
                print(f"\n{'-'*50}")
                service_status = service_data.get('status', 'UNKNOWN')
                emoji = status_emoji.get(service_status, '?')
                print(f"SERVICE: {service_name.upper()} [{emoji} {service_status}]")
                print(f"{'-'*50}")
                print(f"Message: {service_data.get('message', 'No message')}")
                print(f"Duration: {service_data.get('duration_seconds', 0)}s")
                
                # Show individual checks
                checks = service_data.get('checks', {})
                if checks:
                    print("Checks:")
                    for check_name, check_data in checks.items():
                        check_status = check_data.get('status', 'UNKNOWN')
                        check_emoji = status_emoji.get(check_status, '?')
                        duration = check_data.get('duration_ms', 0)
                        print(f"  {check_emoji} {check_name.replace('_', ' ').title()}: {check_data.get('message', 'No message')} ({duration:.1f}ms)")
            
            # Docker Compose status if included
            if args.include_docker and "docker_compose_status" in results:
                docker_data = results["docker_compose_status"]
                print(f"\n{'-'*50}")
                docker_status = docker_data.get('status', 'UNKNOWN')
                emoji = status_emoji.get(docker_status, '?')
                print(f"DOCKER COMPOSE STATUS [{emoji} {docker_status}]")
                print(f"{'-'*50}")
                print(f"Message: {docker_data.get('message', 'No message')}")
    
    # Exit with appropriate code
    if results['overall_status'] == "CRITICAL":
        sys.exit(2)
    elif results['overall_status'] == "WARNING":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()