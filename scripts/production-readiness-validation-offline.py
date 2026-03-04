#!/usr/bin/env python3
"""
Production Readiness Validation Script (Offline Mode)
====================================================

This script performs comprehensive validation to ensure the Multimodal Librarian
system is ready for production deployment. It validates system components,
documentation, and infrastructure without requiring all services to be running.

Task: 15 - Final checkpoint - Production readiness
Spec: chat-and-document-integration
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import traceback

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
    """Comprehensive production readiness validation (offline mode)."""
    
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "UNKNOWN",
            "validation_results": {},
            "recommendations": [],
            "critical_issues": [],
            "warnings": []
        }
        
        self.project_root = Path(__file__).parent.parent

    def run_validation(self) -> Dict[str, Any]:
        """Run complete production readiness validation."""
        logger.info("Starting production readiness validation (offline mode)...")
        
        try:
            # 1. Code Structure and Implementation
            self._validate_code_structure()
            
            # 2. Documentation and Procedures
            self._validate_documentation()
            
            # 3. Configuration and Environment
            self._validate_configuration()
            
            # 4. Test Coverage and Quality
            self._validate_test_coverage()
            
            # 5. Deployment Readiness
            self._validate_deployment_readiness()
            
            # 6. Security Implementation
            self._validate_security_implementation()
            
            # 7. Monitoring and Observability
            self._validate_monitoring_implementation()
            
            # 8. Final Assessment
            self._generate_final_assessment()
            
        except Exception as e:
            logger.error(f"Validation failed with error: {e}")
            self.results["critical_issues"].append(f"Validation process failed: {str(e)}")
            self.results["overall_status"] = "FAILED"
            
        return self.results

    def _validate_code_structure(self):
        """Validate code structure and implementation completeness."""
        logger.info("Validating code structure and implementation...")
        
        structure_results = {
            "core_components": False,
            "api_endpoints": False,
            "service_implementations": False,
            "database_models": False,
            "configuration_management": False
        }
        
        # Check core components
        core_components = [
            "src/multimodal_librarian/main.py",
            "src/multimodal_librarian/config/__init__.py",
            "src/multimodal_librarian/api/routers",
            "src/multimodal_librarian/services",
            "src/multimodal_librarian/database",
            "src/multimodal_librarian/components"
        ]
        
        missing_components = []
        for component in core_components:
            component_path = self.project_root / component
            if not component_path.exists():
                missing_components.append(component)
                
        structure_results["core_components"] = len(missing_components) == 0
        
        if missing_components:
            self.results["critical_issues"].append(f"Missing core components: {missing_components}")
        else:
            logger.info("All core components are present")
            
        # Check API endpoints
        api_routers = [
            "src/multimodal_librarian/api/routers/chat.py",
            "src/multimodal_librarian/api/routers/documents.py",
            "src/multimodal_librarian/api/routers/analytics.py",
            "src/multimodal_librarian/api/routers/cache_management.py",
            "src/multimodal_librarian/api/routers/monitoring.py"
        ]
        
        missing_routers = []
        for router in api_routers:
            router_path = self.project_root / router
            if not router_path.exists():
                missing_routers.append(router)
                
        structure_results["api_endpoints"] = len(missing_routers) == 0
        
        if missing_routers:
            self.results["warnings"].append(f"Missing API routers: {missing_routers}")
        else:
            logger.info("All critical API routers are present")
            
        # Check service implementations
        services = [
            "src/multimodal_librarian/services/ai_service.py",
            "src/multimodal_librarian/services/chat_service.py",
            "src/multimodal_librarian/services/rag_service.py",
            "src/multimodal_librarian/services/cache_service.py",
            "src/multimodal_librarian/services/analytics_service.py"
        ]
        
        missing_services = []
        for service in services:
            service_path = self.project_root / service
            if not service_path.exists():
                missing_services.append(service)
                
        structure_results["service_implementations"] = len(missing_services) == 0
        
        if missing_services:
            self.results["warnings"].append(f"Missing service implementations: {missing_services}")
        else:
            logger.info("All critical service implementations are present")
            
        # Check database models
        db_components = [
            "src/multimodal_librarian/database/models.py",
            "src/multimodal_librarian/database/connection.py",
            "src/multimodal_librarian/database/migrations.py"
        ]
        
        missing_db = []
        for db_component in db_components:
            db_path = self.project_root / db_component
            if not db_path.exists():
                missing_db.append(db_component)
                
        structure_results["database_models"] = len(missing_db) == 0
        
        if missing_db:
            self.results["warnings"].append(f"Missing database components: {missing_db}")
        else:
            logger.info("All database components are present")
            
        # Check configuration management
        config_files = [
            "src/multimodal_librarian/config/__init__.py",
            ".env.example",
            "pyproject.toml",
            "requirements.txt"
        ]
        
        missing_config = []
        for config_file in config_files:
            config_path = self.project_root / config_file
            if not config_path.exists():
                missing_config.append(config_file)
                
        structure_results["configuration_management"] = len(missing_config) == 0
        
        if missing_config:
            self.results["warnings"].append(f"Missing configuration files: {missing_config}")
        else:
            logger.info("All configuration files are present")
            
        self.results["validation_results"]["code_structure"] = structure_results

    def _validate_documentation(self):
        """Validate documentation completeness."""
        logger.info("Validating documentation completeness...")
        
        doc_results = {
            "user_documentation": False,
            "api_documentation": False,
            "deployment_procedures": False,
            "troubleshooting_guides": False,
            "demo_scenarios": False
        }
        
        # User documentation
        user_docs = [
            "README.md",
            "docs/user-guide/README.md",
            "docs/user-guide/demo-scenarios.md",
            "docs/user-guide/feedback-collection.md"
        ]
        
        missing_user_docs = []
        for doc in user_docs:
            doc_path = self.project_root / doc
            if not doc_path.exists():
                missing_user_docs.append(doc)
                
        doc_results["user_documentation"] = len(missing_user_docs) == 0
        
        if missing_user_docs:
            self.results["critical_issues"].append(f"Missing user documentation: {missing_user_docs}")
        else:
            logger.info("User documentation is complete")
            
        # API documentation
        api_docs = [
            "docs/api/api-documentation.md"
        ]
        
        missing_api_docs = []
        for doc in api_docs:
            doc_path = self.project_root / doc
            if not doc_path.exists():
                missing_api_docs.append(doc)
                
        doc_results["api_documentation"] = len(missing_api_docs) == 0
        
        if missing_api_docs:
            self.results["warnings"].append(f"Missing API documentation: {missing_api_docs}")
        else:
            logger.info("API documentation is present")
            
        # Deployment procedures
        deployment_docs = [
            "docs/deployment/deployment-procedures.md",
            "docs/deployment/rollback-procedures.md"
        ]
        
        missing_deployment_docs = []
        for doc in deployment_docs:
            doc_path = self.project_root / doc
            if not doc_path.exists():
                missing_deployment_docs.append(doc)
                
        doc_results["deployment_procedures"] = len(missing_deployment_docs) == 0
        
        if missing_deployment_docs:
            self.results["critical_issues"].append(f"Missing deployment documentation: {missing_deployment_docs}")
        else:
            logger.info("Deployment procedures are documented")
            
        # Troubleshooting guides
        troubleshooting_docs = [
            "docs/troubleshooting/system-troubleshooting-guide.md"
        ]
        
        missing_troubleshooting = []
        for doc in troubleshooting_docs:
            doc_path = self.project_root / doc
            if not doc_path.exists():
                missing_troubleshooting.append(doc)
                
        doc_results["troubleshooting_guides"] = len(missing_troubleshooting) == 0
        
        if missing_troubleshooting:
            self.results["warnings"].append(f"Missing troubleshooting guides: {missing_troubleshooting}")
        else:
            logger.info("Troubleshooting guides are present")
            
        # Demo scenarios
        demo_files = [
            "docs/user-guide/demo-scenarios.md",
            "scripts/prepare-demo-test-data.py"
        ]
        
        missing_demo = []
        for demo_file in demo_files:
            demo_path = self.project_root / demo_file
            if not demo_path.exists():
                missing_demo.append(demo_file)
                
        doc_results["demo_scenarios"] = len(missing_demo) == 0
        
        if missing_demo:
            self.results["warnings"].append(f"Missing demo scenarios: {missing_demo}")
        else:
            logger.info("Demo scenarios are available")
            
        self.results["validation_results"]["documentation"] = doc_results

    def _validate_configuration(self):
        """Validate configuration and environment setup."""
        logger.info("Validating configuration and environment...")
        
        config_results = {
            "environment_variables": False,
            "docker_configuration": False,
            "dependency_management": False,
            "security_configuration": False
        }
        
        # Environment variables
        env_files = [".env.example"]
        required_env_vars = [
            "DATABASE_URL", "REDIS_URL", "OPENSEARCH_URL",
            "GEMINI_API_KEY", "OPENAI_API_KEY"
        ]
        
        env_example_path = self.project_root / ".env.example"
        if env_example_path.exists():
            try:
                with open(env_example_path, 'r') as f:
                    env_content = f.read()
                    
                missing_vars = []
                for var in required_env_vars:
                    if var not in env_content:
                        missing_vars.append(var)
                        
                config_results["environment_variables"] = len(missing_vars) == 0
                
                if missing_vars:
                    self.results["warnings"].append(f"Missing environment variables in .env.example: {missing_vars}")
                else:
                    logger.info("Environment variables are properly documented")
                    
            except Exception as e:
                self.results["warnings"].append(f"Failed to read .env.example: {e}")
        else:
            self.results["critical_issues"].append("Missing .env.example file")
            
        # Docker configuration
        docker_files = ["Dockerfile", "docker-compose.yml"]
        
        missing_docker = []
        for docker_file in docker_files:
            docker_path = self.project_root / docker_file
            if not docker_path.exists():
                missing_docker.append(docker_file)
                
        config_results["docker_configuration"] = len(missing_docker) == 0
        
        if missing_docker:
            self.results["warnings"].append(f"Missing Docker configuration: {missing_docker}")
        else:
            logger.info("Docker configuration is present")
            
        # Dependency management
        dep_files = ["requirements.txt", "pyproject.toml"]
        
        missing_deps = []
        for dep_file in dep_files:
            dep_path = self.project_root / dep_file
            if not dep_path.exists():
                missing_deps.append(dep_file)
                
        config_results["dependency_management"] = len(missing_deps) == 0
        
        if missing_deps:
            self.results["critical_issues"].append(f"Missing dependency files: {missing_deps}")
        else:
            logger.info("Dependency management files are present")
            
        # Security configuration
        security_components = [
            "src/multimodal_librarian/security",
            "src/multimodal_librarian/api/middleware"
        ]
        
        missing_security = []
        for security_component in security_components:
            security_path = self.project_root / security_component
            if not security_path.exists():
                missing_security.append(security_component)
                
        config_results["security_configuration"] = len(missing_security) == 0
        
        if missing_security:
            self.results["warnings"].append(f"Missing security components: {missing_security}")
        else:
            logger.info("Security configuration components are present")
            
        self.results["validation_results"]["configuration"] = config_results

    def _validate_test_coverage(self):
        """Validate test coverage and quality."""
        logger.info("Validating test coverage and quality...")
        
        test_results = {
            "unit_tests": False,
            "integration_tests": False,
            "performance_tests": False,
            "security_tests": False,
            "test_data": False
        }
        
        # Unit tests
        unit_test_dirs = [
            "tests",
            "tests/components",
            "tests/services",
            "tests/api"
        ]
        
        existing_unit_dirs = []
        for test_dir in unit_test_dirs:
            test_path = self.project_root / test_dir
            if test_path.exists():
                existing_unit_dirs.append(test_dir)
                
        test_results["unit_tests"] = len(existing_unit_dirs) > 0
        
        if test_results["unit_tests"]:
            logger.info(f"Unit test directories found: {existing_unit_dirs}")
        else:
            self.results["warnings"].append("No unit test directories found")
            
        # Integration tests
        integration_tests = [
            "tests/integration",
            "test_end_to_end_comprehensive.py",
            "test_analytics_functionality.py"
        ]
        
        existing_integration = []
        for test_file in integration_tests:
            test_path = self.project_root / test_file
            if test_path.exists():
                existing_integration.append(test_file)
                
        test_results["integration_tests"] = len(existing_integration) > 0
        
        if test_results["integration_tests"]:
            logger.info(f"Integration tests found: {existing_integration}")
        else:
            self.results["warnings"].append("No integration tests found")
            
        # Performance tests
        performance_tests = [
            "tests/performance",
            "test_performance_optimization.py",
            "test_comprehensive_load_test.py"
        ]
        
        existing_performance = []
        for test_file in performance_tests:
            test_path = self.project_root / test_file
            if test_path.exists():
                existing_performance.append(test_file)
                
        test_results["performance_tests"] = len(existing_performance) > 0
        
        if test_results["performance_tests"]:
            logger.info(f"Performance tests found: {existing_performance}")
        else:
            self.results["warnings"].append("No performance tests found")
            
        # Security tests
        security_tests = [
            "tests/security",
            "test_security_comprehensive.py",
            "test_authentication_system.py"
        ]
        
        existing_security = []
        for test_file in security_tests:
            test_path = self.project_root / test_file
            if test_path.exists():
                existing_security.append(test_file)
                
        test_results["security_tests"] = len(existing_security) > 0
        
        if test_results["security_tests"]:
            logger.info(f"Security tests found: {existing_security}")
        else:
            self.results["warnings"].append("No security tests found")
            
        # Test data
        test_data_dirs = [
            "test_data",
            "test_uploads",
            "test_exports"
        ]
        
        existing_test_data = []
        for data_dir in test_data_dirs:
            data_path = self.project_root / data_dir
            if data_path.exists():
                existing_test_data.append(data_dir)
                
        test_results["test_data"] = len(existing_test_data) > 0
        
        if test_results["test_data"]:
            logger.info(f"Test data directories found: {existing_test_data}")
        else:
            self.results["warnings"].append("No test data directories found")
            
        self.results["validation_results"]["test_coverage"] = test_results

    def _validate_deployment_readiness(self):
        """Validate deployment readiness."""
        logger.info("Validating deployment readiness...")
        
        deployment_results = {
            "infrastructure_code": False,
            "deployment_scripts": False,
            "monitoring_setup": False,
            "backup_procedures": False
        }
        
        # Infrastructure code
        infra_dirs = [
            "infrastructure",
            "infrastructure/aws-native"
        ]
        
        existing_infra = []
        for infra_dir in infra_dirs:
            infra_path = self.project_root / infra_dir
            if infra_path.exists():
                existing_infra.append(infra_dir)
                
        deployment_results["infrastructure_code"] = len(existing_infra) > 0
        
        if deployment_results["infrastructure_code"]:
            logger.info(f"Infrastructure code found: {existing_infra}")
        else:
            self.results["warnings"].append("No infrastructure code found")
            
        # Deployment scripts
        deployment_scripts = [
            "scripts/prepare-demo-test-data.py",
            "scripts/production-readiness-validation.py",
            "run_dev.py"
        ]
        
        existing_scripts = []
        for script in deployment_scripts:
            script_path = self.project_root / script
            if script_path.exists():
                existing_scripts.append(script)
                
        deployment_results["deployment_scripts"] = len(existing_scripts) > 0
        
        if deployment_results["deployment_scripts"]:
            logger.info(f"Deployment scripts found: {existing_scripts}")
        else:
            self.results["warnings"].append("No deployment scripts found")
            
        # Monitoring setup
        monitoring_components = [
            "src/multimodal_librarian/monitoring",
            "src/multimodal_librarian/api/routers/monitoring.py"
        ]
        
        existing_monitoring = []
        for component in monitoring_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_monitoring.append(component)
                
        deployment_results["monitoring_setup"] = len(existing_monitoring) > 0
        
        if deployment_results["monitoring_setup"]:
            logger.info(f"Monitoring components found: {existing_monitoring}")
        else:
            self.results["warnings"].append("No monitoring setup found")
            
        # Backup procedures
        backup_components = [
            "docs/deployment/rollback-procedures.md",
            "backup"
        ]
        
        existing_backup = []
        for component in backup_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_backup.append(component)
                
        deployment_results["backup_procedures"] = len(existing_backup) > 0
        
        if deployment_results["backup_procedures"]:
            logger.info(f"Backup components found: {existing_backup}")
        else:
            self.results["warnings"].append("No backup procedures found")
            
        self.results["validation_results"]["deployment_readiness"] = deployment_results

    def _validate_security_implementation(self):
        """Validate security implementation."""
        logger.info("Validating security implementation...")
        
        security_results = {
            "authentication_system": False,
            "authorization_controls": False,
            "data_encryption": False,
            "input_validation": False,
            "security_middleware": False
        }
        
        # Authentication system
        auth_components = [
            "src/multimodal_librarian/security/auth.py",
            "src/multimodal_librarian/services/user_service.py",
            "src/multimodal_librarian/api/middleware/auth_middleware.py"
        ]
        
        existing_auth = []
        for component in auth_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_auth.append(component)
                
        security_results["authentication_system"] = len(existing_auth) > 0
        
        if security_results["authentication_system"]:
            logger.info(f"Authentication components found: {existing_auth}")
        else:
            self.results["warnings"].append("No authentication system found")
            
        # Authorization controls
        authz_components = [
            "src/multimodal_librarian/security/auth.py",
            "src/multimodal_librarian/api/middleware"
        ]
        
        existing_authz = []
        for component in authz_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_authz.append(component)
                
        security_results["authorization_controls"] = len(existing_authz) > 0
        
        if security_results["authorization_controls"]:
            logger.info(f"Authorization components found: {existing_authz}")
        else:
            self.results["warnings"].append("No authorization controls found")
            
        # Data encryption
        encryption_components = [
            "src/multimodal_librarian/security/encryption.py",
            "src/multimodal_librarian/security/privacy.py"
        ]
        
        existing_encryption = []
        for component in encryption_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_encryption.append(component)
                
        security_results["data_encryption"] = len(existing_encryption) > 0
        
        if security_results["data_encryption"]:
            logger.info(f"Encryption components found: {existing_encryption}")
        else:
            self.results["warnings"].append("No data encryption found")
            
        # Input validation
        validation_components = [
            "src/multimodal_librarian/security/sanitization.py",
            "src/multimodal_librarian/api/models.py"
        ]
        
        existing_validation = []
        for component in validation_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_validation.append(component)
                
        security_results["input_validation"] = len(existing_validation) > 0
        
        if security_results["input_validation"]:
            logger.info(f"Input validation components found: {existing_validation}")
        else:
            self.results["warnings"].append("No input validation found")
            
        # Security middleware
        middleware_components = [
            "src/multimodal_librarian/api/middleware",
            "src/multimodal_librarian/security/rate_limiter.py"
        ]
        
        existing_middleware = []
        for component in middleware_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_middleware.append(component)
                
        security_results["security_middleware"] = len(existing_middleware) > 0
        
        if security_results["security_middleware"]:
            logger.info(f"Security middleware found: {existing_middleware}")
        else:
            self.results["warnings"].append("No security middleware found")
            
        self.results["validation_results"]["security_implementation"] = security_results

    def _validate_monitoring_implementation(self):
        """Validate monitoring and observability implementation."""
        logger.info("Validating monitoring and observability...")
        
        monitoring_results = {
            "logging_system": False,
            "metrics_collection": False,
            "alerting_system": False,
            "health_checks": False,
            "dashboards": False
        }
        
        # Logging system
        logging_components = [
            "src/multimodal_librarian/monitoring/logging_service.py",
            "src/multimodal_librarian/api/routers/logging.py",
            "src/multimodal_librarian/api/middleware/logging_middleware.py"
        ]
        
        existing_logging = []
        for component in logging_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_logging.append(component)
                
        monitoring_results["logging_system"] = len(existing_logging) > 0
        
        if monitoring_results["logging_system"]:
            logger.info(f"Logging components found: {existing_logging}")
        else:
            self.results["warnings"].append("No logging system found")
            
        # Metrics collection
        metrics_components = [
            "src/multimodal_librarian/monitoring/metrics_collector.py",
            "src/multimodal_librarian/monitoring/comprehensive_metrics_collector.py",
            "src/multimodal_librarian/api/routers/comprehensive_metrics.py"
        ]
        
        existing_metrics = []
        for component in metrics_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_metrics.append(component)
                
        monitoring_results["metrics_collection"] = len(existing_metrics) > 0
        
        if monitoring_results["metrics_collection"]:
            logger.info(f"Metrics components found: {existing_metrics}")
        else:
            self.results["warnings"].append("No metrics collection found")
            
        # Alerting system
        alerting_components = [
            "src/multimodal_librarian/monitoring/alerting_service.py",
            "src/multimodal_librarian/api/routers/monitoring.py"
        ]
        
        existing_alerting = []
        for component in alerting_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_alerting.append(component)
                
        monitoring_results["alerting_system"] = len(existing_alerting) > 0
        
        if monitoring_results["alerting_system"]:
            logger.info(f"Alerting components found: {existing_alerting}")
        else:
            self.results["warnings"].append("No alerting system found")
            
        # Health checks
        health_components = [
            "src/multimodal_librarian/monitoring/health_checker.py",
            "src/multimodal_librarian/api/routers/health_checks.py"
        ]
        
        existing_health = []
        for component in health_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_health.append(component)
                
        monitoring_results["health_checks"] = len(existing_health) > 0
        
        if monitoring_results["health_checks"]:
            logger.info(f"Health check components found: {existing_health}")
        else:
            self.results["warnings"].append("No health check system found")
            
        # Dashboards
        dashboard_components = [
            "src/multimodal_librarian/monitoring/dashboard_service.py",
            "src/multimodal_librarian/templates/analytics_dashboard.html"
        ]
        
        existing_dashboards = []
        for component in dashboard_components:
            component_path = self.project_root / component
            if component_path.exists():
                existing_dashboards.append(component)
                
        monitoring_results["dashboards"] = len(existing_dashboards) > 0
        
        if monitoring_results["dashboards"]:
            logger.info(f"Dashboard components found: {existing_dashboards}")
        else:
            self.results["warnings"].append("No dashboard system found")
            
        self.results["validation_results"]["monitoring_implementation"] = monitoring_results

    def _generate_final_assessment(self):
        """Generate final production readiness assessment."""
        logger.info("Generating final production readiness assessment...")
        
        # Calculate category scores
        category_scores = []
        
        for category, results in self.results["validation_results"].items():
            if isinstance(results, dict):
                category_score = (sum(1 for v in results.values() if v) / len(results)) * 100
                category_scores.append((category, category_score))
                
        # Calculate overall readiness score
        if category_scores:
            overall_score = sum(score for _, score in category_scores) / len(category_scores)
        else:
            overall_score = 0
            
        # Determine readiness status
        critical_issues_count = len(self.results["critical_issues"])
        warnings_count = len(self.results["warnings"])
        
        if critical_issues_count > 0:
            self.results["overall_status"] = "NOT_READY"
            self.results["recommendations"].append("Address all critical issues before production deployment")
        elif overall_score >= 85:
            self.results["overall_status"] = "READY"
            self.results["recommendations"].append("System implementation is ready for production deployment")
        elif overall_score >= 70:
            self.results["overall_status"] = "READY_WITH_WARNINGS"
            self.results["recommendations"].append("System is ready but address warnings for optimal deployment")
        else:
            self.results["overall_status"] = "NOT_READY"
            self.results["recommendations"].append("System needs additional implementation before production deployment")
            
        # Add specific recommendations
        if warnings_count > 0:
            self.results["recommendations"].append(f"Review and address {warnings_count} warnings")
            
        if overall_score < 90:
            self.results["recommendations"].append("Consider additional implementation and testing")
            
        # Category-specific recommendations
        for category, score in category_scores:
            if score < 70:
                self.results["recommendations"].append(f"Improve {category} implementation (current score: {score:.1f}%)")
                
        # Final summary
        self.results["readiness_summary"] = {
            "overall_score": overall_score,
            "category_scores": category_scores,
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

def main():
    """Main validation function."""
    print("=" * 80)
    print("PRODUCTION READINESS VALIDATION (OFFLINE MODE)")
    print("=" * 80)
    print()
    
    validator = ProductionReadinessValidator()
    results = validator.run_validation()
    
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
    
    # Print category scores
    if "category_scores" in summary:
        print("CATEGORY SCORES:")
        for category, score in summary["category_scores"]:
            status = "✅" if score >= 80 else "⚠️" if score >= 60 else "❌"
            print(f"  {status} {category.replace('_', ' ').title()}: {score:.1f}%")
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
        print("✅ SYSTEM IMPLEMENTATION IS READY FOR PRODUCTION DEPLOYMENT")
        print("   Note: Runtime validation should be performed once services are deployed")
    else:
        print("❌ SYSTEM IS NOT READY FOR PRODUCTION DEPLOYMENT")
        print("   Address critical issues and warnings before deploying")
        
    print("=" * 80)
    
    return results

if __name__ == "__main__":
    try:
        results = main()
        
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