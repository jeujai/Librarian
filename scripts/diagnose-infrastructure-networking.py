#!/usr/bin/env python3
"""
Comprehensive Infrastructure Network Diagnostic Script

This script performs a systematic diagnosis of the network connectivity
between load balancers and ECS tasks to identify why health checks are failing.

Usage:
    python scripts/diagnose-infrastructure-networking.py > infrastructure-diagnosis-<timestamp>.json
"""

import boto3
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Initialize AWS clients
ecs = boto3.client('ecs', region_name='us-east-1')
ec2 = boto3.client('ec2', region_name='us-east-1')
elbv2 = boto3.client('elbv2', region_name='us-east-1')
logs = boto3.client('logs', region_name='us-east-1')

# Configuration
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service'
VPC_ID = 'vpc-0b2186b38779e77f6'
ALB_SG_ID = 'sg-0135b368e20b7bd01'
ECS_SG_ID = 'sg-0393d472e770ed1a3'
APP_PORT = 8000


def log_step(message: str):
    """Print step to stderr for progress tracking"""
    print(f"[{datetime.now().isoformat()}] {message}", file=sys.stderr)


def check_ecs_task_status() -> Dict[str, Any]:
    """Check ECS task status and get task details"""
    log_step("Checking ECS task status...")
    
    try:
        # List running tasks
        tasks_response = ecs.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            desiredStatus='RUNNING'
        )
        
        if not tasks_response.get('taskArns'):
            return {
                "status": "ERROR",
                "message": "No running tasks found",
                "task_count": 0
            }
        
        task_arns = tasks_response['taskArns']
        
        # Get task details
        tasks_detail = ecs.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=task_arns
        )
        
        task = tasks_detail['tasks'][0]
        
        # Extract task IP
        task_ip = None
        task_eni = None
        for attachment in task.get('attachments', []):
            if attachment['type'] == 'ElasticNetworkInterface':
                for detail in attachment['details']:
                    if detail['name'] == 'privateIPv4Address':
                        task_ip = detail['value']
                    elif detail['name'] == 'networkInterfaceId':
                        task_eni = detail['value']
        
        # Get subnet
        task_subnet = None
        for attachment in task.get('attachments', []):
            for detail in attachment['details']:
                if detail['name'] == 'subnetId':
                    task_subnet = detail['value']
        
        return {
            "status": "OK",
            "task_count": len(task_arns),
            "task_arn": task_arns[0],
            "last_status": task['lastStatus'],
            "health_status": task.get('healthStatus', 'UNKNOWN'),
            "task_ip": task_ip,
            "task_eni": task_eni,
            "task_subnet": task_subnet,
            "started_at": task.get('startedAt', '').isoformat() if task.get('startedAt') else None
        }
    
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


def check_application_health() -> Dict[str, Any]:
    """Check application logs for health and errors"""
    log_step("Checking application logs...")
    
    try:
        log_group = '/ecs/multimodal-lib-prod-app'
        
        # Check for recent Uvicorn startup
        start_time = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
        
        try:
            startup_logs = logs.filter_log_events(
                logGroupName=log_group,
                startTime=start_time,
                filterPattern='Uvicorn running',
                limit=5
            )
            
            has_startup = len(startup_logs.get('events', [])) > 0
        except Exception:
            has_startup = False
        
        # Check for errors
        try:
            error_logs = logs.filter_log_events(
                logGroupName=log_group,
                startTime=start_time,
                filterPattern='ERROR',
                limit=10
            )
            
            error_count = len(error_logs.get('events', []))
            recent_errors = [e['message'] for e in error_logs.get('events', [])[:3]]
        except Exception:
            error_count = 0
            recent_errors = []
        
        # Check for health check requests
        try:
            health_logs = logs.filter_log_events(
                logGroupName=log_group,
                startTime=start_time,
                filterPattern='GET /api/health',
                limit=5
            )
            
            health_check_count = len(health_logs.get('events', []))
        except Exception:
            health_check_count = 0
        
        return {
            "status": "OK",
            "uvicorn_running": has_startup,
            "error_count": error_count,
            "recent_errors": recent_errors,
            "health_check_requests": health_check_count,
            "assessment": "HEALTHY" if has_startup and error_count == 0 else "DEGRADED" if has_startup else "UNHEALTHY"
        }
    
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


def check_security_groups(task_ip: Optional[str]) -> Dict[str, Any]:
    """Check security group rules for ALB and ECS"""
    log_step("Checking security groups...")
    
    try:
        # Get ALB security group
        alb_sg = ec2.describe_security_groups(GroupIds=[ALB_SG_ID])['SecurityGroups'][0]
        
        # Get ECS security group
        ecs_sg = ec2.describe_security_groups(GroupIds=[ECS_SG_ID])['SecurityGroups'][0]
        
        # Check if ALB SG allows outbound to ECS SG on port 8000
        alb_allows_outbound = False
        for rule in alb_sg.get('IpPermissionsEgress', []):
            # Check for all traffic
            if rule.get('IpProtocol') == '-1':
                alb_allows_outbound = True
                break
            # Check for specific port 8000
            if rule.get('IpProtocol') == 'tcp':
                from_port = rule.get('FromPort')
                to_port = rule.get('ToPort')
                if from_port and to_port and from_port <= APP_PORT <= to_port:
                    # Check if it allows to ECS SG or all
                    for group in rule.get('UserIdGroupPairs', []):
                        if group.get('GroupId') == ECS_SG_ID:
                            alb_allows_outbound = True
                            break
                    for cidr in rule.get('IpRanges', []):
                        if cidr.get('CidrIp') == '0.0.0.0/0':
                            alb_allows_outbound = True
                            break
        
        # Check if ECS SG allows inbound from ALB SG on port 8000
        ecs_allows_inbound = False
        for rule in ecs_sg.get('IpPermissions', []):
            # Check for all traffic
            if rule.get('IpProtocol') == '-1':
                ecs_allows_inbound = True
                break
            # Check for specific port 8000
            if rule.get('IpProtocol') == 'tcp':
                from_port = rule.get('FromPort')
                to_port = rule.get('ToPort')
                if from_port and to_port and from_port <= APP_PORT <= to_port:
                    # Check if it allows from ALB SG
                    for group in rule.get('UserIdGroupPairs', []):
                        if group.get('GroupId') == ALB_SG_ID:
                            ecs_allows_inbound = True
                            break
                    for cidr in rule.get('IpRanges', []):
                        if cidr.get('CidrIp') == '0.0.0.0/0':
                            ecs_allows_inbound = True
                            break
        
        issues = []
        if not alb_allows_outbound:
            issues.append({
                "type": "security_group",
                "severity": "HIGH",
                "description": f"ALB security group ({ALB_SG_ID}) does not allow outbound traffic to ECS security group ({ECS_SG_ID}) on port {APP_PORT}",
                "fix": f"aws ec2 authorize-security-group-egress --group-id {ALB_SG_ID} --protocol tcp --port {APP_PORT} --source-group {ECS_SG_ID}"
            })
        
        if not ecs_allows_inbound:
            issues.append({
                "type": "security_group",
                "severity": "HIGH",
                "description": f"ECS security group ({ECS_SG_ID}) does not allow inbound traffic from ALB security group ({ALB_SG_ID}) on port {APP_PORT}",
                "fix": f"aws ec2 authorize-security-group-ingress --group-id {ECS_SG_ID} --protocol tcp --port {APP_PORT} --source-group {ALB_SG_ID}"
            })
        
        return {
            "status": "OK" if not issues else "ISSUES_FOUND",
            "alb_sg_id": ALB_SG_ID,
            "ecs_sg_id": ECS_SG_ID,
            "alb_allows_outbound_to_ecs": alb_allows_outbound,
            "ecs_allows_inbound_from_alb": ecs_allows_inbound,
            "issues": issues
        }
    
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


def check_route_tables(task_subnet: Optional[str]) -> Dict[str, Any]:
    """Check route tables for ALB and ECS subnets"""
    log_step("Checking route tables...")
    
    try:
        # ALB subnets
        alb_subnets = [
            'subnet-0c352188f5398a718',  # us-east-1a
            'subnet-02f4d9ecb751beb27',  # us-east-1b
            'subnet-02fe694f061238d5a'   # us-east-1c
        ]
        
        # Get route tables for ALB subnets
        alb_route_tables = []
        for subnet in alb_subnets:
            rt_response = ec2.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet]}
                ]
            )
            if rt_response['RouteTables']:
                alb_route_tables.append({
                    'subnet': subnet,
                    'route_table_id': rt_response['RouteTables'][0]['RouteTableId'],
                    'routes': rt_response['RouteTables'][0]['Routes']
                })
        
        # Get route table for ECS subnet if available
        ecs_route_table = None
        if task_subnet:
            rt_response = ec2.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [task_subnet]}
                ]
            )
            if rt_response['RouteTables']:
                ecs_route_table = {
                    'subnet': task_subnet,
                    'route_table_id': rt_response['RouteTables'][0]['RouteTableId'],
                    'routes': rt_response['RouteTables'][0]['Routes']
                }
        
        # Check if all subnets are in the same VPC
        all_subnets = alb_subnets + ([task_subnet] if task_subnet else [])
        subnets_info = ec2.describe_subnets(SubnetIds=all_subnets)
        
        vpcs = set(s['VpcId'] for s in subnets_info['Subnets'])
        same_vpc = len(vpcs) == 1 and VPC_ID in vpcs
        
        issues = []
        if not same_vpc:
            issues.append({
                "type": "route_table",
                "severity": "CRITICAL",
                "description": "ALB and ECS subnets are not in the same VPC",
                "fix": "This is a fundamental architecture issue - subnets must be in the same VPC"
            })
        
        return {
            "status": "OK" if not issues else "ISSUES_FOUND",
            "alb_route_tables": alb_route_tables,
            "ecs_route_table": ecs_route_table,
            "same_vpc": same_vpc,
            "vpc_id": VPC_ID,
            "issues": issues
        }
    
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


def check_network_acls(task_subnet: Optional[str]) -> Dict[str, Any]:
    """Check Network ACLs for blocking rules"""
    log_step("Checking Network ACLs...")
    
    try:
        # Get NACLs for VPC
        nacls_response = ec2.describe_network_acls(
            Filters=[
                {'Name': 'vpc-id', 'Values': [VPC_ID]}
            ]
        )
        
        nacls = nacls_response['NetworkAcls']
        
        # Check for deny rules on port 8000
        blocking_rules = []
        for nacl in nacls:
            for entry in nacl['Entries']:
                # Check if rule denies traffic on port 8000
                if not entry.get('RuleAction') == 'deny':
                    continue
                
                protocol = entry.get('Protocol')
                port_range = entry.get('PortRange', {})
                from_port = port_range.get('From')
                to_port = port_range.get('To')
                
                # Protocol -1 means all protocols
                # Protocol 6 means TCP
                if protocol in ['-1', '6']:
                    if protocol == '-1' or (from_port and to_port and from_port <= APP_PORT <= to_port):
                        blocking_rules.append({
                            'nacl_id': nacl['NetworkAclId'],
                            'rule_number': entry['RuleNumber'],
                            'egress': entry['Egress'],
                            'cidr': entry.get('CidrBlock', entry.get('Ipv6CidrBlock')),
                            'protocol': protocol,
                            'port_range': f"{from_port}-{to_port}" if from_port else "all"
                        })
        
        issues = []
        if blocking_rules:
            for rule in blocking_rules:
                issues.append({
                    "type": "nacl",
                    "severity": "HIGH",
                    "description": f"NACL {rule['nacl_id']} has deny rule {rule['rule_number']} that may block port {APP_PORT}",
                    "fix": f"Review and modify NACL rule: aws ec2 delete-network-acl-entry --network-acl-id {rule['nacl_id']} --rule-number {rule['rule_number']} --{'egress' if rule['egress'] else 'ingress'}"
                })
        
        return {
            "status": "OK" if not issues else "ISSUES_FOUND",
            "nacl_count": len(nacls),
            "blocking_rules": blocking_rules,
            "issues": issues
        }
    
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


def check_vpc_flow_logs(task_ip: Optional[str], task_eni: Optional[str]) -> Dict[str, Any]:
    """Check VPC Flow Logs for traffic evidence"""
    log_step("Checking VPC Flow Logs...")
    
    try:
        # Check if flow logs are enabled
        flow_logs_response = ec2.describe_flow_logs(
            Filters=[
                {'Name': 'resource-id', 'Values': [VPC_ID]}
            ]
        )
        
        flow_logs_enabled = len(flow_logs_response['FlowLogs']) > 0
        
        if not flow_logs_enabled:
            return {
                "status": "NOT_ENABLED",
                "message": "VPC Flow Logs are not enabled",
                "recommendation": "Enable VPC Flow Logs to monitor traffic"
            }
        
        flow_log = flow_logs_response['FlowLogs'][0]
        log_group = flow_log.get('LogDestination', '').split(':')[-1]
        
        # Try to query recent flow logs if task IP is available
        packets_seen = 0
        if task_ip and log_group:
            try:
                start_time = int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000)
                
                # Query for traffic to task IP on port 8000
                filter_pattern = f'[version, account, eni, source, destination="{task_ip}", srcport, destport="8000", ...]'
                
                events = logs.filter_log_events(
                    logGroupName=log_group,
                    startTime=start_time,
                    filterPattern=filter_pattern,
                    limit=100
                )
                
                packets_seen = len(events.get('events', []))
            except Exception as e:
                # Log group might not exist yet or no permissions
                pass
        
        return {
            "status": "ENABLED",
            "flow_log_id": flow_log['FlowLogId'],
            "log_group": log_group,
            "packets_seen_last_5min": packets_seen,
            "traffic_detected": packets_seen > 0
        }
    
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


def check_load_balancers() -> Dict[str, Any]:
    """Check load balancer configuration"""
    log_step("Checking load balancers...")
    
    try:
        # List all load balancers
        lbs_response = elbv2.describe_load_balancers()
        
        # Filter for our load balancers
        our_lbs = [lb for lb in lbs_response['LoadBalancers'] 
                   if 'multimodal-lib-prod' in lb['LoadBalancerName']]
        
        lb_details = []
        for lb in our_lbs:
            # Get target groups
            tgs_response = elbv2.describe_target_groups(
                LoadBalancerArn=lb['LoadBalancerArn']
            )
            
            tg_health = []
            for tg in tgs_response['TargetGroups']:
                health_response = elbv2.describe_target_health(
                    TargetGroupArn=tg['TargetGroupArn']
                )
                
                tg_health.append({
                    'target_group_name': tg['TargetGroupName'],
                    'target_group_arn': tg['TargetGroupArn'],
                    'port': tg['Port'],
                    'protocol': tg['Protocol'],
                    'health_check_path': tg.get('HealthCheckPath'),
                    'targets': [{
                        'id': t['Target']['Id'],
                        'port': t['Target']['Port'],
                        'health': t['TargetHealth']['State'],
                        'reason': t['TargetHealth'].get('Reason', 'N/A')
                    } for t in health_response['TargetHealthDescriptions']]
                })
            
            lb_details.append({
                'name': lb['LoadBalancerName'],
                'arn': lb['LoadBalancerArn'],
                'dns_name': lb['DNSName'],
                'type': lb['Type'],
                'scheme': lb['Scheme'],
                'state': lb['State']['Code'],
                'vpc_id': lb['VpcId'],
                'subnets': [az['SubnetId'] for az in lb['AvailabilityZones']],
                'target_groups': tg_health
            })
        
        return {
            "status": "OK",
            "load_balancer_count": len(lb_details),
            "load_balancers": lb_details
        }
    
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


def generate_recommendation(checks: Dict[str, Any]) -> Dict[str, Any]:
    """Generate recommendation based on diagnostic findings"""
    log_step("Generating recommendation...")
    
    all_issues = []
    
    # Collect all issues
    for check_name, check_result in checks.items():
        if isinstance(check_result, dict) and 'issues' in check_result:
            all_issues.extend(check_result['issues'])
    
    if not all_issues:
        # No configuration issues found
        return {
            "status": "NO_CONFIG_ISSUES",
            "recommendation": "No configuration issues found in security groups, route tables, or NACLs. The issue may be:",
            "possible_causes": [
                "AWS service-level issue with load balancer",
                "Application not actually listening on port 8000",
                "ECS task networking issue",
                "Transient network problem"
            ],
            "next_steps": [
                "Verify application is listening: Check application logs for 'Uvicorn running on 0.0.0.0:8000'",
                "Test direct connectivity if possible (bastion host)",
                "Consider recreating load balancer (original plan)",
                "Open AWS support case if issue persists"
            ]
        }
    
    # Sort issues by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_issues.sort(key=lambda x: severity_order.get(x.get('severity', 'LOW'), 99))
    
    primary_issue = all_issues[0]
    
    return {
        "status": "ISSUES_FOUND",
        "issue_count": len(all_issues),
        "primary_issue": primary_issue,
        "all_issues": all_issues,
        "recommendation": f"Fix {primary_issue['type']} issue: {primary_issue['description']}",
        "immediate_action": primary_issue.get('fix', 'See issue details for fix'),
        "next_steps": [
            "Implement the recommended fix",
            "Monitor VPC Flow Logs for traffic",
            "Check target health status",
            "Verify application logs show incoming requests"
        ]
    }


def main():
    """Main diagnostic function"""
    log_step("Starting comprehensive infrastructure network diagnostic...")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "diagnostic_version": "1.0",
        "configuration": {
            "cluster": CLUSTER_NAME,
            "service": SERVICE_NAME,
            "vpc_id": VPC_ID,
            "alb_sg_id": ALB_SG_ID,
            "ecs_sg_id": ECS_SG_ID,
            "app_port": APP_PORT
        },
        "checks": {}
    }
    
    # Run all checks
    report["checks"]["ecs_task"] = check_ecs_task_status()
    
    task_ip = report["checks"]["ecs_task"].get("task_ip")
    task_eni = report["checks"]["ecs_task"].get("task_eni")
    task_subnet = report["checks"]["ecs_task"].get("task_subnet")
    
    report["checks"]["application"] = check_application_health()
    report["checks"]["security_groups"] = check_security_groups(task_ip)
    report["checks"]["route_tables"] = check_route_tables(task_subnet)
    report["checks"]["network_acls"] = check_network_acls(task_subnet)
    report["checks"]["vpc_flow_logs"] = check_vpc_flow_logs(task_ip, task_eni)
    report["checks"]["load_balancers"] = check_load_balancers()
    
    # Generate recommendation
    report["recommendation"] = generate_recommendation(report["checks"])
    
    # Output report as JSON
    print(json.dumps(report, indent=2, default=str))
    
    log_step("Diagnostic complete!")
    
    # Return exit code based on findings
    if report["recommendation"]["status"] == "ISSUES_FOUND":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
