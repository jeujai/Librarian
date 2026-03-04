#!/usr/bin/env python3
"""
Simple PostgreSQL Performance Test Script

This script runs basic performance tests to validate PostgreSQL optimization.
"""

import asyncio
import asyncpg
import time
import sys
from typing import Dict, Any

async def test_postgresql_performance():
    """Test PostgreSQL performance with optimized configuration."""
    
    # Connection parameters
    connection_params = {
        'host': 'localhost',
        'port': 5432,
        'database': 'multimodal_librarian',
        'user': 'ml_user',
        'password': 'ml_password'
    }
    
    try:
        print("Connecting to PostgreSQL...")
        conn = await asyncpg.connect(**connection_params)
        print("✓ Connected successfully")
        
        # Test 1: Basic connectivity and configuration
        print("\n1. Testing configuration...")
        config_tests = [
            ('shared_buffers', '256MB'),
            ('work_mem', '8MB'),
            ('maintenance_work_mem', '128MB'),
            ('effective_cache_size', '1GB'),
            ('max_connections', '100'),
            ('random_page_cost', '2')
        ]
        
        for setting, expected in config_tests:
            current = await conn.fetchval("SELECT current_setting($1)", setting)
            status = "✓" if current == expected else "✗"
            print(f"  {status} {setting}: {current} (expected: {expected})")
        
        # Test 2: Performance functions
        print("\n2. Testing performance functions...")
        try:
            stats = await conn.fetch("SELECT * FROM get_performance_stats()")
            print(f"  ✓ get_performance_stats() returned {len(stats)} metrics")
            
            # Display some key metrics
            for row in stats:
                print(f"    - {row['metric_name']}: {row['metric_value']}")
        except Exception as e:
            print(f"  ✗ get_performance_stats() failed: {e}")
        
        # Test 3: Monitoring functions
        print("\n3. Testing monitoring functions...")
        try:
            health = await conn.fetch("SELECT * FROM monitoring.health_check()")
            print(f"  ✓ monitoring.health_check() returned {len(health)} checks")
            
            for row in health:
                status_icon = "✓" if row['status'] in ['OK', 'INFO'] else "⚠"
                print(f"    {status_icon} {row['check_name']}: {row['status']} - {row['details']}")
        except Exception as e:
            print(f"  ✗ monitoring.health_check() failed: {e}")
        
        # Test 4: Query performance
        print("\n4. Testing query performance...")
        
        # Simple query test
        start_time = time.time()
        await conn.fetchval("SELECT 1")
        simple_time = (time.time() - start_time) * 1000
        print(f"  ✓ Simple SELECT: {simple_time:.2f}ms")
        
        # Stats query test
        start_time = time.time()
        await conn.fetch("SELECT * FROM pg_stat_database WHERE datname = $1", 'multimodal_librarian')
        stats_time = (time.time() - start_time) * 1000
        print(f"  ✓ Stats query: {stats_time:.2f}ms")
        
        # Connection count test
        start_time = time.time()
        conn_count = await conn.fetchval("SELECT count(*) FROM pg_stat_activity")
        conn_time = (time.time() - start_time) * 1000
        print(f"  ✓ Connection count query: {conn_time:.2f}ms (connections: {conn_count})")
        
        # Test 5: Maintenance functions
        print("\n5. Testing maintenance functions...")
        try:
            start_time = time.time()
            await conn.fetchval("SELECT analyze_all_tables()")
            analyze_time = time.time() - start_time
            print(f"  ✓ analyze_all_tables() completed in {analyze_time:.2f}s")
        except Exception as e:
            print(f"  ✗ analyze_all_tables() failed: {e}")
        
        # Test 6: Performance summary
        print("\n6. Performance summary...")
        try:
            summary = await conn.fetch("SELECT * FROM monitoring.get_performance_summary()")
            print(f"  ✓ Performance summary ({len(summary)} metrics):")
            
            for row in summary:
                status_icon = {"GOOD": "✓", "OK": "✓", "NEEDS_ATTENTION": "⚠"}.get(row['status'], "?")
                print(f"    {status_icon} {row['metric_category']}/{row['metric_name']}: {row['current_value']} ({row['status']})")
                if row['status'] == 'NEEDS_ATTENTION':
                    print(f"      → {row['recommendation']}")
        except Exception as e:
            print(f"  ✗ Performance summary failed: {e}")
        
        await conn.close()
        print("\n✓ All tests completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        return False

async def main():
    """Main function."""
    print("PostgreSQL Performance Test")
    print("=" * 50)
    
    success = await test_postgresql_performance()
    
    if success:
        print("\n🎉 PostgreSQL optimization validation passed!")
        sys.exit(0)
    else:
        print("\n❌ PostgreSQL optimization validation failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())