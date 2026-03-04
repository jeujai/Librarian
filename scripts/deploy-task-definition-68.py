#!/usr/bin/env python3
"""
Deploy specific task definition revision 68 to ECS service.
This script updates the ECS service to use task definition revision 68.
"""

import boto3
import json
import time
from datetime import datetime

def deploy_task_definition_68():
    """Deploy task definition revision 68 to ECS service."""
    print("🚀 Deploying Task Definition Revision 68")
    print("=" * 60)
    
    results = {
        'deployment_time': datetime.now().isoformat(),
        'task_definition_revision': 68,
        'steps': [],
        'success': True,
        'errors': []
    }
    
    try:
        ecs = boto3.client('ecs')
        
        # Configuration
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        task_family = 'multimodal-lib-prod-app'
        task_revision = 68
        task_definition = f'{task_family}:{task_revision}'
        
        # Step 1: Verify task definition exists
        print(f"1️⃣ Verifying task definition {task_definition}...")
        try:
            task_def_response = ecs.describe_task_definition(
                taskDefinition=task_definition
            )
            
            task_def = task_def_response['taskDefinition']
            print(f"✅ Task definition found:")
            print(f"   Family: {task_def['family']}")
            print(f"   Revision: {task_def['revision']}")
            print(f"   Status: {task_def['status']}")
            print(f"   CPU: {task_def['cpu']}")
            print(f"   Memory: {task_def['memory']}")
            
            # Check health check configuration
            if task_def['containerDefinitions']:
                container = task_def['containerDefinitions'][0]
                if 'healthCheck' in container:
                    hc = container['healthCheck']
                    print(f"   Health Check:")
                    print(f"     Command: {hc.get('command', 'N/A')}")
                    print(f"     Interval: {hc.get('interval', 'N/A')}s")
                    print(f"     Timeout: {hc.get('timeout', 'N/A')}s")
                    print(f"     Retries: {hc.get('retries', 'N/A')}")
                    print(f"     Start Period: {hc.get('startPeriod', 'N/A')}s")
            
            results['steps'].append({
                'step': 'verify_task_definition',
                'status': 'success',
                'message': f'Task definition {task_definition} verified',
                'task_definition_arn': task_def['taskDefinitionArn']
            })
            
        except Exception as e:
            print(f"❌ Task definition not found: {e}")
            results['errors'].append(f"Task definition verification failed: {e}")
            results['success'] = False
            return results
        
        # Step 2: Get current service status
        print(f"\n2️⃣ Checking current service status...")
        try:
            service_response = ecs.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if not service_response['services']:
                print(f"❌ Service {service_name} not found")
                results['errors'].append(f"Service {service_name} not found")
                results['success'] = False
                return results
            
            service = service_response['services'][0]
            current_task_def = service['taskDefinition']
            running_count = service['runningCount']
            desired_count = service['desiredCount']
            
            print(f"✅ Current service status:")
            print(f"   Current task definition: {current_task_def}")
            print(f"   Running tasks: {running_count}")
            print(f"   Desired tasks: {desired_count}")
            print(f"   Status: {service['status']}")
            
            results['steps'].append({
                'step': 'check_service_status',
                'status': 'success',
                'message': f'Service status checked',
                'current_task_definition': current_task_def,
                'running_count': running_count,
                'desired_count': desired_count
            })
            
        except Exception as e:
            print(f"❌ Error checking service status: {e}")
            results['errors'].append(f"Service status check failed: {e}")
            results['success'] = False
            return results
        
        # Step 3: Update service to use task definition 68
        print(f"\n3️⃣ Updating service to use task definition {task_revision}...")
        try:
            update_response = ecs.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=task_definition,
                forceNewDeployment=True
            )
            
            print(f"✅ Service update initiated")
            print(f"   Cluster: {cluster_name}")
            print(f"   Service: {service_name}")
            print(f"   New task definition: {task_definition}")
            
            results['steps'].append({
                'step': 'update_service',
                'status': 'success',
                'message': f'Service updated to use {task_definition}'
            })
            
        except Exception as e:
            print(f"❌ Error updating service: {e}")
            results['errors'].append(f"Service update failed: {e}")
            results['success'] = False
            return results
        
        # Step 4: Monitor deployment progress
        print(f"\n4️⃣ Monitoring deployment progress...")
        print("⏳ This may take 5-10 minutes due to health check start period...")
        
        try:
            max_wait_time = 600  # 10 minutes
            check_interval = 15  # 15 seconds
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                time.sleep(check_interval)
                elapsed_time += check_interval
                
                # Check service status
                service_response = ecs.describe_services(
                    cluster=cluster_name,
                    services=[service_name]
                )
                
                if service_response['services']:
                    service = service_response['services'][0]
                    running_count = service['runningCount']
                    desired_count = service['desiredCount']
                    
                    # Check deployments
                    deployments = service.get('deployments', [])
                    primary_deployment = None
                    
                    for deployment in deployments:
                        if deployment['status'] == 'PRIMARY':
                            primary_deployment = deployment
                            break
                    
                    if primary_deployment:
                        print(f"⏳ [{elapsed_time}s] Deployment status:")
                        print(f"   Running: {primary_deployment['runningCount']}")
                        print(f"   Desired: {primary_deployment['desiredCount']}")
                        print(f"   Pending: {primary_deployment.get('pendingCount', 0)}")
                        print(f"   Rollout State: {primary_deployment.get('rolloutState', 'N/A')}")
                        
                        # Check if deployment is complete
                        if (primary_deployment['runningCount'] == primary_deployment['desiredCount'] and
                            primary_deployment.get('rolloutState') == 'COMPLETED'):
                            print(f"✅ Deployment completed successfully!")
                            results['steps'].append({
                                'step': 'monitor_deployment',
                                'status': 'success',
                                'message': f'Deployment completed in {elapsed_time}s'
                            })
                            break
                else:
                    print(f"⚠️ Service not found during monitoring")
                    break
            else:
                print(f"⚠️ Deployment monitoring timed out after {max_wait_time}s")
                print(f"   Service may still be deploying - check AWS console")
                results['steps'].append({
                    'step': 'monitor_deployment',
                    'status': 'warning',
                    'message': f'Monitoring timed out after {max_wait_time}s'
                })
            
        except Exception as e:
            print(f"⚠️ Error monitoring deployment: {e}")
            results['steps'].append({
                'step': 'monitor_deployment',
                'status': 'warning',
                'message': f'Monitoring error: {e}'
            })
        
        # Step 5: Verify final deployment status
        print(f"\n5️⃣ Verifying final deployment status...")
        try:
            service_response = ecs.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if service_response['services']:
                service = service_response['services'][0]
                running_count = service['runningCount']
                desired_count = service['desiredCount']
                current_task_def = service['taskDefinition']
                
                print(f"📊 Final Service Status:")
                print(f"   Task Definition: {current_task_def}")
                print(f"   Running tasks: {running_count}")
                print(f"   Desired tasks: {desired_count}")
                print(f"   Status: {service['status']}")
                
                # Check if using correct task definition
                if f':{task_revision}' in current_task_def:
                    print(f"✅ Service is using task definition revision {task_revision}")
                    results['steps'].append({
                        'step': 'verify_deployment',
                        'status': 'success',
                        'message': f'Service successfully using revision {task_revision}'
                    })
                else:
                    print(f"⚠️ Service may not be using revision {task_revision} yet")
                    results['steps'].append({
                        'step': 'verify_deployment',
                        'status': 'warning',
                        'message': f'Service task definition: {current_task_def}'
                    })
                
                if running_count == desired_count:
                    print(f"✅ All tasks are running")
                else:
                    print(f"⚠️ Task count mismatch: {running_count}/{desired_count}")
            
        except Exception as e:
            print(f"⚠️ Error verifying deployment: {e}")
            results['steps'].append({
                'step': 'verify_deployment',
                'status': 'warning',
                'message': f'Verification error: {e}'
            })
        
        print(f"\n🎉 Deployment process completed!")
        print(f"📋 {len([s for s in results['steps'] if s['status'] == 'success'])} successful steps")
        
        if results['errors']:
            print(f"⚠️ {len(results['errors'])} errors occurred")
        
        return results
        
    except Exception as e:
        print(f"❌ Fatal error during deployment: {e}")
        results['success'] = False
        results['errors'].append(f"Fatal error: {e}")
        return results

def main():
    """Main execution function."""
    print("🚀 Deploy Task Definition Revision 68")
    print("=" * 60)
    print(f"Execution Time: {datetime.now().isoformat()}")
    
    try:
        results = deploy_task_definition_68()
        
        # Save results
        timestamp = int(datetime.now().timestamp())
        results_file = f'deploy-task-68-{timestamp}.json'
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📝 Results saved to: {results_file}")
        
        if results['success']:
            print(f"\n✅ Deployment completed successfully")
            return 0
        else:
            print(f"\n❌ Deployment failed")
            print(f"❌ {len(results['errors'])} errors occurred")
            return 1
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
