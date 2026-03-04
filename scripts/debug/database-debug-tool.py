#!/usr/bin/env python3
"""
Database Debug Tool

Specialized debugging tool for local database services.
Provides detailed diagnostics for PostgreSQL, Neo4j, and Milvus.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import psycopg2
import requests
from neo4j import GraphDatabase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseDebugTool:
    """Database debugging and diagnostics tool."""
    
    def __init__(self):
        self.debug_output_dir = Path("debug_output/database")
        self.debug_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Database configurations
        self.postgres_config = {
            "host": "localhost",
            "port": 5432,
            "database": "multimodal_librarian",
            "user": "ml_user",
            "password": "ml_password"
        }
        
        self.neo4j_config = {
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "password": "ml_password"
        }
        
        self.milvus_config = {
            "host": "localhost",
            "port": 19530
        }
    
    def test_postgresql_connection(self) -> Dict[str, Any]:
        """Test PostgreSQL connection and gather diagnostics."""
        logger.info("🐘 Testing PostgreSQL connection...")
        
        result = {
            "service": "postgresql",
            "timestamp": datetime.now().isoformat(),
            "connection": {"status": "unknown"},
            "server_info": {},
            "database_info": {},
            "performance": {},
            "errors": []
        }
        
        try:
            # Test basic connection
            conn = psycopg2.connect(**self.postgres_config, connect_timeout=10)
            result["connection"]["status"] = "connected"
            logger.info("  ✅ Connection successful")
            
            cursor = conn.cursor()
            
            # Get server version
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            result["server_info"]["version"] = version
            logger.info(f"  📋 Version: {version.split(',')[0]}")
            
            # Get database size
            cursor.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database()));
            """)
            db_size = cursor.fetchone()[0]
            result["database_info"]["size"] = db_size
            logger.info(f"  💾 Database size: {db_size}")
            
            # Get table count
            cursor.execute("""
                SELECT count(*) FROM information_schema.tables 
                WHERE table_schema = 'public';
            """)
            table_count = cursor.fetchone()[0]
            result["database_info"]["table_count"] = table_count
            logger.info(f"  📊 Tables: {table_count}")
            
            # Get connection count
            cursor.execute("""
                SELECT count(*) FROM pg_stat_activity 
                WHERE state = 'active';
            """)
            active_connections = cursor.fetchone()[0]
            result["database_info"]["active_connections"] = active_connections
            logger.info(f"  🔗 Active connections: {active_connections}")
            
            # Test query performance
            start_time = time.time()
            cursor.execute("SELECT 1;")
            cursor.fetchone()
            query_time = time.time() - start_time
            result["performance"]["simple_query_ms"] = query_time * 1000
            logger.info(f"  ⚡ Simple query: {query_time * 1000:.2f}ms")
            
            # Check for slow queries
            cursor.execute("""
                SELECT query, mean_exec_time, calls 
                FROM pg_stat_statements 
                WHERE mean_exec_time > 100 
                ORDER BY mean_exec_time DESC 
                LIMIT 5;
            """)
            slow_queries = cursor.fetchall()
            if slow_queries:
                result["performance"]["slow_queries"] = [
                    {"query": q[0][:100], "mean_time_ms": q[1], "calls": q[2]}
                    for q in slow_queries
                ]
                logger.warning(f"  ⚠️ Found {len(slow_queries)} slow queries")
            
            cursor.close()
            conn.close()
            
        except psycopg2.OperationalError as e:
            result["connection"]["status"] = "failed"
            result["errors"].append(f"Connection failed: {e}")
            logger.error(f"  ❌ Connection failed: {e}")
            
        except Exception as e:
            result["errors"].append(f"Unexpected error: {e}")
            logger.error(f"  ❌ Unexpected error: {e}")
        
        return result
    
    def test_neo4j_connection(self) -> Dict[str, Any]:
        """Test Neo4j connection and gather diagnostics."""
        logger.info("🕸️ Testing Neo4j connection...")
        
        result = {
            "service": "neo4j",
            "timestamp": datetime.now().isoformat(),
            "connection": {"status": "unknown"},
            "server_info": {},
            "database_info": {},
            "performance": {},
            "errors": []
        }
        
        try:
            # Test basic connection
            driver = GraphDatabase.driver(
                self.neo4j_config["uri"],
                auth=(self.neo4j_config["user"], self.neo4j_config["password"])
            )
            
            with driver.session() as session:
                # Test connection
                session.run("RETURN 1")
                result["connection"]["status"] = "connected"
                logger.info("  ✅ Connection successful")
                
                # Get server info
                server_info = session.run("CALL dbms.components()").single()
                if server_info:
                    result["server_info"]["name"] = server_info["name"]
                    result["server_info"]["version"] = server_info["versions"][0]
                    result["server_info"]["edition"] = server_info["edition"]
                    logger.info(f"  📋 Version: {server_info['name']} {server_info['versions'][0]} ({server_info['edition']})")
                
                # Get database statistics
                stats = session.run("""
                    MATCH (n) 
                    RETURN count(n) as node_count
                """).single()
                
                if stats:
                    result["database_info"]["node_count"] = stats["node_count"]
                    logger.info(f"  📊 Nodes: {stats['node_count']}")
                
                # Get relationship count
                rel_stats = session.run("""
                    MATCH ()-[r]->() 
                    RETURN count(r) as relationship_count
                """).single()
                
                if rel_stats:
                    result["database_info"]["relationship_count"] = rel_stats["relationship_count"]
                    logger.info(f"  🔗 Relationships: {rel_stats['relationship_count']}")
                
                # Test query performance
                start_time = time.time()
                session.run("RETURN 1")
                query_time = time.time() - start_time
                result["performance"]["simple_query_ms"] = query_time * 1000
                logger.info(f"  ⚡ Simple query: {query_time * 1000:.2f}ms")
                
                # Check for indexes
                indexes = session.run("SHOW INDEXES").data()
                result["database_info"]["indexes"] = len(indexes)
                logger.info(f"  🗂️ Indexes: {len(indexes)}")
            
            driver.close()
            
        except Exception as e:
            result["connection"]["status"] = "failed"
            result["errors"].append(f"Connection failed: {e}")
            logger.error(f"  ❌ Connection failed: {e}")
        
        return result
    
    def test_milvus_connection(self) -> Dict[str, Any]:
        """Test Milvus connection and gather diagnostics."""
        logger.info("🔍 Testing Milvus connection...")
        
        result = {
            "service": "milvus",
            "timestamp": datetime.now().isoformat(),
            "connection": {"status": "unknown"},
            "server_info": {},
            "database_info": {},
            "performance": {},
            "errors": []
        }
        
        try:
            # Test health endpoint
            health_url = f"http://{self.milvus_config['host']}:9091/healthz"
            response = requests.get(health_url, timeout=10)
            
            if response.status_code == 200:
                result["connection"]["status"] = "connected"
                logger.info("  ✅ Health check successful")
            else:
                result["connection"]["status"] = "unhealthy"
                result["errors"].append(f"Health check failed: HTTP {response.status_code}")
                logger.error(f"  ❌ Health check failed: HTTP {response.status_code}")
                return result
            
            # Try to connect with pymilvus if available
            try:
                from pymilvus import connections, utility
                
                # Connect to Milvus
                connections.connect(
                    alias="default",
                    host=self.milvus_config["host"],
                    port=self.milvus_config["port"]
                )
                
                # Get server version
                version = utility.get_server_version()
                result["server_info"]["version"] = version
                logger.info(f"  📋 Version: {version}")
                
                # List collections
                collections = utility.list_collections()
                result["database_info"]["collections"] = collections
                result["database_info"]["collection_count"] = len(collections)
                logger.info(f"  📊 Collections: {len(collections)}")
                
                if collections:
                    logger.info(f"    Collections: {', '.join(collections)}")
                
                # Test query performance
                start_time = time.time()
                utility.list_collections()
                query_time = time.time() - start_time
                result["performance"]["list_collections_ms"] = query_time * 1000
                logger.info(f"  ⚡ List collections: {query_time * 1000:.2f}ms")
                
                connections.disconnect("default")
                
            except ImportError:
                logger.warning("  ⚠️ pymilvus not available, using HTTP API only")
                result["server_info"]["note"] = "Limited diagnostics (pymilvus not available)"
            
        except requests.RequestException as e:
            result["connection"]["status"] = "failed"
            result["errors"].append(f"HTTP request failed: {e}")
            logger.error(f"  ❌ HTTP request failed: {e}")
            
        except Exception as e:
            result["connection"]["status"] = "failed"
            result["errors"].append(f"Unexpected error: {e}")
            logger.error(f"  ❌ Unexpected error: {e}")
        
        return result
    
    def run_database_diagnostics(self) -> Dict[str, Any]:
        """Run comprehensive database diagnostics."""
        logger.info("🔬 Running comprehensive database diagnostics...")
        
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "databases": {}
        }
        
        # Test each database
        diagnostics["databases"]["postgresql"] = self.test_postgresql_connection()
        diagnostics["databases"]["neo4j"] = self.test_neo4j_connection()
        diagnostics["databases"]["milvus"] = self.test_milvus_connection()
        
        # Generate summary
        connected_dbs = [
            name for name, db in diagnostics["databases"].items()
            if db["connection"]["status"] == "connected"
        ]
        
        diagnostics["summary"] = {
            "total_databases": len(diagnostics["databases"]),
            "connected_databases": len(connected_dbs),
            "connected_list": connected_dbs,
            "overall_status": "healthy" if len(connected_dbs) == len(diagnostics["databases"]) else "degraded"
        }
        
        logger.info(f"📋 Summary: {len(connected_dbs)}/{len(diagnostics['databases'])} databases connected")
        
        # Save diagnostics report
        report_file = self.debug_output_dir / f"database_diagnostics_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(diagnostics, f, indent=2, default=str)
        
        logger.info(f"📄 Diagnostics saved to: {report_file}")
        
        return diagnostics
    
    def test_database_performance(self, duration: int = 30) -> Dict[str, Any]:
        """Test database performance over time."""
        logger.info(f"⚡ Testing database performance for {duration} seconds...")
        
        performance_data = {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration,
            "measurements": []
        }
        
        start_time = time.time()
        
        while time.time() - start_time < duration:
            measurement = {
                "timestamp": time.time(),
                "postgresql": {"query_time_ms": None, "error": None},
                "neo4j": {"query_time_ms": None, "error": None},
                "milvus": {"query_time_ms": None, "error": None}
            }
            
            # Test PostgreSQL
            try:
                conn = psycopg2.connect(**self.postgres_config, connect_timeout=5)
                cursor = conn.cursor()
                
                start = time.time()
                cursor.execute("SELECT 1;")
                cursor.fetchone()
                measurement["postgresql"]["query_time_ms"] = (time.time() - start) * 1000
                
                cursor.close()
                conn.close()
                
            except Exception as e:
                measurement["postgresql"]["error"] = str(e)
            
            # Test Neo4j
            try:
                driver = GraphDatabase.driver(
                    self.neo4j_config["uri"],
                    auth=(self.neo4j_config["user"], self.neo4j_config["password"])
                )
                
                with driver.session() as session:
                    start = time.time()
                    session.run("RETURN 1")
                    measurement["neo4j"]["query_time_ms"] = (time.time() - start) * 1000
                
                driver.close()
                
            except Exception as e:
                measurement["neo4j"]["error"] = str(e)
            
            # Test Milvus
            try:
                start = time.time()
                response = requests.get(f"http://{self.milvus_config['host']}:9091/healthz", timeout=5)
                if response.status_code == 200:
                    measurement["milvus"]["query_time_ms"] = (time.time() - start) * 1000
                else:
                    measurement["milvus"]["error"] = f"HTTP {response.status_code}"
                    
            except Exception as e:
                measurement["milvus"]["error"] = str(e)
            
            performance_data["measurements"].append(measurement)
            
            # Log current performance
            pg_time = measurement["postgresql"]["query_time_ms"]
            neo4j_time = measurement["neo4j"]["query_time_ms"]
            milvus_time = measurement["milvus"]["query_time_ms"]
            
            logger.info(f"  PG: {pg_time:.1f}ms, Neo4j: {neo4j_time:.1f}ms, Milvus: {milvus_time:.1f}ms")
            
            time.sleep(5)
        
        # Calculate averages
        pg_times = [m["postgresql"]["query_time_ms"] for m in performance_data["measurements"] if m["postgresql"]["query_time_ms"] is not None]
        neo4j_times = [m["neo4j"]["query_time_ms"] for m in performance_data["measurements"] if m["neo4j"]["query_time_ms"] is not None]
        milvus_times = [m["milvus"]["query_time_ms"] for m in performance_data["measurements"] if m["milvus"]["query_time_ms"] is not None]
        
        performance_data["averages"] = {
            "postgresql_avg_ms": sum(pg_times) / len(pg_times) if pg_times else None,
            "neo4j_avg_ms": sum(neo4j_times) / len(neo4j_times) if neo4j_times else None,
            "milvus_avg_ms": sum(milvus_times) / len(milvus_times) if milvus_times else None
        }
        
        # Save performance report
        report_file = self.debug_output_dir / f"database_performance_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(performance_data, f, indent=2, default=str)
        
        logger.info(f"📄 Performance data saved to: {report_file}")
        
        return performance_data


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Debug Tool")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Diagnostics command
    diag_parser = subparsers.add_parser("diagnostics", help="Run comprehensive database diagnostics")
    
    # Performance command
    perf_parser = subparsers.add_parser("performance", help="Test database performance")
    perf_parser.add_argument("--duration", "-d", type=int, default=30, help="Test duration in seconds")
    
    # Individual database tests
    pg_parser = subparsers.add_parser("postgresql", help="Test PostgreSQL only")
    neo4j_parser = subparsers.add_parser("neo4j", help="Test Neo4j only")
    milvus_parser = subparsers.add_parser("milvus", help="Test Milvus only")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize tool
    tool = DatabaseDebugTool()
    
    # Execute command
    if args.command == "diagnostics":
        tool.run_database_diagnostics()
    
    elif args.command == "performance":
        tool.test_database_performance(duration=args.duration)
    
    elif args.command == "postgresql":
        tool.test_postgresql_connection()
    
    elif args.command == "neo4j":
        tool.test_neo4j_connection()
    
    elif args.command == "milvus":
        tool.test_milvus_connection()


if __name__ == "__main__":
    main()