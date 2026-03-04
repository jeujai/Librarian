#!/usr/bin/env python3
"""
Enable VPC Flow Logs and Diagnose ALB Connectivity

This script:
1. Enables VPC Flow Logs for the VPC to capture rejected traffic
2. Waits for flow logs to accumulate
3. Analyzes the flow logs to identify where packets are being dropped
4. Provides specific recommendations based on findings
"""

import boto3
import json
import time
from datetime import datetime, timedelta

def create_cloudwatch_log_group():
    """Create CloudWatch log group for VPC Flow Logs."""
    print("\n" + "="*80)
    print("STEP 1: Creating CloudWatch Log Group")
    print("="*80)
    
    logs = boto3.client('logs', region_name='us-east-1')
    log_group_name = '/aws/vpc/flowlogs/multimodal-lib-prod'
    
    try:
        # Check if log group already exists
        logs.describe_log_groups(logGroupNamePrefix=log_group_name)
        print(f"\n✅ Log group already exists: {log_group_name}")
        return log_group_name
    except:
        pass
    
    try:
        logs.create_log_group(logGroupName=log_group_name)
        print(f"\n✅ Created log group: {log_group_name}")
        
        # Set retention to 1 day to minimize costs
        logs.put_retention_policy(
            logGroupName=log_group_name,
            retentionInDays=1
        )
        print(f"   Retention: 1 day")
        
        return log_group_name
    except Exception as e:
        print(f"❌ Failed to create log group: {e}")
        return None

def create_iam_role_for_flow_logs():
    """Create IAM role for VPC Flow Logs."""
    print("\n" + "="*80)
    print("STEP 2: Creating IAM Role for Flow Logs")
    print("="*80)
    
    iam = boto3.client('iam', region_name='us-east-1')
    role_name = 'VPCFlowLogsRole-multimodal-lib'
    
    # Check if role already exists
    try:
        role = iam.get_role(RoleName=role_name)
        print(f"\n✅ IAM role already exists: {role_name}")
        return role['Role']['Arn']
    except:
        pass
    
    # Create role
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "vpc-flow-logs.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='Role for VPC Flow Logs to write to CloudWatch'
        )
        print(f"\n✅ Created IAM role: {role_name}")
        
        # Attach policy
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogGroups",
                        "logs:DescribeLogStreams"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName='VPCFlowLogsPolicy',
            PolicyDocument=json.dumps(policy_document)
        )
        print(f"   Attached policy: VPCFlowLogsPolicy")
        
        # Wait for role to be available
        print(f"   Waiting for role to propagate...")
        time.sleep(10)
        
        return role['Role']['Arn']
    except Exception as e:
        print(f"❌ Failed to create IAM role: {e}")
        return None

def enable_vpc_flow_logs(vpc_id, log_group_name, role_arn):
    """Enable VPC Flow Logs."""
    print("\n" + "="*80)
    print("STEP 3: Enabling VPC Flow Logs")
    print("="*80)
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    # Check if flow logs already exist
    try:
        existing_flow_logs = ec2.describe_flow_logs(
            Filters=[
                {'Name': 'resource-id', 'Values': [vpc_id]}
            ]
        )
        
        if existing_flow_logs['FlowLogs']:
            print(f"\n✅ VPC Flow Logs already enabled for {vpc_id}")
            for flow_log in existing_flow_logs['FlowLogs']:
                print(f"   Flow Log ID: {flow_log['FlowLogId']}")
                print(f"   Status: {flow_log['FlowLogStatus']}")
            return existing_flow_logs['FlowLogs'][0]['FlowLogId']
    except Exception as e:
        print(f"⚠️  Error checking existing flow logs: {e}")
    
    # Create flow logs
    try:
        response = ec2.create_flow_logs(
            ResourceType='VPC',
            ResourceIds=[vpc_id],
            TrafficType='ALL',  # Capture all traffic (ACCEPT and REJECT)
            LogDestinationType='cloud-watch-logs',
            LogGroupName=log_group_name,
            DeliverLogsPermissionArn=role_arn,
            LogFormat='${version} ${account-id} ${interface-id} ${srcaddr} ${dstaddr} ${srcport} ${dstport} ${protocol} ${packets} ${bytes} ${start} ${end} ${action} ${log-status}',
            TagSpecifications=[
                {
                    'ResourceType': 'vpc-flow-log',
                    'Tags': [
                        {'Key': 'Name', 'Value': 'multimodal-lib-prod-flow-logs'},
                        {'Key': 'Purpose', 'Value': 'ALB-connectivity-diagnosis'}
                    ]
                }
            ]
        )
        
        if response['Unsuccessful']:
            print(f"❌ Failed to create flow logs: {response['Unsuccessful']}")
            return None
        
        flow_log_id = response['FlowLogIds'][0]
        print(f"\n✅ VPC Flow Logs enabled")
        print(f"   Flow Log ID: {flow_log_id}")
        print(f"   VPC: {vpc_id}")
        print(f"   Log Group: {log_group_name}")
        print(f"   Traffic Type: ALL")
        
        return flow_log_id
    except Exception as e:
        print(f"❌ Failed to enable flow logs: {e}")
        return None

def wait_for_flow_logs(log_group_name, wait_minutes=3):
    """Wait for flow logs to accumulate."""
    print("\n" + "="*80)
    print(f"STEP 4: Waiting for Flow Logs ({wait_minutes} minutes)")
    print("="*80)
    
    print(f"\n⏱️  Waiting {wait_minutes} minutes for flow logs to accumulate...")
    print(f"   Flow logs are published every ~1 minute")
    print(f"   We need at least 2-3 health check cycles to see patterns")
    
    for i in range(wait_minutes):
        time.sleep(60)
        print(f"   [{i+1}/{wait_minutes}] minutes elapsed...")
    
    print(f"\n✅ Wait complete - flow logs should now be available")

def analyze_flow_logs(log_group_name, alb_sg, ecs_sg, task_ip):
    """Analyze flow logs to identify connectivity issues."""
    print("\n" + "="*80)
    print("STEP 5: Analyzing Flow Logs")
    print("="*80)
    
    logs = boto3.client('logs', region_name='us-east-1')
    
    # Query flow logs for the last 5 minutes
    start_time = int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000)
    end_time = int(datetime.now().timestamp() * 1000)
    
    print(f"\n🔍 Querying flow logs...")
    print(f"   Time range: Last 5 minutes")
    print(f"   Target IP: {task_ip}")
    print(f"   Target Port: 8000")
    
    try:
        # Start query
        query = f'''
        fields @timestamp, srcaddr, dstaddr, srcport, dstport, action, protocol
        | filter dstaddr = "{task_ip}" and dstport = 8000
        | sort @timestamp desc
        | limit 100
        '''
        
        query_response = logs.start_query(
            logGroupName=log_group_name,
            startTime=start_time,
            endTime=end_time,
            queryString=query
        )
        
        query_id = query_response['queryId']
        print(f"   Query ID: {query_id}")
        
        # Wait for query to complete
        print(f"   Waiting for query results...")
        for i in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            result = logs.get_query_results(queryId=query_id)
            
            if result['status'] == 'Complete':
                print(f"   ✅ Query complete")
                break
            elif result['status'] == 'Failed':
                print(f"   ❌ Query failed")
                return None
        
        if result['status'] != 'Complete':
            print(f"   ⏱️  Query timeout")
            return None
        
        # Analyze results
        results = result['results']
        print(f"\n📊 Flow Log Analysis:")
        print(f"   Total records found: {len(results)}")
        
        if not results:
            print(f"\n❌ NO FLOW LOGS FOUND for traffic to {task_ip}:8000")
            print(f"\n💡 This means:")
            print(f"   1. ALB is NOT sending traffic to the task")
            print(f"   2. OR traffic is being blocked before reaching the VPC")
            print(f"   3. OR there's a target registration issue")
            return {
                'total_records': 0,
                'accepted': 0,
                'rejected': 0,
                'issue': 'no_traffic'
            }
        
        # Count accepted vs rejected
        accepted = 0
        rejected = 0
        
        print(f"\n📋 Recent Flow Log Entries:")
        for i, record in enumerate(results[:10]):  # Show first 10
            fields = {field['field']: field['value'] for field in record}
            action = fields.get('action', 'UNKNOWN')
            srcaddr = fields.get('srcaddr', 'UNKNOWN')
            srcport = fields.get('srcport', 'UNKNOWN')
            timestamp = fields.get('@timestamp', 'UNKNOWN')
            
            if action == 'ACCEPT':
                accepted += 1
                status_icon = '✅'
            else:
                rejected += 1
                status_icon = '❌'
            
            print(f"   {status_icon} [{timestamp}] {srcaddr}:{srcport} → {task_ip}:8000 ({action})")
        
        print(f"\n📈 Summary:")
        print(f"   ✅ Accepted: {accepted}")
        print(f"   ❌ Rejected: {rejected}")
        
        analysis = {
            'total_records': len(results),
            'accepted': accepted,
            'rejected': rejected
        }
        
        # Determine issue
        if rejected > 0 and accepted == 0:
            analysis['issue'] = 'all_rejected'
            print(f"\n🔴 ISSUE IDENTIFIED: All traffic is being REJECTED")
            print(f"   This indicates a security group or network ACL issue")
        elif accepted > 0 and rejected == 0:
            analysis['issue'] = 'all_accepted'
            print(f"\n🟢 Traffic is being ACCEPTED")
            print(f"   The network path is working correctly")
            print(f"   Issue is likely with the application or health check endpoint")
        elif accepted > 0 and rejected > 0:
            analysis['issue'] = 'mixed'
            print(f"\n🟡 Mixed results: Some traffic accepted, some rejected")
            print(f"   This suggests intermittent connectivity issues")
        
        return analysis
        
    except Exception as e:
        print(f"❌ Error analyzing flow logs: {e}")
        return None

def provide_recommendations(analysis, task_ip):
    """Provide specific recommendations based on flow log analysis."""
    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    
    if not analysis:
        print("\n⚠️  Unable to analyze flow logs")
        print("\n💡 Next Steps:")
        print("   1. Wait a few more minutes for flow logs to accumulate")
        print("   2. Re-run this script to analyze the logs")
        print("   3. Check if ALB is actually sending health check requests")
        return
    
    issue = analysis.get('issue')
    
    if issue == 'no_traffic':
        print("\n🔴 CRITICAL: No traffic reaching the task")
        print("\n💡 Possible Causes:")
        print("   1. Target not properly registered with ALB")
        print("   2. ALB not sending health checks")
        print("   3. Target group configuration issue")
        print("\n🔧 Recommended Actions:")
        print("   1. Check target registration:")
        print(f"      aws elbv2 describe-target-health --target-group-arn <arn>")
        print("   2. Verify ALB listener rules")
        print("   3. Check if ALB is in the correct subnets")
        print("   4. Consider recreating the target group")
    
    elif issue == 'all_rejected':
        print("\n🔴 CRITICAL: All traffic is being REJECTED")
        print("\n💡 Root Cause:")
        print("   Security groups or Network ACLs are blocking traffic")
        print("\n🔧 Recommended Actions:")
        print("   1. Verify ECS security group allows inbound from ALB SG on port 8000")
        print("   2. Check Network ACL rules for the task subnet")
        print("   3. Ensure no deny rules are blocking traffic")
        print("   4. Review security group rule order")
    
    elif issue == 'all_accepted':
        print("\n🟢 GOOD NEWS: Network path is working!")
        print("\n💡 Root Cause:")
        print("   Traffic reaches the task, but application isn't responding correctly")
        print("\n🔧 Recommended Actions:")
        print("   1. Check if application is listening on 0.0.0.0:8000")
        print("   2. Verify health check endpoint exists and returns 200")
        print("   3. Test health endpoint directly:")
        print(f"      curl http://{task_ip}:8000/api/health/simple")
        print("   4. Check application logs for errors")
        print("   5. Verify health check timeout is sufficient (currently 29s)")
    
    elif issue == 'mixed':
        print("\n🟡 WARNING: Intermittent connectivity")
        print("\n💡 Root Cause:")
        print("   Some packets accepted, some rejected - suggests timing or state issues")
        print("\n🔧 Recommended Actions:")
        print("   1. Check for connection tracking issues")
        print("   2. Verify security group stateful rules")
        print("   3. Look for ephemeral port conflicts")
        print("   4. Check if application is overloaded")

def main():
    """Main execution function."""
    print("\n" + "="*80)
    print("VPC FLOW LOGS DIAGNOSTIC TOOL")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    vpc_id = 'vpc-0b2186b38779e77f6'
    alb_sg = 'sg-0135b368e20b7bd01'
    ecs_sg = 'sg-0393d472e770ed1a3'
    
    # Get current task IP
    print("\n🔍 Getting current task IP...")
    ecs = boto3.client('ecs', region_name='us-east-1')
    tasks = ecs.list_tasks(
        cluster='multimodal-lib-prod-cluster',
        serviceName='multimodal-lib-prod-service',
        desiredStatus='RUNNING'
    )
    
    if not tasks['taskArns']:
        print("❌ No running tasks found")
        return
    
    task_details = ecs.describe_tasks(
        cluster='multimodal-lib-prod-cluster',
        tasks=[tasks['taskArns'][0]]
    )
    
    task_ip = None
    for attachment in task_details['tasks'][0].get('attachments', []):
        if attachment['type'] == 'ElasticNetworkInterface':
            for detail in attachment['details']:
                if detail['name'] == 'privateIPv4Address':
                    task_ip = detail['value']
    
    if not task_ip:
        print("❌ Could not determine task IP")
        return
    
    print(f"✅ Task IP: {task_ip}")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'vpc_id': vpc_id,
        'task_ip': task_ip,
        'steps': {}
    }
    
    # Step 1: Create log group
    log_group_name = create_cloudwatch_log_group()
    if not log_group_name:
        print("\n❌ Failed to create log group")
        return
    results['log_group'] = log_group_name
    
    # Step 2: Create IAM role
    role_arn = create_iam_role_for_flow_logs()
    if not role_arn:
        print("\n❌ Failed to create IAM role")
        return
    results['role_arn'] = role_arn
    
    # Step 3: Enable flow logs
    flow_log_id = enable_vpc_flow_logs(vpc_id, log_group_name, role_arn)
    if not flow_log_id:
        print("\n❌ Failed to enable flow logs")
        return
    results['flow_log_id'] = flow_log_id
    
    # Step 4: Wait for logs
    wait_for_flow_logs(log_group_name, wait_minutes=3)
    
    # Step 5: Analyze logs
    analysis = analyze_flow_logs(log_group_name, alb_sg, ecs_sg, task_ip)
    results['analysis'] = analysis
    
    # Step 6: Provide recommendations
    provide_recommendations(analysis, task_ip)
    
    # Save results
    output_file = f"vpc-flow-logs-analysis-{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
    print(f"\n✅ Results saved to: {output_file}")
    print(f"\n📊 Flow logs will continue to be collected in:")
    print(f"   {log_group_name}")
    print(f"\n💰 Cost Note: Flow logs cost ~$0.50 per GB")
    print(f"   Retention set to 1 day to minimize costs")
    print(f"   You can disable flow logs after diagnosis")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
