#!/usr/bin/env python3
"""
Production Deployment Checklist Validation Test

This script validates the production deployment checklist system by:
1. Testing all validation components
2. Verifying integration with existing fix scripts
3. Validating against current task-definition-update.json format
4. Checking remediation guidance references correct script paths
"""

import os
import sys
import json
import boto3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add the validation module to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from multimodal_librarian.validation.checklist_validator import ChecklistValidator
    from multimodal_librarian.validation.iam_permissions_validator import IAMPermissionsValidator
    from multimodal_librarian.validation.storage_config_validator import StorageConfigValidator
    from multimodal_librarian.validation.ssl_config_validator import SSLConfigValidator
    from multimodal_librarian.validation.fix_script_manager import FixScriptManager
    from multimodal_librarian.validation.models import DeploymentConfig, ValidationResult, ValidationStatus
    from multimodal_librarian.validation.cli import main as cli_main
except ImportError as e:
    print(f"❌ Failed to import validation modules: {e}")
    print("Make sure the validation system is properly installed")
    sys.exit(1)

class ProductionDeploymentChecklistTester:
    """Comprehensive tester for the production deployment checklist system."""
    
    def __init__(self):
        self.test_results = {
            'timestamp': datetime.now().isoformat(),
            'test_name': 'production_deployment_checklist_validation',
            'tests': {},
            'overall_success': False,
            'summary': {}
        }
        
        # Test configuration
        self.test_config = {
            'task_definition_arn': 'arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:1',
            'iam_role_arn': 'arn:aws:iam::591222106065:role/ecsTaskRole',
            'load_balancer_arn': 'arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-librarian-full-ml/test',
            'target_environment': 'production',
            'ssl_certificate_arn': None
        }
        
        # Expected fix script paths
        self.expected_scripts = {
            'iam_fix_scripts': [
                'scripts/fix-iam-secrets-permissions.py',
                'scripts/fix-iam-secrets-permissions-correct.py'
            ],
            'ssl_fix_scripts': [
                'scripts/add-https-ssl-support.py'
            ],
            'storage_fix_scripts': [
                'task-definition-update.json'
            ]
        }
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all validation tests."""
        print("🧪 Production Deployment Checklist Validation")
        print("=" * 60)
        
        # Test 1: Validate fix script existence and structure
        self.test_fix_script_existence()
        
        # Test 2: Validate task definition format
        self.test_task_definition_format()
        
        # Test 3: Test individual validators
        self.test_individual_validators()
        
        # Test 4: Test fix script manager
        self.test_fix_script_manager()
        
        # Test 5: Test checklist validator orchestration
        self.test_checklist_validator()
        
        # Test 6: Test CLI interface
        self.test_cli_interface()
        
        # Test 7: Test remediation guidance
        self.test_remediation_guidance()
        
        # Calculate overall results
        self._calculate_overall_results()
        
        return self.test_results
    
    def test_fix_script_existence(self):
        """Test that all referenced fix scripts exist and are accessible."""
        print("\n1. Fix Script Existence Validation")
        print("-" * 40)
        
        test_result = {
            'test_name': 'fix_script_existence',
            'success': True,
            'details': {},
            'errors': []
        }
        
        for script_type, scripts in self.expected_scripts.items():
            for script_path in scripts:
                if os.path.exists(script_path):
                    print(f"   ✅ {script_path} exists")
                    test_result['details'][script_path] = {'exists': True, 'readable': os.access(script_path, os.R_OK)}
                else:
                    print(f"   ❌ {script_path} not found")
                    test_result['success'] = False
                    test_result['errors'].append(f"Missing script: {script_path}")
                    test_result['details'][script_path] = {'exists': False, 'readable': False}
        
        self.test_results['tests']['fix_script_existence'] = test_result
    
    def test_task_definition_format(self):
        """Test that task-definition-update.json has the correct format."""
        print("\n2. Task Definition Format Validation")
        print("-" * 40)
        
        test_result = {
            'test_name': 'task_definition_format',
            'success': True,
            'details': {},
            'errors': []
        }
        
        try:
            with open('task-definition-update.json', 'r') as f:
                task_def = json.load(f)
            
            # Check required fields
            required_fields = ['family', 'taskRoleArn', 'executionRoleArn', 'cpu', 'memory', 'ephemeralStorage']
            for field in required_fields:
                if field in task_def:
                    print(f"   ✅ {field} field present")
                    test_result['details'][field] = {'present': True, 'value': task_def.get(field)}
                else:
                    print(f"   ❌ {field} field missing")
                    test_result['success'] = False
                    test_result['errors'].append(f"Missing field: {field}")
                    test_result['details'][field] = {'present': False}
            
            # Check ephemeral storage configuration
            if 'ephemeralStorage' in task_def:
                storage_size = task_def['ephemeralStorage'].get('sizeInGiB', 0)
                if storage_size >= 30:
                    print(f"   ✅ Ephemeral storage ({storage_size}GB) meets minimum requirement")
                    test_result['details']['ephemeral_storage_adequate'] = True
                else:
                    print(f"   ❌ Ephemeral storage ({storage_size}GB) below minimum 30GB")
                    test_result['success'] = False
                    test_result['errors'].append(f"Insufficient ephemeral storage: {storage_size}GB < 30GB")
                    test_result['details']['ephemeral_storage_adequate'] = False
            
        except FileNotFoundError:
            print("   ❌ task-definition-update.json not found")
            test_result['success'] = False
            test_result['errors'].append("task-definition-update.json file not found")
        except json.JSONDecodeError as e:
            print(f"   ❌ Invalid JSON format: {e}")
            test_result['success'] = False
            test_result['errors'].append(f"JSON decode error: {e}")
        
        self.test_results['tests']['task_definition_format'] = test_result
    
    def test_individual_validators(self):
        """Test each validator component individually."""
        print("\n3. Individual Validator Testing")
        print("-" * 40)
        
        test_result = {
            'test_name': 'individual_validators',
            'success': True,
            'details': {},
            'errors': []
        }
        
        # Test IAM Permissions Validator
        try:
            iam_validator = IAMPermissionsValidator()
            print("   ✅ IAMPermissionsValidator instantiated successfully")
            test_result['details']['iam_validator'] = {'instantiated': True}
            
            # Test required permissions list
            required_perms = iam_validator.get_required_permissions()
            if 'secretsmanager:GetSecretValue' in required_perms:
                print("   ✅ Required permissions include secretsmanager:GetSecretValue")
                test_result['details']['iam_validator']['required_permissions'] = True
            else:
                print("   ❌ Missing secretsmanager:GetSecretValue in required permissions")
                test_result['success'] = False
                test_result['errors'].append("Missing required permission: secretsmanager:GetSecretValue")
                test_result['details']['iam_validator']['required_permissions'] = False
                
        except Exception as e:
            print(f"   ❌ IAMPermissionsValidator failed: {e}")
            test_result['success'] = False
            test_result['errors'].append(f"IAMPermissionsValidator error: {e}")
            test_result['details']['iam_validator'] = {'instantiated': False, 'error': str(e)}
        
        # Test Storage Config Validator
        try:
            storage_validator = StorageConfigValidator()
            print("   ✅ StorageConfigValidator instantiated successfully")
            test_result['details']['storage_validator'] = {'instantiated': True}
            
            # Test minimum storage requirement
            min_storage = storage_validator.get_minimum_storage_requirement()
            if min_storage == 30:
                print("   ✅ Minimum storage requirement is 30GB")
                test_result['details']['storage_validator']['min_storage_correct'] = True
            else:
                print(f"   ❌ Incorrect minimum storage requirement: {min_storage}GB (expected 30GB)")
                test_result['success'] = False
                test_result['errors'].append(f"Incorrect minimum storage: {min_storage}GB")
                test_result['details']['storage_validator']['min_storage_correct'] = False
                
        except Exception as e:
            print(f"   ❌ StorageConfigValidator failed: {e}")
            test_result['success'] = False
            test_result['errors'].append(f"StorageConfigValidator error: {e}")
            test_result['details']['storage_validator'] = {'instantiated': False, 'error': str(e)}
        
        # Test SSL Config Validator
        try:
            ssl_validator = SSLConfigValidator()
            print("   ✅ SSLConfigValidator instantiated successfully")
            test_result['details']['ssl_validator'] = {'instantiated': True}
            
        except Exception as e:
            print(f"   ❌ SSLConfigValidator failed: {e}")
            test_result['success'] = False
            test_result['errors'].append(f"SSLConfigValidator error: {e}")
            test_result['details']['ssl_validator'] = {'instantiated': False, 'error': str(e)}
        
        self.test_results['tests']['individual_validators'] = test_result
    
    def test_fix_script_manager(self):
        """Test the fix script manager functionality."""
        print("\n4. Fix Script Manager Testing")
        print("-" * 40)
        
        test_result = {
            'test_name': 'fix_script_manager',
            'success': True,
            'details': {},
            'errors': []
        }
        
        try:
            fix_manager = FixScriptManager()
            print("   ✅ FixScriptManager instantiated successfully")
            test_result['details']['instantiated'] = True
            
            # Test IAM fix scripts
            iam_scripts = fix_manager.get_iam_fix_scripts()
            expected_iam_scripts = ['scripts/fix-iam-secrets-permissions.py', 'scripts/fix-iam-secrets-permissions-correct.py']
            
            for script in expected_iam_scripts:
                if any(script in ref.script_path for ref in iam_scripts):
                    print(f"   ✅ IAM fix script reference found: {script}")
                    test_result['details'][f'iam_script_{script}'] = True
                else:
                    print(f"   ❌ IAM fix script reference missing: {script}")
                    test_result['success'] = False
                    test_result['errors'].append(f"Missing IAM script reference: {script}")
                    test_result['details'][f'iam_script_{script}'] = False
            
            # Test SSL fix scripts
            ssl_scripts = fix_manager.get_ssl_fix_scripts()
            if any('add-https-ssl-support.py' in ref.script_path for ref in ssl_scripts):
                print("   ✅ SSL fix script reference found: add-https-ssl-support.py")
                test_result['details']['ssl_script_reference'] = True
            else:
                print("   ❌ SSL fix script reference missing: add-https-ssl-support.py")
                test_result['success'] = False
                test_result['errors'].append("Missing SSL script reference: add-https-ssl-support.py")
                test_result['details']['ssl_script_reference'] = False
            
            # Test storage fix scripts
            storage_scripts = fix_manager.get_storage_fix_scripts()
            if any('task-definition-update.json' in ref.script_path for ref in storage_scripts):
                print("   ✅ Storage fix script reference found: task-definition-update.json")
                test_result['details']['storage_script_reference'] = True
            else:
                print("   ❌ Storage fix script reference missing: task-definition-update.json")
                test_result['success'] = False
                test_result['errors'].append("Missing storage script reference: task-definition-update.json")
                test_result['details']['storage_script_reference'] = False
            
        except Exception as e:
            print(f"   ❌ FixScriptManager failed: {e}")
            test_result['success'] = False
            test_result['errors'].append(f"FixScriptManager error: {e}")
            test_result['details']['instantiated'] = False
        
        self.test_results['tests']['fix_script_manager'] = test_result
    
    def test_checklist_validator(self):
        """Test the main checklist validator orchestration."""
        print("\n5. Checklist Validator Orchestration Testing")
        print("-" * 40)
        
        test_result = {
            'test_name': 'checklist_validator',
            'success': True,
            'details': {},
            'errors': []
        }
        
        try:
            checklist_validator = ChecklistValidator()
            print("   ✅ ChecklistValidator instantiated successfully")
            test_result['details']['instantiated'] = True
            
            # Create test deployment config
            deployment_config = DeploymentConfig(
                task_definition_arn=self.test_config['task_definition_arn'],
                iam_role_arn=self.test_config['iam_role_arn'],
                load_balancer_arn=self.test_config['load_balancer_arn'],
                target_environment=self.test_config['target_environment'],
                ssl_certificate_arn=self.test_config['ssl_certificate_arn']
            )
            
            print("   ✅ Test deployment config created")
            test_result['details']['deployment_config_created'] = True
            
            # Note: We won't run actual validation against AWS resources in this test
            # as it requires valid AWS credentials and resources
            print("   ℹ️  Skipping actual AWS validation (requires live resources)")
            test_result['details']['aws_validation_skipped'] = True
            
        except Exception as e:
            print(f"   ❌ ChecklistValidator failed: {e}")
            test_result['success'] = False
            test_result['errors'].append(f"ChecklistValidator error: {e}")
            test_result['details']['instantiated'] = False
        
        self.test_results['tests']['checklist_validator'] = test_result
    
    def test_cli_interface(self):
        """Test the CLI interface functionality."""
        print("\n6. CLI Interface Testing")
        print("-" * 40)
        
        test_result = {
            'test_name': 'cli_interface',
            'success': True,
            'details': {},
            'errors': []
        }
        
        try:
            # Test CLI help functionality
            import subprocess
            result = subprocess.run([
                sys.executable, '-m', 'multimodal_librarian.validation.cli', '--help'
            ], capture_output=True, text=True, cwd='src')
            
            if result.returncode == 0:
                print("   ✅ CLI help command works")
                test_result['details']['help_command'] = True
            else:
                print(f"   ❌ CLI help command failed: {result.stderr}")
                test_result['success'] = False
                test_result['errors'].append(f"CLI help failed: {result.stderr}")
                test_result['details']['help_command'] = False
            
        except Exception as e:
            print(f"   ❌ CLI interface test failed: {e}")
            test_result['success'] = False
            test_result['errors'].append(f"CLI interface error: {e}")
            test_result['details']['help_command'] = False
        
        self.test_results['tests']['cli_interface'] = test_result
    
    def test_remediation_guidance(self):
        """Test that remediation guidance references correct script paths."""
        print("\n7. Remediation Guidance Testing")
        print("-" * 40)
        
        test_result = {
            'test_name': 'remediation_guidance',
            'success': True,
            'details': {},
            'errors': []
        }
        
        try:
            fix_manager = FixScriptManager()
            
            # Test remediation guide generation
            failed_checks = ['iam_permissions', 'storage_configuration', 'ssl_configuration']
            remediation_guide = fix_manager.generate_remediation_guide(failed_checks)
            
            print("   ✅ Remediation guide generated successfully")
            test_result['details']['guide_generated'] = True
            
            # Check that guide contains script references
            script_paths = [ref.script_path for ref in remediation_guide.script_references]
            
            expected_references = [
                'fix-iam-secrets-permissions',
                'task-definition-update.json',
                'add-https-ssl-support'
            ]
            
            for reference in expected_references:
                if any(reference in path for path in script_paths):
                    print(f"   ✅ Remediation guide contains reference to: {reference}")
                    test_result['details'][f'reference_{reference}'] = True
                else:
                    print(f"   ❌ Remediation guide missing reference to: {reference}")
                    test_result['success'] = False
                    test_result['errors'].append(f"Missing reference: {reference}")
                    test_result['details'][f'reference_{reference}'] = False
            
        except Exception as e:
            print(f"   ❌ Remediation guidance test failed: {e}")
            test_result['success'] = False
            test_result['errors'].append(f"Remediation guidance error: {e}")
            test_result['details']['guide_generated'] = False
        
        self.test_results['tests']['remediation_guidance'] = test_result
    
    def _calculate_overall_results(self):
        """Calculate overall test results and summary."""
        total_tests = len(self.test_results['tests'])
        passed_tests = sum(1 for test in self.test_results['tests'].values() if test['success'])
        failed_tests = total_tests - passed_tests
        
        self.test_results['overall_success'] = failed_tests == 0
        self.test_results['summary'] = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0
        }
        
        print(f"\n📊 Test Summary")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {self.test_results['summary']['success_rate']:.1f}%")
        
        if self.test_results['overall_success']:
            print("\n🎉 All tests passed! Production deployment checklist system is ready.")
        else:
            print("\n⚠️  Some tests failed. Please review the issues above.")
            
            # List all errors
            print("\n❌ Errors found:")
            for test_name, test_data in self.test_results['tests'].items():
                if not test_data['success']:
                    print(f"   {test_name}:")
                    for error in test_data['errors']:
                        print(f"     - {error}")

def main():
    """Run the production deployment checklist validation."""
    tester = ProductionDeploymentChecklistTester()
    results = tester.run_all_tests()
    
    # Save results to file
    results_file = f"production-deployment-checklist-test-results-{int(datetime.now().timestamp())}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Test results saved to: {results_file}")
    
    return results['overall_success']

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)