#!/usr/bin/env python3
"""
Comprehensive Database Health Check Script

This script checks the health of all database services in the local development environment:
- PostgreSQL
- Neo4j
- Milvus (with etcd and MinIO dependencies)
- Redis

Usage:
    python scripts/check-all-database-health.py [--json] [--quiet] [--services SERVICE1,SERVICE2,...]
"""

import sys
import json
import time
import subprocess
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import argparse

# Database-specific health checkers
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

try:
    from pymilvus import connections, utility
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class DatabaseHealthChecker:
    """Comprehensive health checker for all database services."""
    
    def __init__(self):
        self.results: Dict[str, Dict[str, Any]] = {}
        self.start_time = datetime.now()
    
    def add_result(self, service: str, check_name: str, status: str, details: str, 
                   duration_ms: Optional[float] = None, error: Optional[str] = None):
        """Add a health check result for a service."""
        if service not in self.results:
            self.results[service] = {
                "service_name": service,
                "overall_status": "OK",
                "checks": [],
                "summary": {"ok": 0, "warning": 0, "critical": 0, "info": 0}
            }
        
        result = {
            "check_name": check_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        
        if duration_ms is not None:
            result["duration_ms"] = round(duration_ms, 2)
        
        if error:
            result["error"] = error
        
        self.results[service]["checks"].append(result)
        self.results[service]["summary"][status.lower()] += 1
        
        # Update overall status
        if status == "CRITICAL":
            self.results[service]["overall_status"] = "CRITICAL"
        elif status == "WARNING" and self.results[service]["overall_status"] != "CRITICAL":
            self.results[service]["overall_status"] = "WARNING"
    
    async def check_postgresql(self):
        """Check PostgreSQL health."""
        service = "postgresql"
        
        if not PSYCOPG2_AVAILABLE:
            self.add_result(service, "Dependency Check", "WARNING", 
                          "psycopg2 not available, using basic connectivity test")
            await self._check_postgresql_basic()
            return
        
        start_time = time.time()
        try:
            # Connection test
            conn = psycopg2.connect(
                host="localhost",
                port=5432,
                database="multimodal_librarian",
                user="ml_user",
                password="ml_password",
                connect_timeout=10
            )
            
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Connection Test", "OK", 
                          "Successfully connected to PostgreSQL", duration)
            
            # Run health check queries
            with conn.cursor() as cur:
                # Basic query test
                start_time = time.time()
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
                duration = (time.time() - start_time) * 1000
                self.add_result(service, "Version Check", "INFO", 
                              f"PostgreSQL version: {version.split()[1]}", duration)
                
                # Connection count check
                start_time = time.time()
                cur.execute("""
                    SELECT count(*) as active_connections 
                    FROM pg_stat_activity 
                    WHERE state = 'active'
                """)
                active_conn = cur.fetchone()[0]
                duration = (time.time() - start_time) * 1000
                
                status = "OK" if active_conn < 50 else "WARNING" if active_conn < 80 else "CRITICAL"
                self.add_result(service, "Active Connections", status,
                              f"Active connections: {active_conn}/100", duration)
                
                # Database size check
                start_time = time.time()
                cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
                db_size = cur.fetchone()[0]
                duration = (time.time() - start_time) * 1000
                self.add_result(service, "Database Size", "INFO",
                              f"Database size: {db_size}", duration)
                
                # Extension check
                start_time = time.time()
                cur.execute("""
                    SELECT count(*) FROM pg_extension 
                    WHERE extname IN ('uuid-ossp', 'pg_trgm', 'btree_gin', 'pg_stat_statements', 'pgcrypto', 'citext')
                """)
                ext_count = cur.fetchone()[0]
                duration = (time.time() - start_time) * 1000
                
                status = "OK" if ext_count >= 6 else "WARNING"
                self.add_result(service, "Required Extensions", status,
                              f"Installed extensions: {ext_count}/6", duration)
            
            conn.close()
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Connection Test", "CRITICAL",
                          "Failed to connect to PostgreSQL", duration, str(e))
    
    async def _check_postgresql_basic(self):
        """Basic PostgreSQL connectivity check using pg_isready."""
        service = "postgresql"
        start_time = time.time()
        
        try:
            result = subprocess.run(
                ["pg_isready", "-h", "localhost", "-p", "5432", "-U", "ml_user", "-d", "multimodal_librarian"],
                capture_output=True, text=True, timeout=10
            )
            duration = (time.time() - start_time) * 1000
            
            if result.returncode == 0:
                self.add_result(service, "Basic Connectivity", "OK",
                              "PostgreSQL is accepting connections", duration)
            else:
                self.add_result(service, "Basic Connectivity", "CRITICAL",
                              f"PostgreSQL not ready: {result.stderr.strip()}", duration)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Basic Connectivity", "CRITICAL",
                          "Failed to check PostgreSQL", duration, str(e))
    
    async def check_neo4j(self):
        """Check Neo4j health."""
        service = "neo4j"
        
        if not NEO4J_AVAILABLE:
            self.add_result(service, "Dependency Check", "WARNING",
                          "neo4j driver not available, using basic connectivity test")
            await self._check_neo4j_basic()
            return
        
        start_time = time.time()
        try:
            driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "ml_password"))
            
            with driver.session() as session:
                # Connection test
                duration = (time.time() - start_time) * 1000
                self.add_result(service, "Connection Test", "OK",
                              "Successfully connected to Neo4j", duration)
                
                # Version check
                start_time = time.time()
                result = session.run("CALL dbms.components() YIELD name, versions, edition "
                                   "WHERE name = 'Neo4j Kernel' RETURN versions[0] as version, edition")
                record = result.single()
                duration = (time.time() - start_time) * 1000
                self.add_result(service, "Version Check", "INFO",
                              f"Neo4j {record['version']} ({record['edition']})", duration)
                
                # APOC plugin check
                start_time = time.time()
                try:
                    result = session.run("CALL apoc.version() YIELD version RETURN version")
                    apoc_version = result.single()["version"]
                    duration = (time.time() - start_time) * 1000
                    self.add_result(service, "APOC Plugin", "OK",
                                  f"APOC version: {apoc_version}", duration)
                except Exception:
                    duration = (time.time() - start_time) * 1000
                    self.add_result(service, "APOC Plugin", "WARNING",
                                  "APOC plugin not available", duration)
                
                # GDS plugin check
                start_time = time.time()
                try:
                    result = session.run("CALL gds.version() YIELD version RETURN version")
                    gds_version = result.single()["version"]
                    duration = (time.time() - start_time) * 1000
                    self.add_result(service, "GDS Plugin", "OK",
                                  f"GDS version: {gds_version}", duration)
                except Exception:
                    duration = (time.time() - start_time) * 1000
                    self.add_result(service, "GDS Plugin", "WARNING",
                                  "GDS plugin not available", duration)
                
                # Database statistics
                start_time = time.time()
                result = session.run("CALL db.stats.retrieve('GRAPH COUNTS') YIELD data "
                                   "RETURN data.nodes as nodes, data.relationships as rels")
                record = result.single()
                duration = (time.time() - start_time) * 1000
                self.add_result(service, "Database Statistics", "INFO",
                              f"Nodes: {record['nodes']}, Relationships: {record['rels']}", duration)
            
            driver.close()
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Connection Test", "CRITICAL",
                          "Failed to connect to Neo4j", duration, str(e))
    
    async def _check_neo4j_basic(self):
        """Basic Neo4j connectivity check using cypher-shell."""
        service = "neo4j"
        start_time = time.time()
        
        try:
            result = subprocess.run(
                ["cypher-shell", "-a", "bolt://localhost:7687", "-u", "neo4j", "-p", "ml_password", "RETURN 1"],
                capture_output=True, text=True, timeout=15
            )
            duration = (time.time() - start_time) * 1000
            
            if result.returncode == 0:
                self.add_result(service, "Basic Connectivity", "OK",
                              "Neo4j is responding to queries", duration)
            else:
                self.add_result(service, "Basic Connectivity", "CRITICAL",
                              f"Neo4j not responding: {result.stderr.strip()}", duration)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Basic Connectivity", "CRITICAL",
                          "Failed to check Neo4j", duration, str(e))
    
    async def check_milvus(self):
        """Check Milvus health."""
        service = "milvus"
        
        if not PYMILVUS_AVAILABLE:
            self.add_result(service, "Dependency Check", "WARNING",
                          "pymilvus not available, using basic connectivity test")
            await self._check_milvus_basic()
            return
        
        start_time = time.time()
        try:
            connections.connect(host="localhost", port=19530, timeout=10)
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Connection Test", "OK",
                          "Successfully connected to Milvus", duration)
            
            # Version check
            start_time = time.time()
            version = utility.get_server_version()
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Version Check", "INFO",
                          f"Milvus version: {version}", duration)
            
            # Collections check
            start_time = time.time()
            collections = utility.list_collections()
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Collections", "INFO",
                          f"Collections: {len(collections)} ({', '.join(collections) if collections else 'none'})",
                          duration)
            
            connections.disconnect("default")
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Connection Test", "CRITICAL",
                          "Failed to connect to Milvus", duration, str(e))
    
    async def _check_milvus_basic(self):
        """Basic Milvus connectivity check using HTTP endpoint."""
        service = "milvus"
        start_time = time.time()
        
        try:
            result = subprocess.run(
                ["curl", "-f", "-s", "http://localhost:9091/healthz"],
                capture_output=True, text=True, timeout=10
            )
            duration = (time.time() - start_time) * 1000
            
            if result.returncode == 0:
                self.add_result(service, "Basic Connectivity", "OK",
                              "Milvus HTTP health endpoint responding", duration)
            else:
                self.add_result(service, "Basic Connectivity", "CRITICAL",
                              "Milvus health endpoint not responding", duration)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Basic Connectivity", "CRITICAL",
                          "Failed to check Milvus", duration, str(e))
    
    async def check_redis(self):
        """Check Redis health."""
        service = "redis"
        
        if not REDIS_AVAILABLE:
            self.add_result(service, "Dependency Check", "WARNING",
                          "redis-py not available, using basic connectivity test")
            await self._check_redis_basic()
            return
        
        start_time = time.time()
        try:
            r = redis.Redis(host="localhost", port=6379, decode_responses=True, socket_timeout=10)
            
            # Connection test
            pong = r.ping()
            duration = (time.time() - start_time) * 1000
            if pong:
                self.add_result(service, "Connection Test", "OK",
                              "Successfully connected to Redis", duration)
            else:
                self.add_result(service, "Connection Test", "CRITICAL",
                              "Redis ping failed", duration)
                return
            
            # Info check
            start_time = time.time()
            info = r.info()
            duration = (time.time() - start_time) * 1000
            
            version = info.get("redis_version", "unknown")
            memory_used = info.get("used_memory_human", "unknown")
            connected_clients = info.get("connected_clients", 0)
            
            self.add_result(service, "Server Info", "INFO",
                          f"Redis {version}, Memory: {memory_used}, Clients: {connected_clients}",
                          duration)
            
            # Memory usage check
            memory_used_bytes = info.get("used_memory", 0)
            maxmemory = info.get("maxmemory", 0)
            
            if maxmemory > 0:
                memory_pct = (memory_used_bytes / maxmemory) * 100
                status = "OK" if memory_pct < 80 else "WARNING" if memory_pct < 95 else "CRITICAL"
                self.add_result(service, "Memory Usage", status,
                              f"Memory usage: {memory_pct:.1f}% ({memory_used})")
            else:
                self.add_result(service, "Memory Usage", "INFO",
                              f"Memory usage: {memory_used} (no limit set)")
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Connection Test", "CRITICAL",
                          "Failed to connect to Redis", duration, str(e))
    
    async def _check_redis_basic(self):
        """Basic Redis connectivity check using redis-cli."""
        service = "redis"
        start_time = time.time()
        
        try:
            result = subprocess.run(
                ["redis-cli", "-h", "localhost", "-p", "6379", "ping"],
                capture_output=True, text=True, timeout=10
            )
            duration = (time.time() - start_time) * 1000
            
            if result.returncode == 0 and result.stdout.strip() == "PONG":
                self.add_result(service, "Basic Connectivity", "OK",
                              "Redis is responding to ping", duration)
            else:
                self.add_result(service, "Basic Connectivity", "CRITICAL",
                              f"Redis not responding: {result.stderr.strip()}", duration)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Basic Connectivity", "CRITICAL",
                          "Failed to check Redis", duration, str(e))
    
    async def check_dependencies(self):
        """Check Milvus dependencies (etcd and MinIO)."""
        # Check etcd
        service = "etcd"
        start_time = time.time()
        try:
            result = subprocess.run(
                ["curl", "-f", "-s", "http://localhost:2379/health"],
                capture_output=True, text=True, timeout=10
            )
            duration = (time.time() - start_time) * 1000
            
            if result.returncode == 0:
                self.add_result(service, "Health Check", "OK",
                              "etcd health endpoint responding", duration)
            else:
                self.add_result(service, "Health Check", "CRITICAL",
                              "etcd health endpoint not responding", duration)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Health Check", "CRITICAL",
                          "Failed to check etcd", duration, str(e))
        
        # Check MinIO
        service = "minio"
        start_time = time.time()
        try:
            result = subprocess.run(
                ["curl", "-f", "-s", "http://localhost:9000/minio/health/live"],
                capture_output=True, text=True, timeout=10
            )
            duration = (time.time() - start_time) * 1000
            
            if result.returncode == 0:
                self.add_result(service, "Health Check", "OK",
                              "MinIO health endpoint responding", duration)
            else:
                self.add_result(service, "Health Check", "CRITICAL",
                              "MinIO health endpoint not responding", duration)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(service, "Health Check", "CRITICAL",
                          "Failed to check MinIO", duration, str(e))
    
    async def run_all_checks(self, services: Optional[List[str]] = None):
        """Run health checks for all or specified services."""
        available_services = ["postgresql", "neo4j", "milvus", "redis", "dependencies"]
        
        if services:
            services = [s.lower() for s in services if s.lower() in available_services]
        else:
            services = available_services
        
        tasks = []
        if "postgresql" in services:
            tasks.append(self.check_postgresql())
        if "neo4j" in services:
            tasks.append(self.check_neo4j())
        if "milvus" in services:
            tasks.append(self.check_milvus())
        if "redis" in services:
            tasks.append(self.check_redis())
        if "dependencies" in services:
            tasks.append(self.check_dependencies())
        
        await asyncio.gather(*tasks)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get overall health check summary."""
        total_services = len(self.results)
        healthy_services = sum(1 for r in self.results.values() if r["overall_status"] == "OK")
        warning_services = sum(1 for r in self.results.values() if r["overall_status"] == "WARNING")
        critical_services = sum(1 for r in self.results.values() if r["overall_status"] == "CRITICAL")
        
        overall_status = "OK"
        if critical_services > 0:
            overall_status = "CRITICAL"
        elif warning_services > 0:
            overall_status = "WARNING"
        
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        return {
            "overall_status": overall_status,
            "summary": {
                "total_services": total_services,
                "healthy": healthy_services,
                "warning": warning_services,
                "critical": critical_services,
                "duration_seconds": round(duration, 2)
            },
            "services": self.results,
            "timestamp": end_time.isoformat()
        }


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Database Health Check")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--quiet", action="store_true", help="Only show summary")
    parser.add_argument("--services", help="Comma-separated list of services to check (postgresql,neo4j,milvus,redis,dependencies)")
    
    args = parser.parse_args()
    
    services = None
    if args.services:
        services = [s.strip() for s in args.services.split(",")]
    
    checker = DatabaseHealthChecker()
    await checker.run_all_checks(services)
    results = checker.get_summary()
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Human-readable output
        print(f"\n{'='*70}")
        print(f"DATABASE HEALTH CHECK RESULTS")
        print(f"{'='*70}")
        print(f"Overall Status: {results['overall_status']}")
        print(f"Duration: {results['summary']['duration_seconds']}s")
        print(f"Services: {results['summary']['healthy']}/{results['summary']['total_services']} healthy")
        if results['summary']['warning'] > 0:
            print(f"Warnings: {results['summary']['warning']}")
        if results['summary']['critical'] > 0:
            print(f"Critical: {results['summary']['critical']}")
        print(f"Timestamp: {results['timestamp']}")
        
        if not args.quiet:
            for service_name, service_data in results['services'].items():
                print(f"\n{'-'*50}")
                print(f"SERVICE: {service_name.upper()} [{service_data['overall_status']}]")
                print(f"{'-'*50}")
                
                for check in service_data['checks']:
                    duration_str = f" ({check['duration_ms']}ms)" if 'duration_ms' in check else ""
                    print(f"[{check['status']:>8}] {check['check_name']}: {check['details']}{duration_str}")
                    if 'error' in check:
                        print(f"           Error: {check['error']}")
    
    # Exit with appropriate code
    if results['overall_status'] == "CRITICAL":
        sys.exit(2)
    elif results['overall_status'] == "WARNING":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())