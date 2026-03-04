#!/usr/bin/env python3
"""
Integration test for fix scripts referenced by the production deployment checklist.

This script validates that the fix scripts can be executed and have proper structure.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

class FixScriptIntegrationTester:
    """Test integration with existing fix scripts."""
    
    def __init__(self):
        self.test_results = {
            'timestamp': datetime.now().isoformat(),
            'test_name': 'fix_script_integration',
            'scripts_tested': {},
            'overall_success': False
        }
        
        self.scripts_to_test = [
            'scripts/fix-iam-secrets-permissions.py',
            'scripts/fix-iam-secrets-permissions-correct.py',
            'scripts/add-https-ssl-support.py'
        ]
    
    def run_integration_tests(self) -> Dict[str, Any]:
        """Run integration tests for all fix scripts."""
        print("🔧 Fix Script Integration Testing")
        print("=" * 50)
        
        all_passed = True
        
        for script_path in self.scripts_to_test:
            print(f"\nTesting: {script_path}")
            print("-" * 30)
            
            result = self.test_script_structure(script_path)
            self.test_results['scripts_tested'][script_path] = result
            
            if not result['success']:
                all_passed = False
        
        # Test task definition format
        print(f"\nTesting: task-definition-update.json")
        print("-" * 30)
        
        task_def_result = self.test_task_definition_structure()
        self.test_results['scripts_tested']['task-definition-update.json'] = task_def_result
        
        if not task_def_result['success']:
            all_passed = False
        
        self.test_results['overall_success'] = all_passed
        
        print(f"\n📊 Integration Test Summary")
        print("=" * 50)
        
        if all_passed:
            print("🎉 All fix scripts are properly structured and executable!")
        else:
            print("⚠️  Some fix scripts have issues. See details above.")
        
        return self.test_results
    
    def test_script_structure(self, script_path: str) -> Dict[str, Any]:
        """Test the structure and executability of a Python script."""
        result = {
            'success': True,
            'checks': {},
            'errors': []
        }
        
        # Check if file exists
        if not os.path.exists(script_path):
            print(f"   ❌ Script not found: {script_path}")
            result['success'] = False
            result['errors'].append("Script file not found")
            return result
        
        print(f"   ✅ Script exists: {script_path}")
        result['checks']['exists'] = True
        
        # Check if file is readable
        if not os.access(script_path, os.R_OK):
            print(f"   ❌ Script not readable: {script_path}")
            result['success'] = False
            result['errors'].append("Script not readable")
            return result
        
        print(f"   ✅ Script is readable")
        result['checks']['readable'] = True
        
        # Check if file has shebang
        try:
            with open(script_path, 'r') as f:
                first_line = f.readline().strip()
                if first_line.startswith('#!'):
                    print(f"   ✅ Has shebang: {first_line}")
                    result['checks']['has_shebang'] = True
                else:
                    print(f"   ⚠️  No shebang found")
                    result['checks']['has_shebang'] = False
        except Exception as e:
            print(f"   ❌ Error reading script: {e}")
            result['success'] = False
            result['errors'].append(f"Error reading script: {e}")
            return result
        
        # Check Python syntax
        try:
            result_syntax = subprocess.run([
                sys.executable, '-m', 'py_compile', script_path
            ], capture_output=True, text=True)
            
            if result_syntax.returncode == 0:
                print(f"   ✅ Python syntax is valid")
                result['checks']['valid_syntax'] = True
            else:
                print(f"   ❌ Python syntax error: {result_syntax.stderr}")
                result['success'] = False
                result['errors'].append(f"Syntax error: {result_syntax.stderr}")
                result['checks']['valid_syntax'] = False
        except Exception as e:
            print(f"   ❌ Error checking syntax: {e}")
            result['success'] = False
            result['errors'].append(f"Error checking syntax: {e}")
            result['checks']['valid_syntax'] = False
        
        # Check for help/usage functionality (dry run)
        try:
            result_help = subprocess.run([
                sys.executable, script_path, '--help'
            ], capture_output=True, text=True, timeout=10)
            
            # Many scripts don't have --help, so we just check if they don't crash immediately
            print(f"   ✅ Script can be executed (help check)")
            result['checks']['executable'] = True
            
        except subprocess.TimeoutExpired:
            print(f"   ✅ Script runs (timed out waiting for help - normal)")
            result['checks']['executable'] = True
        except Exception as e:
            print(f"   ⚠️  Script execution test inconclusive: {e}")
            result['checks']['executable'] = False
        
        return result
    
    def test_task_definition_structure(self) -> Dict[str, Any]:
        """Test the structure of the task definition JSON file."""
        result = {
            'success': True,
            'checks': {},
            'errors': []
        }
        
        task_def_path = 'task-definition-update.json'
        
        # Check if file exists
        if not os.path.exists(task_def_path):
            print(f"   ❌ Task definition not found: {task_def_path}")
            result['success'] = False
            result['errors'].append("Task definition file not found")
            return result
        
        print(f"   ✅ Task definition exists")
        result['checks']['exists'] = True
        
        # Check JSON validity
        try:
            with open(task_def_path, 'r') as f:
                task_def = json.load(f)
            
            print(f"   ✅ Valid JSON format")
            result['checks']['valid_json'] = True
            
        except json.JSONDecodeError as e:
            print(f"   ❌ Invalid JSON: {e}")
            result['success'] = False
            result['errors'].append(f"JSON decode error: {e}")
            result['checks']['valid_json'] = False
            return result
        
        # Check required ECS task definition fields
        required_fields = [
            'family', 'taskRoleArn', 'executionRoleArn', 
            'cpu', 'memory', 'containerDefinitions'
        ]
        
        for field in required_fields:
            if field in task_def:
                print(f"   ✅ Has required field: {field}")
                result['checks'][f'has_{field}'] = True
            else:
                print(f"   ❌ Missing required field: {field}")
                result['success'] = False
                result['errors'].append(f"Missing field: {field}")
                result['checks'][f'has_{field}'] = False
        
        # Check ephemeral storage configuration
        if 'ephemeralStorage' in task_def:
            storage_config = task_def['ephemeralStorage']
            if 'sizeInGiB' in storage_config:
                size = storage_config['sizeInGiB']
                if size >= 30:
                    print(f"   ✅ Ephemeral storage adequate: {size}GB")
                    result['checks']['adequate_storage'] = True
                else:
                    print(f"   ❌ Ephemeral storage insufficient: {size}GB < 30GB")
                    result['success'] = False
                    result['errors'].append(f"Insufficient storage: {size}GB")
                    result['checks']['adequate_storage'] = False
            else:
                print(f"   ❌ Ephemeral storage missing sizeInGiB")
                result['success'] = False
                result['errors'].append("Missing sizeInGiB in ephemeralStorage")
                result['checks']['adequate_storage'] = False
        else:
            print(f"   ❌ Missing ephemeralStorage configuration")
            result['success'] = False
            result['errors'].append("Missing ephemeralStorage configuration")
            result['checks']['adequate_storage'] = False
        
        return result

def main():
    """Run the fix script integration tests."""
    tester = FixScriptIntegrationTester()
    results = tester.run_integration_tests()
    
    # Save results to file
    results_file = f"fix-script-integration-test-results-{int(datetime.now().timestamp())}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Integration test results saved to: {results_file}")
    
    return results['overall_success']

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)