#!/usr/bin/env python3
"""
Fix Task Definition Secret Names

This script updates the ECS task definition to use the correct
environment variables for AWS secret names.
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

class TaskDefinitionSecretNamesFixer:
    """Updates ECS task definition with correct secret names."""
    
    def __init__(self):
        self.ecs_client = boto3.client('ecs', region_name='us-east-1')
        
        # Task definition configuration
        self.task_family = "multimodal-lib-prod-app"
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'fix_task_definition_secret_names',
            'steps': {},
            'success': False
        }
    
    def fix_secret_names(self) -> Dict[str, Any]:
        """Fix secret names in task definition."""
        
        print("🔧 Fixing Task Definition Secret Names")
        print("=" * 50)
        
        try:
            # Step 1: Get current task definition
            if not self._get_current_task_definition():
                return self.results
            
            # Step 2: Update environment variables
            if not self._update_environment_variables():
                return self.results
            
            # Step 3: Register new task definition
            if not self._register_new_task_definition():
                return self.results
            
            # Step 4: Update ECS service
            if not self._update_ecs_service():
                return self.results
            
            self.results['success'] = True
            print("\n🎉 Task definition secret names fixed successfully!")
            print("✅ Environment variables updated with correct secret names")
            print("✅ ECS service updated with new task definition")
            
        except Exception as e:
            self.results['error'] = str(e)
            print(f"\n❌ Task definition fix failed: {e}")
        
        return self.results
    
    def _get_current_task_definition(self) -> bool:
        """Get the current task definition."""
        
        print("\n📍 Step 1: Getting current task definition...")
        
        try:
            # Get the latest task definition
            response = self.ecs_client.describe_task_definition(
                taskDefinition=self.task_family
            )
            
            self.current_task_def = response['taskDefinition']
            
            self.results['steps']['get_current_task_definition'] = {
                'success': True,
                'family': self.current_task_def['family'],
                'revision': self.current_task_def['revision'],
                'arn': self.current_task_def['taskDefinitionArn']
            }
            
            print(f"✅ Retrieved task definition: {self.current_task_def['family']}:{self.current_task_def['revision']}")
            print(f"   - ARN: {self.current_task_def['taskDefinitionArn']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error getting task definition: {e}")
            self.results['steps']['get_current_task_definition'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _update_environment_variables(self) -> bool:
        """Update environment variables with correct secret names."""
        
        print("\n📝 Step 2: Updating environment variables...")
        
        try:
            # Create a copy of the task definition for modification
            self.new_task_def = {
                'family': self.current_task_def['family'],
                'taskRoleArn': self.current_task_def['taskRoleArn'],
                'executionRoleArn': self.current_task_def['executionRoleArn'],
                'networkMode': self.current_task_def['networkMode'],
                'requiresCompatibilities': self.current_task_def['requiresCompatibilities'],
                'cpu': self.current_task_def['cpu'],
                'memory': self.current_task_def['memory'],
                'containerDefinitions': []
            }
            
            # Add ephemeral storage if present
            if 'ephemeralStorage' in self.current_task_def:
                self.new_task_def['ephemeralStorage'] = self.current_task_def['ephemeralStorage']
            
            # Update container definitions
            for container in self.current_task_def['containerDefinitions']:
                new_container = container.copy()
                
                # Update environment variables
                if 'environment' not in new_container:
                    new_container['environment'] = []
                
                # Add/update secret name environment variables
                env_vars = {env['name']: env['value'] for env in new_container['environment']}
                
                # Set correct secret names
                env_vars['NEPTUNE_SECRET_NAME'] = 'multimodal-lib-prod/neptune/connection'
                env_vars['OPENSEARCH_SECRET_NAME'] = 'multimodal-lib-prod/opensearch/connection'
                
                # Convert back to list format
                new_container['environment'] = [
                    {'name': name, 'value': value} 
                    for name, value in env_vars.items()
                ]
                
                self.new_task_def['containerDefinitions'].append(new_container)
            
            self.results['steps']['update_environment_variables'] = {
                'success': True,
                'added_variables': [
                    'NEPTUNE_SECRET_NAME=multimodal-lib-prod/neptune/connection',
                    'OPENSEARCH_SECRET_NAME=multimodal-lib-prod/opensearch/connection'
                ]
            }
            
            print("✅ Environment variables updated:")
            print("   - NEPTUNE_SECRET_NAME=multimodal-lib-prod/neptune/connection")
            print("   - OPENSEARCH_SECRET_NAME=multimodal-lib-prod/opensearch/connection")
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating environment variables: {e}")
            self.results['steps']['update_environment_variables'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _register_new_task_definition(self) -> bool:
        """Register the new task definition."""
        
        print("\n🔄 Step 3: Registering new task definition...")
        
        try:
            response = self.ecs_client.register_task_definition(**self.new_task_def)
            
            self.new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
            self.new_revision = response['taskDefinition']['revision']
            
            self.results['steps']['register_new_task_definition'] = {
                'success': True,
                'new_arn': self.new_task_def_arn,
                'new_revision': self.new_revision
            }
            
            print(f"✅ New task definition registered:")
            print(f"   - ARN: {self.new_task_def_arn}")
            print(f"   - Revision: {self.new_revision}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error registering task definition: {e}")
            self.results['steps']['register_new_task_definition'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _update_ecs_service(self) -> bool:
        """Update the ECS service to use the new task definition."""
        
        print("\n🚀 Step 4: Updating ECS service...")
        
        try:
            cluster_name = "multimodal-lib-prod-cluster"
            service_name = "multimodal-lib-prod-service"
            
            response = self.ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=self.new_task_def_arn,
                forceNewDeployment=True
            )
            
            deployment_id = response['service']['deployments'][0]['id']
            
            self.results['steps']['update_ecs_service'] = {
                'success': True,
                'cluster': cluster_name,
                'service': service_name,
                'deployment_id': deployment_id,
                'task_definition': self.new_task_def_arn
            }
            
            print(f"✅ ECS service updated:")
            print(f"   - Cluster: {cluster_name}")
            print(f"   - Service: {service_name}")
            print(f"   - Task Definition: {self.new_task_def_arn}")
            print(f"   - Deployment ID: {deployment_id}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating ECS service: {e}")
            self.results['steps']['update_ecs_service'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def save_results(self) -> str:
        """Save fix results to file."""
        
        filename = f"task-definition-secret-names-fix-{int(time.time())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🔧 Task Definition Secret Names Fix")
    print("Updating environment variables for correct secret names")
    print()
    
    fixer = TaskDefinitionSecretNamesFixer()
    results = fixer.fix_secret_names()
    
    # Save results
    results_file = fixer.save_results()
    print(f"\n📄 Fix results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n🎉 Task Definition Fix Summary:")
        print("=" * 40)
        print("✅ Task definition updated with correct secret names")
        print("✅ Environment variables added:")
        print("   - NEPTUNE_SECRET_NAME=multimodal-lib-prod/neptune/connection")
        print("   - OPENSEARCH_SECRET_NAME=multimodal-lib-prod/opensearch/connection")
        print("✅ ECS service updated with new task definition")
        print()
        print("🔄 Next Steps:")
        print("1. Wait 2-3 minutes for new ECS tasks to start")
        print("2. Run the end-to-end test again")
        print("3. Application should now access correct secrets")
        print("4. Document upload API should work")
        
        return 0
    else:
        print("\n❌ Task Definition Fix Failed")
        print("Check the results file for detailed error information")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)