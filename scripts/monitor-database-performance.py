#!/usr/bin/env python3
"""
Database Performance Monitor for Local Development

This script specifically monitors database performance metrics for:
- PostgreSQL: Query performance, connection pools, slow queries
- Neo4j: Cypher query performance, memory usage, transaction stats
- Milvus: Vector operations, index performance, collection stats

Usage:
    python scripts/monitor-database-performance.py [options]

Options:
    --database DB         Database to monitor (postgres, neo4j, milvus, all)
    --interval SECONDS    Monitoring interval in seconds (default: 10)
    --duration MINUTES    Total monitoring duration in minutes (default: 30)
    --output FILE         Output file for performance data
    --threshold-cpu PCT   CPU threshold for alerts (default: 80)
    --threshold-memory MB Memory threshold for alerts (default: 1000)
    --verbose             Enable verbose logging
"""

import asyncio
import json
import time
import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import asyncpg
import neo4j
from pymilvus import connections, Collection, utility
import psutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class DatabaseMetrics:
    """Container for database performance metrics."""
    timestamp: str
    database: str
    query_count: int
    avg_query_time_ms: float
    slow_queries: int
    active_connections: int
    memory_usage_mb: float
    cpu_percent: float
    custom_metrics: Dict[str, Any]
    alerts: List[str]

class DatabasePerformanceMonitor:
    """Monitor database performance for local development."""
    
    def __init__(self, interval: int = 10, cpu_threshold: float = 80, memory_threshold: float = 1000):
        self.interval = interval
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.metrics_history: List[DatabaseMetrics] = []
        self.start_time = datetime.now()
        
        # Database configurations
        self.postgres_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'multimodal_librarian',
            'user': 'ml_user',
            'password': 'ml_password'
        }
        
        self.neo4j_config = {
            'uri': 'bolt://localhost:7687',
            'user': 'neo4j',
            'password': 'ml_password'
        }
        
        self.milvus_config = {
            'host': 'localhost',
            'port': 19530
        }
    
    async def _monitor_postgres(self) -> DatabaseMetrics:
        """Monitor PostgreSQL performance."""
        alerts = []
        custom_metrics = {}
        
        try:
            conn = await asyncpg.connect(**self.postgres_config)
            
            # Query statistics from pg_stat_statements
            query_stats = await conn.fetch("""
                SELECT 
                    calls,
                    total_time,
                    mean_time,
                    max_time,
                    min_time,
                    rows,
                    query
                FROM pg_stat_statements 
                WHERE calls > 0
                ORDER BY total_time DESC 
                LIMIT 20
            """)
            
            # Connection statistics
            connection_stats = await conn.fetchrow("""
                SELECT 
                    count(*) as total_connections,
                    count(*) FILTER (WHERE state = 'active') as active_connections,
                    count(*) FILTER (WHERE state = 'idle') as idle_connections,
                    count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
                FROM pg_stat_activity
                WHERE pid != pg_backend_pid()
            """)
            
            # Database statistics
            db_stats = await conn.fetchrow("""
                SELECT 
                    numbackends,
                    xact_commit,
                    xact_rollback,
                    blks_read,
                    blks_hit,
                    tup_returned,
                    tup_fetched,
                    tup_inserted,
                    tup_updated,
                    tup_deleted
                FROM pg_stat_database 
                WHERE datname = 'multimodal_librarian'
            """)
            
            # Lock statistics
            lock_stats = await conn.fetch("""
                SELECT mode, count(*) as count
                FROM pg_locks 
                GROUP BY mode
                ORDER BY count DESC
            """)
            
            # Slow queries (queries taking more than 1 second)
            slow_queries = [q for q in query_stats if q['mean_time'] > 1000]
            
            # Calculate metrics
            total_queries = sum(q['calls'] for q in query_stats)
            avg_query_time = sum(q['mean_time'] * q['calls'] for q in query_stats) / total_queries if total_queries > 0 else 0
            
            # Cache hit ratio
            cache_hit_ratio = 0
            if db_stats and (db_stats['blks_read'] + db_stats['blks_hit']) > 0:
                cache_hit_ratio = (db_stats['blks_hit'] / (db_stats['blks_read'] + db_stats['blks_hit'])) * 100
            
            custom_metrics.update({
                'cache_hit_ratio': cache_hit_ratio,
                'transactions_committed': db_stats['xact_commit'] if db_stats else 0,
                'transactions_rolled_back': db_stats['xact_rollback'] if db_stats else 0,
                'tuples_returned': db_stats['tup_returned'] if db_stats else 0,
                'tuples_fetched': db_stats['tup_fetched'] if db_stats else 0,
                'locks': {lock['mode']: lock['count'] for lock in lock_stats},
                'slowest_query_time': max((q['max_time'] for q in query_stats), default=0),
                'idle_in_transaction': connection_stats['idle_in_transaction'] if connection_stats else 0
            })
            
            # Generate alerts
            if connection_stats and connection_stats['active_connections'] > 50:
                alerts.append(f"High number of active connections: {connection_stats['active_connections']}")
            
            if cache_hit_ratio < 95:
                alerts.append(f"Low cache hit ratio: {cache_hit_ratio:.1f}%")
            
            if len(slow_queries) > 5:
                alerts.append(f"Many slow queries detected: {len(slow_queries)}")
            
            await conn.close()
            
            return DatabaseMetrics(
                timestamp=datetime.now().isoformat(),
                database='postgres',
                query_count=total_queries,
                avg_query_time_ms=avg_query_time,
                slow_queries=len(slow_queries),
                active_connections=connection_stats['active_connections'] if connection_stats else 0,
                memory_usage_mb=0,  # Will be filled by container stats
                cpu_percent=0,      # Will be filled by container stats
                custom_metrics=custom_metrics,
                alerts=alerts
            )
            
        except Exception as e:
            logger.error(f"Error monitoring PostgreSQL: {e}")
            return DatabaseMetrics(
                timestamp=datetime.now().isoformat(),
                database='postgres',
                query_count=0,
                avg_query_time_ms=0,
                slow_queries=0,
                active_connections=0,
                memory_usage_mb=0,
                cpu_percent=0,
                custom_metrics={'error': str(e)},
                alerts=[f"PostgreSQL monitoring error: {str(e)}"]
            )
    
    async def _monitor_neo4j(self) -> DatabaseMetrics:
        """Monitor Neo4j performance."""
        alerts = []
        custom_metrics = {}
        
        try:
            driver = neo4j.GraphDatabase.driver(
                self.neo4j_config['uri'],
                auth=(self.neo4j_config['user'], self.neo4j_config['password'])
            )
            
            with driver.session() as session:
                # Database info
                db_info = session.run("CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Store file sizes')")
                store_data = db_info.single()
                
                # Memory usage
                memory_info = session.run("CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Memory Mapping')")
                memory_data = memory_info.single()
                
                # Transaction stats
                tx_info = session.run("CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Transactions')")
                tx_data = tx_info.single()
                
                # Query performance (if available)
                try:
                    query_stats = session.run("CALL dbms.listQueries() YIELD query, elapsedTimeMillis, status")
                    active_queries = list(query_stats)
                except:
                    active_queries = []
                
                # Node and relationship counts
                node_count = session.run("MATCH (n) RETURN count(n) as count").single()['count']
                rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()['count']
                
                # Index information
                try:
                    indexes = session.run("SHOW INDEXES")
                    index_list = list(indexes)
                except:
                    index_list = []
                
                # Calculate metrics
                heap_used = memory_data.get('HeapUsed', 0) if memory_data else 0
                heap_max = memory_data.get('HeapMax', 0) if memory_data else 0
                heap_usage_percent = (heap_used / heap_max * 100) if heap_max > 0 else 0
                
                store_size = store_data.get('TotalStoreSize', 0) if store_data else 0
                
                committed_tx = tx_data.get('NumberOfCommittedTransactions', 0) if tx_data else 0
                rolled_back_tx = tx_data.get('NumberOfRolledBackTransactions', 0) if tx_data else 0
                
                custom_metrics.update({
                    'node_count': node_count,
                    'relationship_count': rel_count,
                    'store_size_mb': store_size / (1024 * 1024),
                    'heap_used_mb': heap_used / (1024 * 1024),
                    'heap_max_mb': heap_max / (1024 * 1024),
                    'heap_usage_percent': heap_usage_percent,
                    'committed_transactions': committed_tx,
                    'rolled_back_transactions': rolled_back_tx,
                    'active_queries_count': len(active_queries),
                    'indexes_count': len(index_list)
                })
                
                # Generate alerts
                if heap_usage_percent > 85:
                    alerts.append(f"High heap usage: {heap_usage_percent:.1f}%")
                
                if len(active_queries) > 10:
                    alerts.append(f"Many active queries: {len(active_queries)}")
                
                long_running_queries = [q for q in active_queries if q.get('elapsedTimeMillis', 0) > 5000]
                if long_running_queries:
                    alerts.append(f"Long running queries detected: {len(long_running_queries)}")
            
            driver.close()
            
            return DatabaseMetrics(
                timestamp=datetime.now().isoformat(),
                database='neo4j',
                query_count=len(active_queries),
                avg_query_time_ms=sum(q.get('elapsedTimeMillis', 0) for q in active_queries) / len(active_queries) if active_queries else 0,
                slow_queries=len([q for q in active_queries if q.get('elapsedTimeMillis', 0) > 1000]),
                active_connections=len(active_queries),  # Approximation
                memory_usage_mb=heap_used / (1024 * 1024),
                cpu_percent=0,  # Will be filled by container stats
                custom_metrics=custom_metrics,
                alerts=alerts
            )
            
        except Exception as e:
            logger.error(f"Error monitoring Neo4j: {e}")
            return DatabaseMetrics(
                timestamp=datetime.now().isoformat(),
                database='neo4j',
                query_count=0,
                avg_query_time_ms=0,
                slow_queries=0,
                active_connections=0,
                memory_usage_mb=0,
                cpu_percent=0,
                custom_metrics={'error': str(e)},
                alerts=[f"Neo4j monitoring error: {str(e)}"]
            )
    
    async def _monitor_milvus(self) -> DatabaseMetrics:
        """Monitor Milvus performance."""
        alerts = []
        custom_metrics = {}
        
        try:
            connections.connect(host=self.milvus_config['host'], port=self.milvus_config['port'])
            
            # List collections
            collection_names = utility.list_collections()
            
            # Collection statistics
            collection_stats = {}
            total_entities = 0
            
            for collection_name in collection_names:
                try:
                    collection = Collection(collection_name)
                    
                    # Load collection to get stats
                    collection.load()
                    
                    num_entities = collection.num_entities
                    total_entities += num_entities
                    
                    # Get collection info
                    collection_info = {
                        'num_entities': num_entities,
                        'schema': {
                            'fields': len(collection.schema.fields),
                            'description': collection.schema.description
                        }
                    }
                    
                    # Get index info if available
                    try:
                        indexes = collection.indexes
                        collection_info['indexes'] = len(indexes)
                    except:
                        collection_info['indexes'] = 0
                    
                    collection_stats[collection_name] = collection_info
                    
                except Exception as e:
                    logger.warning(f"Error getting stats for collection {collection_name}: {e}")
                    collection_stats[collection_name] = {'error': str(e)}
            
            # Server version and status
            try:
                server_version = utility.get_server_version()
            except:
                server_version = "unknown"
            
            custom_metrics.update({
                'collections_count': len(collection_names),
                'total_entities': total_entities,
                'collections': collection_names,
                'collection_stats': collection_stats,
                'server_version': server_version
            })
            
            # Generate alerts
            if len(collection_names) == 0:
                alerts.append("No collections found in Milvus")
            
            if total_entities > 1000000:  # 1M entities
                alerts.append(f"Large number of entities: {total_entities}")
            
            # Check for collections without indexes
            collections_without_indexes = [name for name, stats in collection_stats.items() 
                                         if stats.get('indexes', 0) == 0 and 'error' not in stats]
            if collections_without_indexes:
                alerts.append(f"Collections without indexes: {collections_without_indexes}")
            
            connections.disconnect('default')
            
            return DatabaseMetrics(
                timestamp=datetime.now().isoformat(),
                database='milvus',
                query_count=0,  # Milvus doesn't expose query stats easily
                avg_query_time_ms=0,
                slow_queries=0,
                active_connections=0,
                memory_usage_mb=0,  # Will be filled by container stats
                cpu_percent=0,      # Will be filled by container stats
                custom_metrics=custom_metrics,
                alerts=alerts
            )
            
        except Exception as e:
            logger.error(f"Error monitoring Milvus: {e}")
            return DatabaseMetrics(
                timestamp=datetime.now().isoformat(),
                database='milvus',
                query_count=0,
                avg_query_time_ms=0,
                slow_queries=0,
                active_connections=0,
                memory_usage_mb=0,
                cpu_percent=0,
                custom_metrics={'error': str(e)},
                alerts=[f"Milvus monitoring error: {str(e)}"]
            )
    
    def _get_container_resource_usage(self, container_name: str) -> Dict[str, float]:
        """Get container resource usage using psutil."""
        try:
            # This is a simplified approach - in a real scenario you'd use Docker API
            # For now, we'll return system-wide stats as approximation
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            return {
                'cpu_percent': cpu_percent / 3,  # Approximate per-service
                'memory_mb': memory.used / (1024 * 1024) / 3  # Approximate per-service
            }
        except Exception as e:
            logger.warning(f"Error getting container stats for {container_name}: {e}")
            return {'cpu_percent': 0, 'memory_mb': 0}
    
    async def monitor_database(self, database: str) -> Optional[DatabaseMetrics]:
        """Monitor a specific database."""
        if database == 'postgres':
            metrics = await self._monitor_postgres()
        elif database == 'neo4j':
            metrics = await self._monitor_neo4j()
        elif database == 'milvus':
            metrics = await self._monitor_milvus()
        else:
            logger.error(f"Unknown database: {database}")
            return None
        
        # Add container resource usage
        container_names = {
            'postgres': 'multimodal-librarian-postgres-1',
            'neo4j': 'multimodal-librarian-neo4j-1',
            'milvus': 'multimodal-librarian-milvus-1'
        }
        
        if database in container_names:
            resource_usage = self._get_container_resource_usage(container_names[database])
            metrics.cpu_percent = resource_usage['cpu_percent']
            metrics.memory_usage_mb = resource_usage['memory_mb']
            
            # Add resource-based alerts
            if metrics.cpu_percent > self.cpu_threshold:
                metrics.alerts.append(f"High CPU usage: {metrics.cpu_percent:.1f}%")
            
            if metrics.memory_usage_mb > self.memory_threshold:
                metrics.alerts.append(f"High memory usage: {metrics.memory_usage_mb:.1f}MB")
        
        return metrics
    
    async def monitor_cycle(self, databases: List[str]) -> None:
        """Run one monitoring cycle."""
        logger.info(f"Running monitoring cycle for databases: {databases}")
        
        for database in databases:
            try:
                metrics = await self.monitor_database(database)
                if metrics:
                    self.metrics_history.append(metrics)
                    
                    # Log current status
                    status = f"{database.upper()}: "
                    status += f"Queries: {metrics.query_count}, "
                    status += f"Avg Time: {metrics.avg_query_time_ms:.1f}ms, "
                    status += f"CPU: {metrics.cpu_percent:.1f}%, "
                    status += f"Memory: {metrics.memory_usage_mb:.1f}MB"
                    
                    if metrics.alerts:
                        status += f" [ALERTS: {len(metrics.alerts)}]"
                    
                    logger.info(status)
                    
                    # Print alerts immediately
                    for alert in metrics.alerts:
                        logger.warning(f"{database.upper()} ALERT: {alert}")
                        
            except Exception as e:
                logger.error(f"Error monitoring {database}: {e}")
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate database performance report."""
        if not self.metrics_history:
            return {"error": "No metrics collected"}
        
        # Group metrics by database
        db_metrics = {}
        for metric in self.metrics_history:
            if metric.database not in db_metrics:
                db_metrics[metric.database] = []
            db_metrics[metric.database].append(asdict(metric))
        
        # Calculate summary statistics
        summary = {}
        all_alerts = []
        
        for database, metrics in db_metrics.items():
            if not metrics:
                continue
            
            query_times = [m['avg_query_time_ms'] for m in metrics if m['avg_query_time_ms'] > 0]
            cpu_values = [m['cpu_percent'] for m in metrics]
            memory_values = [m['memory_usage_mb'] for m in metrics]
            
            # Collect all alerts
            for m in metrics:
                all_alerts.extend(m['alerts'])
            
            summary[database] = {
                'sample_count': len(metrics),
                'avg_query_time_ms': sum(query_times) / len(query_times) if query_times else 0,
                'max_query_time_ms': max(query_times) if query_times else 0,
                'total_queries': sum(m['query_count'] for m in metrics),
                'total_slow_queries': sum(m['slow_queries'] for m in metrics),
                'avg_cpu_percent': sum(cpu_values) / len(cpu_values) if cpu_values else 0,
                'max_cpu_percent': max(cpu_values) if cpu_values else 0,
                'avg_memory_mb': sum(memory_values) / len(memory_values) if memory_values else 0,
                'max_memory_mb': max(memory_values) if memory_values else 0,
                'alert_count': sum(len(m['alerts']) for m in metrics),
                'first_timestamp': metrics[0]['timestamp'],
                'last_timestamp': metrics[-1]['timestamp']
            }
        
        return {
            'monitoring_session': {
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'duration_minutes': (datetime.now() - self.start_time).total_seconds() / 60,
                'interval_seconds': self.interval,
                'total_samples': len(self.metrics_history)
            },
            'summary': summary,
            'detailed_metrics': db_metrics,
            'all_alerts': list(set(all_alerts)),  # Unique alerts
            'recommendations': self._generate_recommendations(summary)
        }
    
    def _generate_recommendations(self, summary: Dict[str, Any]) -> List[str]:
        """Generate performance recommendations."""
        recommendations = []
        
        for database, stats in summary.items():
            if stats['avg_query_time_ms'] > 100:
                recommendations.append(f"{database}: Consider optimizing queries (avg time: {stats['avg_query_time_ms']:.1f}ms)")
            
            if stats['total_slow_queries'] > 0:
                recommendations.append(f"{database}: {stats['total_slow_queries']} slow queries detected - review and optimize")
            
            if stats['avg_cpu_percent'] > 70:
                recommendations.append(f"{database}: High CPU usage ({stats['avg_cpu_percent']:.1f}%) - consider scaling or optimization")
            
            if stats['avg_memory_mb'] > 800:
                recommendations.append(f"{database}: High memory usage ({stats['avg_memory_mb']:.1f}MB) - review memory settings")
            
            if stats['alert_count'] > 5:
                recommendations.append(f"{database}: Multiple alerts ({stats['alert_count']}) - requires attention")
        
        if not recommendations:
            recommendations.append("All databases are performing within acceptable parameters.")
        
        return recommendations
    
    def save_report(self, report: Dict[str, Any], output_file: str) -> None:
        """Save performance report to file."""
        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Database performance report saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving report: {e}")
    
    async def run(self, duration_minutes: int, databases: List[str], output_file: Optional[str] = None) -> None:
        """Run database performance monitoring."""
        logger.info(f"Starting database performance monitoring for {duration_minutes} minutes")
        logger.info(f"Monitoring databases: {databases}")
        logger.info(f"Monitoring interval: {self.interval} seconds")
        
        if output_file is None:
            output_file = f"database_performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        try:
            while datetime.now() < end_time:
                await self.monitor_cycle(databases)
                await asyncio.sleep(self.interval)
                
                # Print progress
                elapsed = (datetime.now() - self.start_time).total_seconds() / 60
                logger.info(f"Monitoring progress: {elapsed:.1f}/{duration_minutes} minutes")
        
        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user")
        
        # Generate and save final report
        report = self.generate_report()
        self.save_report(report, output_file)
        
        # Print summary
        print("\n" + "="*60)
        print("DATABASE PERFORMANCE MONITORING SUMMARY")
        print("="*60)
        
        for database, stats in report['summary'].items():
            print(f"\n{database.upper()}:")
            print(f"  Total Queries: {stats['total_queries']}")
            print(f"  Avg Query Time: {stats['avg_query_time_ms']:.1f}ms")
            print(f"  Slow Queries: {stats['total_slow_queries']}")
            print(f"  Average CPU: {stats['avg_cpu_percent']:.1f}%")
            print(f"  Average Memory: {stats['avg_memory_mb']:.1f}MB")
            print(f"  Alerts: {stats['alert_count']}")
        
        if report['all_alerts']:
            print(f"\nALL ALERTS:")
            for alert in report['all_alerts']:
                print(f"  ⚠️  {alert}")
        
        print(f"\nRECOMMENDATIONS:")
        for rec in report['recommendations']:
            print(f"  • {rec}")
        
        print(f"\nDetailed report saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Monitor database performance for local development')
    parser.add_argument('--database', choices=['postgres', 'neo4j', 'milvus', 'all'], default='all',
                       help='Database to monitor')
    parser.add_argument('--interval', type=int, default=10, help='Monitoring interval in seconds')
    parser.add_argument('--duration', type=int, default=30, help='Total monitoring duration in minutes')
    parser.add_argument('--output', help='Output file for performance data')
    parser.add_argument('--threshold-cpu', type=float, default=80, help='CPU threshold for alerts')
    parser.add_argument('--threshold-memory', type=float, default=1000, help='Memory threshold for alerts (MB)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Parse databases to monitor
    if args.database == 'all':
        databases = ['postgres', 'neo4j', 'milvus']
    else:
        databases = [args.database]
    
    # Create and run monitor
    monitor = DatabasePerformanceMonitor(
        interval=args.interval,
        cpu_threshold=args.threshold_cpu,
        memory_threshold=args.threshold_memory
    )
    
    try:
        asyncio.run(monitor.run(args.duration, databases, args.output))
    except Exception as e:
        logger.error(f"Database monitoring failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())