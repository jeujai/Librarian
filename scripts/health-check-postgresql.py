#!/usr/bin/env python3
"""
PostgreSQL Health Check Script

Dedicated health check script for PostgreSQL service in local development.
Provides detailed PostgreSQL-specific health monitoring and diagnostics.
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

class PostgreSQLHealthChecker:
    """Dedicated PostgreSQL health checker with comprehensive diagnostics."""
    
    def __init__(self, host: str = "localhost", port: int = 5432, 
                 database: str = "multimodal_librarian", user: str = "ml_user", 
                 password: str = "ml_password"):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.connection = None
        
    def connect(self, timeout: int = 10) -> bool:
        """Establish database connection with timeout."""
        try:
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=timeout,
                cursor_factory=RealDictCursor
            )
            return True
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            return False
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Execute query and return results."""
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def check_basic_connectivity(self) -> Dict[str, Any]:
        """Test basic database connectivity."""
        start_time = time.time()
        
        try:
            if not self.connect():
                return {
                    "status": "CRITICAL",
                    "message": "Failed to connect to PostgreSQL",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            result = self.execute_query("SELECT version(), current_database(), current_user, now()")
            row = result[0]
            
            return {
                "status": "OK",
                "message": "PostgreSQL connection successful",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "version": row["version"].split()[1],
                    "database": row["current_database"],
                    "user": row["current_user"],
                    "server_time": row["now"].isoformat()
                }
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Connection test failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_database_size(self) -> Dict[str, Any]:
        """Check database size and growth."""
        start_time = time.time()
        
        try:
            result = self.execute_query("""
                SELECT 
                    pg_size_pretty(pg_database_size(current_database())) as size_pretty,
                    pg_database_size(current_database()) as size_bytes,
                    (SELECT count(*) FROM information_schema.tables 
                     WHERE table_schema NOT IN ('information_schema', 'pg_catalog')) as user_tables
            """)
            
            row = result[0]
            size_mb = row["size_bytes"] / (1024 * 1024)
            
            # Determine status based on size
            if size_mb < 100:
                status = "OK"
            elif size_mb < 500:
                status = "WARNING"
            else:
                status = "CRITICAL"
            
            return {
                "status": status,
                "message": f"Database size: {row['size_pretty']}",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "size_pretty": row["size_pretty"],
                    "size_bytes": row["size_bytes"],
                    "size_mb": round(size_mb, 2),
                    "user_tables": row["user_tables"]
                }
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Database size check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_connections(self) -> Dict[str, Any]:
        """Check connection statistics."""
        start_time = time.time()
        
        try:
            result = self.execute_query("""
                SELECT 
                    count(*) as total_connections,
                    count(*) FILTER (WHERE state = 'active') as active_connections,
                    count(*) FILTER (WHERE state = 'idle') as idle_connections,
                    count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction,
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
                FROM pg_stat_activity
            """)
            
            row = result[0]
            usage_pct = (row["total_connections"] / row["max_connections"]) * 100
            
            # Determine status based on connection usage
            if usage_pct < 50:
                status = "OK"
            elif usage_pct < 80:
                status = "WARNING"
            else:
                status = "CRITICAL"
            
            return {
                "status": status,
                "message": f"Connections: {row['total_connections']}/{row['max_connections']} ({usage_pct:.1f}%)",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "total_connections": row["total_connections"],
                    "active_connections": row["active_connections"],
                    "idle_connections": row["idle_connections"],
                    "idle_in_transaction": row["idle_in_transaction"],
                    "max_connections": row["max_connections"],
                    "usage_percentage": round(usage_pct, 2)
                }
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Connection check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_extensions(self) -> Dict[str, Any]:
        """Check required PostgreSQL extensions."""
        start_time = time.time()
        
        required_extensions = [
            'uuid-ossp', 'pg_trgm', 'btree_gin', 
            'pg_stat_statements', 'pgcrypto', 'citext'
        ]
        
        try:
            result = self.execute_query("""
                SELECT extname, extversion 
                FROM pg_extension 
                WHERE extname = ANY(%s)
            """, (required_extensions,))
            
            installed = {row["extname"]: row["extversion"] for row in result}
            missing = set(required_extensions) - set(installed.keys())
            
            if not missing:
                status = "OK"
                message = f"All {len(required_extensions)} required extensions installed"
            else:
                status = "WARNING"
                message = f"Missing extensions: {', '.join(missing)}"
            
            return {
                "status": status,
                "message": message,
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "required": required_extensions,
                    "installed": installed,
                    "missing": list(missing)
                }
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Extension check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_performance_stats(self) -> Dict[str, Any]:
        """Check database performance statistics."""
        start_time = time.time()
        
        try:
            # Check if pg_stat_statements is available
            result = self.execute_query("""
                SELECT count(*) as has_pg_stat_statements
                FROM pg_extension 
                WHERE extname = 'pg_stat_statements'
            """)
            
            if result[0]["has_pg_stat_statements"] == 0:
                return {
                    "status": "WARNING",
                    "message": "pg_stat_statements extension not available",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            # Get performance statistics
            result = self.execute_query("""
                SELECT 
                    sum(calls) as total_queries,
                    round(avg(mean_exec_time)::numeric, 2) as avg_query_time_ms,
                    round(max(mean_exec_time)::numeric, 2) as max_avg_query_time_ms,
                    count(*) as unique_queries
                FROM pg_stat_statements
                WHERE calls > 0
            """)
            
            if not result or result[0]["total_queries"] is None:
                return {
                    "status": "INFO",
                    "message": "No query statistics available yet",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            row = result[0]
            avg_time = float(row["avg_query_time_ms"] or 0)
            
            # Determine status based on average query time
            if avg_time < 10:
                status = "OK"
            elif avg_time < 50:
                status = "WARNING"
            else:
                status = "CRITICAL"
            
            return {
                "status": status,
                "message": f"Avg query time: {avg_time}ms",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "total_queries": row["total_queries"],
                    "avg_query_time_ms": avg_time,
                    "max_avg_query_time_ms": float(row["max_avg_query_time_ms"] or 0),
                    "unique_queries": row["unique_queries"]
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Performance stats check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_replication_lag(self) -> Dict[str, Any]:
        """Check replication lag (if applicable)."""
        start_time = time.time()
        
        try:
            # Check if this is a replica
            result = self.execute_query("SELECT pg_is_in_recovery()")
            is_replica = result[0]["pg_is_in_recovery"]
            
            if not is_replica:
                return {
                    "status": "INFO",
                    "message": "Not a replica server",
                    "duration_ms": (time.time() - start_time) * 1000,
                    "details": {"is_replica": False}
                }
            
            # Get replication lag
            result = self.execute_query("""
                SELECT 
                    CASE 
                        WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() THEN 0
                        ELSE EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))
                    END as lag_seconds
            """)
            
            lag_seconds = float(result[0]["lag_seconds"] or 0)
            
            if lag_seconds < 5:
                status = "OK"
            elif lag_seconds < 30:
                status = "WARNING"
            else:
                status = "CRITICAL"
            
            return {
                "status": status,
                "message": f"Replication lag: {lag_seconds:.2f}s",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "is_replica": True,
                    "lag_seconds": lag_seconds
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Replication check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_locks(self) -> Dict[str, Any]:
        """Check for blocking locks."""
        start_time = time.time()
        
        try:
            result = self.execute_query("""
                SELECT 
                    count(*) as total_locks,
                    count(*) FILTER (WHERE NOT granted) as waiting_locks,
                    count(DISTINCT pid) as processes_with_locks
                FROM pg_locks
                WHERE locktype != 'virtualxid'
            """)
            
            row = result[0]
            waiting_locks = row["waiting_locks"]
            
            if waiting_locks == 0:
                status = "OK"
                message = f"No waiting locks ({row['total_locks']} total locks)"
            elif waiting_locks < 5:
                status = "WARNING"
                message = f"{waiting_locks} waiting locks"
            else:
                status = "CRITICAL"
                message = f"{waiting_locks} waiting locks (potential deadlock)"
            
            return {
                "status": status,
                "message": message,
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "total_locks": row["total_locks"],
                    "waiting_locks": waiting_locks,
                    "processes_with_locks": row["processes_with_locks"]
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Lock check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def run_comprehensive_check(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive results."""
        if not PSYCOPG2_AVAILABLE:
            return {
                "status": "CRITICAL",
                "message": "psycopg2 not available - cannot perform PostgreSQL health checks",
                "timestamp": datetime.now().isoformat(),
                "checks": {}
            }
        
        start_time = datetime.now()
        checks = {}
        
        # Run all checks
        check_methods = [
            ("connectivity", self.check_basic_connectivity),
            ("database_size", self.check_database_size),
            ("connections", self.check_connections),
            ("extensions", self.check_extensions),
            ("performance", self.check_performance_stats),
            ("replication", self.check_replication_lag),
            ("locks", self.check_locks)
        ]
        
        overall_status = "OK"
        
        for check_name, check_method in check_methods:
            try:
                result = check_method()
                checks[check_name] = result
                
                # Update overall status
                if result["status"] == "CRITICAL":
                    overall_status = "CRITICAL"
                elif result["status"] == "WARNING" and overall_status != "CRITICAL":
                    overall_status = "WARNING"
                    
            except Exception as e:
                checks[check_name] = {
                    "status": "CRITICAL",
                    "message": f"Check failed: {str(e)}",
                    "duration_ms": 0
                }
                overall_status = "CRITICAL"
            finally:
                self.disconnect()
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        return {
            "service": "postgresql",
            "status": overall_status,
            "message": f"PostgreSQL health check completed ({overall_status})",
            "timestamp": end_time.isoformat(),
            "duration_seconds": round(total_duration, 2),
            "connection_info": {
                "host": self.host,
                "port": self.port,
                "database": self.database,
                "user": self.user
            },
            "checks": checks,
            "summary": {
                "total_checks": len(checks),
                "ok": sum(1 for c in checks.values() if c["status"] == "OK"),
                "warning": sum(1 for c in checks.values() if c["status"] == "WARNING"),
                "critical": sum(1 for c in checks.values() if c["status"] == "CRITICAL"),
                "info": sum(1 for c in checks.values() if c["status"] == "INFO")
            }
        }


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="PostgreSQL Health Check")
    parser.add_argument("--host", default="localhost", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--database", default="multimodal_librarian", help="Database name")
    parser.add_argument("--user", default="ml_user", help="Database user")
    parser.add_argument("--password", default="ml_password", help="Database password")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    
    args = parser.parse_args()
    
    # Override with environment variables if available
    host = os.getenv("POSTGRES_HOST", args.host)
    port = int(os.getenv("POSTGRES_PORT", args.port))
    database = os.getenv("POSTGRES_DB", args.database)
    user = os.getenv("POSTGRES_USER", args.user)
    password = os.getenv("POSTGRES_PASSWORD", args.password)
    
    checker = PostgreSQLHealthChecker(host, port, database, user, password)
    results = checker.run_comprehensive_check()
    
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
        
        print(f"\n{'='*60}")
        print(f"PostgreSQL Health Check Results")
        print(f"{'='*60}")
        print(f"Overall Status: {status_emoji.get(results['status'], '?')} {results['status']}")
        print(f"Duration: {results['duration_seconds']}s")
        print(f"Timestamp: {results['timestamp']}")
        
        if not args.quiet:
            print(f"\nConnection: {host}:{port}/{database} (user: {user})")
            
            print(f"\nCheck Results:")
            for check_name, check_result in results['checks'].items():
                emoji = status_emoji.get(check_result['status'], '?')
                duration = check_result.get('duration_ms', 0)
                print(f"  {emoji} {check_name.replace('_', ' ').title()}: {check_result['message']} ({duration:.1f}ms)")
            
            summary = results['summary']
            print(f"\nSummary: {summary['ok']} OK, {summary['warning']} Warning, {summary['critical']} Critical, {summary['info']} Info")
    
    # Exit with appropriate code
    if results['status'] == "CRITICAL":
        sys.exit(2)
    elif results['status'] == "WARNING":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()