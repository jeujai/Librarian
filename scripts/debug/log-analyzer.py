#!/usr/bin/env python3
"""
Log Analyzer

Advanced log analysis tool for local development debugging.
Analyzes logs from all services to identify patterns, errors, and performance issues.
"""

import json
import logging
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LogAnalyzer:
    """Advanced log analysis tool."""
    
    def __init__(self):
        self.compose_file = Path("docker-compose.local.yml")
        self.debug_output_dir = Path("debug_output/logs")
        self.debug_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Log patterns for different types of issues
        self.error_patterns = [
            (r'ERROR', 'error'),
            (r'CRITICAL', 'critical'),
            (r'FATAL', 'fatal'),
            (r'Exception', 'exception'),
            (r'Traceback', 'traceback'),
            (r'failed', 'failure'),
            (r'timeout', 'timeout'),
            (r'connection.*refused', 'connection_refused'),
            (r'permission.*denied', 'permission_denied'),
            (r'out of memory', 'oom'),
            (r'disk.*full', 'disk_full')
        ]
        
        self.warning_patterns = [
            (r'WARNING', 'warning'),
            (r'WARN', 'warning'),
            (r'deprecated', 'deprecated'),
            (r'retry', 'retry'),
            (r'slow', 'performance'),
            (r'high.*usage', 'resource_usage')
        ]
        
        self.performance_patterns = [
            (r'(\d+\.?\d*)\s*ms', 'response_time_ms'),
            (r'(\d+\.?\d*)\s*seconds?', 'response_time_s'),
            (r'memory.*?(\d+\.?\d*)\s*MB', 'memory_mb'),
            (r'cpu.*?(\d+\.?\d*)%', 'cpu_percent'),
            (r'query.*?(\d+\.?\d*)\s*ms', 'query_time_ms')
        ]
    
    def get_compose_services(self) -> List[str]:
        """Get list of services from docker-compose file."""
        try:
            with open(self.compose_file, 'r') as f:
                compose_config = yaml.safe_load(f)
            
            services = list(compose_config.get('services', {}).keys())
            return services
        
        except Exception as e:
            logger.error(f"Failed to read compose file: {e}")
            return []
    
    def collect_service_logs(self, service: str, lines: int = 1000) -> List[str]:
        """Collect logs from a specific service."""
        try:
            result = subprocess.run(
                ["docker-compose", "-f", str(self.compose_file), "logs", "--tail", str(lines), service],
                capture_output=True,
                text=True,
                check=True
            )
            
            log_lines = result.stdout.strip().split('\n')
            return [line for line in log_lines if line.strip()]
        
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to collect logs for {service}: {e}")
            return []
    
    def parse_log_line(self, line: str) -> Dict[str, Any]:
        """Parse a single log line to extract structured information."""
        parsed = {
            "raw_line": line,
            "timestamp": None,
            "level": "unknown",
            "service": "unknown",
            "message": line,
            "patterns_matched": []
        }
        
        # Extract timestamp (various formats)
        timestamp_patterns = [
            r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})',
            r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})',
            r'(\w{3} \d{2} \d{2}:\d{2}:\d{2})'
        ]
        
        for pattern in timestamp_patterns:
            match = re.search(pattern, line)
            if match:
                parsed["timestamp"] = match.group(1)
                break
        
        # Extract log level
        level_match = re.search(r'\b(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\b', line, re.IGNORECASE)
        if level_match:
            parsed["level"] = level_match.group(1).upper()
        
        # Extract service name (from docker-compose format)
        service_match = re.match(r'^([a-zA-Z0-9_-]+)\s*\|\s*', line)
        if service_match:
            parsed["service"] = service_match.group(1)
            parsed["message"] = line[service_match.end():]
        
        # Check for error patterns
        for pattern, category in self.error_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                parsed["patterns_matched"].append(("error", category))
        
        # Check for warning patterns
        for pattern, category in self.warning_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                parsed["patterns_matched"].append(("warning", category))
        
        # Check for performance patterns
        for pattern, category in self.performance_patterns:
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                parsed["patterns_matched"].append(("performance", category, matches))
        
        return parsed
    
    def analyze_service_logs(self, service: str, lines: int = 1000) -> Dict[str, Any]:
        """Analyze logs for a specific service."""
        logger.info(f"📋 Analyzing logs for service: {service}")
        
        log_lines = self.collect_service_logs(service, lines)
        
        analysis = {
            "service": service,
            "timestamp": datetime.now().isoformat(),
            "total_lines": len(log_lines),
            "log_levels": Counter(),
            "error_summary": Counter(),
            "warning_summary": Counter(),
            "performance_metrics": defaultdict(list),
            "recent_errors": [],
            "patterns": {
                "errors": [],
                "warnings": [],
                "performance_issues": []
            },
            "timeline": []
        }
        
        for line in log_lines:
            parsed = self.parse_log_line(line)
            
            # Count log levels
            analysis["log_levels"][parsed["level"]] += 1
            
            # Process matched patterns
            for pattern_match in parsed["patterns_matched"]:
                if pattern_match[0] == "error":
                    analysis["error_summary"][pattern_match[1]] += 1
                    analysis["patterns"]["errors"].append({
                        "timestamp": parsed["timestamp"],
                        "category": pattern_match[1],
                        "message": parsed["message"][:200]
                    })
                    
                    # Keep recent errors
                    if len(analysis["recent_errors"]) < 10:
                        analysis["recent_errors"].append({
                            "timestamp": parsed["timestamp"],
                            "message": parsed["message"]
                        })
                
                elif pattern_match[0] == "warning":
                    analysis["warning_summary"][pattern_match[1]] += 1
                    analysis["patterns"]["warnings"].append({
                        "timestamp": parsed["timestamp"],
                        "category": pattern_match[1],
                        "message": parsed["message"][:200]
                    })
                
                elif pattern_match[0] == "performance":
                    category = pattern_match[1]
                    values = pattern_match[2]
                    for value in values:
                        try:
                            analysis["performance_metrics"][category].append(float(value))
                        except ValueError:
                            pass
            
            # Build timeline for critical events
            if parsed["level"] in ["ERROR", "CRITICAL", "FATAL"] or any(p[0] == "error" for p in parsed["patterns_matched"]):
                analysis["timeline"].append({
                    "timestamp": parsed["timestamp"],
                    "level": parsed["level"],
                    "message": parsed["message"][:100]
                })
        
        # Calculate performance statistics
        for metric, values in analysis["performance_metrics"].items():
            if values:
                analysis["performance_metrics"][metric] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                    "values": values[-10:]  # Keep last 10 values
                }
        
        # Sort timeline by timestamp
        analysis["timeline"].sort(key=lambda x: x["timestamp"] or "")
        
        logger.info(f"  📊 Processed {analysis['total_lines']} log lines")
        logger.info(f"  ❌ Errors: {sum(analysis['error_summary'].values())}")
        logger.info(f"  ⚠️ Warnings: {sum(analysis['warning_summary'].values())}")
        
        return analysis
    
    def analyze_all_services(self, lines: int = 1000) -> Dict[str, Any]:
        """Analyze logs for all services."""
        logger.info("📋 Analyzing logs for all services...")
        
        services = self.get_compose_services()
        
        full_analysis = {
            "timestamp": datetime.now().isoformat(),
            "services_analyzed": len(services),
            "services": {},
            "cross_service_analysis": {
                "total_errors": 0,
                "total_warnings": 0,
                "error_correlation": {},
                "service_health": {}
            }
        }
        
        # Analyze each service
        for service in services:
            service_analysis = self.analyze_service_logs(service, lines)
            full_analysis["services"][service] = service_analysis
            
            # Update cross-service metrics
            full_analysis["cross_service_analysis"]["total_errors"] += sum(service_analysis["error_summary"].values())
            full_analysis["cross_service_analysis"]["total_warnings"] += sum(service_analysis["warning_summary"].values())
            
            # Determine service health
            error_count = sum(service_analysis["error_summary"].values())
            warning_count = sum(service_analysis["warning_summary"].values())
            
            if error_count > 10:
                health = "critical"
            elif error_count > 0 or warning_count > 20:
                health = "degraded"
            else:
                health = "healthy"
            
            full_analysis["cross_service_analysis"]["service_health"][service] = {
                "status": health,
                "error_count": error_count,
                "warning_count": warning_count
            }
        
        # Look for error correlations (errors happening around the same time)
        self._analyze_error_correlations(full_analysis)
        
        # Generate summary
        healthy_services = sum(1 for s in full_analysis["cross_service_analysis"]["service_health"].values() if s["status"] == "healthy")
        
        logger.info(f"📊 Analysis complete:")
        logger.info(f"  🟢 Healthy services: {healthy_services}/{len(services)}")
        logger.info(f"  ❌ Total errors: {full_analysis['cross_service_analysis']['total_errors']}")
        logger.info(f"  ⚠️ Total warnings: {full_analysis['cross_service_analysis']['total_warnings']}")
        
        # Save analysis report
        report_file = self.debug_output_dir / f"log_analysis_{int(datetime.now().timestamp())}.json"
        with open(report_file, 'w') as f:
            json.dump(full_analysis, f, indent=2, default=str)
        
        logger.info(f"📄 Analysis report saved to: {report_file}")
        
        return full_analysis
    
    def _analyze_error_correlations(self, analysis: Dict[str, Any]) -> None:
        """Analyze correlations between errors across services."""
        # Group errors by time windows (5-minute windows)
        time_windows = defaultdict(lambda: defaultdict(int))
        
        for service, service_data in analysis["services"].items():
            for error in service_data["patterns"]["errors"]:
                if error["timestamp"]:
                    try:
                        # Parse timestamp and round to 5-minute window
                        dt = datetime.fromisoformat(error["timestamp"].replace('Z', '+00:00'))
                        window = dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)
                        time_windows[window][service] += 1
                    except:
                        pass
        
        # Find windows with multiple services having errors
        correlations = []
        for window, service_errors in time_windows.items():
            if len(service_errors) > 1:  # Multiple services with errors
                correlations.append({
                    "time_window": window.isoformat(),
                    "affected_services": dict(service_errors),
                    "total_errors": sum(service_errors.values())
                })
        
        analysis["cross_service_analysis"]["error_correlation"] = correlations
    
    def search_logs(self, pattern: str, services: Optional[List[str]] = None, lines: int = 1000) -> Dict[str, Any]:
        """Search for specific patterns in logs."""
        logger.info(f"🔍 Searching logs for pattern: {pattern}")
        
        if services is None:
            services = self.get_compose_services()
        
        search_results = {
            "pattern": pattern,
            "timestamp": datetime.now().isoformat(),
            "services_searched": services,
            "matches": {},
            "total_matches": 0
        }
        
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
        
        for service in services:
            log_lines = self.collect_service_logs(service, lines)
            service_matches = []
            
            for i, line in enumerate(log_lines):
                if compiled_pattern.search(line):
                    parsed = self.parse_log_line(line)
                    service_matches.append({
                        "line_number": i + 1,
                        "timestamp": parsed["timestamp"],
                        "message": line.strip(),
                        "context": {
                            "before": log_lines[max(0, i-1):i],
                            "after": log_lines[i+1:min(len(log_lines), i+3)]
                        }
                    })
            
            if service_matches:
                search_results["matches"][service] = service_matches
                search_results["total_matches"] += len(service_matches)
                logger.info(f"  📋 {service}: {len(service_matches)} matches")
        
        logger.info(f"🔍 Search complete: {search_results['total_matches']} total matches")
        
        # Save search results
        search_file = self.debug_output_dir / f"log_search_{pattern.replace(' ', '_')}_{int(datetime.now().timestamp())}.json"
        with open(search_file, 'w') as f:
            json.dump(search_results, f, indent=2, default=str)
        
        logger.info(f"📄 Search results saved to: {search_file}")
        
        return search_results
    
    def generate_log_summary(self, hours: int = 1) -> Dict[str, Any]:
        """Generate a summary of recent log activity."""
        logger.info(f"📊 Generating log summary for last {hours} hour(s)...")
        
        # For simplicity, we'll analyze recent logs (this could be enhanced with timestamp filtering)
        analysis = self.analyze_all_services(lines=500)
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "time_period_hours": hours,
            "services": {},
            "overall_health": "unknown",
            "recommendations": []
        }
        
        critical_services = 0
        degraded_services = 0
        healthy_services = 0
        
        for service, health_info in analysis["cross_service_analysis"]["service_health"].items():
            status = health_info["status"]
            summary["services"][service] = {
                "status": status,
                "error_count": health_info["error_count"],
                "warning_count": health_info["warning_count"]
            }
            
            if status == "critical":
                critical_services += 1
            elif status == "degraded":
                degraded_services += 1
            else:
                healthy_services += 1
        
        # Determine overall health
        if critical_services > 0:
            summary["overall_health"] = "critical"
        elif degraded_services > 0:
            summary["overall_health"] = "degraded"
        else:
            summary["overall_health"] = "healthy"
        
        # Generate recommendations
        if critical_services > 0:
            summary["recommendations"].append("🚨 Critical services detected - immediate attention required")
        
        if analysis["cross_service_analysis"]["total_errors"] > 50:
            summary["recommendations"].append("⚠️ High error rate detected - investigate error patterns")
        
        if len(analysis["cross_service_analysis"]["error_correlation"]) > 0:
            summary["recommendations"].append("🔗 Error correlations found - check for cascading failures")
        
        if not summary["recommendations"]:
            summary["recommendations"].append("✅ System appears healthy")
        
        logger.info(f"📊 Summary: {healthy_services} healthy, {degraded_services} degraded, {critical_services} critical")
        
        return summary


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Log Analyzer")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze service logs")
    analyze_parser.add_argument("--service", "-s", help="Specific service to analyze")
    analyze_parser.add_argument("--lines", "-n", type=int, default=1000, help="Number of log lines to analyze")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search logs for patterns")
    search_parser.add_argument("pattern", help="Pattern to search for (regex supported)")
    search_parser.add_argument("--services", "-s", nargs="+", help="Services to search in")
    search_parser.add_argument("--lines", "-n", type=int, default=1000, help="Number of log lines to search")
    
    # Summary command
    summary_parser = subparsers.add_parser("summary", help="Generate log summary")
    summary_parser.add_argument("--hours", type=int, default=1, help="Time period in hours")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize analyzer
    analyzer = LogAnalyzer()
    
    # Execute command
    if args.command == "analyze":
        if args.service:
            analyzer.analyze_service_logs(args.service, args.lines)
        else:
            analyzer.analyze_all_services(args.lines)
    
    elif args.command == "search":
        analyzer.search_logs(args.pattern, args.services, args.lines)
    
    elif args.command == "summary":
        summary = analyzer.generate_log_summary(args.hours)
        
        print("\n" + "="*50)
        print("LOG SUMMARY")
        print("="*50)
        print(f"Overall Health: {summary['overall_health'].upper()}")
        print(f"Time Period: {summary['time_period_hours']} hour(s)")
        print("\nService Status:")
        for service, info in summary["services"].items():
            status_icon = {"healthy": "🟢", "degraded": "🟡", "critical": "🔴"}.get(info["status"], "⚪")
            print(f"  {status_icon} {service}: {info['status']} (errors: {info['error_count']}, warnings: {info['warning_count']})")
        
        print("\nRecommendations:")
        for rec in summary["recommendations"]:
            print(f"  {rec}")


if __name__ == "__main__":
    main()