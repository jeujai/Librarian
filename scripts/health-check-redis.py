#!/usr/bin/env python3
"""
Redis Health Check Script

Dedicated health check script for Redis service in local development.
Provides detailed Redis-specific health monitoring and diagnostics.
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

class RedisHealthChecker:
    """Dedicated Redis health checker with comprehensive diagnostics."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self.client = None
        
    def connect(self, timeout: int = 10) -> bool:
        """Establish Redis connection with timeout."""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_timeout=timeout,
                socket_connect_timeout=timeout
            )
            
            # Test connection
            self.client.ping()
            return True
            
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            return False
    
    def disconnect(self):
        """Close Redis connection."""
        if self.client:
            try:
                self.client.close()
            except:
                pass
            self.client = None
    
    def check_basic_connectivity(self) -> Dict[str, Any]:
        """Test basic Redis connectivity."""
        start_time = time.time()
        
        try:
            if not self.connect():
                return {
                    "status": "CRITICAL",
                    "message": "Failed to connect to Redis",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            # Test ping
            pong = self.client.ping()
            if not pong:
                return {
                    "status": "CRITICAL",
                    "message": "Redis ping failed",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            return {
                "status": "OK",
                "message": "Redis connection successful",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {"ping_response": pong}
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Connection test failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_server_info(self) -> Dict[str, Any]:
        """Check Redis server information."""
        start_time = time.time()
        
        try:
            info = self.client.info()
            
            version = info.get("redis_version", "unknown")
            mode = info.get("redis_mode", "unknown")
            uptime = info.get("uptime_in_seconds", 0)
            
            return {
                "status": "OK",
                "message": f"Redis {version} ({mode}), uptime: {uptime}s",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "version": version,
                    "mode": mode,
                    "uptime_seconds": uptime,
                    "uptime_days": round(uptime / 86400, 2)
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Server info check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_memory_usage(self) -> Dict[str, Any]:
        """Check Redis memory usage."""
        start_time = time.time()
        
        try:
            info = self.client.info("memory")
            
            used_memory = info.get("used_memory", 0)
            used_memory_human = info.get("used_memory_human", "0B")
            maxmemory = info.get("maxmemory", 0)
            
            if maxmemory > 0:
                memory_pct = (used_memory / maxmemory) * 100
                status = "OK" if memory_pct < 80 else "WARNING" if memory_pct < 95 else "CRITICAL"
                message = f"Memory usage: {memory_pct:.1f}% ({used_memory_human})"
            else:
                status = "INFO"
                message = f"Memory usage: {used_memory_human} (no limit set)"
                memory_pct = 0
            
            return {
                "status": status,
                "message": message,
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "used_memory_bytes": used_memory,
                    "used_memory_human": used_memory_human,
                    "maxmemory_bytes": maxmemory,
                    "memory_usage_percentage": round(memory_pct, 2) if maxmemory > 0 else None
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Memory check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_client_connections(self) -> Dict[str, Any]:
        """Check Redis client connections."""
        start_time = time.time()
        
        try:
            info = self.client.info("clients")
            
            connected_clients = info.get("connected_clients", 0)
            blocked_clients = info.get("blocked_clients", 0)
            
            # Determine status based on connection count
            if connected_clients < 50:
                status = "OK"
            elif connected_clients < 100:
                status = "WARNING"
            else:
                status = "CRITICAL"
            
            return {
                "status": status,
                "message": f"Clients: {connected_clients} connected, {blocked_clients} blocked",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "connected_clients": connected_clients,
                    "blocked_clients": blocked_clients
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Client connections check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_keyspace_info(self) -> Dict[str, Any]:
        """Check Redis keyspace information."""
        start_time = time.time()
        
        try:
            info = self.client.info("keyspace")
            
            # Get database information
            databases = {}
            total_keys = 0
            
            for key, value in info.items():
                if key.startswith("db"):
                    db_num = key
                    # Parse db info: keys=X,expires=Y,avg_ttl=Z
                    db_info = {}
                    for item in value.split(","):
                        k, v = item.split("=")
                        db_info[k] = int(v)
                    databases[db_num] = db_info
                    total_keys += db_info.get("keys", 0)
            
            return {
                "status": "OK",
                "message": f"Keyspace: {total_keys} total keys across {len(databases)} databases",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "total_keys": total_keys,
                    "databases": databases
                }
            }
        except Exception as e:
            return {
                "status": "INFO",
                "message": f"Keyspace info: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_persistence_config(self) -> Dict[str, Any]:
        """Check Redis persistence configuration."""
        start_time = time.time()
        
        try:
            info = self.client.info("persistence")
            
            aof_enabled = info.get("aof_enabled", 0) == 1
            rdb_last_save_time = info.get("rdb_last_save_time", 0)
            
            # Check if persistence is configured
            if aof_enabled or rdb_last_save_time > 0:
                status = "OK"
                message = f"Persistence enabled (AOF: {aof_enabled}, RDB: {rdb_last_save_time > 0})"
            else:
                status = "WARNING"
                message = "No persistence configured"
            
            return {
                "status": status,
                "message": message,
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "aof_enabled": aof_enabled,
                    "rdb_last_save_time": rdb_last_save_time,
                    "rdb_changes_since_last_save": info.get("rdb_changes_since_last_save", 0)
                }
            }
        except Exception as e:
            return {
                "status": "INFO",
                "message": f"Persistence check: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_performance_stats(self) -> Dict[str, Any]:
        """Check Redis performance statistics."""
        start_time = time.time()
        
        try:
            info = self.client.info("stats")
            
            total_commands = info.get("total_commands_processed", 0)
            ops_per_sec = info.get("instantaneous_ops_per_sec", 0)
            keyspace_hits = info.get("keyspace_hits", 0)
            keyspace_misses = info.get("keyspace_misses", 0)
            
            # Calculate hit rate
            total_requests = keyspace_hits + keyspace_misses
            hit_rate = (keyspace_hits / total_requests * 100) if total_requests > 0 else 0
            
            # Determine status based on hit rate
            if hit_rate > 90:
                status = "OK"
            elif hit_rate > 70:
                status = "WARNING"
            else:
                status = "INFO"  # Not critical for development
            
            return {
                "status": status,
                "message": f"Performance: {ops_per_sec} ops/sec, {hit_rate:.1f}% hit rate",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "total_commands_processed": total_commands,
                    "ops_per_sec": ops_per_sec,
                    "keyspace_hits": keyspace_hits,
                    "keyspace_misses": keyspace_misses,
                    "hit_rate_percentage": round(hit_rate, 2)
                }
            }
        except Exception as e:
            return {
                "status": "INFO",
                "message": f"Performance stats: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_basic_operations(self) -> Dict[str, Any]:
        """Test basic Redis operations."""
        start_time = time.time()
        
        try:
            test_key = "health_check_test"
            test_value = f"health_check_{int(time.time())}"
            
            # Test SET operation
            set_result = self.client.set(test_key, test_value, ex=60)  # Expire in 60 seconds
            if not set_result:
                raise Exception("SET operation failed")
            
            # Test GET operation
            get_result = self.client.get(test_key)
            if get_result != test_value:
                raise Exception("GET operation failed or value mismatch")
            
            # Test DELETE operation
            del_result = self.client.delete(test_key)
            if del_result != 1:
                raise Exception("DELETE operation failed")
            
            # Test that key is gone
            final_get = self.client.get(test_key)
            if final_get is not None:
                raise Exception("Key still exists after deletion")
            
            return {
                "status": "OK",
                "message": "Basic operations (SET/GET/DELETE) successful",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "operations_tested": ["SET", "GET", "DELETE"],
                    "test_key": test_key
                }
            }
        except Exception as e:
            # Clean up in case of error
            try:
                self.client.delete(test_key)
            except:
                pass
            
            return {
                "status": "CRITICAL",
                "message": f"Basic operations failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def run_comprehensive_check(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive results."""
        if not REDIS_AVAILABLE:
            return {
                "status": "CRITICAL",
                "message": "redis-py not available - cannot perform Redis health checks",
                "timestamp": datetime.now().isoformat(),
                "checks": {}
            }
        
        start_time = datetime.now()
        checks = {}
        
        # Run all checks
        check_methods = [
            ("connectivity", self.check_basic_connectivity),
            ("server_info", self.check_server_info),
            ("memory_usage", self.check_memory_usage),
            ("client_connections", self.check_client_connections),
            ("keyspace_info", self.check_keyspace_info),
            ("persistence_config", self.check_persistence_config),
            ("performance_stats", self.check_performance_stats),
            ("basic_operations", self.check_basic_operations)
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
            "service": "redis",
            "status": overall_status,
            "message": f"Redis health check completed ({overall_status})",
            "timestamp": end_time.isoformat(),
            "duration_seconds": round(total_duration, 2),
            "connection_info": {
                "host": self.host,
                "port": self.port,
                "database": self.db
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
    parser = argparse.ArgumentParser(description="Redis Health Check")
    parser.add_argument("--host", default="localhost", help="Redis host")
    parser.add_argument("--port", type=int, default=6379, help="Redis port")
    parser.add_argument("--db", type=int, default=0, help="Redis database number")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    
    args = parser.parse_args()
    
    # Override with environment variables if available
    host = os.getenv("REDIS_HOST", args.host)
    port = int(os.getenv("REDIS_PORT", args.port))
    db = int(os.getenv("REDIS_DB", args.db))
    
    checker = RedisHealthChecker(host, port, db)
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
        print(f"Redis Health Check Results")
        print(f"{'='*60}")
        print(f"Overall Status: {status_emoji.get(results['status'], '?')} {results['status']}")
        print(f"Duration: {results['duration_seconds']}s")
        print(f"Timestamp: {results['timestamp']}")
        
        if not args.quiet:
            print(f"\nConnection: {host}:{port}/{db}")
            
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