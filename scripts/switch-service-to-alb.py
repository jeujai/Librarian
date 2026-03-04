#!/usr/bin/env python3
"""
Switch ECS service from NLB to ALB
"""

import boto3
import json
import time
from datetime import datetime

def switch_to_alb():
    """Switch ECS service to use ALB instead of NLB"""
    
    ecs = boto3.client('ecs')
    elbv2 = boto3.client('elbv2')
    
    cluster = 'multimodal-lib-prod-cluster'
    service = 'multimodal-lib-prod-service'
    alb_tg_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-alb-tg/8f7b59ea06a035bf'
    
    print(f"Switching service to ALB...")
    print(f"Cluster: {cluster}")
    print(f"Service: {service}")
    print(f"Target Group: {alb_tg_arn}")
    print()
    
    # Update service to use ALB
    print("Updating ECS service...")
    response = ecs.update_service(
        cluster=cluster,
        service=service,
        loadBalancers=[
            {
                'targetGroupArn': alb_tg_arn,
                'containerName': 'multimodal-lib-prod-app',
                'containerPort': 8000
            }
        ],
        healthCheckGracePeriodSeconds=300,
        forceNewDeployment=True
    )
    
    print("✅ Service update initiated")
    print(f"Deployment ID: {response['service']['deployments'][0]['id']}")
    print()
    
    # Monitor deployment
    print("Monitoring deployment...")
    for i in range(60):  # Monitor for up to 10 minutes
        time.sleep(10)
        
        # Get service status
        service_resp = ecs.describe_services(
            cluster=cluster,
            services=[service]
        )
        
        service_data = service_resp['services'][0]
        deployments = service_data['deployments']
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Deployment Status:")
        for dep in deployments:
            print(f"  - Status: {dep['status']}")
            print(f"    Running: {dep['runningCount']}/{dep['desiredCount']}")
            if dep['rolloutState']:
                print(f"    Rollout: {dep['rolloutState']}")
        
        # Check target health
        try:
            health_resp = elbv2.describe_target_health(
                TargetGroupArn=alb_tg_arn
            )
            
            if health_resp['TargetHealthDescriptions']:
                print(f"\n  Target Health:")
                for target in health_resp['TargetHealthDescriptions']:
                    state = target['TargetHealth']['State']
                    reason = target['TargetHealth'].get('Reason', 'N/A')
                    print(f"    - {target['Target']['Id']}: {state} ({reason})")
            else:
                print(f"\n  No targets registered yet")
        except Exception as e:
            print(f"\n  Error checking target health: {e}")
        
        # Check if deployment is complete
        if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
            if deployments[0]['runningCount'] == deployments[0]['desiredCount']:
                print("\n✅ Deployment complete!")
                break
    
    # Final status check
    print("\n" + "="*60)
    print("FINAL STATUS")
    print("="*60)
    
    # Check target health
    health_resp = elbv2.describe_target_health(
        TargetGroupArn=alb_tg_arn
    )
    
    if health_resp['TargetHealthDescriptions']:
        print("\nTarget Health:")
        for target in health_resp['TargetHealthDescriptions']:
            state = target['TargetHealth']['State']
            reason = target['TargetHealth'].get('Reason', 'N/A')
            print(f"  - {target['Target']['Id']}: {state}")
            if reason != 'N/A':
                print(f"    Reason: {reason}")
    else:
        print("\n❌ No targets registered")
    
    # Test ALB
    print("\nTesting ALB connectivity...")
    alb_dns = "multimodal-lib-prod-alb-1415728107.us-east-1.elb.amazonaws.com"
    print(f"ALB DNS: {alb_dns}")
    print(f"\nTest with: curl http://{alb_dns}/api/health/simple")
    
    return {
        "status": "complete",
        "alb_dns": alb_dns,
        "target_group": alb_tg_arn
    }

if __name__ == "__main__":
    result = switch_to_alb()
    
    # Save results
    timestamp = int(time.time())
    filename = f"alb-switch-{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\nResults saved to: {filename}")
