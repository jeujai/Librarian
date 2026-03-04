#!/usr/bin/env python3
"""
Fix Secret ARN Format - Remove Version Suffixes

This script fixes the secret ARN format issue in task definition 44
by removing the :password and :redis suffixes that are causing
AWS Secrets Manager errors.

Root Cause: Task definition 44 has incorrect secret ARN format with
version specifiers (:password suffix) which AWS Secrets Manager rejects.

Fix: Remove the version specifiers from secret ARNs.
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any

class SecretARNFormatFixer:
    """Fixes secret ARN format by removing version suffixes."""
    
    def __init__(self):
        self.ecs_client = boto3.client('ecs', region_name='us-east-1')
        self.task_family = "multimodal-lib-prod-app"
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'fix_secret_arn_format',
            'task_definition': 44,
            'steps': {},
            'success': False
        }
    
    def fix_secret_arns(self) -> Dict[str, Any]:
        """Fix secret ARN format in task definition."""
        
        print("🔧 Fixing Secret ARN Format in Task Definition 44")
        print("=" * 60)
        print("Issue: Secret ARNs have :password suffix causing failures")
        print("Fix: Remove version specifiers from secret ARNs")
        print()
        
        try:
            # Step 1: Get task definition 44
            if not self._get_task_definition():
                return self.results
            
            # Step 2: Fix secret ARNs
            if not self._fix_secret_arns():
                return self.results
            
            # Step 3: Register new task definition
            if not self._register_new_task_definition():
                return self.results
            
            # Step 4: Update ECS service
            if not self._update_ecs_service():
                return self.results
            
            self.results['success'] = True
            print("\n🎉 Secret ARN format fixed successfully!")
            
        except Exception as e:
            self.results['error'] = str(e)
            print(f"\n❌ Fix failed: {e}")
        
        return self.results
    
    def _get_task_definition(self) -> bool:
        """Get task definition 44."""
        
        print("📍 Step 1: Getting task definition 44...")
        
        try:
            response = self.ecs_client.describe_task_definition(
                taskDefinition=f"{self.task_family}:44"
            )
            
            self.current_task_def = response['taskDefinition']
            
            # Display current secret configuration
            container = self.current_task_def['containerDefinitions'][0]
            if 'secrets' in container:
                print("\n❌ Current problematic secrets:")
                for secret in container['secrets']:
                    print(f"   {secret['name']}: {secret['valueFrom']}")
            
            self.results['steps']['get_task_definition'] = {
                'success': True,
                'revision': 44,
                'arn': self.current_task_def['taskDefinitionArn']
            }
            
            print(f"\n✅ Retrieved task definition 44")
            return True
            
        except Exception as e:
            print(f"❌ Error getting task definition: {e}")
            self.results['steps']['get_task_definition'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _fix_secret_arns(self) -> bool:
        """Fix secret ARNs by removing version suffixes."""
        
        print("\n📝 Step 2: Fixing secret ARNs...")
        
        try:
            # Create new task definition structure
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
            
            # Process container definitions
            for container in self.current_task_def['containerDefinitions']:
                new_container = container.copy()
                
                # Fix secrets if present
                if 'secrets' in new_container:
                    fixed_secrets = []
                    
                    for secret in new_container['secrets']:
                        secret_arn = secret['valueFrom']
                        
                        # Remove :password or :redis suffix
                        if ':password' in secret_arn:
                            fixed_arn = secret_arn.replace(':password', '')
                            print(f"   Fixing {secret['name']}:")
                            print(f"     Before: {secret_arn}")
                            print(f"     After:  {fixed_arn}")
                            
                            fixed_secrets.append({
                                'name': secret['name'],
                                'valueFrom': fixed_arn
                            })
                        elif ':redis' in secret_arn:
                            fixed_arn = secret_arn.replace(':redis', '')
                            print(f"   Fixing {secret['name']}:")
                            print(f"     Before: {secret_arn}")
                            print(f"     After:  {fixed_arn}")
                            
                            fixed_secrets.append({
                                'name': secret['name'],
                                'valueFrom': fixed_arn
                            })
                        else:
                            # Keep as-is if no suffix
                            fixed_secrets.append(secret)
                    
                    new_container['secrets'] = fixed_secrets
                
                self.new_task_def['containerDefinitions'].append(new_container)
            
            self.results['steps']['fix_secret_arns'] = {
                'success': True,
                'fixed_secrets': len([s for s in new_container.get('secrets', [])
                                     if ':password' in str(s) or ':redis' in str(s)])
            }
            
            print("\n✅ Secret ARNs fixed (removed version suffixes)")
            return True
            
        except Exception as e:
            print(f"❌ Error fixing secret ARNs: {e}")
            self.results['steps']['fix_secret_arns'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _register_new_task_definition(self) -> bool:
        """Register new task definition with fixed secrets."""
        
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
            print(f"   Revision: {self.new_revision}")
            print(f"   ARN: {self.new_task_def_arn}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error registering task definition: {e}")
            self.results['steps']['register_new_task_definition'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def _update_ecs_service(self) -> bool:
        """Update ECS service with new task definition."""
        
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
                'task_definition': self.new_task_def_arn,
                'new_revision': self.new_revision
            }
            
            print(f"✅ ECS service updated:")
            print(f"   Cluster: {cluster_name}")
            print(f"   Service: {service_name}")
            print(f"   New Task Definition: revision {self.new_revision}")
            print(f"   Deployment ID: {deployment_id}")
            
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
        
        filename = f"secret-arn-format-fix-{int(time.time())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("🔧 Secret ARN Format Fix")
    print("Removing :password and :redis suffixes from secret ARNs")
    print()
    
    fixer = SecretARNFormatFixer()
    results = fixer.fix_secret_arns()
    
    # Save results
    results_file = fixer.save_results()
    print(f"\n📄 Results saved to: {results_file}")
    
    # Summary
    if results['success']:
        print("\n🎉 Secret ARN Format Fix Summary:")
        print("=" * 50)
        print("✅ Secret ARNs fixed (removed version suffixes)")
        print("✅ New task definition registered")
        print("✅ ECS service updated with fixed task definition")
        print()
        print("🔄 Next Steps:")
        print("1. Wait 2-3 minutes for new tasks to start")
        print("2. Monitor task startup in AWS Console")
        print("3. Verify tasks pass health checks")
        print("4. Check CloudWatch logs for successful secret retrieval")
        
        return 0
    else:
        print("\n❌ Secret ARN Format Fix Failed")
        print("Check the results file for detailed error information")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
