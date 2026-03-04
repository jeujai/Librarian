#!/usr/bin/env python3
"""
Test if the ALB can actually reach the container's health check endpoint.
This will test the full path: ALB → Target Group → ECS Task → Container → Health Endpoint
"""

import boto3
import json
import time
import requests

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
TARGET_GROUP_ARN = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34'

ecs = boto3.client('ecs', region_name=REGION)
elbv2 = boto3.client('elbv2', region_name=REGION)
ec2 = boto3.client('ec2', region_name=REGION)

def get_target_group_config():
    """Get target group health check configuration"""
    print("=" * 70)
    print("TARGET GROUP HEALTH CHECK CONFIGURATION")
    print("=" * 70)
    
    response = elbv2.describe_target_groups(TargetGroupArns=[TARGET_GROUP_ARN])
    tg = response['TargetGroups'][0]
    
    print(f"\n📋 Target Group: {tg['TargetGroupName']}")
    print(f"   Health Check Path: {tg['HealthCheckPath']}")
    print(f"   Health Check Port: {tg['HealthCheckPort']}")
    print(f"   Health Check Protocol: {tg['HealthCheckProtocol']}")
    print(f"   Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
    print(f"   Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    print(f"   Healthy Threshold: {tg['HealthyThresholdCount']}")
    print(f"   Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
    
    return tg

def get_target_health():
    """Get current target health status"""
    print("\n" + "=" * 70)
    print("CURRENT TARGET HEALTH STATUS")
    print("=" * 70)
    
    response = elbv2.describe_target_health(TargetGroupArn=TARGET_GROUP_ARN)
    
    print(f"\n📊 Registered Targets: {len(response['TargetHealthDescriptions'])}")
    
    for target in response['TargetHealthDescriptions']:
        ip = target['Target']['Id']
        port = target['Target']['Port']
        state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', 'N/A')
        description = target['TargetHealth'].get('Description', 'N/A')
        
        status_icon = "✅" if state == "healthy" else "❌" if state == "unhealthy" else "⏳"
        
        print(f"\n   {status_icon} Target: {ip}:{port}")
        print(f"      State: {state}")
        print(f"      Reason: {reason}")
        print(f"      Description: {description}")
    
    return response['TargetHealthDescriptions']

def test_direct_container_access():
    """Test direct access to container IP (if possible from this machine)"""
    print("\n" + "=" * 70)
    print("TEST 1: DIRECT CONTAINER ACCESS")
    print("=" * 70)
    
    # Get running tasks
    tasks = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='RUNNING'
    )
    
    if not tasks['taskArns']:
        print("❌ No running tasks found")
        return
    
    # Get task details
    task_details = ecs.describe_tasks(
        cluster=CLUSTER_NAME,
        tasks=[tasks['taskArns'][0]]
    )
    
    task = task_details['tasks'][0]
    
    # Get ENI
    for attachment in task['attachments']:
        if attachment['type'] == 'ElasticNetworkInterface':
            for detail in attachment['details']:
                if detail['name'] == 'privateIPv4Address':
                    container_ip = detail['value']
                    
                    print(f"\n🔍 Container IP: {container_ip}")
                    print(f"   Testing: http://{container_ip}:8000/health/simple")
                    
                    try:
                        response = requests.get(
                            f'http://{container_ip}:8000/health/simple',
                            timeout=5
                        )
                        print(f"   ✅ SUCCESS: HTTP {response.status_code}")
                        print(f"   Response: {response.text[:200]}")
                    except requests.exceptions.Timeout:
                        print(f"   ❌ TIMEOUT: Request timed out after 5 seconds")
                    except requests.exceptions.ConnectionError as e:
                        print(f"   ❌ CONNECTION ERROR: {str(e)}")
                    except Exception as e:
                        print(f"   ❌ ERROR: {str(e)}")

def check_security_groups():
    """Check security group rules between ALB and ECS tasks"""
    print("\n" + "=" * 70)
    print("TEST 2: SECURITY GROUP RULES")
    print("=" * 70)
    
    # Get ALB security group
    response = elbv2.describe_load_balancers(
        LoadBalancerArns=[
            'arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-lib-prod-alb-v2/5964a1d711ab8dfe'
        ]
    )
    alb_sg = response['LoadBalancers'][0]['SecurityGroups'][0]
    
    print(f"\n🔒 ALB Security Group: {alb_sg}")
    
    # Get ECS task security group
    service = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    ecs_sg = service['services'][0]['networkConfiguration']['awsvpcConfiguration']['securityGroups'][0]
    
    print(f"🔒 ECS Task Security Group: {ecs_sg}")
    
    # Check ECS SG ingress rules
    print(f"\n🔍 Checking if ECS SG allows traffic from ALB SG on port 8000...")
    
    sg_details = ec2.describe_security_groups(GroupIds=[ecs_sg])
    ingress_rules = sg_details['SecurityGroups'][0]['IpPermissions']
    
    allows_alb = False
    for rule in ingress_rules:
        if rule.get('FromPort') == 8000 or rule.get('ToPort') == 8000:
            sources = []
            if rule.get('UserIdGroupPairs'):
                sources = [pair['GroupId'] for pair in rule['UserIdGroupPairs']]
            if rule.get('IpRanges'):
                sources.extend([r['CidrIp'] for r in rule['IpRanges']])
            
            print(f"   Port 8000 rule found:")
            print(f"   Sources: {', '.join(sources)}")
            
            if alb_sg in sources or '0.0.0.0/0' in sources:
                allows_alb = True
                print(f"   ✅ ALB security group IS allowed!")
    
    if not allows_alb:
        print(f"   ❌ ALB security group is NOT allowed on port 8000!")
        print(f"   This is likely the problem!")

def check_alb_listener_rules():
    """Check ALB listener rules"""
    print("\n" + "=" * 70)
    print("TEST 3: ALB LISTENER RULES")
    print("=" * 70)
    
    # Get ALB
    alb_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-lib-prod-alb-v2/5964a1d711ab8dfe'
    
    # Get listeners
    listeners = elbv2.describe_listeners(LoadBalancerArn=alb_arn)
    
    print(f"\n📋 ALB Listeners: {len(listeners['Listeners'])}")
    
    for listener in listeners['Listeners']:
        print(f"\n   Listener: {listener['ListenerArn'].split('/')[-1]}")
        print(f"   Protocol: {listener['Protocol']}")
        print(f"   Port: {listener['Port']}")
        print(f"   Default Actions:")
        
        for action in listener['DefaultActions']:
            if action['Type'] == 'forward':
                tg_arn = action['TargetGroupArn']
                tg_name = tg_arn.split('/')[-2]
                print(f"      → Forward to: {tg_name}")

def test_alb_endpoint():
    """Test the ALB endpoint directly"""
    print("\n" + "=" * 70)
    print("TEST 4: ALB ENDPOINT ACCESS")
    print("=" * 70)
    
    alb_dns = 'multimodal-lib-prod-alb-v2-1090291461.us-east-1.elb.amazonaws.com'
    
    print(f"\n🔍 Testing ALB endpoint: http://{alb_dns}/health/simple")
    
    try:
        response = requests.get(
            f'http://{alb_dns}/health/simple',
            timeout=30
        )
        print(f"   ✅ SUCCESS: HTTP {response.status_code}")
        print(f"   Response: {response.text[:200]}")
    except requests.exceptions.Timeout:
        print(f"   ❌ TIMEOUT: Request timed out after 30 seconds")
        print(f"   This suggests the ALB cannot reach the targets")
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ CONNECTION ERROR: {str(e)}")
    except Exception as e:
        print(f"   ❌ ERROR: {str(e)}")

def main():
    print("=" * 70)
    print("ALB → CONTAINER CONNECTIVITY TEST")
    print("=" * 70)
    print("\nThis script will test the full path:")
    print("ALB → Target Group → ECS Task → Container → Health Endpoint")
    
    try:
        tg_config = get_target_group_config()
        target_health = get_target_health()
        check_security_groups()
        check_alb_listener_rules()
        test_alb_endpoint()
        test_direct_container_access()
        
        print("\n" + "=" * 70)
        print("DIAGNOSIS COMPLETE")
        print("=" * 70)
        
        # Summary
        unhealthy_count = sum(1 for t in target_health if t['TargetHealth']['State'] != 'healthy')
        
        if unhealthy_count > 0:
            print(f"\n⚠️  {unhealthy_count} unhealthy target(s) detected")
            print("\nMost likely causes:")
            print("1. Security group not allowing ALB → ECS traffic on port 8000")
            print("2. Application not listening on port 8000")
            print("3. Health check path /health/simple not responding")
            print("4. Health check timeout too short")
        else:
            print("\n✅ All targets are healthy!")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
