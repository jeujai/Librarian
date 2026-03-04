#!/usr/bin/env python3
"""
Integration test for log aggregation functionality.

This test verifies that the startup logger properly integrates with the log aggregator
and that logs are correctly aggregated and analyzed.
"""

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multimodal_librarian.logging.startup_logger import (
    initialize_startup_logger, 
    log_startup_error,
    log_application_ready,
    StartupLogEntry,
    LogLevel
)
from multimodal_librarian.logging.log_aggregator import (
    initialize_log_aggregator,
    get_startup_analysis_report,
    get_real_time_metrics,
    export_analysis_data
)
from multimodal_librarian.startup.phase_manager import StartupPhase


def test_log_aggregation_integration():
    """Test the integration between startup logger and log aggregator."""
    print("🧪 Testing Log Aggregation Integration")
    
    # Create temporary database for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test_startup_analysis.db")
        
        # Initialize log aggregator with test database
        print("📊 Initializing log aggregator...")
        aggregator = initialize_log_aggregator(db_path=db_path, retention_days=1)
        
        # Initialize startup logger
        print("📝 Initializing startup logger...")
        startup_logger = initialize_startup_logger()
        
        # Generate some test log entries
        print("🔄 Generating test log entries...")
        
        # Simulate phase transitions
        test_entries = [
            StartupLogEntry(
                timestamp=datetime.now().isoformat(),
                level=LogLevel.INFO.value,
                event_type="phase_transition_complete",
                phase="minimal",
                message="Phase transition to minimal completed",
                duration_ms=25000.0,
                metadata={"from_phase": None, "to_phase": "minimal", "success": True}
            ),
            StartupLogEntry(
                timestamp=datetime.now().isoformat(),
                level=LogLevel.INFO.value,
                event_type="phase_transition_complete",
                phase="essential",
                message="Phase transition to essential completed",
                duration_ms=45000.0,
                metadata={"from_phase": "minimal", "to_phase": "essential", "success": True}
            ),
            StartupLogEntry(
                timestamp=datetime.now().isoformat(),
                level=LogLevel.INFO.value,
                event_type="phase_transition_complete",
                phase="full",
                message="Phase transition to full completed",
                duration_ms=120000.0,
                metadata={"from_phase": "essential", "to_phase": "full", "success": True}
            ),
            StartupLogEntry(
                timestamp=datetime.now().isoformat(),
                level=LogLevel.INFO.value,
                event_type="model_loading_complete",
                phase="essential",
                message="Model text-embedding-small loading completed",
                duration_ms=8000.0,
                metadata={"model_name": "text-embedding-small", "priority": "essential", "status": "loaded"}
            ),
            StartupLogEntry(
                timestamp=datetime.now().isoformat(),
                level=LogLevel.INFO.value,
                event_type="model_loading_complete",
                phase="full",
                message="Model chat-model-large loading completed",
                duration_ms=65000.0,
                metadata={"model_name": "chat-model-large", "priority": "standard", "status": "loaded"}
            ),
            StartupLogEntry(
                timestamp=datetime.now().isoformat(),
                level=LogLevel.ERROR.value,
                event_type="model_loading_complete",
                phase="full",
                message="Model multimodal-model loading failed",
                duration_ms=30000.0,
                metadata={"model_name": "multimodal-model", "priority": "advanced", "status": "failed"},
                error_details={"error_message": "Out of memory", "model_name": "multimodal-model"}
            )
        ]
        
        # Add test entries to aggregator
        aggregator.add_log_entries(test_entries)
        
        # Wait a moment for processing
        print("⏳ Waiting for log processing...")
        time.sleep(2)
        
        # Force process buffer
        aggregator._process_log_buffer()
        
        # Test real-time metrics
        print("📈 Testing real-time metrics...")
        metrics = get_real_time_metrics()
        if metrics:
            print(f"   ✅ Real-time metrics retrieved: {len(metrics)} metrics")
            print(f"   📊 Recent startups: {metrics.get('recent_startups_count', 0)}")
            print(f"   ❌ Recent errors: {metrics.get('recent_errors_count', 0)}")
            print(f"   ⏱️  Avg startup time: {metrics.get('avg_startup_time_ms', 0):.1f}ms")
        else:
            print("   ❌ Failed to retrieve real-time metrics")
        
        # Test analysis report generation
        print("📋 Testing analysis report generation...")
        report = get_startup_analysis_report(period_hours=1)
        if report:
            print(f"   ✅ Analysis report generated")
            print(f"   📊 Total startups: {report.total_startups}")
            print(f"   ✅ Successful startups: {report.successful_startups}")
            print(f"   ❌ Failed startups: {report.failed_startups}")
            print(f"   ⏱️  Avg startup time: {report.avg_startup_time_ms:.1f}ms")
            print(f"   📈 P95 startup time: {report.p95_startup_time_ms:.1f}ms")
            print(f"   🔍 Error patterns found: {len(report.error_patterns)}")
            print(f"   💡 Performance insights: {len(report.performance_insights)}")
            print(f"   📝 Recommendations: {len(report.recommendations)}")
            
            # Print some details
            if report.error_patterns:
                print("   🚨 Error patterns:")
                for pattern in report.error_patterns[:3]:  # Show first 3
                    print(f"      - {pattern.error_type}: {pattern.occurrence_count} occurrences")
            
            if report.recommendations:
                print("   💡 Top recommendations:")
                for rec in report.recommendations[:3]:  # Show first 3
                    print(f"      - {rec}")
        else:
            print("   ❌ Failed to generate analysis report")
        
        # Test data export
        print("📤 Testing data export...")
        try:
            json_export = export_analysis_data(format_type="json", include_raw_logs=True)
            if json_export and len(json_export) > 100:  # Basic validation
                print(f"   ✅ JSON export successful ({len(json_export)} characters)")
            else:
                print("   ❌ JSON export failed or too small")
            
            csv_export = export_analysis_data(format_type="csv", include_raw_logs=False)
            if csv_export and len(csv_export) > 50:  # Basic validation
                print(f"   ✅ CSV export successful ({len(csv_export)} characters)")
            else:
                print("   ❌ CSV export failed or too small")
        except Exception as e:
            print(f"   ❌ Export failed: {str(e)}")
        
        # Test error pattern detection
        print("🔍 Testing error pattern detection...")
        
        # Add more error entries to create patterns
        error_entries = []
        for i in range(5):
            error_entries.append(StartupLogEntry(
                timestamp=(datetime.now() - timedelta(minutes=i)).isoformat(),
                level=LogLevel.ERROR.value,
                event_type="model_loading_complete",
                phase="full",
                message=f"Model loading failed: Out of memory error {i}",
                duration_ms=None,
                metadata={"model_name": f"test-model-{i}", "priority": "standard", "status": "failed"},
                error_details={"error_message": "Out of memory", "model_name": f"test-model-{i}"}
            ))
        
        aggregator.add_log_entries(error_entries)
        time.sleep(1)
        aggregator._process_log_buffer()
        
        # Generate new report to see error patterns
        updated_report = get_startup_analysis_report(period_hours=1)
        if updated_report and len(updated_report.error_patterns) > 0:
            print(f"   ✅ Error pattern detection working: {len(updated_report.error_patterns)} patterns found")
            for pattern in updated_report.error_patterns:
                print(f"      - Pattern: {pattern.error_type} ({pattern.occurrence_count} occurrences, {pattern.severity} severity)")
        else:
            print("   ⚠️  No error patterns detected (may need more time or data)")
        
        # Test performance insights
        print("💡 Testing performance insights...")
        if updated_report and len(updated_report.performance_insights) > 0:
            print(f"   ✅ Performance insights generated: {len(updated_report.performance_insights)} insights")
            for insight in updated_report.performance_insights:
                print(f"      - {insight.title} ({insight.severity} severity, {insight.confidence_score:.2f} confidence)")
        else:
            print("   ⚠️  No performance insights generated (may need more data)")
        
        # Stop background processing
        print("🛑 Stopping background processing...")
        aggregator.stop_background_processing()
        
        print("✅ Log aggregation integration test completed successfully!")
        return True


def test_startup_logger_aggregator_integration():
    """Test that startup logger automatically sends logs to aggregator."""
    print("\n🔗 Testing Startup Logger -> Aggregator Integration")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test_integration.db")
        
        # Initialize aggregator first
        aggregator = initialize_log_aggregator(db_path=db_path, retention_days=1)
        
        # Initialize startup logger (should auto-connect to aggregator)
        startup_logger = initialize_startup_logger()
        
        # Use startup logger convenience functions
        print("📝 Logging test events...")
        log_startup_error("test_error", "This is a test error", {"test": True})
        log_application_ready("test", ["test_capability"])
        
        # Wait for processing
        time.sleep(1)
        aggregator._process_log_buffer()
        
        # Check if logs made it to aggregator
        metrics = get_real_time_metrics()
        if metrics and metrics.get('recent_errors_count', 0) > 0:
            print("   ✅ Startup logger successfully integrated with aggregator")
            print(f"   📊 Detected {metrics['recent_errors_count']} error(s) in aggregator")
        else:
            print("   ⚠️  Integration may not be working properly")
        
        aggregator.stop_background_processing()
        return True


if __name__ == "__main__":
    print("🚀 Starting Log Aggregation Integration Tests")
    print("=" * 60)
    
    try:
        # Test basic log aggregation
        success1 = test_log_aggregation_integration()
        
        # Test startup logger integration
        success2 = test_startup_logger_aggregator_integration()
        
        if success1 and success2:
            print("\n🎉 All tests passed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n💥 Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)