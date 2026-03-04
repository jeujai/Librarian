#!/usr/bin/env python3
"""
Test script for the new validator components (NetworkConfigValidator, TaskDefinitionValidator)
"""

import json
from datetime import datetime
from src.multimodal_librarian.validation.checklist_validator import ChecklistValidator
from src.multimodal_librarian.validation.models import DeploymentConfig
from src.multimodal_librarian.validation.network_config_validator import NetworkConfigValidator
from src.multimodal_librarian.validation.task_definition_validator import TaskDefinitionValidator

def test_new_validators():
    """Test the new validator components"""
    print("🧪 Testing New Validator Components")
    print("=" * 60)
    
    # Test 1: NetworkConfigValidator instantiation
    print("\n1. NetworkConfigValidator Testing")
    print("-" * 40)
    
    try:
        network_validator = NetworkConfigValidator()
        print("✅ NetworkConfigValidator instantiated successfully")
        
        # Test with minimal config (should skip validation)
        deployment_config = DeploymentConfig(
            task_definition_arn='arn:aws:ecs:us-east-1:591222106065:task-definition/test:1',
            iam_role_arn='arn:aws:iam::591222106065:role/testRole',
            load_balancer_arn='arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/test/123',
            target_environment='production'
        )
        
        result = network_validator.validate(deployment_config)
        print(f"✅ Network validation result: {result.status.value}")
        print(f"   Message: {result.message}")
        
    except Exception as e:
        print(f"❌ NetworkConfigValidator test failed: {e}")
    
    # Test 2: TaskDefinitionValidator instantiation
    print("\n2. TaskDefinitionValidator Testing")
    print("-" * 40)
    
    try:
        task_def_validator = TaskDefinitionValidator()
        print("✅ TaskDefinitionValidator instantiated successfully")
        
        # Test with real task definition ARN
        deployment_config = DeploymentConfig(
            task_definition_arn='arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:15',
            iam_role_arn='arn:aws:iam::591222106065:role/ecsTaskRole',
            load_balancer_arn='arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/test/123',
            target_environment='production'
        )
        
        result = task_def_validator.validate(deployment_config)
        print(f"✅ Task definition validation result: {result.status.value}")
        print(f"   Message: {result.message}")
        
    except Exception as e:
        print(f"❌ TaskDefinitionValidator test failed: {e}")
    
    # Test 3: ChecklistValidator with all validators
    print("\n3. ChecklistValidator Integration Testing")
    print("-" * 40)
    
    try:
        checklist_validator = ChecklistValidator()
        print("✅ ChecklistValidator with all validators instantiated successfully")
        
        # Check that all validators are present
        validators = [
            ('IAM', checklist_validator.iam_validator),
            ('Storage', checklist_validator.storage_validator),
            ('SSL', checklist_validator.ssl_validator),
            ('Network', checklist_validator.network_validator),
            ('Task Definition', checklist_validator.task_definition_validator)
        ]
        
        for name, validator in validators:
            print(f"✅ {name} validator: {validator.__class__.__name__}")
        
        # Check validation checks configuration
        print(f"\n✅ Validation checks configured: {len(checklist_validator._validation_checks)}")
        for check in checklist_validator._validation_checks:
            print(f"   - {check['name']} (critical: {check['critical']})")
        
    except Exception as e:
        print(f"❌ ChecklistValidator integration test failed: {e}")
    
    # Test 4: Fix Script Manager with new validation types
    print("\n4. Fix Script Manager Testing")
    print("-" * 40)
    
    try:
        fix_script_manager = checklist_validator.fix_script_manager
        
        # Test new validation types
        new_validation_types = ['network_config', 'task_definition']
        
        for validation_type in new_validation_types:
            scripts = fix_script_manager.get_scripts_by_validation_type(validation_type)
            print(f"✅ {validation_type}: {len(scripts)} fix scripts available")
            for script in scripts:
                print(f"   - {script.script_path}: {script.description}")
        
        # Test remediation guide with new check names
        failed_checks = [
            'VPC Compatibility',
            'Target Group Mapping', 
            'Task Definition Registration',
            'Task Definition Storage'
        ]
        
        remediation_guide = fix_script_manager.generate_remediation_guide(failed_checks)
        print(f"\n✅ Remediation guide generated for new check types")
        print(f"   Script references: {len(remediation_guide.script_references)}")
        print(f"   Instructions: {len(remediation_guide.step_by_step_instructions)}")
        
    except Exception as e:
        print(f"❌ Fix Script Manager test failed: {e}")
    
    # Test 5: Configuration Manager with new validation types
    print("\n5. Configuration Manager Testing")
    print("-" * 40)
    
    try:
        config_manager = checklist_validator.config_manager
        
        # Check default enabled validations
        enabled_validations = config_manager.get_enabled_validations()
        print(f"✅ Default enabled validations: {enabled_validations}")
        
        # Verify new validation types are enabled by default
        new_types = ['network_config', 'task_definition']
        for validation_type in new_types:
            if validation_type in enabled_validations:
                print(f"✅ {validation_type} is enabled by default")
            else:
                print(f"❌ {validation_type} is NOT enabled by default")
        
    except Exception as e:
        print(f"❌ Configuration Manager test failed: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 New Validator Components Testing Complete!")
    
    # Save test results
    test_results = {
        'timestamp': datetime.utcnow().isoformat(),
        'test_name': 'New Validator Components Test',
        'validators_tested': [
            'NetworkConfigValidator',
            'TaskDefinitionValidator', 
            'ChecklistValidator Integration',
            'Fix Script Manager',
            'Configuration Manager'
        ],
        'status': 'completed'
    }
    
    with open(f'new-validators-test-results-{int(datetime.utcnow().timestamp())}.json', 'w') as f:
        json.dump(test_results, f, indent=2)
    
    print(f"📄 Test results saved to: new-validators-test-results-{int(datetime.utcnow().timestamp())}.json")

if __name__ == "__main__":
    test_new_validators()