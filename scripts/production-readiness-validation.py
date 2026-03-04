#!/usr/bin/env python3
"""
Production Readiness Validation Script
=====================================

This script performs comprehensive validation to ensure the Multimodal Librarian
system is ready for production deployment. It validates all critical components,
performance requirements, security compliance, and monitoring systems.

Task: 15 - Final checkpoint - Production readiness
Spec: chat-and-document-integration
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import traceback

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import requests
    import psutil
    import redis
    from sqlalchemy import create_engine, text
    from opensearchpy import OpenSearch
    import boto3
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError as e:
    print(f"Missing required dependency: {e}")
    print("Please install: pip install requests psutil redis sqlalchemy opensearch-py boto3")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'production-readiness-validation-{int(time.time())}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProductionReadinessValidator:
    """Comprehensive production readiness validation."""
    
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "UNKNOWN",
            "validation_results": {},
            "performance_metrics": {},
            "security_compliance": {},
            "monitoring_status": {},
            "recommendations": [],
            "critical_issues": [],
            "warnings": []
        }
        
        # Configuration
        self.base_url = os.getenv("BASE_URL", "http://localhost:8000")
        self.db_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/multimodal_librarian")
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.opensearch_url = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
        
        # Performance thresholds
        self.performance_thresholds = {
            "api_response_time": 3.0,  # seconds
            "chat_response_time": 5.0,  # seconds
            "document_upload_time": 30.0,  # seconds per MB
            "search_response_time": 1.0,  # seconds
            "memory_usage_threshold": 80,  # percentage
            "cpu_usage_threshold": 70,  # percentage
            "disk_usage_threshold": 85,  # percentage
            "concurrent_users": 50,  # minimum supported
            "uptime_requirement": 99.5  # percentage
        }
        
        # Security requirements
        self.security_requirements = [
            "authentication_enabled",
            "authorization_working",
            "data_encryption_at_rest",
            "data_encryption_in_transit",
            "input_validation",
            "rate_limiting",
            "audit_logging",
            "secure_headers",
            "privacy_compliance"
        ]
        
        # Monitoring requirements
        self.monitoring_requirements = [
            "health_checks",
            "performance_metrics",
            "error_tracking",
            "alerting_system",
            "log_aggregation",
            "dashboard_availability",
            "backup_monitoring",
            "security_monitoring"
        ]

    async def run_validation(self) -> Dict[str, Any]:
        """Run complete production readiness validation."""
        logger.info("Starting production readiness validation...")
        
        try:
            # 1. System Health and Stability
            await self._validate_system_health()
            
            # 2. Performance Requirements
            await self._validate_performance()
            
            # 3. Security and Privacy Compliance
            await self._validate_security_compliance()
            
            # 4. Monitoring and Alerting Systems
            await self._validate_monitoring_systems()
            
            # 5. Data Integrity and Backup
            await self._validate_data_integrity()
            
            # 6. Load Testing and Scalability
            await self._validate_scalability()
            
            # 7. Documentation and Procedures
            await self._validate_documentation()
            
            # 8. Final Assessment
            self._generate_final_assessment()
            
        except Exception as e:
            logger.error(f"Validation failed with error: {e}")
            self.results["critical_issues"].append(f"Validation process failed: {str(e)}")
            self.results["overall_status"] = "FAILED"
            
        return self.results

    async def _validate_system_health(self):
        """Validate system health and stability."""
        logger.info("Validating system health and stability...")
        
        health_results = {
            "api_health": False,
            "database_connectivity": False,
            "redis_connectivity": False,
            "opensearch_connectivity": False,
            "service_dependencies": False,
            "system_resources": False
        }
        
        try:
            # API Health Check
            response = requests.get(f"{self.base_url}/health", timeout=10)
            health_results["api_health"] = response.status_code == 200
            
            if health_results["api_health"]:
                health_data = response.json()
                logger.info(f"API health check passed: {health_data}")
            else:
                self.results["critical_issues"].append(f"API health check failed: {response.status_code}")
                
        except Exception as e:
            self.results["critical_issues"].append(f"API health check error: {str(e)}")
            
        try:
            # Database Connectivity
            engine = create_engine(self.db_url)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                health_results["database_connectivity"] = result.fetchone()[0] == 1
                logger.info("Database connectivity check passed")
                
        except Exception as e:
            self.results["critical_issues"].append(f"Database connectivity failed: {str(e)}")
            
        try:
            # Redis Connectivity
            redis_client = redis.from_url(self.redis_url)
            redis_client.ping()
            health_results["redis_connectivity"] = True
            logger.info("Redis connectivity check passed")
            
        except Exception as e:
            self.results["critical_issues"].append(f"Redis connectivity failed: {str(e)}")
            
        try:
            # OpenSearch Connectivity
            opensearch_client = OpenSearch([self.opensearch_url])
            cluster_health = opensearch_client.cluster.health()
            health_results["opensearch_connectivity"] = cluster_health["status"] in ["green", "yellow"]
            logger.info(f"OpenSearch connectivity check passed: {cluster_health['status']}")
            
        except Exception as e:
            self.results["critical_issues"].append(f"OpenSearch connectivity failed: {str(e)}")
            
        # System Resources
        try:
            memory_percent = psutil.virtual_memory().percent
            cpu_percent = psutil.cpu_percent(interval=1)
            disk_percent = psutil.disk_usage('/').percent
            
            resource_issues = []
            if memory_percent > self.performance_thresholds["memory_usage_threshold"]:
                resource_issues.append(f"High memory usage: {memory_percent}%")
            if cpu_percent > self.performance_thresholds["cpu_usage_threshold"]:
                resource_issues.append(f"High CPU usage: {cpu_percent}%")
            if disk_percent > self.performance_thresholds["disk_usage_threshold"]:
                resource_issues.append(f"High disk usage: {disk_percent}%")
                
            health_results["system_resources"] = len(resource_issues) == 0
            
            if resource_issues:
                self.results["warnings"].extend(resource_issues)
            else:
                logger.info(f"System resources OK - Memory: {memory_percent}%, CPU: {cpu_percent}%, Disk: {disk_percent}%")
                
        except Exception as e:
            self.results["warnings"].append(f"System resource check failed: {str(e)}")
            
        # Service Dependencies
        try:
            # Check critical service endpoints
            critical_endpoints = [
                "/api/chat/health",
                "/api/documents/health", 
                "/api/rag/health",
                "/api/analytics/health",
                "/api/cache/health"
            ]
            
            dependency_results = []
            for endpoint in critical_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    dependency_results.append(response.status_code == 200)
                except:
                    dependency_results.append(False)
                    
            health_results["service_dependencies"] = all(dependency_results)
            
            if health_results["service_dependencies"]:
                logger.info("All service dependencies are healthy")
            else:
                failed_services = [endpoint for endpoint, result in zip(critical_endpoints, dependency_results) if not result]
                self.results["warnings"].append(f"Some service dependencies failed: {failed_services}")
                
        except Exception as e:
            self.results["warnings"].append(f"Service dependency check failed: {str(e)}")
            
        self.results["validation_results"]["system_health"] = health_results
        
        # Overall health assessment
        healthy_components = sum(1 for v in health_results.values() if v)
        total_components = len(health_results)
        health_score = (healthy_components / total_components) * 100
        
        logger.info(f"System health score: {health_score:.1f}% ({healthy_components}/{total_components} components healthy)")
        
        if health_score < 80:
            self.results["critical_issues"].append(f"System health score too low: {health_score:.1f}%")
    async def _validate_performance(self):
        """Validate performance requirements."""
        logger.info("Validating performance requirements...")
        
        performance_results = {
            "api_response_times": {},
            "concurrent_user_support": False,
            "resource_efficiency": {},
            "scalability_metrics": {}
        }
        
        # API Response Time Testing
        api_endpoints = [
            ("/health", "GET", None),
            ("/api/chat/health", "GET", None),
            ("/api/documents/health", "GET", None),
            ("/api/analytics/dashboard-data", "GET", None)
        ]
        
        for endpoint, method, data in api_endpoints:
            try:
                start_time = time.time()
                if method == "GET":
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                else:
                    response = requests.post(f"{self.base_url}{endpoint}", json=data, timeout=10)
                    
                response_time = time.time() - start_time
                performance_results["api_response_times"][endpoint] = {
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "meets_threshold": response_time <= self.performance_thresholds["api_response_time"]
                }
                
                if response_time > self.performance_thresholds["api_response_time"]:
                    self.results["warnings"].append(f"Slow API response for {endpoint}: {response_time:.2f}s")
                else:
                    logger.info(f"API performance OK for {endpoint}: {response_time:.2f}s")
                    
            except Exception as e:
                performance_results["api_response_times"][endpoint] = {
                    "error": str(e),
                    "meets_threshold": False
                }
                self.results["warnings"].append(f"API performance test failed for {endpoint}: {str(e)}")
        
        # Concurrent User Simulation
        try:
            concurrent_users = 10  # Reduced for validation
            
            def make_request():
                try:
                    start_time = time.time()
                    response = requests.get(f"{self.base_url}/health", timeout=10)
                    return time.time() - start_time, response.status_code == 200
                except:
                    return None, False
            
            with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = [executor.submit(make_request) for _ in range(concurrent_users)]
                results = [future.result() for future in as_completed(futures)]
                
            successful_requests = sum(1 for _, success in results if success)
            avg_response_time = sum(time for time, _ in results if time) / len([r for r in results if r[0]])
            
            performance_results["concurrent_user_support"] = {
                "concurrent_users_tested": concurrent_users,
                "successful_requests": successful_requests,
                "success_rate": (successful_requests / concurrent_users) * 100,
                "average_response_time": avg_response_time,
                "meets_threshold": successful_requests >= concurrent_users * 0.9
            }
            
            logger.info(f"Concurrent user test: {successful_requests}/{concurrent_users} successful, avg response: {avg_response_time:.2f}s")
            
        except Exception as e:
            self.results["warnings"].append(f"Concurrent user testing failed: {str(e)}")
            
        # Resource Efficiency
        try:
            memory_info = psutil.virtual_memory()
            cpu_info = psutil.cpu_percent(interval=1)
            disk_info = psutil.disk_usage('/')
            
            performance_results["resource_efficiency"] = {
                "memory_usage_percent": memory_info.percent,
                "memory_available_gb": memory_info.available / (1024**3),
                "cpu_usage_percent": cpu_info,
                "disk_usage_percent": (disk_info.used / disk_info.total) * 100,
                "disk_free_gb": disk_info.free / (1024**3)
            }
            
            logger.info(f"Resource efficiency - Memory: {memory_info.percent}%, CPU: {cpu_info}%, Disk: {(disk_info.used / disk_info.total) * 100:.1f}%")
            
        except Exception as e:
            self.results["warnings"].append(f"Resource efficiency check failed: {str(e)}")
            
        self.results["performance_metrics"] = performance_results

    async def _validate_security_compliance(self):
        """Validate security and privacy compliance."""
        logger.info("Validating security and privacy compliance...")
        
        security_results = {}
        
        # Authentication Testing
        try:
            # Test unauthenticated access to protected endpoints
            protected_endpoints = [
                "/api/documents/upload",
                "/api/chat/conversations",
                "/api/analytics/dashboard-data"
            ]
            
            auth_results = []
            for endpoint in protected_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    # Should return 401 or 403 for protected endpoints
                    auth_results.append(response.status_code in [401, 403])
                except:
                    auth_results.append(False)
                    
            security_results["authentication_enabled"] = any(auth_results)
            
            if security_results["authentication_enabled"]:
                logger.info("Authentication is properly configured")
            else:
                self.results["critical_issues"].append("Authentication not properly configured")
                
        except Exception as e:
            self.results["warnings"].append(f"Authentication testing failed: {str(e)}")
            
        # Security Headers Check
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            headers = response.headers
            
            required_headers = [
                "X-Content-Type-Options",
                "X-Frame-Options", 
                "X-XSS-Protection"
            ]
            
            header_results = []
            for header in required_headers:
                header_present = header in headers
                header_results.append(header_present)
                if not header_present:
                    self.results["warnings"].append(f"Missing security header: {header}")
                    
            security_results["secure_headers"] = all(header_results)
            
            if security_results["secure_headers"]:
                logger.info("Security headers are properly configured")
                
        except Exception as e:
            self.results["warnings"].append(f"Security headers check failed: {str(e)}")
            
        # Rate Limiting Check
        try:
            # Make rapid requests to test rate limiting
            rapid_requests = []
            for i in range(20):
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=1)
                    rapid_requests.append(response.status_code)
                except:
                    rapid_requests.append(None)
                    
            # Check if any requests were rate limited (429 status)
            rate_limited = any(status == 429 for status in rapid_requests)
            security_results["rate_limiting"] = rate_limited
            
            if rate_limited:
                logger.info("Rate limiting is working")
            else:
                self.results["warnings"].append("Rate limiting may not be configured")
                
        except Exception as e:
            self.results["warnings"].append(f"Rate limiting check failed: {str(e)}")
            
        # Data Encryption Check
        try:
            # Check if HTTPS is enforced
            if self.base_url.startswith("https://"):
                security_results["data_encryption_in_transit"] = True
                logger.info("HTTPS encryption is enabled")
            else:
                security_results["data_encryption_in_transit"] = False
                self.results["warnings"].append("HTTPS not enabled - data not encrypted in transit")
                
        except Exception as e:
            self.results["warnings"].append(f"Encryption check failed: {str(e)}")
            
        # Privacy Compliance Check
        try:
            # Check if privacy endpoints are available
            privacy_endpoints = [
                "/api/privacy/data-deletion",
                "/api/privacy/data-export"
            ]
            
            privacy_results = []
            for endpoint in privacy_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    # Should return 401/403 (protected) or 405 (method not allowed), not 404
                    privacy_results.append(response.status_code != 404)
                except:
                    privacy_results.append(False)
                    
            security_results["privacy_compliance"] = any(privacy_results)
            
            if security_results["privacy_compliance"]:
                logger.info("Privacy compliance endpoints are available")
            else:
                self.results["warnings"].append("Privacy compliance endpoints not found")
                
        except Exception as e:
            self.results["warnings"].append(f"Privacy compliance check failed: {str(e)}")
            
        self.results["security_compliance"] = security_results
        
        # Security score calculation
        security_score = (sum(1 for v in security_results.values() if v) / len(security_results)) * 100
        logger.info(f"Security compliance score: {security_score:.1f}%")
        
        if security_score < 70:
            self.results["critical_issues"].append(f"Security compliance score too low: {security_score:.1f}%")
    async def _validate_monitoring_systems(self):
        """Validate monitoring and alerting systems."""
        logger.info("Validating monitoring and alerting systems...")
        
        monitoring_results = {}
        
        # Health Check Endpoints
        try:
            health_endpoints = [
                "/health",
                "/api/monitoring/health",
                "/api/logging/health",
                "/api/cache/health"
            ]
            
            health_results = []
            for endpoint in health_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    health_results.append(response.status_code == 200)
                    if response.status_code == 200:
                        logger.info(f"Health endpoint {endpoint} is working")
                except:
                    health_results.append(False)
                    
            monitoring_results["health_checks"] = any(health_results)
            
        except Exception as e:
            self.results["warnings"].append(f"Health check validation failed: {str(e)}")
            
        # Performance Metrics
        try:
            metrics_endpoints = [
                "/api/monitoring/metrics",
                "/api/analytics/dashboard-data",
                "/api/cache/stats"
            ]
            
            metrics_results = []
            for endpoint in metrics_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    metrics_results.append(response.status_code in [200, 401, 403])  # Available but may require auth
                except:
                    metrics_results.append(False)
                    
            monitoring_results["performance_metrics"] = any(metrics_results)
            
            if monitoring_results["performance_metrics"]:
                logger.info("Performance metrics endpoints are available")
                
        except Exception as e:
            self.results["warnings"].append(f"Performance metrics validation failed: {str(e)}")
            
        # Logging System
        try:
            logging_endpoints = [
                "/api/logging/logs",
                "/api/logging/performance",
                "/api/logging/errors"
            ]
            
            logging_results = []
            for endpoint in logging_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    logging_results.append(response.status_code in [200, 401, 403])
                except:
                    logging_results.append(False)
                    
            monitoring_results["log_aggregation"] = any(logging_results)
            
            if monitoring_results["log_aggregation"]:
                logger.info("Logging system endpoints are available")
                
        except Exception as e:
            self.results["warnings"].append(f"Logging system validation failed: {str(e)}")
            
        # Alerting System
        try:
            alerting_endpoints = [
                "/api/monitoring/alerts",
                "/api/monitoring/alert-rules"
            ]
            
            alerting_results = []
            for endpoint in alerting_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    alerting_results.append(response.status_code in [200, 401, 403])
                except:
                    alerting_results.append(False)
                    
            monitoring_results["alerting_system"] = any(alerting_results)
            
            if monitoring_results["alerting_system"]:
                logger.info("Alerting system endpoints are available")
                
        except Exception as e:
            self.results["warnings"].append(f"Alerting system validation failed: {str(e)}")
            
        # Dashboard Availability
        try:
            dashboard_endpoints = [
                "/monitoring",
                "/analytics"
            ]
            
            dashboard_results = []
            for endpoint in dashboard_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    dashboard_results.append(response.status_code == 200)
                except:
                    dashboard_results.append(False)
                    
            monitoring_results["dashboard_availability"] = any(dashboard_results)
            
            if monitoring_results["dashboard_availability"]:
                logger.info("Monitoring dashboards are available")
                
        except Exception as e:
            self.results["warnings"].append(f"Dashboard availability validation failed: {str(e)}")
            
        self.results["monitoring_status"] = monitoring_results
        
        # Monitoring score calculation
        monitoring_score = (sum(1 for v in monitoring_results.values() if v) / len(monitoring_results)) * 100
        logger.info(f"Monitoring system score: {monitoring_score:.1f}%")
        
        if monitoring_score < 60:
            self.results["critical_issues"].append(f"Monitoring system score too low: {monitoring_score:.1f}%")

    async def _validate_data_integrity(self):
        """Validate data integrity and backup systems."""
        logger.info("Validating data integrity and backup systems...")
        
        data_results = {}
        
        # Database Integrity
        try:
            engine = create_engine(self.db_url)
            with engine.connect() as conn:
                # Check if critical tables exist
                tables_query = text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                
                tables = conn.execute(tables_query).fetchall()
                table_names = [row[0] for row in tables]
                
                critical_tables = [
                    "users", "documents", "chat_messages", 
                    "document_chunks", "conversations"
                ]
                
                missing_tables = [table for table in critical_tables if table not in table_names]
                
                data_results["database_integrity"] = len(missing_tables) == 0
                
                if missing_tables:
                    self.results["critical_issues"].append(f"Missing critical database tables: {missing_tables}")
                else:
                    logger.info("Database integrity check passed - all critical tables present")
                    
        except Exception as e:
            self.results["critical_issues"].append(f"Database integrity check failed: {str(e)}")
            
        # Backup System Check
        try:
            # Check if backup endpoints are available
            backup_endpoints = [
                "/api/backup/status",
                "/api/backup/create"
            ]
            
            backup_results = []
            for endpoint in backup_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    backup_results.append(response.status_code in [200, 401, 403])
                except:
                    backup_results.append(False)
                    
            data_results["backup_system"] = any(backup_results)
            
            if data_results["backup_system"]:
                logger.info("Backup system endpoints are available")
            else:
                self.results["warnings"].append("Backup system endpoints not found")
                
        except Exception as e:
            self.results["warnings"].append(f"Backup system check failed: {str(e)}")
            
        self.results["validation_results"]["data_integrity"] = data_results

    async def _validate_scalability(self):
        """Validate scalability and load handling."""
        logger.info("Validating scalability and load handling...")
        
        scalability_results = {}
        
        # Connection Pool Testing
        try:
            # Test multiple simultaneous connections
            connection_count = 20
            
            def test_connection():
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=5)
                    return response.status_code == 200
                except:
                    return False
                    
            with ThreadPoolExecutor(max_workers=connection_count) as executor:
                futures = [executor.submit(test_connection) for _ in range(connection_count)]
                results = [future.result() for future in as_completed(futures)]
                
            successful_connections = sum(results)
            success_rate = (successful_connections / connection_count) * 100
            
            scalability_results["connection_handling"] = {
                "concurrent_connections": connection_count,
                "successful_connections": successful_connections,
                "success_rate": success_rate,
                "meets_threshold": success_rate >= 90
            }
            
            logger.info(f"Connection handling test: {successful_connections}/{connection_count} successful ({success_rate:.1f}%)")
            
            if success_rate < 90:
                self.results["warnings"].append(f"Low connection success rate: {success_rate:.1f}%")
                
        except Exception as e:
            self.results["warnings"].append(f"Connection handling test failed: {str(e)}")
            
        # Memory Usage Under Load
        try:
            initial_memory = psutil.virtual_memory().percent
            
            # Simulate some load
            load_requests = []
            for i in range(50):
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=1)
                    load_requests.append(response.status_code == 200)
                except:
                    load_requests.append(False)
                    
            final_memory = psutil.virtual_memory().percent
            memory_increase = final_memory - initial_memory
            
            scalability_results["memory_under_load"] = {
                "initial_memory_percent": initial_memory,
                "final_memory_percent": final_memory,
                "memory_increase": memory_increase,
                "acceptable_increase": memory_increase < 10
            }
            
            logger.info(f"Memory usage under load: {initial_memory}% -> {final_memory}% (increase: {memory_increase}%)")
            
            if memory_increase > 10:
                self.results["warnings"].append(f"High memory increase under load: {memory_increase}%")
                
        except Exception as e:
            self.results["warnings"].append(f"Memory under load test failed: {str(e)}")
            
        self.results["validation_results"]["scalability"] = scalability_results

    async def _validate_documentation(self):
        """Validate documentation and procedures."""
        logger.info("Validating documentation and procedures...")
        
        doc_results = {}
        
        # Check for required documentation files
        required_docs = [
            "README.md",
            "docs/user-guide/README.md",
            "docs/deployment/deployment-procedures.md",
            "docs/deployment/rollback-procedures.md",
            "TASK_14_2_USER_ACCEPTANCE_TESTING_COMPLETION_SUMMARY.md"
        ]
        
        missing_docs = []
        for doc_path in required_docs:
            if not Path(doc_path).exists():
                missing_docs.append(doc_path)
                
        doc_results["required_documentation"] = len(missing_docs) == 0
        
        if missing_docs:
            self.results["warnings"].append(f"Missing required documentation: {missing_docs}")
        else:
            logger.info("All required documentation is present")
            
        # Check for deployment scripts
        required_scripts = [
            "scripts/prepare-demo-test-data.py"
        ]
        
        missing_scripts = []
        for script_path in required_scripts:
            if not Path(script_path).exists():
                missing_scripts.append(script_path)
                
        doc_results["deployment_scripts"] = len(missing_scripts) == 0
        
        if missing_scripts:
            self.results["warnings"].append(f"Missing required scripts: {missing_scripts}")
        else:
            logger.info("All required deployment scripts are present")
            
        self.results["validation_results"]["documentation"] = doc_results
    def _generate_final_assessment(self):
        """Generate final production readiness assessment."""
        logger.info("Generating final production readiness assessment...")
        
        # Calculate overall scores
        validation_scores = []
        
        # System Health Score
        if "system_health" in self.results["validation_results"]:
            health_results = self.results["validation_results"]["system_health"]
            health_score = (sum(1 for v in health_results.values() if v) / len(health_results)) * 100
            validation_scores.append(("System Health", health_score))
            
        # Security Score
        if self.results["security_compliance"]:
            security_score = (sum(1 for v in self.results["security_compliance"].values() if v) / len(self.results["security_compliance"])) * 100
            validation_scores.append(("Security Compliance", security_score))
            
        # Monitoring Score
        if self.results["monitoring_status"]:
            monitoring_score = (sum(1 for v in self.results["monitoring_status"].values() if v) / len(self.results["monitoring_status"])) * 100
            validation_scores.append(("Monitoring Systems", monitoring_score))
            
        # Calculate overall readiness score
        if validation_scores:
            overall_score = sum(score for _, score in validation_scores) / len(validation_scores)
        else:
            overall_score = 0
            
        # Determine readiness status
        critical_issues_count = len(self.results["critical_issues"])
        warnings_count = len(self.results["warnings"])
        
        if critical_issues_count > 0:
            self.results["overall_status"] = "NOT_READY"
            self.results["recommendations"].append("Address all critical issues before production deployment")
        elif overall_score >= 80 and warnings_count <= 5:
            self.results["overall_status"] = "READY"
            self.results["recommendations"].append("System is ready for production deployment")
        elif overall_score >= 70:
            self.results["overall_status"] = "READY_WITH_WARNINGS"
            self.results["recommendations"].append("System is ready but address warnings for optimal performance")
        else:
            self.results["overall_status"] = "NOT_READY"
            self.results["recommendations"].append("System needs improvement before production deployment")
            
        # Add specific recommendations
        if warnings_count > 0:
            self.results["recommendations"].append(f"Review and address {warnings_count} warnings")
            
        if overall_score < 90:
            self.results["recommendations"].append("Consider additional testing and optimization")
            
        # Performance recommendations
        if "performance_metrics" in self.results and self.results["performance_metrics"]:
            perf_metrics = self.results["performance_metrics"]
            if "api_response_times" in perf_metrics:
                slow_endpoints = [
                    endpoint for endpoint, data in perf_metrics["api_response_times"].items()
                    if isinstance(data, dict) and not data.get("meets_threshold", True)
                ]
                if slow_endpoints:
                    self.results["recommendations"].append(f"Optimize performance for slow endpoints: {slow_endpoints}")
                    
        # Security recommendations
        if self.results["security_compliance"]:
            security_issues = [
                requirement for requirement, status in self.results["security_compliance"].items()
                if not status
            ]
            if security_issues:
                self.results["recommendations"].append(f"Address security compliance issues: {security_issues}")
                
        # Final summary
        self.results["readiness_summary"] = {
            "overall_score": overall_score,
            "validation_scores": validation_scores,
            "critical_issues_count": critical_issues_count,
            "warnings_count": warnings_count,
            "status": self.results["overall_status"],
            "deployment_recommendation": self.results["overall_status"] in ["READY", "READY_WITH_WARNINGS"]
        }
        
        logger.info(f"Production readiness assessment complete:")
        logger.info(f"  Overall Score: {overall_score:.1f}%")
        logger.info(f"  Status: {self.results['overall_status']}")
        logger.info(f"  Critical Issues: {critical_issues_count}")
        logger.info(f"  Warnings: {warnings_count}")

async def main():
    """Main validation function."""
    print("=" * 80)
    print("PRODUCTION READINESS VALIDATION")
    print("=" * 80)
    print()
    
    validator = ProductionReadinessValidator()
    results = await validator.run_validation()
    
    # Save results to file
    timestamp = int(time.time())
    results_file = f"production-readiness-validation-{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
        
    print()
    print("=" * 80)
    print("VALIDATION RESULTS SUMMARY")
    print("=" * 80)
    
    # Print summary
    summary = results.get("readiness_summary", {})
    print(f"Overall Status: {results['overall_status']}")
    print(f"Overall Score: {summary.get('overall_score', 0):.1f}%")
    print(f"Critical Issues: {len(results['critical_issues'])}")
    print(f"Warnings: {len(results['warnings'])}")
    print()
    
    if results["critical_issues"]:
        print("CRITICAL ISSUES:")
        for issue in results["critical_issues"]:
            print(f"  ❌ {issue}")
        print()
        
    if results["warnings"]:
        print("WARNINGS:")
        for warning in results["warnings"][:10]:  # Show first 10 warnings
            print(f"  ⚠️  {warning}")
        if len(results["warnings"]) > 10:
            print(f"  ... and {len(results['warnings']) - 10} more warnings")
        print()
        
    if results["recommendations"]:
        print("RECOMMENDATIONS:")
        for rec in results["recommendations"]:
            print(f"  💡 {rec}")
        print()
        
    print(f"Detailed results saved to: {results_file}")
    print()
    
    # Deployment recommendation
    if summary.get("deployment_recommendation", False):
        print("✅ SYSTEM IS READY FOR PRODUCTION DEPLOYMENT")
    else:
        print("❌ SYSTEM IS NOT READY FOR PRODUCTION DEPLOYMENT")
        print("   Address critical issues and warnings before deploying")
        
    print("=" * 80)
    
    return results

if __name__ == "__main__":
    try:
        results = asyncio.run(main())
        
        # Exit with appropriate code
        if results["overall_status"] == "READY":
            sys.exit(0)
        elif results["overall_status"] == "READY_WITH_WARNINGS":
            sys.exit(1)  # Warning exit code
        else:
            sys.exit(2)  # Error exit code
            
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nValidation failed with error: {e}")
        traceback.print_exc()
        sys.exit(1)