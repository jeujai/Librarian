#!/usr/bin/env python3
"""
Basic Performance Check Script for AWS Learning Deployment

This script performs comprehensive performance analysis including:
- Application performance metrics
- Database performance analysis
- Cache performance evaluation
- System resource utilization
- Cost optimization recommendations
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from multimodal_librarian.aws.performance_basic import (
    performance_optimizer,
    get_performance_summary,
    run_performance_analysis,
    optimize_performance
)
from multimodal_librarian.logging_config import get_logger


def main():
    """Main performance check function."""
    parser = argparse.ArgumentParser(description='Basic Performance Check for AWS Learning Deployment')
    parser.add_argument('--full-analysis', action='store_true', 
                       help='Run comprehensive performance analysis')
    parser.add_argument('--optimize', action='store_true',
                       help='Apply automatic performance optimizations')
    parser.add_argument('--output-format', choices=['json', 'text'], default='text',
                       help='Output format for results')
    parser.add_argument('--output-file', type=str,
                       help='Output file path (optional)')
    
    args = parser.parse_args()
    
    logger = get_logger("performance_check")
    logger.info("Starting basic performance check...")
    
    try:
        # Initialize results
        results = {
            "timestamp": datetime.now().isoformat(),
            "performance_check": "basic",
            "summary": {},
            "analysis": {},
            "optimizations": {},
            "recommendations": []
        }
        
        # Get performance summary
        print("🔍 Analyzing current performance...")
        summary = get_performance_summary()
        results["summary"] = summary
        
        # Run full analysis if requested
        if args.full_analysis:
            print("📊 Running comprehensive performance analysis...")
            analysis = run_performance_analysis()
            results["analysis"] = analysis
        
        # Apply optimizations if requested
        if args.optimize:
            print("⚡ Applying performance optimizations...")
            optimizations = optimize_performance()
            results["optimizations"] = optimizations
        
        # Generate recommendations
        recommendations = generate_recommendations(results)
        results["recommendations"] = recommendations
        
        # Output results
        if args.output_format == 'json':
            output_json(results, args.output_file)
        else:
            output_text(results, args.output_file)
        
        # Exit with appropriate code
        health_score = summary.get("overall_health_score", 50)
        if health_score >= 80:
            print("\n✅ Performance check completed - System is healthy!")
            sys.exit(0)
        elif health_score >= 60:
            print("\n⚠️  Performance check completed - System needs attention")
            sys.exit(1)
        else:
            print("\n❌ Performance check completed - System has critical issues")
            sys.exit(2)
            
    except Exception as e:
        logger.error(f"Performance check failed: {e}")
        print(f"\n❌ Performance check failed: {e}")
        sys.exit(3)


def generate_recommendations(results: Dict[str, Any]) -> List[str]:
    """Generate performance recommendations based on analysis."""
    recommendations = []
    
    try:
        summary = results.get("summary", {})
        analysis = results.get("analysis", {})
        
        # Health score based recommendations
        health_score = summary.get("overall_health_score", 50)
        
        if health_score < 60:
            recommendations.append("🚨 Critical: System health is below acceptable levels - immediate attention required")
        elif health_score < 80:
            recommendations.append("⚠️  Warning: System performance could be improved")
        
        # Key metrics recommendations
        key_metrics = summary.get("key_metrics", {})
        
        # Database recommendations
        db_pool_util = key_metrics.get("database_pool_utilization", 0)
        if db_pool_util > 80:
            recommendations.append("📊 Database: High connection pool utilization - consider increasing pool size")
        elif db_pool_util < 20:
            recommendations.append("💰 Database: Low connection pool utilization - consider reducing pool size for cost savings")
        
        # Cache recommendations
        cache_hit_rate = key_metrics.get("cache_hit_rate", 0)
        if cache_hit_rate < 50:
            recommendations.append("🔄 Cache: Low hit rate detected - review caching strategy and TTL settings")
        elif cache_hit_rate > 90:
            recommendations.append("✅ Cache: Excellent hit rate - caching strategy is working well")
        
        # System resource recommendations
        cpu_usage = key_metrics.get("cpu_usage", 0)
        memory_usage = key_metrics.get("memory_usage", 0)
        
        if cpu_usage > 80:
            recommendations.append("🖥️  System: High CPU usage - consider scaling or optimization")
        elif cpu_usage < 30:
            recommendations.append("💰 System: Low CPU usage - consider downsizing for cost optimization")
        
        if memory_usage > 85:
            recommendations.append("🧠 System: High memory usage - check for memory leaks or increase capacity")
        
        # Analysis-based recommendations
        if analysis:
            analysis_recommendations = analysis.get("recommendations", [])
            recommendations.extend(analysis_recommendations[:3])  # Top 3 from analysis
        
        # Learning-specific recommendations
        recommendations.extend([
            "📚 Learning: Monitor these metrics regularly to understand performance patterns",
            "💡 Learning: Experiment with different optimization strategies to see their impact",
            "📈 Learning: Use the performance dashboard to track improvements over time"
        ])
        
        # Cost optimization recommendations
        recommendations.extend([
            "💰 Cost: Review resource utilization weekly to identify optimization opportunities",
            "📊 Cost: Use CloudWatch metrics to right-size resources based on actual usage",
            "🎯 Cost: Target 50-70% resource utilization for optimal cost-performance balance"
        ])
        
    except Exception as e:
        recommendations.append(f"❌ Error generating recommendations: {e}")
    
    return recommendations


def output_text(results: Dict[str, Any], output_file: str = None):
    """Output results in human-readable text format."""
    output_lines = []
    
    # Header
    output_lines.extend([
        "=" * 80,
        "🚀 MULTIMODAL LIBRARIAN - BASIC PERFORMANCE CHECK",
        "=" * 80,
        f"📅 Timestamp: {results['timestamp']}",
        f"🔍 Check Type: {results['performance_check']}",
        ""
    ])
    
    # Performance Summary
    summary = results.get("summary", {})
    if summary:
        output_lines.extend([
            "📊 PERFORMANCE SUMMARY",
            "-" * 40,
            f"🏥 Overall Health Score: {summary.get('overall_health_score', 'N/A')}/100",
            f"📈 Status: {summary.get('status', 'Unknown').upper()}",
            ""
        ])
        
        # Key Metrics
        key_metrics = summary.get("key_metrics", {})
        if key_metrics:
            output_lines.extend([
                "🔑 Key Metrics:",
                f"  📊 Database Pool Utilization: {key_metrics.get('database_pool_utilization', 'N/A')}",
                f"  🔄 Cache Hit Rate: {key_metrics.get('cache_hit_rate', 'N/A')}%",
                f"  🖥️  CPU Usage: {key_metrics.get('cpu_usage', 'N/A')}%",
                f"  🧠 Memory Usage: {key_metrics.get('memory_usage', 'N/A')}%",
                ""
            ])
    
    # Analysis Results
    analysis = results.get("analysis", {})
    if analysis:
        output_lines.extend([
            "🔬 DETAILED ANALYSIS",
            "-" * 40,
        ])
        
        # Database Analysis
        db_analysis = analysis.get("database_analysis", {})
        if db_analysis:
            output_lines.append("📊 Database Analysis:")
            
            conn_pool = db_analysis.get("connection_pool", {})
            if conn_pool and conn_pool.get("current_stats"):
                stats = conn_pool["current_stats"]
                output_lines.extend([
                    f"  Pool Size: {stats.get('pool_size', 'N/A')}",
                    f"  Checked Out: {stats.get('checked_out', 'N/A')}",
                    f"  Overflow: {stats.get('overflow', 'N/A')}",
                ])
            
            slow_queries = db_analysis.get("slow_queries", {})
            if slow_queries:
                output_lines.append(f"  Slow Queries: {slow_queries.get('total_slow_queries', 0)}")
        
        # Cache Analysis
        cache_analysis = analysis.get("cache_analysis", {})
        if cache_analysis and "error" not in cache_analysis:
            output_lines.extend([
                "",
                "🔄 Cache Analysis:",
                f"  Hit Rate: {cache_analysis.get('hit_rate_percent', 'N/A')}%",
                f"  Status: {cache_analysis.get('status', 'Unknown')}"
            ])
        
        # System Analysis
        system_analysis = analysis.get("system_analysis", {})
        if system_analysis and "error" not in system_analysis:
            output_lines.extend([
                "",
                "🖥️  System Analysis:",
                f"  CPU Usage: {system_analysis.get('cpu_usage_percent', 'N/A')}%",
                f"  Memory Usage: {system_analysis.get('memory_usage_percent', 'N/A')}%",
                f"  Disk Usage: {system_analysis.get('disk_usage_percent', 'N/A')}%",
                f"  Available Memory: {system_analysis.get('memory_available_gb', 'N/A')} GB",
            ])
        
        output_lines.append("")
    
    # Optimizations Applied
    optimizations = results.get("optimizations", {})
    if optimizations:
        output_lines.extend([
            "⚡ OPTIMIZATIONS APPLIED",
            "-" * 40,
        ])
        
        applied = optimizations.get("optimizations_applied", [])
        if applied:
            for opt in applied:
                output_lines.append(f"  ✅ {opt.get('type', 'Unknown')}: {opt.get('details', {}).get('status', 'Applied')}")
        
        errors = optimizations.get("errors", [])
        if errors:
            output_lines.append("  ❌ Errors:")
            for error in errors:
                output_lines.append(f"    - {error}")
        
        output_lines.append("")
    
    # Recommendations
    recommendations = results.get("recommendations", [])
    if recommendations:
        output_lines.extend([
            "💡 RECOMMENDATIONS",
            "-" * 40,
        ])
        
        for i, rec in enumerate(recommendations, 1):
            output_lines.append(f"{i:2d}. {rec}")
        
        output_lines.append("")
    
    # Footer
    output_lines.extend([
        "=" * 80,
        "🎓 LEARNING NOTES:",
        "- Monitor performance metrics regularly to understand patterns",
        "- Experiment with optimizations to see their impact",
        "- Use CloudWatch dashboards for ongoing monitoring",
        "- Keep costs under $100/month with right-sizing",
        "=" * 80
    ])
    
    # Output to file or console
    output_text = "\n".join(output_lines)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(output_text)
        print(f"📄 Results written to: {output_file}")
    else:
        print(output_text)


def output_json(results: Dict[str, Any], output_file: str = None):
    """Output results in JSON format."""
    json_output = json.dumps(results, indent=2, default=str)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(json_output)
        print(f"📄 JSON results written to: {output_file}")
    else:
        print(json_output)


if __name__ == "__main__":
    main()