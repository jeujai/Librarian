#!/usr/bin/env python3
"""
Simple test to debug log aggregation issues.
"""

import os
import sys
import tempfile
import time
import sqlite3
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multimodal_librarian.logging.startup_logger import StartupLogEntry, LogLevel
from multimodal_librarian.logging.log_aggregator import LogAggregator


def test_direct_aggregation():
    """Test log aggregation directly."""
    print("🧪 Testing Direct Log Aggregation")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test.db")
        
        # Create aggregator
        aggregator = LogAggregator(db_path=db_path, retention_days=1)
        
        # Create test log entry
        log_entry = StartupLogEntry(
            timestamp=datetime.now().isoformat(),
            level=LogLevel.ERROR.value,
            event_type="startup_error",
            phase="test",
            message="Test error message",
            metadata={"test": True},
            error_details={"error_message": "Test error"}
        )
        
        print(f"📝 Adding log entry: {log_entry.event_type}")
        aggregator.add_log_entry(log_entry)
        
        # Force processing
        print("⚙️ Processing buffer...")
        aggregator._process_log_buffer()
        
        # Check database directly
        print("🔍 Checking database...")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if log was stored
            cursor.execute("SELECT COUNT(*) FROM startup_logs")
            log_count = cursor.fetchone()[0]
            print(f"   📊 Logs in database: {log_count}")
            
            if log_count > 0:
                cursor.execute("SELECT event_type, level, message FROM startup_logs LIMIT 5")
                logs = cursor.fetchall()
                for log in logs:
                    print(f"   📝 Log: {log[0]} ({log[1]}) - {log[2]}")
            
            # Check recent errors
            cursor.execute("""
                SELECT COUNT(*) FROM startup_logs 
                WHERE level = 'ERROR' 
                AND timestamp >= datetime('now', '-1 hour')
            """)
            recent_errors = cursor.fetchone()[0]
            print(f"   ❌ Recent errors: {recent_errors}")
        
        # Test real-time metrics
        print("📈 Testing real-time metrics...")
        metrics = aggregator.get_real_time_metrics()
        print(f"   📊 Metrics: {metrics}")
        
        return log_count > 0


if __name__ == "__main__":
    success = test_direct_aggregation()
    if success:
        print("✅ Direct aggregation test passed!")
    else:
        print("❌ Direct aggregation test failed!")
    sys.exit(0 if success else 1)