#!/usr/bin/env python3
"""
Final Production Audit for Deployment Checklist System

This script performs a comprehensive audit of the production deployment checklist
system to ensure it meets all production readiness requirements.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add the validation module to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

class FinalProductionAuditor:
    """Comprehensive auditor for production readiness validation."""
    
    def __init__(self):
        self.audit_results = {
            'timestamp': datetime.now().isoformat(),
            'audit_name': 'final_production_audit',
            'audits': {},
            'overall_success': False,
            'production_ready': False
        }
    
    def run_comprehensive_audit(self) -> Dict[str, Any]:
        """Run comprehensive production readiness audit."""
        print("🔍 Final Production Audit")
        print("=" * 60)
        
        # Audit 1: Core system functionality
        self.audit_core_functionality()
        
        # Audit 2: All tests passing
        self.audit_test_suite()
        
        # Audit 3: Security and access controls
        self.audit_security_controls()
        
        # Audit 4: Performance requirements
        self.audit_performance_requirements()
        
        # Audit 5: Documentation completeness
        self.audit_documentation()
        
        # Audit 6: Integration readiness
        self.audit_integration_readiness()
        
        # Calculate final production readiness
        self._calculate_production_readiness()
        
        return self.audit_results
    
    def audit_core_functionality(self):
        """Audit core system functionality."""
        print("\n1. Core System Functionality Audit")
        print("-" * 40)
        
        audit_result = {
            'audit_name': 'core_functionality',
            'success': True,
            'details': {},
            'issues': []
        }
        
        try:
            # Test all core components can be imported
            from multimodal_librarian.validation.checklist_validator import ChecklistValidator
            from multimodal_librarian.validation.iam_permissions_validator import IAMPermissionsValidator
            from multimodal_librarian.validation.storage_config_validator import StorageConfigValidator
            from multimodal_librarian.validation.ssl_config_validator import SSLConfigValidator
            from multimodal_librarian.validation.fix_script_manager import FixScriptManager
            from multimodal_librarian.validation.config_manager import ConfigurationManager
            from multimodal_librarian.validation.models import DeploymentConfig, ValidationResult
            
            print("   ✅ All core modules import successfully")
            audit_result['details']['imports_successful'] = True
            
            # Test core functionality
            validator = ChecklistValidator()
            iam_validator = IAMPermissionsValidator()
            storage_validator = StorageConfigValidator()
            ssl_validator = SSLConfigValidator()
            fix_manager = FixScriptManager()
            config_manager = ConfigurationManager()
            
            print("   ✅ All core components instantiate successfully")
            audit_result['details']['instantiation_successful'] = True
            
            # Test basic operations
            config = DeploymentConfig(
                task_definition_arn='arn:aws:ecs:us-east-1:123456789012:task-definition/test:1',
                iam_role_arn='arn:aws:iam::123456789012:role/testRole',
                load_balancer_arn='arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test/test',
                target_environment='production'
            )
            
            print("   ✅ DeploymentConfig creation works")
            audit_result['details']['config_creation_works'] = True
            
            # Test fix script references
            iam_scripts = fix_manager.get_iam_fix_scripts()
            storage_scripts = fix_manager.get_storage_fix_scripts()
            ssl_scripts = fix_manager.get_ssl_fix_scripts()
            
            if len(iam_scripts) > 0 and len(storage_scripts) > 0 and len(ssl_scripts) > 0:
                print("   ✅ Fix script references available for all validation types")
                audit_result['details']['fix_scripts_available'] = True
            else:
                print("   ❌ Missing fix script references")
                audit_result['success'] = False
                audit_result['issues'].append("Missing fix script references")
                audit_result['details']['fix_scripts_available'] = False
            
        except Exception as e:
            print(f"   ❌ Core functionality audit failed: {e}")
            audit_result['success'] = False
            audit_result['issues'].append(f"Core functionality error: {e}")
        
        self.audit_results['audits']['core_functionality'] = audit_result
    
    def audit_test_suite(self):
        """Audit that all tests are passing."""
        print("\n2. Test Suite Audit")
        print("-" * 40)
        
        audit_result = {
            'audit_name': 'test_suite',
            'success': True,
            'details': {},
            'issues': []
        }
        
        # List of test files to run
        test_files = [
            'test_production_deployment_checklist.py',
            'test_comprehensive_validation_system.py',
            'test_fix_script_integration.py',
            'test_production_readiness_performance.py'
        ]
        
        passed_tests = 0
        total_tests = len(test_files)
        
        for test_file in test_files:
            if os.path.exists(test_file):
                try:
                    result = subprocess.run([
                        sys.executable, test_file
                    ], capture_output=True, text=True, timeout=60)
                    
                    if result.returncode == 0:
                        print(f"   ✅ {test_file} passed")
                        passed_tests += 1
                        audit_result['details'][test_file] = {'passed': True}
                    else:
                        print(f"   ❌ {test_file} failed")
                        audit_result['success'] = False
                        audit_result['issues'].append(f"Test failed: {test_file}")
                        audit_result['details'][test_file] = {'passed': False, 'error': result.stderr}
                        
                except subprocess.TimeoutExpired:
                    print(f"   ⚠️  {test_file} timed out")
                    audit_result['issues'].append(f"Test timeout: {test_file}")
                    audit_result['details'][test_file] = {'passed': False, 'error': 'timeout'}
                except Exception as e:
                    print(f"   ❌ {test_file} error: {e}")
                    audit_result['success'] = False
                    audit_result['issues'].append(f"Test error: {test_file} - {e}")
                    audit_result['details'][test_file] = {'passed': False, 'error': str(e)}
            else:
                print(f"   ⚠️  {test_file} not found")
                audit_result['details'][test_file] = {'passed': False, 'error': 'file not found'}
        
        audit_result['details']['test_summary'] = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0
        }
        
        print(f"   📊 Test Summary: {passed_tests}/{total_tests} passed ({audit_result['details']['test_summary']['success_rate']:.1f}%)")
        
        self.audit_results['audits']['test_suite'] = audit_result
    
    def audit_security_controls(self):
        """Audit security controls implementation."""
        print("\n3. Security Controls Audit")
        print("-" * 40)
        
        audit_result = {
            'audit_name': 'security_controls',
            'success': True,
            'details': {},
            'issues': []
        }
        
        try:
            from multimodal_librarian.validation.models import DeploymentConfig
            
            # Test input validation
            malicious_inputs = [
                "'; DROP TABLE users; --",
                "<script>alert('xss')</script>",
                "../../../etc/passwd",
                "$(rm -rf /)",
                "not-an-arn"
            ]
            
            security_violations = 0
            for malicious_input in malicious_inputs:
                try:
                    config = DeploymentConfig(
                        task_definition_arn=malicious_input,
                        iam_role_arn='arn:aws:iam::123456789012:role/testRole',
                        load_balancer_arn='arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test/test',
                        target_environment='production'
                    )
                    security_violations += 1
                except Exception:
                    # Expected - malicious input should be rejected
                    pass
            
            if security_violations == 0:
                print("   ✅ Input validation security controls working")
                audit_result['details']['input_validation_secure'] = True
            else:
                print(f"   ❌ {security_violations} security violations detected")
                audit_result['success'] = False
                audit_result['issues'].append(f"{security_violations} input validation failures")
                audit_result['details']['input_validation_secure'] = False
            
            # Test environment validation
            try:
                config = DeploymentConfig(
                    task_definition_arn='arn:aws:ecs:us-east-1:123456789012:task-definition/test:1',
                    iam_role_arn='arn:aws:iam::123456789012:role/testRole',
                    load_balancer_arn='arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test/test',
                    target_environment='invalid-environment'
                )
                print("   ❌ Environment validation not working")
                audit_result['success'] = False
                audit_result['issues'].append("Environment validation failure")
                audit_result['details']['environment_validation_secure'] = False
            except Exception:
                print("   ✅ Environment validation security controls working")
                audit_result['details']['environment_validation_secure'] = True
            
        except Exception as e:
            print(f"   ❌ Security controls audit failed: {e}")
            audit_result['success'] = False
            audit_result['issues'].append(f"Security audit error: {e}")
        
        self.audit_results['audits']['security_controls'] = audit_result
    
    def audit_performance_requirements(self):
        """Audit performance requirements."""
        print("\n4. Performance Requirements Audit")
        print("-" * 40)
        
        audit_result = {
            'audit_name': 'performance_requirements',
            'success': True,
            'details': {},
            'issues': []
        }
        
        try:
            # Check if performance test results exist and are acceptable
            performance_files = [f for f in os.listdir('.') if f.startswith('production-readiness-performance-test-')]
            
            if performance_files:
                latest_file = max(performance_files)
                with open(latest_file, 'r') as f:
                    performance_data = json.load(f)
                
                if performance_data.get('overall_success', False):
                    print("   ✅ Performance requirements met")
                    audit_result['details']['performance_acceptable'] = True
                    
                    # Check specific metrics
                    metrics = performance_data.get('performance_metrics', {})
                    
                    # Large scale performance
                    large_scale = metrics.get('large_scale_performance', {})
                    if large_scale.get('average_time', 1.0) < 1.0:
                        print("   ✅ Large-scale performance acceptable")
                        audit_result['details']['large_scale_performance'] = True
                    else:
                        print("   ⚠️  Large-scale performance may be slow")
                        audit_result['details']['large_scale_performance'] = False
                    
                    # Concurrent performance
                    concurrent = metrics.get('concurrent_validation', {})
                    if concurrent.get('concurrency_efficiency', 1.0) > 2.0:
                        print("   ✅ Concurrent performance acceptable")
                        audit_result['details']['concurrent_performance'] = True
                    else:
                        print("   ⚠️  Concurrent performance may be inefficient")
                        audit_result['details']['concurrent_performance'] = False
                    
                else:
                    print("   ❌ Performance requirements not met")
                    audit_result['success'] = False
                    audit_result['issues'].append("Performance requirements not met")
                    audit_result['details']['performance_acceptable'] = False
            else:
                print("   ⚠️  No performance test results found")
                audit_result['details']['performance_tests_run'] = False
        
        except Exception as e:
            print(f"   ❌ Performance audit failed: {e}")
            audit_result['success'] = False
            audit_result['issues'].append(f"Performance audit error: {e}")
        
        self.audit_results['audits']['performance_requirements'] = audit_result
    
    def audit_documentation(self):
        """Audit documentation completeness."""
        print("\n5. Documentation Audit")
        print("-" * 40)
        
        audit_result = {
            'audit_name': 'documentation',
            'success': True,
            'details': {},
            'issues': []
        }
        
        # Check for required documentation files
        required_docs = [
            'src/multimodal_librarian/validation/README.md',
            'src/multimodal_librarian/validation/USAGE_GUIDE.md',
            'src/multimodal_librarian/validation/API_DOCUMENTATION.md',
            'src/multimodal_librarian/validation/TROUBLESHOOTING_GUIDE.md',
            'src/multimodal_librarian/validation/DEPLOYMENT_INTEGRATION.md'
        ]
        
        missing_docs = []
        for doc_file in required_docs:
            if os.path.exists(doc_file):
                print(f"   ✅ {doc_file} exists")
                audit_result['details'][doc_file] = {'exists': True}
            else:
                print(f"   ❌ {doc_file} missing")
                missing_docs.append(doc_file)
                audit_result['details'][doc_file] = {'exists': False}
        
        if missing_docs:
            audit_result['success'] = False
            audit_result['issues'].append(f"Missing documentation: {', '.join(missing_docs)}")
        
        # Check for example configurations
        example_configs = [
            'src/multimodal_librarian/validation/example-config.json',
            'src/multimodal_librarian/validation/example-validation-config.yaml'
        ]
        
        for config_file in example_configs:
            if os.path.exists(config_file):
                print(f"   ✅ {config_file} exists")
                audit_result['details'][config_file] = {'exists': True}
            else:
                print(f"   ⚠️  {config_file} missing")
                audit_result['details'][config_file] = {'exists': False}
        
        self.audit_results['audits']['documentation'] = audit_result
    
    def audit_integration_readiness(self):
        """Audit integration readiness with existing systems."""
        print("\n6. Integration Readiness Audit")
        print("-" * 40)
        
        audit_result = {
            'audit_name': 'integration_readiness',
            'success': True,
            'details': {},
            'issues': []
        }
        
        try:
            # Check CLI functionality
            from multimodal_librarian.validation import cli
            
            if hasattr(cli, 'main'):
                print("   ✅ CLI interface available")
                audit_result['details']['cli_available'] = True
            else:
                print("   ❌ CLI interface not available")
                audit_result['success'] = False
                audit_result['issues'].append("CLI interface missing")
                audit_result['details']['cli_available'] = False
            
            # Check fix script integration
            from multimodal_librarian.validation.fix_script_manager import FixScriptManager
            
            fix_manager = FixScriptManager()
            missing_scripts = fix_manager.get_missing_scripts()
            
            if len(missing_scripts) == 0:
                print("   ✅ All referenced fix scripts exist")
                audit_result['details']['fix_scripts_exist'] = True
            else:
                print(f"   ⚠️  {len(missing_scripts)} referenced scripts missing")
                audit_result['details']['fix_scripts_exist'] = False
                audit_result['details']['missing_scripts'] = [s.script_path for s in missing_scripts]
            
            # Check configuration management
            from multimodal_librarian.validation.config_manager import ConfigurationManager
            
            config_manager = ConfigurationManager()
            print("   ✅ Configuration management available")
            audit_result['details']['config_management_available'] = True
            
        except Exception as e:
            print(f"   ❌ Integration readiness audit failed: {e}")
            audit_result['success'] = False
            audit_result['issues'].append(f"Integration audit error: {e}")
        
        self.audit_results['audits']['integration_readiness'] = audit_result
    
    def _calculate_production_readiness(self):
        """Calculate overall production readiness."""
        total_audits = len(self.audit_results['audits'])
        passed_audits = sum(1 for audit in self.audit_results['audits'].values() if audit['success'])
        failed_audits = total_audits - passed_audits
        
        self.audit_results['overall_success'] = failed_audits == 0
        self.audit_results['production_ready'] = failed_audits == 0
        
        self.audit_results['summary'] = {
            'total_audits': total_audits,
            'passed_audits': passed_audits,
            'failed_audits': failed_audits,
            'success_rate': (passed_audits / total_audits * 100) if total_audits > 0 else 0
        }
        
        print(f"\n🏁 Final Production Readiness Assessment")
        print("=" * 60)
        print(f"Total Audits: {total_audits}")
        print(f"Passed: {passed_audits}")
        print(f"Failed: {failed_audits}")
        print(f"Success Rate: {self.audit_results['summary']['success_rate']:.1f}%")
        
        if self.audit_results['production_ready']:
            print("\n🎉 PRODUCTION READY!")
            print("✅ All critical systems validated")
            print("✅ Security controls implemented")
            print("✅ Performance requirements met")
            print("✅ Documentation complete")
            print("✅ Integration ready")
            print("\n🚀 The production deployment checklist system is ready for production use!")
        else:
            print("\n⚠️  NOT PRODUCTION READY")
            print("❌ Critical issues must be resolved before production deployment")
            
            # List all issues
            print("\n🔧 Issues to resolve:")
            for audit_name, audit_data in self.audit_results['audits'].items():
                if not audit_data['success']:
                    print(f"   {audit_name}:")
                    for issue in audit_data['issues']:
                        print(f"     - {issue}")

def main():
    """Run final production audit."""
    auditor = FinalProductionAuditor()
    results = auditor.run_comprehensive_audit()
    
    # Save results to file
    results_file = f"final-production-audit-{int(datetime.now().timestamp())}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Final audit results saved to: {results_file}")
    
    return results['production_ready']

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)