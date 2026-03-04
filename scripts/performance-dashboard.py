#!/usr/bin/env python3
"""
Performance Dashboard for Local Development

This script provides a real-time performance dashboard for local development services.
It displays live metrics in a terminal-based interface with charts and alerts.

Usage:
    python scripts/performance-dashboard.py [options]

Options:
    --refresh SECONDS     Dashboard refresh interval (default: 2)
    --history MINUTES     History to keep in memory (default: 30)
    --no-charts           Disable ASCII charts
    --compact             Use compact display mode
    --services SERVICE    Comma-separated services to monitor
    --verbose             Enable verbose logging
"""

import asyncio
import time
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Deque
from collections import deque
import psutil
import docker
import asyncpg
import neo4j
from pymilvus import connections, utility

# Configure logging to file to avoid interfering with dashboard
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('performance_dashboard.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

class PerformanceDashboard:
    """Real-time performance dashboard for local development."""
    
    def __init__(self, refresh_interval: int = 2, history_minutes: int = 30):
        self.refresh_interval = refresh_interval
        self.history_minutes = history_minutes
        self.max_history = int((history_minutes * 60) / refresh_interval)
        
        # Data storage
        self.system_history: Deque = deque(maxlen=self.max_history)
        self.container_history: Dict[str, Deque] = {}
        self.database_history: Dict[str, Deque] = {}
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            self.docker_available = True
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            self.docker_client = None
            self.docker_available = False
        
        # Services to monitor
        self.services = {
            'postgres': {'container': 'multimodal-librarian-postgres-1', 'port': 5432},
            'neo4j': {'container': 'multimodal-librarian-neo4j-1', 'port': 7687},
            'milvus': {'container': 'multimodal-librarian-milvus-1', 'port': 19530},
            'etcd': {'container': 'multimodal-librarian-etcd-1', 'port': 2379},
            'minio': {'container': 'multimodal-librarian-minio-1', 'port': 9000}
        }
        
        # Initialize container history
        for service in self.services:
            self.container_history[service] = deque(maxlen=self.max_history)
            self.database_history[service] = deque(maxlen=self.max_history)
    
    def _clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        network = psutil.net_io_counters()
        
        try:
            load_avg = list(psutil.getloadavg())
        except AttributeError:
            load_avg = [0.0, 0.0, 0.0]
        
        return {
            'timestamp': datetime.now(),
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used_gb': memory.used / (1024**3),
            'memory_total_gb': memory.total / (1024**3),
            'disk_percent': disk.percent,
            'disk_used_gb': disk.used / (1024**3),
            'disk_total_gb': disk.total / (1024**3),
            'network_sent_mb': network.bytes_sent / (1024**2),
            'network_recv_mb': network.bytes_recv / (1024**2),
            'load_average': load_avg,
            'processes': len(psutil.pids())
        }
    
    def _get_container_metrics(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get container metrics."""
        if not self.docker_available:
            return None
        
        try:
            container = self.docker_client.containers.get(container_name)
            stats = container.stats(stream=False)
            
            # CPU calculation
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            else:
                cpu_percent = 0.0
            
            # Memory calculation
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            memory_percent = (memory_usage / memory_limit) * 100.0
            
            return {
                'timestamp': datetime.now(),
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'memory_used_mb': memory_usage / (1024**2),
                'memory_limit_mb': memory_limit / (1024**2),
                'status': container.status
            }
            
        except Exception as e:
            logger.debug(f"Error getting container metrics for {container_name}: {e}")
            return None
    
    async def _get_postgres_metrics(self) -> Dict[str, Any]:
        """Get PostgreSQL-specific metrics."""
        try:
            conn = await asyncpg.connect(
                host='localhost', port=5432, database='multimodal_librarian',
                user='ml_user', password='ml_password'
            )
            
            # Connection stats
            conn_stats = await conn.fetchrow("""
                SELECT 
                    count(*) as total,
                    count(*) FILTER (WHERE state = 'active') as active,
                    count(*) FILTER (WHERE state = 'idle') as idle
                FROM pg_stat_activity WHERE pid != pg_backend_pid()
            """)
            
            # Database stats
            db_stats = await conn.fetchrow("""
                SELECT xact_commit, xact_rollback, blks_read, blks_hit
                FROM pg_stat_database WHERE datname = 'multimodal_librarian'
            """)
            
            await conn.close()
            
            cache_hit_ratio = 0
            if db_stats and (db_stats['blks_read'] + db_stats['blks_hit']) > 0:
                cache_hit_ratio = (db_stats['blks_hit'] / (db_stats['blks_read'] + db_stats['blks_hit'])) * 100
            
            return {
                'timestamp': datetime.now(),
                'connections_total': conn_stats['total'] if conn_stats else 0,
                'connections_active': conn_stats['active'] if conn_stats else 0,
                'connections_idle': conn_stats['idle'] if conn_stats else 0,
                'cache_hit_ratio': cache_hit_ratio,
                'transactions_committed': db_stats['xact_commit'] if db_stats else 0,
                'status': 'connected'
            }
            
        except Exception as e:
            return {
                'timestamp': datetime.now(),
                'status': 'error',
                'error': str(e)
            }
    
    async def _get_neo4j_metrics(self) -> Dict[str, Any]:
        """Get Neo4j-specific metrics."""
        try:
            driver = neo4j.GraphDatabase.driver(
                "bolt://localhost:7687",
                auth=("neo4j", "ml_password")
            )
            
            with driver.session() as session:
                # Node and relationship counts
                node_count = session.run("MATCH (n) RETURN count(n) as count").single()['count']
                rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()['count']
                
                # Try to get memory info
                try:
                    memory_info = session.run("CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Memory Mapping')")
                    memory_data = memory_info.single()
                    heap_used = memory_data.get('HeapUsed', 0) if memory_data else 0
                except:
                    heap_used = 0
            
            driver.close()
            
            return {
                'timestamp': datetime.now(),
                'node_count': node_count,
                'relationship_count': rel_count,
                'heap_used_mb': heap_used / (1024**2),
                'status': 'connected'
            }
            
        except Exception as e:
            return {
                'timestamp': datetime.now(),
                'status': 'error',
                'error': str(e)
            }
    
    async def _get_milvus_metrics(self) -> Dict[str, Any]:
        """Get Milvus-specific metrics."""
        try:
            connections.connect(host='localhost', port=19530)
            
            # List collections
            collection_names = utility.list_collections()
            total_entities = 0
            
            for collection_name in collection_names:
                try:
                    from pymilvus import Collection
                    collection = Collection(collection_name)
                    collection.load()
                    total_entities += collection.num_entities
                except:
                    pass
            
            connections.disconnect('default')
            
            return {
                'timestamp': datetime.now(),
                'collections_count': len(collection_names),
                'total_entities': total_entities,
                'status': 'connected'
            }
            
        except Exception as e:
            return {
                'timestamp': datetime.now(),
                'status': 'error',
                'error': str(e)
            }
    
    def _create_ascii_chart(self, values: List[float], width: int = 40, height: int = 8) -> List[str]:
        """Create ASCII chart from values."""
        if not values:
            return [" " * width for _ in range(height)]
        
        max_val = max(values) if max(values) > 0 else 1
        min_val = min(values)
        
        chart = []
        for row in range(height):
            line = ""
            threshold = max_val - (row * (max_val - min_val) / (height - 1))
            
            for i, val in enumerate(values[-width:]):
                if val >= threshold:
                    line += "█"
                elif val >= threshold - (max_val - min_val) / (height * 2):
                    line += "▄"
                else:
                    line += " "
            
            chart.append(line.ljust(width))
        
        return chart
    
    def _format_bytes(self, bytes_val: float) -> str:
        """Format bytes to human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f}PB"
    
    def _get_status_color(self, value: float, warning: float = 70, critical: float = 90) -> str:
        """Get ANSI color code based on value thresholds."""
        if value >= critical:
            return "\033[91m"  # Red
        elif value >= warning:
            return "\033[93m"  # Yellow
        else:
            return "\033[92m"  # Green
    
    def _render_system_panel(self, show_charts: bool = True) -> str:
        """Render system metrics panel."""
        if not self.system_history:
            return "No system data available"
        
        current = self.system_history[-1]
        
        # Status colors
        cpu_color = self._get_status_color(current['cpu_percent'])
        mem_color = self._get_status_color(current['memory_percent'])
        disk_color = self._get_status_color(current['disk_percent'])
        reset_color = "\033[0m"
        
        panel = f"""
┌─ SYSTEM RESOURCES ─────────────────────────────────────────────────────────┐
│ CPU:    {cpu_color}{current['cpu_percent']:6.1f}%{reset_color}  │ Memory: {mem_color}{current['memory_percent']:6.1f}%{reset_color}  │ Disk:   {disk_color}{current['disk_percent']:6.1f}%{reset_color} │
│ Load:   {current['load_average'][0]:6.2f}   │ Used:   {current['memory_used_gb']:6.1f}GB │ Used:   {current['disk_used_gb']:6.1f}GB │
│ Procs:  {current['processes']:6d}   │ Total:  {current['memory_total_gb']:6.1f}GB │ Total:  {current['disk_total_gb']:6.1f}GB │
"""
        
        if show_charts and len(self.system_history) > 1:
            cpu_values = [m['cpu_percent'] for m in self.system_history]
            mem_values = [m['memory_percent'] for m in self.system_history]
            
            cpu_chart = self._create_ascii_chart(cpu_values, width=35, height=6)
            mem_chart = self._create_ascii_chart(mem_values, width=35, height=6)
            
            panel += "│                                     │                                     │\n"
            panel += "│ CPU Usage (%)                       │ Memory Usage (%)                    │\n"
            
            for i in range(6):
                panel += f"│ {cpu_chart[i]} │ {mem_chart[i]} │\n"
        
        panel += "└───────────────────────────────────────────────────────────────────────────┘"
        
        return panel
    
    def _render_containers_panel(self, services: List[str], show_charts: bool = True) -> str:
        """Render containers metrics panel."""
        panel = "┌─ CONTAINERS ───────────────────────────────────────────────────────────────┐\n"
        
        for service in services:
            if service not in self.container_history or not self.container_history[service]:
                panel += f"│ {service:10} │ No data available                                    │\n"
                continue
            
            current = self.container_history[service][-1]
            
            if current is None:
                panel += f"│ {service:10} │ Container not found                                  │\n"
                continue
            
            cpu_color = self._get_status_color(current['cpu_percent'], 50, 80)
            mem_color = self._get_status_color(current['memory_percent'], 70, 90)
            reset_color = "\033[0m"
            
            status_indicator = "🟢" if current['status'] == 'running' else "🔴"
            
            panel += f"│ {service:10} │ {status_indicator} CPU: {cpu_color}{current['cpu_percent']:5.1f}%{reset_color} │ "
            panel += f"Memory: {mem_color}{current['memory_percent']:5.1f}%{reset_color} │ "
            panel += f"Used: {current['memory_used_mb']:6.1f}MB │\n"
        
        panel += "└───────────────────────────────────────────────────────────────────────────┘"
        
        return panel
    
    def _render_databases_panel(self, services: List[str]) -> str:
        """Render database metrics panel."""
        panel = "┌─ DATABASES ────────────────────────────────────────────────────────────────┐\n"
        
        for service in services:
            if service not in self.database_history or not self.database_history[service]:
                panel += f"│ {service:10} │ No data available                                    │\n"
                continue
            
            current = self.database_history[service][-1]
            
            if 'error' in current:
                panel += f"│ {service:10} │ 🔴 Error: {current['error'][:45]:45} │\n"
                continue
            
            status_indicator = "🟢" if current['status'] == 'connected' else "🔴"
            
            if service == 'postgres':
                panel += f"│ {service:10} │ {status_indicator} Connections: {current['connections_active']:3d}/{current['connections_total']:3d} │ "
                panel += f"Cache Hit: {current['cache_hit_ratio']:5.1f}% │\n"
            
            elif service == 'neo4j':
                panel += f"│ {service:10} │ {status_indicator} Nodes: {current['node_count']:8d} │ "
                panel += f"Relationships: {current['relationship_count']:8d} │\n"
            
            elif service == 'milvus':
                panel += f"│ {service:10} │ {status_indicator} Collections: {current['collections_count']:3d} │ "
                panel += f"Entities: {current['total_entities']:10d} │\n"
            
            else:
                panel += f"│ {service:10} │ {status_indicator} Status: {current['status']:20} │\n"
        
        panel += "└───────────────────────────────────────────────────────────────────────────┘"
        
        return panel
    
    def _render_alerts_panel(self) -> str:
        """Render alerts and warnings panel."""
        alerts = []
        
        # Check system alerts
        if self.system_history:
            current = self.system_history[-1]
            if current['cpu_percent'] > 80:
                alerts.append(f"🔴 High system CPU usage: {current['cpu_percent']:.1f}%")
            if current['memory_percent'] > 85:
                alerts.append(f"🔴 High system memory usage: {current['memory_percent']:.1f}%")
            if current['disk_percent'] > 90:
                alerts.append(f"🔴 High disk usage: {current['disk_percent']:.1f}%")
            if current['load_average'][0] > psutil.cpu_count() * 1.5:
                alerts.append(f"🟡 High system load: {current['load_average'][0]:.2f}")
        
        # Check container alerts
        for service, history in self.container_history.items():
            if history and history[-1]:
                current = history[-1]
                if current['cpu_percent'] > 70:
                    alerts.append(f"🟡 {service}: High CPU usage: {current['cpu_percent']:.1f}%")
                if current['memory_percent'] > 80:
                    alerts.append(f"🟡 {service}: High memory usage: {current['memory_percent']:.1f}%")
                if current['status'] != 'running':
                    alerts.append(f"🔴 {service}: Container not running: {current['status']}")
        
        # Check database alerts
        for service, history in self.database_history.items():
            if history and history[-1]:
                current = history[-1]
                if 'error' in current:
                    alerts.append(f"🔴 {service}: Database connection error")
                elif service == 'postgres' and current.get('connections_active', 0) > 20:
                    alerts.append(f"🟡 {service}: High connection count: {current['connections_active']}")
        
        panel = "┌─ ALERTS & STATUS ──────────────────────────────────────────────────────────┐\n"
        
        if not alerts:
            panel += "│ 🟢 All systems operating normally                                          │\n"
        else:
            for alert in alerts[:8]:  # Show max 8 alerts
                panel += f"│ {alert[:74]:74} │\n"
            
            if len(alerts) > 8:
                panel += f"│ ... and {len(alerts) - 8} more alerts                                      │\n"
        
        panel += "└───────────────────────────────────────────────────────────────────────────┘"
        
        return panel
    
    async def _collect_metrics(self, services: List[str]) -> None:
        """Collect all metrics for one cycle."""
        # Collect system metrics
        system_metrics = self._get_system_metrics()
        self.system_history.append(system_metrics)
        
        # Collect container metrics
        for service in services:
            if service in self.services:
                container_name = self.services[service]['container']
                container_metrics = self._get_container_metrics(container_name)
                self.container_history[service].append(container_metrics)
        
        # Collect database metrics
        db_tasks = []
        if 'postgres' in services:
            db_tasks.append(('postgres', self._get_postgres_metrics()))
        if 'neo4j' in services:
            db_tasks.append(('neo4j', self._get_neo4j_metrics()))
        if 'milvus' in services:
            db_tasks.append(('milvus', self._get_milvus_metrics()))
        
        # Execute database queries concurrently
        if db_tasks:
            results = await asyncio.gather(*[task[1] for task in db_tasks], return_exceptions=True)
            
            for i, (service, _) in enumerate(db_tasks):
                if isinstance(results[i], Exception):
                    self.database_history[service].append({
                        'timestamp': datetime.now(),
                        'status': 'error',
                        'error': str(results[i])
                    })
                else:
                    self.database_history[service].append(results[i])
    
    def _render_dashboard(self, services: List[str], show_charts: bool = True, compact: bool = False) -> str:
        """Render the complete dashboard."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        dashboard = f"""
╔═══════════════════════════════════════════════════════════════════════════╗
║                    MULTIMODAL LIBRARIAN PERFORMANCE DASHBOARD             ║
║                              {timestamp}                              ║
╚═══════════════════════════════════════════════════════════════════════════╝

"""
        
        # System panel
        dashboard += self._render_system_panel(show_charts and not compact)
        dashboard += "\n\n"
        
        # Containers panel
        dashboard += self._render_containers_panel(services, show_charts and not compact)
        dashboard += "\n\n"
        
        # Databases panel
        dashboard += self._render_databases_panel(services)
        dashboard += "\n\n"
        
        # Alerts panel
        dashboard += self._render_alerts_panel()
        dashboard += "\n\n"
        
        # Footer
        dashboard += f"Refresh: {self.refresh_interval}s | History: {self.history_minutes}m | "
        dashboard += f"Samples: {len(self.system_history)}/{self.max_history}\n"
        dashboard += "Press Ctrl+C to exit\n"
        
        return dashboard
    
    async def run(self, services: List[str], show_charts: bool = True, compact: bool = False) -> None:
        """Run the performance dashboard."""
        logger.info(f"Starting performance dashboard for services: {services}")
        
        try:
            while True:
                # Collect metrics
                await self._collect_metrics(services)
                
                # Clear screen and render dashboard
                self._clear_screen()
                dashboard = self._render_dashboard(services, show_charts, compact)
                print(dashboard)
                
                # Wait for next refresh
                await asyncio.sleep(self.refresh_interval)
                
        except KeyboardInterrupt:
            print("\n\nDashboard stopped by user")
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            print(f"\nDashboard error: {e}")

def main():
    parser = argparse.ArgumentParser(description='Performance dashboard for local development')
    parser.add_argument('--refresh', type=int, default=2, help='Dashboard refresh interval in seconds')
    parser.add_argument('--history', type=int, default=30, help='History to keep in memory (minutes)')
    parser.add_argument('--no-charts', action='store_true', help='Disable ASCII charts')
    parser.add_argument('--compact', action='store_true', help='Use compact display mode')
    parser.add_argument('--services', default='postgres,neo4j,milvus', 
                       help='Comma-separated services to monitor')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Parse services
    services = [s.strip() for s in args.services.split(',')]
    
    # Create and run dashboard
    dashboard = PerformanceDashboard(
        refresh_interval=args.refresh,
        history_minutes=args.history
    )
    
    try:
        asyncio.run(dashboard.run(services, not args.no_charts, args.compact))
    except Exception as e:
        logger.error(f"Dashboard failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())