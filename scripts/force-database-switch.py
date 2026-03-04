#!/usr/bin/env python3
"""
Force switch to old database by updating service with correct task definition
"""

import boto3
import json
import time

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
TASK_DEF_ARN = 'arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:52'

ecs = boto3.client('ecs', region_name=REGION)

print("🔄 Forcing service update to task definition 52...")
print(f"   Task Definition: {TASK_DEF_ARN}")

response = ecs.update_service(
    cluster=CLUSTER_NAME,
    service=SERVICE_NAME,
    taskDefinition=TASK_DEF_ARN,
    forceNewDeployment=True,
    healthCheckGracePeriodSeconds=300  # Give it 5 minutes to stabilize
)

print("✅ Service update initiated")
print(f"\n📊 Deployment details:")
print(f"   Service: {response['service']['serviceName']}")
print(f"   Task Definition: {response['service']['taskDefinition']}")
print(f"   Desired Count: {response['service']['desiredCount']}")

print("\n⏳ Monitoring deployment...")
for i in range(30):  # Monitor for 5 minutes
    time.sleep(10)
    
    svc_response = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    service = svc_response['services'][0]
    deployments = service['deployments']
    
    print(f"\n[{i+1}/30] Deployments:")
    for dep in deployments:
        task_def = dep['taskDefinition'].split('/')[-1]
        print(f"   {dep['status']}: {task_def} - Running: {dep['runningCount']}/{dep['desiredCount']}")
    
    # Check if deployment is complete
    if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
        if deployments[0]['runningCount'] == deployments[0]['desiredCount']:
            print("\n✅ Deployment completed!")
            break

print("\n✅ Done!")
