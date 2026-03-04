#!/usr/bin/env python3
"""
Demonstration of Log Aggregation and Analysis System

This script demonstrates the comprehensive log aggregation and analysis
capabilities implemented for startup optimization.
"""

import os
import sys
import tempfile
import time
import json
from datetime import datetime, timedelta

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multimodal_librarian.logging.startup_logger import (
    initialize_startup_logger,
    StartupLogEntry,
    LogLevel
)
from multimodal_librarian.logging.log_aggregator import (
    initialize_log_aggregator,
    get_startup_analysis_report,
    get_real_time_metrics,
    export_analysis_data
)


def generate_sample_startup_logs(aggregator, num_startups=5):
    """Generate sample startup logs for demonstration."""
    print(f"📝 Generating {num_startups} sample startup sessions...")
    
    base_time = datetime.now() - timedelta(hours=2)
    
    for session in range(num_startups):
        session_start = base_time + timedelta(minutes=session * 10)
        
        # Simulate different startup performance characteristics
        if session == 0:
            # Fast startup
            phase_times = {"minimal": 15000, "essential": 35000, "full": 85000}
            model_times = {"essential": 8000, "standard": 25000, "advanced": 45000}
            has_errors = False
        elif session == 1:
            # Slow startup
            phase_times = {"minimal": 45000, "essential": 120000, "full": 280000}
            model_times = {"essential": 25000, "standard": 85000, "advanced": 150000}
            has_errors = True
        elif session == 2:
            # Average startup
            phase_times = {"minimal": 25000, "essential": 65000, "full": 150000}
            model_times = {"essential": 12000, "standard": 45000, "advanced": 80000}
            has_errors = False
        elif session == 3:
            # Startup with model failures
            phase_times = {"minimal": 30000, "essential": 75000, "full": 200000}
            model_times = {"essential": 15000, "standard": 55000, "advanced": None}  # Failed
            has_errors = True
        else:
            # Recent fast startup
            phase_times = {"minimal": 18000, "essential": 42000, "full": 95000}
            model_times = {"essential": 10000, "standard": 30000, "advanced": 50000}
            has_errors = False
        
        session_logs = []
        current_time = session_start
        
        # Phase transitions
        for phase, duration in phase_times.items():
            current_time += timedelta(milliseconds=duration)
            session_logs.append(StartupLogEntry(
                timestamp=current_time.isoformat(),
                level=LogLevel.INFO.value,
                event_type="phase_transition_complete",
                phase=phase,
                message=f"Phase transition to {phase} completed",
                duration_ms=float(duration),
                metadata={
                    "from_phase": "initial" if phase == "minimal" else ("minimal" if phase == "essential" else "essential"),
                    "to_phase": phase,
                    "success": True,
                    "session_id": f"session_{session}"
                }
            ))
        
        # Model loading
        for priority, duration in model_times.items():
            if duration is None:
                # Failed model loading
                current_time += timedelta(milliseconds=30000)
                session_logs.append(StartupLogEntry(
                    timestamp=current_time.isoformat(),
                    level=LogLevel.ERROR.value,
                    event_type="model_loading_complete",
                    phase="full",
                    message=f"Model loading failed for {priority} priority model",
                    duration_ms=30000.0,
                    metadata={
                        "model_name": f"{priority}-model",
                        "priority": priority,
                        "status": "failed",
                        "session_id": f"session_{session}"
                    },
                    error_details={
                        "error_message": "Out of memory during model loading",
                        "model_name": f"{priority}-model"
                    }
                ))
            else:
                current_time += timedelta(milliseconds=duration)
                session_logs.append(StartupLogEntry(
                    timestamp=current_time.isoformat(),
                    level=LogLevel.INFO.value,
                    event_type="model_loading_complete",
                    phase="essential" if priority == "essential" else "full",
                    message=f"Model loading completed for {priority} priority model",
                    duration_ms=float(duration),
                    metadata={
                        "model_name": f"{priority}-model",
                        "priority": priority,
                        "status": "loaded",
                        "session_id": f"session_{session}"
                    }
                ))
        
        # Add some errors if needed
        if has_errors:
            current_time += timedelta(milliseconds=5000)
            session_logs.append(StartupLogEntry(
                timestamp=current_time.isoformat(),
                level=LogLevel.ERROR.value,
                event_type="resource_init_complete",
                phase="essential",
                message="Database connection failed",
                duration_ms=5000.0,
                metadata={
                    "resource_name": "database",
                    "resource_type": "postgresql",
                    "success": False,
                    "session_id": f"session_{session}"
                },
                error_details={
                    "error_message": "Connection timeout after 5 seconds",
                    "resource_name": "database"
                }
            ))
        
        # Application ready
        final_time = current_time + timedelta(milliseconds=2000)
        session_logs.append(StartupLogEntry(
            timestamp=final_time.isoformat(),
            level=LogLevel.INFO.value,
            event_type="application_ready",
            phase="full",
            message="Application ready to serve traffic",
            duration_ms=(final_time - session_start).total_seconds() * 1000,
            metadata={
                "ready_type": "full",
                "capabilities": ["chat", "document_processing", "search"],
                "session_id": f"session_{session}"
            }
        ))
        
        # Add all logs for this session
        aggregator.add_log_entries(session_logs)
        print(f"   ✅ Session {session + 1}: {len(session_logs)} log entries")
    
    # Force processing
    aggregator._process_log_buffer()
    print("   ⚙️ Processed all log entries")


def demonstrate_real_time_monitoring(aggregator):
    """Demonstrate real-time monitoring capabilities."""
    print("\n📊 Real-Time Monitoring Dashboard")
    print("=" * 50)
    
    metrics = aggregator.get_real_time_metrics()
    
    print(f"🕐 Timestamp: {metrics['timestamp']}")
    print(f"🚀 Recent Startups (last hour): {metrics['recent_startups_count']}")
    print(f"❌ Recent Errors (last hour): {metrics['recent_errors_count']}")
    print(f"⏱️  Average Startup Time: {metrics['avg_startup_time_ms']:.1f}ms")
    print(f"📦 Log Buffer Size: {metrics['log_buffer_size']}")
    print(f"⚙️ Background Processing: {'Active' if metrics['processing_active'] else 'Inactive'}")
    print(f"💾 Cache Entries: {metrics['cache_entries']}")


def demonstrate_analysis_report(aggregator):
    """Demonstrate comprehensive analysis report generation."""
    print("\n📋 Comprehensive Analysis Report")
    print("=" * 50)
    
    report = aggregator.get_startup_analysis_report(period_hours=24)
    
    print(f"📊 Report ID: {report.report_id}")
    print(f"🕐 Generated: {report.generated_at}")
    print(f"📅 Analysis Period: {report.analysis_period}")
    print()
    
    # Startup Statistics
    print("🚀 Startup Statistics:")
    print(f"   Total Startups: {report.total_startups}")
    print(f"   Successful: {report.successful_startups}")
    print(f"   Failed: {report.failed_startups}")
    if report.total_startups > 0:
        success_rate = (report.successful_startups / report.total_startups) * 100
        print(f"   Success Rate: {success_rate:.1f}%")
    print()
    
    # Performance Metrics
    print("⏱️ Performance Metrics:")
    print(f"   Average Startup Time: {report.avg_startup_time_ms:.1f}ms ({report.avg_startup_time_ms/1000:.1f}s)")
    print(f"   Median Startup Time: {report.median_startup_time_ms:.1f}ms ({report.median_startup_time_ms/1000:.1f}s)")
    print(f"   95th Percentile: {report.p95_startup_time_ms:.1f}ms ({report.p95_startup_time_ms/1000:.1f}s)")
    print(f"   99th Percentile: {report.p99_startup_time_ms:.1f}ms ({report.p99_startup_time_ms/1000:.1f}s)")
    print()
    
    # Phase Performance
    if report.phase_performance:
        print("🔄 Phase Performance:")
        for phase, metrics in report.phase_performance.items():
            print(f"   {phase.capitalize()} Phase:")
            print(f"      Average: {metrics['avg_duration_ms']:.1f}ms")
            print(f"      Range: {metrics['min_duration_ms']:.1f}ms - {metrics['max_duration_ms']:.1f}ms")
            print(f"      Count: {metrics['count']}")
        print()
    
    # Model Loading Performance
    if report.model_loading_performance:
        print("🤖 Model Loading Performance:")
        for priority, metrics in report.model_loading_performance.items():
            print(f"   {priority.capitalize()} Priority Models:")
            print(f"      Average: {metrics['avg_duration_ms']:.1f}ms")
            print(f"      Range: {metrics['min_duration_ms']:.1f}ms - {metrics['max_duration_ms']:.1f}ms")
            print(f"      Count: {metrics['count']}")
        print()
    
    # Error Patterns
    if report.error_patterns:
        print("🚨 Error Patterns:")
        for pattern in report.error_patterns:
            print(f"   Pattern: {pattern.error_type}")
            print(f"      Message: {pattern.error_message_pattern}")
            print(f"      Occurrences: {pattern.occurrence_count}")
            print(f"      Frequency: {pattern.frequency_per_hour:.2f}/hour")
            print(f"      Severity: {pattern.severity}")
            print(f"      Affected Phases: {', '.join(pattern.affected_phases)}")
            if pattern.suggested_actions:
                print(f"      Suggestions:")
                for action in pattern.suggested_actions[:2]:  # Show first 2
                    print(f"         - {action}")
            print()
    
    # Performance Insights
    if report.performance_insights:
        print("💡 Performance Insights:")
        for insight in report.performance_insights:
            print(f"   {insight.title} ({insight.severity} severity)")
            print(f"      Type: {insight.insight_type}")
            print(f"      Description: {insight.description}")
            print(f"      Confidence: {insight.confidence_score:.2f}")
            print(f"      Affected: {', '.join(insight.affected_components)}")
            if insight.recommendations:
                print(f"      Recommendations:")
                for rec in insight.recommendations[:2]:  # Show first 2
                    print(f"         - {rec}")
            print()
    
    # Trends
    if report.trends:
        print("📈 Trends:")
        for trend_name, trend_data in report.trends.items():
            print(f"   {trend_name.replace('_', ' ').title()}: {len(trend_data)} data points")
        print()
    
    # Recommendations
    if report.recommendations:
        print("📝 Top Recommendations:")
        for i, rec in enumerate(report.recommendations[:5], 1):
            print(f"   {i}. {rec}")
        print()


def demonstrate_data_export(aggregator):
    """Demonstrate data export capabilities."""
    print("\n📤 Data Export Capabilities")
    print("=" * 50)
    
    # JSON Export
    print("📄 JSON Export (with raw logs):")
    json_data = aggregator.export_analysis_data(format_type="json", include_raw_logs=True)
    json_size = len(json_data)
    print(f"   Size: {json_size:,} characters")
    
    # Parse and show structure
    try:
        parsed = json.loads(json_data)
        print(f"   Analysis Report: ✅")
        print(f"   Raw Logs: {len(parsed.get('raw_logs', []))} entries")
        print(f"   Export Format: {parsed.get('export_format', 'unknown')}")
    except:
        print("   ❌ Failed to parse JSON")
    print()
    
    # CSV Export
    print("📊 CSV Export:")
    csv_data = aggregator.export_analysis_data(format_type="csv", include_raw_logs=False)
    csv_lines = len(csv_data.split('\n'))
    print(f"   Lines: {csv_lines}")
    print(f"   Size: {len(csv_data):,} characters")
    print()
    
    # Show sample of CSV
    print("📋 CSV Sample (first 10 lines):")
    for i, line in enumerate(csv_data.split('\n')[:10]):
        if line.strip():
            print(f"   {i+1:2d}: {line}")
    print()


def demonstrate_trend_analysis(aggregator):
    """Demonstrate trend analysis capabilities."""
    print("\n📈 Trend Analysis")
    print("=" * 50)
    
    report = aggregator.get_startup_analysis_report(period_hours=24)
    
    if report.trends:
        for trend_name, trend_data in report.trends.items():
            print(f"📊 {trend_name.replace('_', ' ').title()}:")
            
            if trend_data:
                print(f"   Data Points: {len(trend_data)}")
                
                # Show recent trend
                if len(trend_data) >= 2:
                    recent = trend_data[-1]
                    previous = trend_data[-2]
                    
                    if trend_name == "startup_times":
                        current_avg = recent.get('avg_startup_time_ms', 0)
                        previous_avg = previous.get('avg_startup_time_ms', 0)
                        if previous_avg > 0:
                            change = ((current_avg - previous_avg) / previous_avg) * 100
                            trend_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                            print(f"   Recent Trend: {trend_emoji} {change:+.1f}% change")
                            print(f"   Current Avg: {current_avg:.1f}ms")
                            print(f"   Previous Avg: {previous_avg:.1f}ms")
                    
                    elif trend_name == "error_rates":
                        current_errors = recent.get('error_count', 0)
                        previous_errors = previous.get('error_count', 0)
                        change = current_errors - previous_errors
                        trend_emoji = "🚨" if change > 0 else "✅" if change < 0 else "➡️"
                        print(f"   Recent Trend: {trend_emoji} {change:+d} errors")
                        print(f"   Current: {current_errors} errors")
                        print(f"   Previous: {previous_errors} errors")
                
                # Show time range
                if trend_data:
                    first_time = trend_data[0].get('timestamp', 'unknown')
                    last_time = trend_data[-1].get('timestamp', 'unknown')
                    print(f"   Time Range: {first_time} to {last_time}")
            else:
                print("   No data available")
            print()


def main():
    """Main demonstration function."""
    print("🚀 Log Aggregation and Analysis System Demo")
    print("=" * 60)
    print()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "demo_startup_analysis.db")
        
        # Initialize system
        print("⚙️ Initializing Log Aggregation System...")
        aggregator = initialize_log_aggregator(db_path=db_path, retention_days=7)
        startup_logger = initialize_startup_logger()
        print("   ✅ System initialized")
        print()
        
        # Generate sample data
        generate_sample_startup_logs(aggregator, num_startups=5)
        
        # Wait for background processing
        print("\n⏳ Waiting for background processing...")
        time.sleep(2)
        
        # Demonstrate capabilities
        demonstrate_real_time_monitoring(aggregator)
        demonstrate_analysis_report(aggregator)
        demonstrate_trend_analysis(aggregator)
        demonstrate_data_export(aggregator)
        
        # Cleanup
        print("🛑 Stopping background processing...")
        aggregator.stop_background_processing()
        
        print("\n🎉 Demo completed successfully!")
        print("\n💡 Key Features Demonstrated:")
        print("   ✅ Real-time log aggregation and storage")
        print("   ✅ Comprehensive startup performance analysis")
        print("   ✅ Error pattern detection and classification")
        print("   ✅ Performance insights and recommendations")
        print("   ✅ Trend analysis over time")
        print("   ✅ Data export in multiple formats")
        print("   ✅ Background processing and caching")
        print("\n📚 This system provides the foundation for:")
        print("   • Automated startup performance monitoring")
        print("   • Proactive error detection and alerting")
        print("   • Data-driven optimization recommendations")
        print("   • Historical trend analysis and reporting")
        print("   • Integration with external monitoring tools")


if __name__ == "__main__":
    main()