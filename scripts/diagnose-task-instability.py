#!/usr/bin/env python3
"""
Diagnose Task Instability

This script investigates why ECS tasks keep failing and provides a comprehensive
diagnosis of the root causes.
"""

import json
import boto3
import sys
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
REGION = "us-east-1"


def get_recent_stopped_tasks(limit=10):
    """Get recently stopped tasks to analyze failure patterns."""
    try:
        ecs_client = boto3.client('ecs', region_name=REGION)
        
        logger.info(f"Fetching last {limit} stopped tasks...")
        
        # List stopped tasks
        response = ecs_client.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            desiredStatus='STOPPED',
            maxResults=limit
        )
        
        if not response['taskArns']:
            logger.warning("No stopped tasks found")
            return []
        
        # Get task details
        tasks_response = ecs_client.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=response['taskArns']
        )
        
        return tasks_response['tasks']
        
    except Exception as e:
        logger.error(f"Failed to get stopped tasks: {e}")
        return []


def analyze_task_failures(tasks):
    """Analyze task failure patterns."""
    logger.info("\n" + "=" * 80)
    logger.info("TASK FAILURE ANALYSIS")
    logger.info("=" * 80)
    
    failure_reasons = {}
    stop_codes = {}
    container_exit_codes = {}
    
    for task in tasks:
        task_id = task['taskArn'].split('/')[-1]
        stopped_reason = task.get('stoppedReason', 'Unknown')
        stop_code = task.get('stopCode', 'Unknown')
        
        logger.info(f"\nTask: {task_id}")
        logger.info(f"  Started: {task.get('startedAt', 'N/A')}")
        logger.info(f"  Stopped: {task.get('stoppedAt', 'N/A')}")
        logger.info(f"  Stop Code: {stop_code}")
        logger.info(f"  Stop Reason: {stopped_reason}")
        
        # Count failure reasons
        failure_reasons[stopped_reason] = failure_reasons.get(stopped_reason, 0) + 1
        stop_codes[stop_code] = stop_codes.get(stop_code, 0) + 1
        
        # Check container exit codes
        for container in task.get('containers', []):
            container_name = container['name']
            exit_code = container.get('exitCode')
            reason = container.get('reason', 'N/A')
            
            logger.info(f"  Container: {container_name}")
            logger.info(f"    Exit Code: {exit_code}")
            logger.info(f"    Reason: {reason}")
            
            if exit_code is not None:
                container_exit_codes[exit_code] = container_exit_codes.get(exit_code, 0) + 1
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("FAILURE PATTERN SUMMARY")
    logger.info("=" * 80)
    
    logger.info("\nStop Codes:")
    for code, count in sorted(stop_codes.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {code}: {count} occurrences")
    
    logger.info("\nStop Reasons:")
    for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {reason}: {count} occurrences")
    
    logger.info("\nContainer Exit Codes:")
    for code, count in sorted(container_exit_codes.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {code}: {count} occurrences")
    
    return {
        'stop_codes': stop_codes,
        'failure_reasons': failure_reasons,
        'container_exit_codes': container_exit_codes
    }


def get_recent_task_logs(task_arn):
    """Get logs from a specific task."""
    try:
        ecs_client = boto3.client('ecs', region_name=REGION)
        logs_client = boto3.client('logs', region_name=REGION)
        
        # Get task details
        task_response = ecs_client.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=[task_arn]
        )
        
        if not task_response['tasks']:
            return None
        
        task = task_response['tasks'][0]
        task_id = task_arn.split('/')[-1]
        
        # Get log stream name
        log_group = '/ecs/multimodal-lib-prod'
        log_stream_prefix = f"ecs/multimodal-lib-prod-app/{task_id}"
        
        # List log streams
        streams_response = logs_client.describe_log_streams(
            logGroupName=log_group,
            logStreamNamePrefix=log_stream_prefix,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        
        if not streams_response['logStreams']:
            logger.warning(f"No log streams found for task {task_id}")
            return None
        
        log_stream_name = streams_response['logStreams'][0]['logStreamName']
        
        # Get log events
        logs_response = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=log_stream_name,
            limit=100,
            startFromHead=False
        )
        
        return logs_response['events']
        
    except Exception as e:
        logger.error(f"Failed to get task logs: {e}")
        return None


def analyze_logs_for_errors(tasks):
    """Analyze logs from failed tasks for error patterns."""
    logger.info("\n" + "=" * 80)
    logger.info("LOG ANALYSIS")
    logger.info("=" * 80)
    
    error_patterns = {}
    
    for task in tasks[:3]:  # Analyze last 3 tasks
        task_arn = task['taskArn']
        task_id = task_arn.split('/')[-1]
        
        logger.info(f"\nAnalyzing logs for task: {task_id}")
        
        logs = get_recent_task_logs(task_arn)
        
        if not logs:
            logger.warning("  No logs available")
            continue
        
        # Look for error patterns
        for event in logs[-50:]:  # Last 50 log lines
            message = event['message']
            
            # Check for common error patterns
            if 'ERROR' in message or 'Error' in message or 'error' in message:
                # Extract error type
                if 'KeyError' in message:
                    error_patterns['KeyError'] = error_patterns.get('KeyError', 0) + 1
                    logger.info(f"  Found KeyError: {message[:200]}")
                elif 'ImportError' in message:
                    error_patterns['ImportError'] = error_patterns.get('ImportError', 0) + 1
                    logger.info(f"  Found ImportError: {message[:200]}")
                elif 'ConnectionError' in message or 'connection' in message.lower():
                    error_patterns['ConnectionError'] = error_patterns.get('ConnectionError', 0) + 1
                    logger.info(f"  Found ConnectionError: {message[:200]}")
                elif 'timeout' in message.lower():
                    error_patterns['Timeout'] = error_patterns.get('Timeout', 0) + 1
                    logger.info(f"  Found Timeout: {message[:200]}")
                elif 'health check' in message.lower():
                    error_patterns['HealthCheck'] = error_patterns.get('HealthCheck', 0) + 1
                    logger.info(f"  Found Health Check issue: {message[:200]}")
    
    logger.info("\nError Pattern Summary:")
    for pattern, count in sorted(error_patterns.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {pattern}: {count} occurrences")
    
    return error_patterns


def check_target_group_health():
    """Check ALB target group health."""
    try:
        elbv2_client = boto3.client('elbv2', region_name=REGION)
        
        logger.info("\n" + "=" * 80)
        logger.info("TARGET GROUP HEALTH CHECK")
        logger.info("=" * 80)
        
        # Get target groups
        tg_response = elbv2_client.describe_target_groups(
            Names=['multimodal-lib-prod-tg']
        )
        
        if not tg_response['TargetGroups']:
            logger.warning("Target group not found")
            return
        
        target_group = tg_response['TargetGroups'][0]
        target_group_arn = target_group['TargetGroupArn']
        
        logger.info(f"Target Group: {target_group['TargetGroupName']}")
        logger.info(f"Health Check Path: {target_group['HealthCheckPath']}")
        logger.info(f"Health Check Protocol: {target_group['HealthCheckProtocol']}")
        logger.info(f"Health Check Port: {target_group['HealthCheckPort']}")
        logger.info(f"Health Check Interval: {target_group['HealthCheckIntervalSeconds']}s")
        logger.info(f"Health Check Timeout: {target_group['HealthCheckTimeoutSeconds']}s")
        logger.info(f"Healthy Threshold: {target_group['HealthyThresholdCount']}")
        logger.info(f"Unhealthy Threshold: {target_group['UnhealthyThresholdCount']}")
        
        # Get target health
        health_response = elbv2_client.describe_target_health(
            TargetGroupArn=target_group_arn
        )
        
        logger.info(f"\nTarget Health ({len(health_response['TargetHealthDescriptions'])} targets):")
        for target in health_response['TargetHealthDescriptions']:
            state = target['TargetHealth']['State']
            reason = target['TargetHealth'].get('Reason', 'N/A')
            description = target['TargetHealth'].get('Description', 'N/A')
            
            logger.info(f"  Target {target['Target']['Id']}:{target['Target']['Port']}")
            logger.info(f"    State: {state}")
            logger.info(f"    Reason: {reason}")
            logger.info(f"    Description: {description}")
        
    except Exception as e:
        logger.error(f"Failed to check target group health: {e}")


def check_task_definition():
    """Check current task definition for issues."""
    try:
        ecs_client = boto3.client('ecs', region_name=REGION)
        
        logger.info("\n" + "=" * 80)
        logger.info("TASK DEFINITION ANALYSIS")
        logger.info("=" * 80)
        
        # Get service to find task definition
        service_response = ecs_client.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        if not service_response['services']:
            logger.error("Service not found")
            return
        
        task_def_arn = service_response['services'][0]['taskDefinition']
        
        # Get task definition
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=task_def_arn
        )
        
        task_def = task_def_response['taskDefinition']
        
        logger.info(f"Task Definition: {task_def['family']}:{task_def['revision']}")
        logger.info(f"CPU: {task_def.get('cpu', 'N/A')}")
        logger.info(f"Memory: {task_def.get('memory', 'N/A')}")
        
        # Check container definitions
        for container in task_def['containerDefinitions']:
            logger.info(f"\nContainer: {container['name']}")
            logger.info(f"  Image: {container['image']}")
            logger.info(f"  Memory: {container.get('memory', 'N/A')}")
            logger.info(f"  Memory Reservation: {container.get('memoryReservation', 'N/A')}")
            
            # Check health check
            if 'healthCheck' in container:
                hc = container['healthCheck']
                logger.info(f"  Health Check Command: {hc.get('command', 'N/A')}")
                logger.info(f"  Health Check Interval: {hc.get('interval', 'N/A')}s")
                logger.info(f"  Health Check Timeout: {hc.get('timeout', 'N/A')}s")
                logger.info(f"  Health Check Retries: {hc.get('retries', 'N/A')}")
            else:
                logger.warning("  No container health check configured")
            
            # Check environment variables
            logger.info(f"  Environment Variables ({len(container.get('environment', []))}):")
            for env in container.get('environment', []):
                if 'ENABLE' in env['name'] or 'SKIP' in env['name']:
                    logger.info(f"    {env['name']}: {env['value']}")
        
    except Exception as e:
        logger.error(f"Failed to check task definition: {e}")


def provide_recommendations(analysis):
    """Provide recommendations based on analysis."""
    logger.info("\n" + "=" * 80)
    logger.info("RECOMMENDATIONS")
    logger.info("=" * 80)
    
    stop_codes = analysis.get('stop_codes', {})
    failure_reasons = analysis.get('failure_reasons', {})
    container_exit_codes = analysis.get('container_exit_codes', {})
    
    recommendations = []
    
    # Check for health check failures
    if 'TaskFailedToStart' in stop_codes or any('health' in str(r).lower() for r in failure_reasons):
        recommendations.append({
            'issue': 'Health Check Failures',
            'severity': 'HIGH',
            'description': 'Tasks are failing health checks',
            'actions': [
                '1. Fix OpenSearch configuration (domain_endpoint KeyError)',
                '2. Fix SearchService import error',
                '3. Disable OpenSearch/Neptune on startup (ENABLE_VECTOR_SEARCH=false)',
                '4. Increase health check timeout from 10s to 30s',
                '5. Increase health check interval from 30s to 60s'
            ]
        })
    
    # Check for configuration errors
    if 1 in container_exit_codes:  # Exit code 1 = general error
        recommendations.append({
            'issue': 'Application Configuration Errors',
            'severity': 'HIGH',
            'description': 'Application failing to start due to configuration issues',
            'actions': [
                '1. Run: python scripts/fix-startup-configuration-errors.py',
                '2. Update task definition with ENABLE_VECTOR_SEARCH=false',
                '3. Update task definition with ENABLE_GRAPH_DB=false',
                '4. Rebuild and redeploy container'
            ]
        })
    
    # Check for resource issues
    if 137 in container_exit_codes:  # Exit code 137 = OOM killed
        recommendations.append({
            'issue': 'Out of Memory',
            'severity': 'HIGH',
            'description': 'Container killed due to memory limits',
            'actions': [
                '1. Increase task memory from 8GB to 16GB',
                '2. Review memory usage patterns',
                '3. Optimize model loading'
            ]
        })
    
    # Print recommendations
    for i, rec in enumerate(recommendations, 1):
        logger.info(f"\n{i}. {rec['issue']} (Severity: {rec['severity']})")
        logger.info(f"   {rec['description']}")
        logger.info("   Actions:")
        for action in rec['actions']:
            logger.info(f"     {action}")
    
    if not recommendations:
        logger.info("\nNo specific recommendations. Review logs for more details.")


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("TASK INSTABILITY DIAGNOSIS")
    logger.info("=" * 80)
    
    # Get recent stopped tasks
    tasks = get_recent_stopped_tasks(limit=10)
    
    if not tasks:
        logger.error("No stopped tasks found to analyze")
        return 1
    
    logger.info(f"Found {len(tasks)} stopped tasks to analyze")
    
    # Analyze task failures
    analysis = analyze_task_failures(tasks)
    
    # Analyze logs for error patterns
    log_errors = analyze_logs_for_errors(tasks)
    analysis['log_errors'] = log_errors
    
    # Check target group health
    check_target_group_health()
    
    # Check task definition
    check_task_definition()
    
    # Provide recommendations
    provide_recommendations(analysis)
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("DIAGNOSIS COMPLETE")
    logger.info("=" * 80)
    logger.info("\nNext Steps:")
    logger.info("1. Review the recommendations above")
    logger.info("2. Apply the configuration fixes")
    logger.info("3. Update the task definition")
    logger.info("4. Scale the service back up to desiredCount=1")
    logger.info("5. Monitor the deployment")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
