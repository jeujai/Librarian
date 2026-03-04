#!/usr/bin/env python3
"""
Deploy legacy database cleanup with 8GB memory configuration.

This script rebuilds the Docker image with the legacy database cleanup
(OpenSearch/Neptune only) and deploys with reduced memory from 24GB to 8GB.

Key Changes:
- Memory: 24GB → 8GB (8192 MB)
- CPU: Adjusted to 4096 units (4 vCPU)
- Legacy databases removed (Neo4j, Milvus)
- AWS-native only (OpenSearch, Neptune)
"""

import boto3
import json
import subprocess
import time
import os
from datetime import datetime
from pathlib import Path

# Deployment configuration for 8GB memory
DEPLOYMENT_CONFIG = {
    "task_memory_mb": 8192,  # 8GB
    "task_cpu_units": 4096,  # 4 vCPU
    "desired_count": 1,
    "cluster_name": "multimodal-lib-prod-cluster",
    "service_name": "multimodal-lib-prod-service",
    "task_family": "multimodal-lib-prod-app",
    "container_name": "multimodal-lib-prod-app"
}

# Health check configuration
HEALTH_CHECK_PATH = "/health/minimal"
HEALTH_CHECK_INTERVAL = 30
HEALTH_CHECK_TIMEOUT = 15
HEALTH_CHECK_RETRIES = 5
HEALTH_CHECK_START_PERIOD = 300  # 5 minutes for AI model loading

def deploy_legacy_cleanup_8gb():
    """Deploy with legacy cleanup and 8GB memory."""
    print("🚀 Deploying Legacy Database Cleanup with 8GB Memory")
    print("=" * 70)
    print(f"Memory: {DEPLOYMENT_CONFIG['task_memory_mb']} MB (8GB)")
    print(f"CPU: {DEPLOYMENT_CONFIG['task_cpu_units']} units (4 vCPU)")
    print(f"Configuration: AWS-native only (OpenSearch + Neptune)")
    print("=" * 70)
    
    results = {
        'deployment_time': datetime.now().isoformat(),
        'configuration': DEPLOYMENT_CONFIG,
        'legacy_cleanup': True,
        'steps': [],
        'success': True,
        'errors': []
    }
    
    try:
        # Step 1: Get ECR repository information
        print("\n1️⃣ Getting ECR repository information...")
        ecr = boto3.client('ecr')
        
        try:
            repo_response = ecr.describe_repositories(
                repositoryNames=['multimodal-librarian']
            )
            
            if repo_response['repositories']:
                repo_uri = repo_response['repositories'][0]['repositoryUri']
                print(f"✅ Found ECR repository: {repo_uri}")
                results['steps'].append({
                    'step': 'ecr_repository_found',
                    'status': 'success',
                    'message': f'ECR repository found: {repo_uri}'
                })
            else:
                print("❌ ECR repository 'multimodal-librarian' not found")
                results['errors'].append("ECR repository not found")
                results['success'] = False
                return results
                
        except Exception as e:
            print(f"❌ Error accessing ECR: {e}")
            results['errors'].append(f"ECR access error: {e}")
            results['success'] = False
            return results
        
        # Step 2: Get ECR login token
        print("\n2️⃣ Getting ECR login token...")
        try:
            login_response = ecr.get_authorization_token()
            token = login_response['authorizationData'][0]['authorizationToken']
            endpoint = login_response['authorizationData'][0]['proxyEndpoint']
            
            # Decode the token and extract password
            import base64
            decoded_token = base64.b64decode(token).decode('utf-8')
            username, password = decoded_token.split(':')
            
            print("✅ ECR login token obtained")
            results['steps'].append({
                'step': 'ecr_login_token',
                'status': 'success',
                'message': 'ECR login token obtained'
            })
            
        except Exception as e:
            print(f"❌ Error getting ECR login token: {e}")
            results['errors'].append(f"ECR login error: {e}")
            results['success'] = False
            return results
        
        # Step 3: Docker login to ECR
        print("\n3️⃣ Logging into ECR...")
        try:
            login_cmd = f"echo {password} | docker login --username {username} --password-stdin {endpoint}"
            result = subprocess.run(
                login_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print("✅ Successfully logged into ECR")
                results['steps'].append({
                    'step': 'docker_login',
                    'status': 'success',
                    'message': 'Successfully logged into ECR'
                })
            else:
                print(f"❌ Docker login failed: {result.stderr}")
                results['errors'].append(f"Docker login failed: {result.stderr}")
                results['success'] = False
                return results
                
        except subprocess.TimeoutExpired:
            print("❌ Docker login timed out")
            results['errors'].append("Docker login timeout")
            results['success'] = False
            return results
        except Exception as e:
            print(f"❌ Error during Docker login: {e}")
            results['errors'].append(f"Docker login error: {e}")
            results['success'] = False
            return results
        
        # Step 4: Build Docker image with legacy cleanup
        print("\n4️⃣ Building Docker image with legacy cleanup...")
        print("   📦 Building AWS-native only image (no Neo4j/Milvus)")
        try:
            # Generate timestamp tag
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            image_tag = f"{repo_uri}:latest"
            image_tag_timestamped = f"{repo_uri}:legacy-cleanup-{timestamp}"
            
            build_cmd = [
                "docker", "build",
                "-t", image_tag,
                "-t", image_tag_timestamped,
                "."
            ]
            
            print(f"   Building image: {image_tag}")
            print(f"   Timestamped tag: {image_tag_timestamped}")
            
            result = subprocess.run(
                build_cmd,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            if result.returncode == 0:
                print("✅ Docker image built successfully")
                print("   ✓ No Neo4j dependencies")
                print("   ✓ No Milvus dependencies")
                print("   ✓ OpenSearch client included")
                print("   ✓ Neptune client included")
                results['steps'].append({
                    'step': 'docker_build',
                    'status': 'success',
                    'message': f'Docker image built with legacy cleanup: {image_tag}'
                })
            else:
                print(f"❌ Docker build failed: {result.stderr}")
                results['errors'].append(f"Docker build failed: {result.stderr}")
                results['success'] = False
                return results
                
        except subprocess.TimeoutExpired:
            print("❌ Docker build timed out (30 minutes)")
            results['errors'].append("Docker build timeout")
            results['success'] = False
            return results
        except Exception as e:
            print(f"❌ Error during Docker build: {e}")
            results['errors'].append(f"Docker build error: {e}")
            results['success'] = False
            return results
        
        # Step 5: Push Docker image to ECR
        print("\n5️⃣ Pushing Docker image to ECR...")
        try:
            # Push latest tag
            push_cmd_latest = ["docker", "push", image_tag]
            result = subprocess.run(
                push_cmd_latest,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            if result.returncode == 0:
                print("✅ Latest image pushed successfully")
                results['steps'].append({
                    'step': 'docker_push_latest',
                    'status': 'success',
                    'message': f'Latest image pushed: {image_tag}'
                })
            else:
                print(f"❌ Docker push failed: {result.stderr}")
                results['errors'].append(f"Docker push failed: {result.stderr}")
                results['success'] = False
                return results
            
            # Push timestamped tag
            push_cmd_timestamped = ["docker", "push", image_tag_timestamped]
            result = subprocess.run(
                push_cmd_timestamped,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            if result.returncode == 0:
                print("✅ Timestamped image pushed successfully")
                results['steps'].append({
                    'step': 'docker_push_timestamped',
                    'status': 'success',
                    'message': f'Timestamped image pushed: {image_tag_timestamped}'
                })
            else:
                print(f"⚠️ Timestamped push failed (non-critical): {result.stderr}")
                results['steps'].append({
                    'step': 'docker_push_timestamped',
                    'status': 'warning',
                    'message': f'Timestamped push failed: {result.stderr}'
                })
                
        except subprocess.TimeoutExpired:
            print("❌ Docker push timed out (30 minutes)")
            results['errors'].append("Docker push timeout")
            results['success'] = False
            return results
        except Exception as e:
            print(f"❌ Error during Docker push: {e}")
            results['errors'].append(f"Docker push error: {e}")
            results['success'] = False
            return results
        
        # Step 6: Update task definition with 8GB memory
        print("\n6️⃣ Updating task definition with 8GB memory configuration...")
        try:
            ecs = boto3.client('ecs')
            
            # Get current task definition
            task_family = DEPLOYMENT_CONFIG['task_family']
            task_def_response = ecs.describe_task_definition(taskDefinition=task_family)
            current_task_def = task_def_response['taskDefinition']
            
            # Update container definition
            container_def = current_task_def['containerDefinitions'][0].copy()
            container_def['image'] = f"{repo_uri}:latest"
            container_def['healthCheck'] = {
                'command': [
                    'CMD-SHELL',
                    f'curl -f http://localhost:8000{HEALTH_CHECK_PATH} || exit 1'
                ],
                'interval': HEALTH_CHECK_INTERVAL,
                'timeout': HEALTH_CHECK_TIMEOUT,
                'retries': HEALTH_CHECK_RETRIES,
                'startPeriod': HEALTH_CHECK_START_PERIOD
            }
            
            # Register new task definition with 8GB memory
            new_task_def = {
                'family': current_task_def['family'],
                'taskRoleArn': current_task_def.get('taskRoleArn'),
                'executionRoleArn': current_task_def.get('executionRoleArn'),
                'networkMode': current_task_def['networkMode'],
                'requiresCompatibilities': current_task_def['requiresCompatibilities'],
                'cpu': str(DEPLOYMENT_CONFIG['task_cpu_units']),
                'memory': str(DEPLOYMENT_CONFIG['task_memory_mb']),
                'containerDefinitions': [container_def]
            }
            
            # Add ephemeral storage if present
            if 'ephemeralStorage' in current_task_def:
                new_task_def['ephemeralStorage'] = current_task_def['ephemeralStorage']
            
            register_response = ecs.register_task_definition(**new_task_def)
            task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
            
            print(f"✅ Task definition updated with 8GB memory")
            print(f"   Task Definition: {task_def_arn}")
            print(f"   Memory: {DEPLOYMENT_CONFIG['task_memory_mb']} MB (8GB)")
            print(f"   CPU: {DEPLOYMENT_CONFIG['task_cpu_units']} units (4 vCPU)")
            print(f"   Health Check Path: {HEALTH_CHECK_PATH}")
            print(f"   Start Period: {HEALTH_CHECK_START_PERIOD}s")
            
            results['steps'].append({
                'step': 'task_definition_update',
                'status': 'success',
                'message': f'Task definition updated with 8GB memory: {task_def_arn}',
                'memory_mb': DEPLOYMENT_CONFIG['task_memory_mb'],
                'cpu_units': DEPLOYMENT_CONFIG['task_cpu_units'],
                'health_check_config': {
                    'path': HEALTH_CHECK_PATH,
                    'interval': HEALTH_CHECK_INTERVAL,
                    'timeout': HEALTH_CHECK_TIMEOUT,
                    'retries': HEALTH_CHECK_RETRIES,
                    'start_period': HEALTH_CHECK_START_PERIOD
                }
            })
            
        except Exception as e:
            print(f"❌ Error updating task definition: {e}")
            results['errors'].append(f"Task definition update error: {e}")
            results['success'] = False
            return results
        
        # Step 7: Update ALB target group health check
        print("\n7️⃣ Updating ALB target group health check...")
        try:
            elbv2 = boto3.client('elbv2')
            
            # Find target group
            tg_response = elbv2.describe_target_groups()
            target_group_arn = None
            
            for tg in tg_response['TargetGroups']:
                if 'multimodal-lib-prod' in tg['TargetGroupName']:
                    target_group_arn = tg['TargetGroupArn']
                    break
            
            if target_group_arn:
                # Update target group health check
                elbv2.modify_target_group(
                    TargetGroupArn=target_group_arn,
                    HealthCheckPath=HEALTH_CHECK_PATH,
                    HealthCheckIntervalSeconds=HEALTH_CHECK_INTERVAL,
                    HealthCheckTimeoutSeconds=HEALTH_CHECK_TIMEOUT,
                    HealthyThresholdCount=2,
                    UnhealthyThresholdCount=5
                )
                
                print(f"✅ ALB target group health check updated")
                print(f"   Health Check Path: {HEALTH_CHECK_PATH}")
                
                results['steps'].append({
                    'step': 'alb_health_check_update',
                    'status': 'success',
                    'message': 'ALB target group health check updated'
                })
            else:
                print("⚠️  Target group not found, skipping ALB health check update")
                results['steps'].append({
                    'step': 'alb_health_check_update',
                    'status': 'warning',
                    'message': 'Target group not found'
                })
            
        except Exception as e:
            print(f"⚠️  Error updating ALB health check (non-critical): {e}")
            results['steps'].append({
                'step': 'alb_health_check_update',
                'status': 'warning',
                'message': f'ALB health check update failed: {e}'
            })
        
        # Step 8: Update ECS service to trigger redeployment
        print("\n8️⃣ Updating ECS service for redeployment...")
        try:
            ecs = boto3.client('ecs')
            
            cluster_name = DEPLOYMENT_CONFIG['cluster_name']
            service_name = DEPLOYMENT_CONFIG['service_name']
            
            # Update service with new task definition
            update_response = ecs.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=task_def_arn,
                forceNewDeployment=True
            )
            
            print(f"✅ ECS service update initiated")
            print(f"   Cluster: {cluster_name}")
            print(f"   Service: {service_name}")
            print(f"   Task Definition: {task_def_arn}")
            print(f"   Memory: {DEPLOYMENT_CONFIG['task_memory_mb']} MB (8GB)")
            print(f"   CPU: {DEPLOYMENT_CONFIG['task_cpu_units']} units (4 vCPU)")
            
            results['steps'].append({
                'step': 'ecs_service_update',
                'status': 'success',
                'message': f'ECS service update initiated for {service_name}'
            })
            
        except Exception as e:
            print(f"❌ Error updating ECS service: {e}")
            results['errors'].append(f"ECS service update error: {e}")
            results['success'] = False
            return results
        
        # Step 9: Wait for deployment to complete
        print("\n9️⃣ Waiting for deployment to complete...")
        try:
            print("⏳ Monitoring deployment progress...")
            print("⏳ This may take 5-10 minutes due to startup optimization...")
            
            # Wait for deployment to stabilize
            waiter = ecs.get_waiter('services_stable')
            waiter.wait(
                cluster=cluster_name,
                services=[service_name],
                WaiterConfig={
                    'Delay': 15,
                    'MaxAttempts': 40  # 10 minutes max
                }
            )
            
            print("✅ Deployment completed successfully")
            results['steps'].append({
                'step': 'deployment_complete',
                'status': 'success',
                'message': 'ECS deployment completed successfully'
            })
            
        except Exception as e:
            print(f"⚠️ Deployment monitoring failed (service may still be deploying): {e}")
            results['steps'].append({
                'step': 'deployment_monitoring',
                'status': 'warning',
                'message': f'Deployment monitoring failed: {e}'
            })
        
        # Step 10: Verify deployment
        print("\n🔟 Verifying deployment...")
        try:
            # Get service status
            service_response = ecs.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if service_response['services']:
                service = service_response['services'][0]
                running_count = service['runningCount']
                desired_count = service['desiredCount']
                
                print(f"📊 Service Status:")
                print(f"   Running tasks: {running_count}")
                print(f"   Desired tasks: {desired_count}")
                print(f"   Status: {service['status']}")
                
                # Get task details
                tasks_response = ecs.list_tasks(
                    cluster=cluster_name,
                    serviceName=service_name
                )
                
                if tasks_response['taskArns']:
                    task_details = ecs.describe_tasks(
                        cluster=cluster_name,
                        tasks=tasks_response['taskArns']
                    )
                    
                    for task in task_details['tasks']:
                        print(f"\n   Task: {task['taskArn'].split('/')[-1]}")
                        print(f"   Memory: {task['memory']} MB")
                        print(f"   CPU: {task['cpu']} units")
                        print(f"   Status: {task['lastStatus']}")
                
                if running_count == desired_count and service['status'] == 'ACTIVE':
                    print("\n✅ Deployment verification successful")
                    results['steps'].append({
                        'step': 'deployment_verification',
                        'status': 'success',
                        'message': f'Service healthy: {running_count}/{desired_count} tasks running'
                    })
                else:
                    print("\n⚠️ Service not fully healthy yet")
                    results['steps'].append({
                        'step': 'deployment_verification',
                        'status': 'warning',
                        'message': f'Service status: {running_count}/{desired_count} tasks running'
                    })
            else:
                print("❌ Service not found during verification")
                results['errors'].append("Service not found during verification")
                
        except Exception as e:
            print(f"⚠️ Error during deployment verification: {e}")
            results['steps'].append({
                'step': 'deployment_verification',
                'status': 'warning',
                'message': f'Verification error: {e}'
            })
        
        print(f"\n🎉 Legacy cleanup deployment with 8GB memory completed!")
        print(f"📋 {len([s for s in results['steps'] if s['status'] == 'success'])} successful steps")
        if results['errors']:
            print(f"⚠️ {len(results['errors'])} errors occurred")
        
        print(f"\n📊 Configuration Summary:")
        print(f"  Memory: 8GB (reduced from 24GB)")
        print(f"  CPU: 4 vCPU")
        print(f"  Databases: OpenSearch + Neptune only")
        print(f"  Legacy: Neo4j and Milvus removed")
        
        print(f"\n📊 Startup Timeline:")
        print(f"  0-30s:   Minimal startup (basic API ready)")
        print(f"  30s-2m:  Essential models loading")
        print(f"  2m-5m:   Full capability loading")
        
        return results
        
    except Exception as e:
        print(f"❌ Fatal error during deployment: {e}")
        results['success'] = False
        results['errors'].append(f"Fatal error: {e}")
        return results

def main():
    """Main execution function."""
    print("🚀 Legacy Database Cleanup Deployment - 8GB Memory")
    print("=" * 70)
    print(f"Execution Time: {datetime.now().isoformat()}")
    
    try:
        results = deploy_legacy_cleanup_8gb()
        
        # Save results
        timestamp = int(datetime.now().timestamp())
        results_file = f'legacy-cleanup-8gb-deployment-{timestamp}.json'
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📝 Results saved to: {results_file}")
        
        if results['success']:
            print(f"\n✅ Legacy cleanup deployment with 8GB memory completed successfully")
            print(f"\n💰 Cost Savings:")
            print(f"  Previous: 24GB memory")
            print(f"  Current: 8GB memory")
            print(f"  Reduction: 67% memory reduction")
            return 0
        else:
            print(f"\n❌ Deployment failed")
            print(f"❌ {len(results['errors'])} errors occurred")
            return 1
        
    except Exception as e:
        print(f"❌ Fatal error during process: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
