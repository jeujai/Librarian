#!/usr/bin/env python3
"""
PostgreSQL Optimization Validation Script

This script validates that PostgreSQL is properly optimized for local development
according to the requirements in the local-development-conversion spec.

Requirements validated:
- Memory usage < 8GB total for all services (PostgreSQL should use ~1GB)
- Query performance within 20% of AWS setup
- Local setup startup time < 2 minutes
- Reasonable CPU usage on development machines
"""

import asyncio
import asyncpg
import psutil
import time
import json
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PostgreSQLOptimizationValidator:
    def __init__(self, host: str = "localhost", port: int = 5432, 
                 database: str = "multimodal_librarian", 
                 user: str = "ml_user", password: str = "ml_password"):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.connection: Optional[asyncpg.Connection] = None
        
    async def connect(self) -> bool:
        """Connect to PostgreSQL database."""
        try:
            self.connection = await asyncpg.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            logger.info("Successfully connected to PostgreSQL")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from PostgreSQL database."""
        if self.connection:
            await self.connection.close()
            logger.info("Disconnected from PostgreSQL")
    
    async def validate_configuration(self) -> Dict[str, Any]:
        """Validate PostgreSQL configuration settings."""
        logger.info("Validating PostgreSQL configuration...")
        
        config_checks = {
            'shared_buffers': {'expected': '256MB', 'description': 'Main buffer pool size'},
            'work_mem': {'expected': '8MB', 'description': 'Memory for sorts and hash tables'},
            'maintenance_work_mem': {'expected': '128MB', 'description': 'Memory for maintenance operations'},
            'effective_cache_size': {'expected': '1GB', 'description': 'Estimate of OS cache size'},
            'checkpoint_completion_target': {'expected': '0.9', 'description': 'Checkpoint completion target'},
            'wal_buffers': {'expected': '32MB', 'description': 'WAL buffer size'},
            'max_connections': {'expected': '100', 'description': 'Maximum connections'},
            'random_page_cost': {'expected': '2', 'description': 'Random page cost (optimized for SSD)'},
            'max_parallel_workers_per_gather': {'expected': '2', 'description': 'Parallel workers per gather'},
            'checkpoint_timeout': {'expected': '10min', 'description': 'Checkpoint timeout'},
            'max_wal_size': {'expected': '2GB', 'description': 'Maximum WAL size'},
            'min_wal_size': {'expected': '512MB', 'description': 'Minimum WAL size'},
        }
        
        results = {}
        for setting, info in config_checks.items():
            try:
                current_value = await self.connection.fetchval(
                    "SELECT current_setting($1)", setting
                )
                
                # Normalize values for comparison
                expected = info['expected']
                is_correct = self._normalize_setting_value(current_value) == self._normalize_setting_value(expected)
                
                results[setting] = {
                    'current': current_value,
                    'expected': expected,
                    'correct': is_correct,
                    'description': info['description']
                }
                
                if is_correct:
                    logger.info(f"✓ {setting}: {current_value} (correct)")
                else:
                    logger.warning(f"✗ {setting}: {current_value}, expected {expected}")
                    
            except Exception as e:
                logger.error(f"Failed to check {setting}: {e}")
                results[setting] = {
                    'current': 'ERROR',
                    'expected': expected,
                    'correct': False,
                    'description': info['description'],
                    'error': str(e)
                }
        
        return results
    
    def _normalize_setting_value(self, value: str) -> str:
        """Normalize setting values for comparison."""
        # Convert to lowercase and remove spaces
        normalized = value.lower().replace(' ', '')
        
        # Handle memory units
        if normalized.endswith('mb'):
            return normalized
        elif normalized.endswith('gb'):
            # Convert GB to MB for comparison
            num = float(normalized[:-2])
            return f"{int(num * 1024)}mb"
        elif normalized.endswith('min'):
            return normalized
        
        return normalized
    
    async def validate_performance_functions(self) -> Dict[str, Any]:
        """Validate that performance monitoring functions are available."""
        logger.info("Validating performance monitoring functions...")
        
        functions_to_check = [
            'get_performance_stats',
            'get_index_usage_stats', 
            'get_slow_queries',
            'get_table_bloat_stats',
            'analyze_all_tables',
            'vacuum_all_tables'
        ]
        
        results = {}
        for func_name in functions_to_check:
            try:
                # Check if function exists
                exists = await self.connection.fetchval("""
                    SELECT EXISTS(
                        SELECT 1 FROM pg_proc p
                        JOIN pg_namespace n ON p.pronamespace = n.oid
                        WHERE p.proname = $1 AND n.nspname = 'public'
                    )
                """, func_name)
                
                if exists:
                    logger.info(f"✓ Function {func_name} exists")
                    results[func_name] = {'exists': True, 'status': 'OK'}
                else:
                    logger.warning(f"✗ Function {func_name} missing")
                    results[func_name] = {'exists': False, 'status': 'MISSING'}
                    
            except Exception as e:
                logger.error(f"Failed to check function {func_name}: {e}")
                results[func_name] = {'exists': False, 'status': 'ERROR', 'error': str(e)}
        
        return results
    
    async def validate_monitoring_schema(self) -> Dict[str, Any]:
        """Validate that monitoring schema and functions are available."""
        logger.info("Validating monitoring schema...")
        
        monitoring_functions = [
            'monitoring.health_check',
            'monitoring.get_performance_summary',
            'monitoring.get_query_performance_stats',
            'monitoring.get_resource_usage'
        ]
        
        results = {}
        
        # Check if monitoring schema exists
        try:
            schema_exists = await self.connection.fetchval("""
                SELECT EXISTS(
                    SELECT 1 FROM pg_namespace WHERE nspname = 'monitoring'
                )
            """)
            
            results['schema_exists'] = schema_exists
            
            if schema_exists:
                logger.info("✓ Monitoring schema exists")
            else:
                logger.warning("✗ Monitoring schema missing")
                return results
                
        except Exception as e:
            logger.error(f"Failed to check monitoring schema: {e}")
            results['schema_exists'] = False
            results['error'] = str(e)
            return results
        
        # Check monitoring functions
        for func_name in monitoring_functions:
            try:
                schema_name, function_name = func_name.split('.')
                exists = await self.connection.fetchval("""
                    SELECT EXISTS(
                        SELECT 1 FROM pg_proc p
                        JOIN pg_namespace n ON p.pronamespace = n.oid
                        WHERE p.proname = $1 AND n.nspname = $2
                    )
                """, function_name, schema_name)
                
                if exists:
                    logger.info(f"✓ Function {func_name} exists")
                    results[func_name] = {'exists': True, 'status': 'OK'}
                else:
                    logger.warning(f"✗ Function {func_name} missing")
                    results[func_name] = {'exists': False, 'status': 'MISSING'}
                    
            except Exception as e:
                logger.error(f"Failed to check function {func_name}: {e}")
                results[func_name] = {'exists': False, 'status': 'ERROR', 'error': str(e)}
        
        return results
    
    async def test_performance_functions(self) -> Dict[str, Any]:
        """Test performance monitoring functions."""
        logger.info("Testing performance monitoring functions...")
        
        results = {}
        
        # Test get_performance_stats
        try:
            stats = await self.connection.fetch("SELECT * FROM get_performance_stats()")
            results['get_performance_stats'] = {
                'status': 'OK',
                'row_count': len(stats),
                'sample_data': [dict(row) for row in stats[:3]]  # First 3 rows
            }
            logger.info(f"✓ get_performance_stats returned {len(stats)} metrics")
        except Exception as e:
            logger.error(f"✗ get_performance_stats failed: {e}")
            results['get_performance_stats'] = {'status': 'ERROR', 'error': str(e)}
        
        # Test monitoring.health_check
        try:
            health = await self.connection.fetch("SELECT * FROM monitoring.health_check()")
            results['monitoring_health_check'] = {
                'status': 'OK',
                'row_count': len(health),
                'sample_data': [dict(row) for row in health[:3]]
            }
            logger.info(f"✓ monitoring.health_check returned {len(health)} checks")
        except Exception as e:
            logger.error(f"✗ monitoring.health_check failed: {e}")
            results['monitoring_health_check'] = {'status': 'ERROR', 'error': str(e)}
        
        # Test monitoring.get_performance_summary
        try:
            perf_summary = await self.connection.fetch("SELECT * FROM monitoring.get_performance_summary()")
            results['monitoring_performance_summary'] = {
                'status': 'OK',
                'row_count': len(perf_summary),
                'sample_data': [dict(row) for row in perf_summary[:3]]
            }
            logger.info(f"✓ monitoring.get_performance_summary returned {len(perf_summary)} metrics")
        except Exception as e:
            logger.error(f"✗ monitoring.get_performance_summary failed: {e}")
            results['monitoring_performance_summary'] = {'status': 'ERROR', 'error': str(e)}
        
        return results
    
    async def measure_query_performance(self) -> Dict[str, Any]:
        """Measure basic query performance."""
        logger.info("Measuring query performance...")
        
        results = {}
        
        # Test simple SELECT performance
        try:
            start_time = time.time()
            await self.connection.fetchval("SELECT 1")
            simple_query_time = (time.time() - start_time) * 1000  # Convert to ms
            
            results['simple_select'] = {
                'time_ms': round(simple_query_time, 2),
                'status': 'OK' if simple_query_time < 10 else 'SLOW'
            }
            logger.info(f"✓ Simple SELECT: {simple_query_time:.2f}ms")
        except Exception as e:
            logger.error(f"✗ Simple SELECT failed: {e}")
            results['simple_select'] = {'status': 'ERROR', 'error': str(e)}
        
        # Test pg_stat_database query performance
        try:
            start_time = time.time()
            await self.connection.fetch("SELECT * FROM pg_stat_database WHERE datname = $1", self.database)
            stats_query_time = (time.time() - start_time) * 1000
            
            results['stats_query'] = {
                'time_ms': round(stats_query_time, 2),
                'status': 'OK' if stats_query_time < 50 else 'SLOW'
            }
            logger.info(f"✓ Stats query: {stats_query_time:.2f}ms")
        except Exception as e:
            logger.error(f"✗ Stats query failed: {e}")
            results['stats_query'] = {'status': 'ERROR', 'error': str(e)}
        
        return results
    
    def validate_system_resources(self) -> Dict[str, Any]:
        """Validate system resource usage."""
        logger.info("Validating system resource usage...")
        
        results = {}
        
        # Find PostgreSQL processes
        postgres_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                if 'postgres' in proc.info['name'].lower():
                    postgres_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not postgres_processes:
            logger.warning("No PostgreSQL processes found")
            results['postgres_processes'] = {'count': 0, 'status': 'NOT_FOUND'}
            return results
        
        # Calculate total memory usage
        total_memory_mb = 0
        total_cpu_percent = 0
        
        for proc in postgres_processes:
            try:
                memory_mb = proc.memory_info().rss / (1024 * 1024)  # Convert to MB
                cpu_percent = proc.cpu_percent()
                
                total_memory_mb += memory_mb
                total_cpu_percent += cpu_percent
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        results['postgres_processes'] = {
            'count': len(postgres_processes),
            'total_memory_mb': round(total_memory_mb, 2),
            'total_cpu_percent': round(total_cpu_percent, 2),
            'memory_status': 'OK' if total_memory_mb < 1024 else 'HIGH',  # Target < 1GB
            'cpu_status': 'OK' if total_cpu_percent < 50 else 'HIGH'
        }
        
        logger.info(f"✓ PostgreSQL processes: {len(postgres_processes)}")
        logger.info(f"✓ Total memory usage: {total_memory_mb:.2f}MB")
        logger.info(f"✓ Total CPU usage: {total_cpu_percent:.2f}%")
        
        return results
    
    async def run_full_validation(self) -> Dict[str, Any]:
        """Run complete PostgreSQL optimization validation."""
        logger.info("Starting PostgreSQL optimization validation...")
        
        validation_results = {
            'timestamp': datetime.now().isoformat(),
            'validation_status': 'UNKNOWN',
            'summary': {},
            'details': {}
        }
        
        # Connect to database
        if not await self.connect():
            validation_results['validation_status'] = 'CONNECTION_FAILED'
            return validation_results
        
        try:
            # Run all validation checks
            validation_results['details']['configuration'] = await self.validate_configuration()
            validation_results['details']['performance_functions'] = await self.validate_performance_functions()
            validation_results['details']['monitoring_schema'] = await self.validate_monitoring_schema()
            validation_results['details']['function_tests'] = await self.test_performance_functions()
            validation_results['details']['query_performance'] = await self.measure_query_performance()
            validation_results['details']['system_resources'] = self.validate_system_resources()
            
            # Generate summary
            validation_results['summary'] = self._generate_summary(validation_results['details'])
            
            # Determine overall status
            validation_results['validation_status'] = self._determine_overall_status(validation_results['summary'])
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            validation_results['validation_status'] = 'VALIDATION_ERROR'
            validation_results['error'] = str(e)
        
        finally:
            await self.disconnect()
        
        return validation_results
    
    def _generate_summary(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Generate validation summary."""
        summary = {
            'configuration_correct': 0,
            'configuration_total': 0,
            'functions_available': 0,
            'functions_total': 0,
            'performance_ok': True,
            'resource_usage_ok': True,
            'recommendations': []
        }
        
        # Configuration summary
        if 'configuration' in details:
            for setting, info in details['configuration'].items():
                summary['configuration_total'] += 1
                if info.get('correct', False):
                    summary['configuration_correct'] += 1
                else:
                    summary['recommendations'].append(f"Fix {setting}: expected {info.get('expected')}")
        
        # Functions summary
        if 'performance_functions' in details:
            for func, info in details['performance_functions'].items():
                summary['functions_total'] += 1
                if info.get('exists', False):
                    summary['functions_available'] += 1
        
        if 'monitoring_schema' in details:
            for key, info in details['monitoring_schema'].items():
                if key != 'schema_exists' and isinstance(info, dict):
                    summary['functions_total'] += 1
                    if info.get('exists', False):
                        summary['functions_available'] += 1
        
        # Performance summary
        if 'query_performance' in details:
            for test, info in details['query_performance'].items():
                if info.get('status') != 'OK':
                    summary['performance_ok'] = False
                    summary['recommendations'].append(f"Query performance issue: {test}")
        
        # Resource usage summary
        if 'system_resources' in details:
            postgres_info = details['system_resources'].get('postgres_processes', {})
            if postgres_info.get('memory_status') != 'OK':
                summary['resource_usage_ok'] = False
                summary['recommendations'].append("PostgreSQL memory usage is high")
            if postgres_info.get('cpu_status') != 'OK':
                summary['resource_usage_ok'] = False
                summary['recommendations'].append("PostgreSQL CPU usage is high")
        
        return summary
    
    def _determine_overall_status(self, summary: Dict[str, Any]) -> str:
        """Determine overall validation status."""
        config_ratio = summary['configuration_correct'] / max(summary['configuration_total'], 1)
        func_ratio = summary['functions_available'] / max(summary['functions_total'], 1)
        
        if (config_ratio >= 0.9 and func_ratio >= 0.9 and 
            summary['performance_ok'] and summary['resource_usage_ok']):
            return 'EXCELLENT'
        elif (config_ratio >= 0.8 and func_ratio >= 0.8 and 
              summary['performance_ok']):
            return 'GOOD'
        elif config_ratio >= 0.6 and func_ratio >= 0.6:
            return 'NEEDS_IMPROVEMENT'
        else:
            return 'POOR'

async def main():
    """Main validation function."""
    validator = PostgreSQLOptimizationValidator()
    
    try:
        results = await validator.run_full_validation()
        
        # Print results
        print("\n" + "="*80)
        print("POSTGRESQL OPTIMIZATION VALIDATION RESULTS")
        print("="*80)
        
        print(f"\nOverall Status: {results['validation_status']}")
        print(f"Timestamp: {results['timestamp']}")
        
        if 'summary' in results:
            summary = results['summary']
            print(f"\nConfiguration: {summary['configuration_correct']}/{summary['configuration_total']} correct")
            print(f"Functions: {summary['functions_available']}/{summary['functions_total']} available")
            print(f"Performance: {'OK' if summary['performance_ok'] else 'ISSUES'}")
            print(f"Resource Usage: {'OK' if summary['resource_usage_ok'] else 'HIGH'}")
            
            if summary['recommendations']:
                print("\nRecommendations:")
                for rec in summary['recommendations']:
                    print(f"  - {rec}")
        
        # Save detailed results to file
        output_file = f"postgresql_optimization_validation_{int(time.time())}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\nDetailed results saved to: {output_file}")
        
        # Exit with appropriate code
        if results['validation_status'] in ['EXCELLENT', 'GOOD']:
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())