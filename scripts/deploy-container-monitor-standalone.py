#!/usr/bin/env python3
"""
Standalone deployment script for container failure monitor.
Deploys only the Lambda function and SNS topic without modifying existing infrastructure.
"""

import boto3
import json
import zipfile
import io
import sys
import time
from pathlib import Path

def create_lambda_zip():
    """Create a zip file containing the Lambda function code."""
    lambda_code_path = Path("infrastructure/aws-native/lambda/container_failure_monitor.py")
    
    if not lambda_code_path.exists():
        print(f"❌ Lambda function code not found at {lambda_code_path}")
        sys.exit(1)
    
    # Create zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(lambda_code_path, 'container_failure_monitor.py')
    
    zip_buffer.seek(0)
    return zip_buffer.read()

def deploy_container_failure_monitor(email_address, cluster_name="multimodal-lib-prod-cluster", 
                                     service_name="multimodal-lib-prod-service"):
    """Deploy the container failure monitor Lambda function."""
    
    # AWS clients
    iam = boto3.client('iam')
    lambda_client = boto3.client('lambda')
    sns = boto3.client('sns')
    events = boto3.client('events')
    logs = boto3.client('logs')
    
    function_name = "container-failure-monitor"
    role_name = "container-failure-monitor-role"
    topic_name = "container-failure-alerts"
    rule_name = "container-failure-monitor-schedule"
    
    print("=" * 80)
    print("DEPLOYING CONTAINER FAILURE MONITOR")
    print("=" * 80)
    print()
    
    # Step 1: Create SNS Topic
    print("1. Creating SNS topic for alerts...")
    try:
        topic_response = sns.create_topic(Name=topic_name)
        topic_arn = topic_response['TopicArn']
        print(f"✓ SNS topic created: {topic_arn}")
        
        # Subscribe email if provided
        if email_address:
            sns.subscribe(
                TopicArn=topic_arn,
                Protocol='email',
                Endpoint=email_address
            )
            print(f"✓ Email subscription created for {email_address}")
            print("  ⚠️  Check your email to confirm the subscription!")
    except Exception as e:
        print(f"❌ Failed to create SNS topic: {e}")
        sys.exit(1)
    
    # Step 2: Create IAM Role
    print("\n2. Creating IAM role for Lambda...")
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }
    
    try:
        role_response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="Role for container failure monitor Lambda"
        )
        role_arn = role_response['Role']['Arn']
        print(f"✓ IAM role created: {role_arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        role_response = iam.get_role(RoleName=role_name)
        role_arn = role_response['Role']['Arn']
        print(f"✓ Using existing IAM role: {role_arn}")
    except Exception as e:
        print(f"❌ Failed to create IAM role: {e}")
        sys.exit(1)
    
    # Step 3: Attach policies to role
    print("\n3. Attaching policies to IAM role...")
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ecs:ListTasks",
                    "ecs:DescribeTasks",
                    "ecs:DescribeTaskDefinition"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": ["sns:Publish"],
                "Resource": topic_arn
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "arn:aws:logs:*:*:*"
            }
        ]
    }
    
    try:
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{role_name}-policy",
            PolicyDocument=json.dumps(policy_document)
        )
        print("✓ Policies attached to role")
    except Exception as e:
        print(f"❌ Failed to attach policies: {e}")
        sys.exit(1)
    
    # Wait for role to propagate
    print("  Waiting for IAM role to propagate...")
    time.sleep(10)
    
    # Step 4: Create Lambda function
    print("\n4. Creating Lambda function...")
    lambda_zip = create_lambda_zip()
    
    try:
        lambda_response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python3.11',
            Role=role_arn,
            Handler='container_failure_monitor.lambda_handler',
            Code={'ZipFile': lambda_zip},
            Description='Monitors ECS tasks for container-level failures',
            Timeout=60,
            MemorySize=256,
            Environment={
                'Variables': {
                    'ECS_CLUSTER_NAME': cluster_name,
                    'ECS_SERVICE_NAME': service_name,
                    'SNS_TOPIC_ARN': topic_arn,
                    'CHECK_WINDOW_MINUTES': '5'
                }
            }
        )
        function_arn = lambda_response['FunctionArn']
        print(f"✓ Lambda function created: {function_arn}")
    except lambda_client.exceptions.ResourceConflictException:
        # Update existing function
        lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=lambda_zip
        )
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Runtime='python3.11',
            Role=role_arn,
            Handler='container_failure_monitor.lambda_handler',
            Timeout=60,
            MemorySize=256,
            Environment={
                'Variables': {
                    'ECS_CLUSTER_NAME': cluster_name,
                    'ECS_SERVICE_NAME': service_name,
                    'SNS_TOPIC_ARN': topic_arn,
                    'CHECK_WINDOW_MINUTES': '5'
                }
            }
        )
        function_response = lambda_client.get_function(FunctionName=function_name)
        function_arn = function_response['Configuration']['FunctionArn']
        print(f"✓ Lambda function updated: {function_arn}")
    except Exception as e:
        print(f"❌ Failed to create Lambda function: {e}")
        sys.exit(1)
    
    # Step 5: Create CloudWatch Log Group
    print("\n5. Creating CloudWatch log group...")
    log_group_name = f"/aws/lambda/{function_name}"
    try:
        logs.create_log_group(logGroupName=log_group_name)
        logs.put_retention_policy(logGroupName=log_group_name, retentionInDays=7)
        print(f"✓ Log group created: {log_group_name}")
    except logs.exceptions.ResourceAlreadyExistsException:
        print(f"✓ Using existing log group: {log_group_name}")
    except Exception as e:
        print(f"⚠️  Warning: Could not create log group: {e}")
    
    # Step 6: Create EventBridge rule
    print("\n6. Creating EventBridge schedule rule...")
    try:
        events.put_rule(
            Name=rule_name,
            Description="Trigger container failure monitor every 5 minutes",
            ScheduleExpression="rate(5 minutes)",
            State='ENABLED'
        )
        print(f"✓ EventBridge rule created: {rule_name}")
    except Exception as e:
        print(f"❌ Failed to create EventBridge rule: {e}")
        sys.exit(1)
    
    # Step 7: Add Lambda permission for EventBridge
    print("\n7. Adding Lambda permission for EventBridge...")
    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId='AllowEventBridgeInvoke',
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=f"arn:aws:events:{boto3.session.Session().region_name}:{boto3.client('sts').get_caller_identity()['Account']}:rule/{rule_name}"
        )
        print("✓ Lambda permission added")
    except lambda_client.exceptions.ResourceConflictException:
        print("✓ Lambda permission already exists")
    except Exception as e:
        print(f"❌ Failed to add Lambda permission: {e}")
        sys.exit(1)
    
    # Step 8: Add target to EventBridge rule
    print("\n8. Adding Lambda as target to EventBridge rule...")
    try:
        events.put_targets(
            Rule=rule_name,
            Targets=[{
                'Id': '1',
                'Arn': function_arn
            }]
        )
        print("✓ Lambda added as EventBridge target")
    except Exception as e:
        print(f"❌ Failed to add EventBridge target: {e}")
        sys.exit(1)
    
    # Summary
    print("\n" + "=" * 80)
    print("DEPLOYMENT COMPLETE!")
    print("=" * 80)
    print()
    print("📋 Summary:")
    print(f"  • Lambda Function: {function_name}")
    print(f"  • SNS Topic: {topic_arn}")
    print(f"  • Schedule: Every 5 minutes")
    print(f"  • Monitoring Cluster: {cluster_name}")
    print(f"  • Monitoring Service: {service_name}")
    if email_address:
        print(f"  • Email Alerts: {email_address} (check your email to confirm!)")
    print()
    print("🔍 The Lambda function will check for container failures every 5 minutes.")
    print("   You'll receive SNS alerts when OOM kills, segfaults, or other failures are detected.")
    print()
    print("📊 View logs:")
    print(f"   aws logs tail {log_group_name} --follow")
    print()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy container failure monitor")
    parser.add_argument("--email", help="Email address for alerts", required=True)
    parser.add_argument("--cluster", default="multimodal-lib-prod-cluster", help="ECS cluster name")
    parser.add_argument("--service", default="multimodal-lib-prod-service", help="ECS service name")
    
    args = parser.parse_args()
    
    deploy_container_failure_monitor(args.email, args.cluster, args.service)
