#!/usr/bin/env python3
"""
Production deployment validation script.
Validates that all services are running correctly after deployment.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProductionValidator:
    """Validates production deployment health and functionality."""
    
    def __init__(self, base_url: str, aws_region: str = 'us-east-1'):
        self.base_url = base_url.rstrip('/')
        self.aws_region = aws_region
        self.session = None
        
        # AWS clients
        self.ecs_client = boto3.client('ecs', region_name=aws_region)
        self.elbv2_client = boto3.client('elbv2', region_name=aws_region)
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=aws_region)
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def validate_health_endpoints(self) -> Dict[str, bool]:
        """Validate application health endpoints."""
        logger.info("Validating health endpoints...")
        
        endpoints = {
            'simple_health': '/health/simple',
            'detailed_health': '/health/detailed',
            'database_health': '/health/database',
            'ready': '/ready'
        }
        
        results = {}
        
        for name, endpoint in endpoints.items():
            try:
                url = urljoin(self.base_url, endpoint)
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        results[name] = data.get('status') == 'healthy'
                        logger.info(f"✓ {name}: healthy")
                    else:
                        results[name] = False
                        logger.error(f"✗ {name}: HTTP {response.status}")
                        
            except Exception as e:
                results[name] = False
                logger.error(f"✗ {name}: {str(e)}")
                
        return results
    
    async def validate_api_endpoints(self) -> Dict[str, bool]:
        """Validate core API functionality."""
        logger.info("Validating API endpoints...")
        
        test_cases = [
            {
                'name': 'chat_endpoint',
                'method': 'POST',
                'url': '/api/chat',
                'data': {'message': 'Hello, this is a test message'},
                'expected_status': 200
            },
            {
                'name': 'documents_list',
                'method': 'GET',
                'url': '/api/documents',
                'expected_status': 200
            },
            {
                'name': 'search_endpoint',
                'method': 'POST',
                'url': '/api/search',
                'data': {'query': 'test search', 'limit': 5},
                'expected_status': 200
            },
            {
                'name': 'analytics_endpoint',
                'method': 'GET',
                'url': '/api/analytics/summary',
                'expected_status': 200
            }
        ]
        
        results = {}
        
        for test_case in test_cases:
            try:
                url = urljoin(self.base_url, test_case['url'])
                
                if test_case['method'] == 'GET':
                    async with self.session.get(url) as response:
                        success = response.status == test_case['expected_status']
                else:
                    async with self.session.post(
                        url, 
                        json=test_case.get('data', {})
                    ) as response:
                        success = response.status == test_case['expected_status']
                
                results[test_case['name']] = success
                
                if success:
                    logger.info(f"✓ {test_case['name']}: passed")
                else:
                    logger.error(f"✗ {test_case['name']}: HTTP {response.status}")
                    
            except Exception as e:
                results[test_case['name']] = False
                logger.error(f"✗ {test_case['name']}: {str(e)}")
                
        return results
    
    def validate_ecs_service(self, cluster_name: str, service_name: str) -> Dict[str, bool]:
        """Validate ECS service health."""
        logger.info(f"Validating ECS service: {service_name}")
        
        try:
            response = self.ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if not response['services']:
                logger.error(f"✗ ECS service {service_name} not found")
                return {'service_exists': False}
            
            service = response['services'][0]
            
            results = {
                'service_exists': True,
                'service_running': service['status'] == 'ACTIVE',
                'desired_count_met': service['runningCount'] >= service['desiredCount'],
                'deployment_stable': len([d for d in service['deployments'] if d['status'] == 'PRIMARY']) == 1
            }
            
            # Check task health
            if results['service_running']:
                tasks_response = self.ecs_client.list_tasks(
                    cluster=cluster_name,
                    serviceName=service_name
                )
                
                if tasks_response['taskArns']:
                    tasks_detail = self.ecs_client.describe_tasks(
                        cluster=cluster_name,
                        tasks=tasks_response['taskArns']
                    )
                    
                    healthy_tasks = sum(1 for task in tasks_detail['tasks'] 
                                      if task['lastStatus'] == 'RUNNING')
                    total_tasks = len(tasks_detail['tasks'])
                    
                    results['tasks_healthy'] = healthy_tasks == total_tasks
                    logger.info(f"✓ ECS tasks: {healthy_tasks}/{total_tasks} healthy")
                else:
                    results['tasks_healthy'] = False
                    logger.error("✗ No ECS tasks found")
            
            for key, value in results.items():
                if value:
                    logger.info(f"✓ ECS {key}: passed")
                else:
                    logger.error(f"✗ ECS {key}: failed")
                    
            return results
            
        except ClientError as e:
            logger.error(f"✗ ECS validation failed: {str(e)}")
            return {'service_exists': False}
    
    def validate_load_balancer(self, lb_name: str) -> Dict[str, bool]:
        """Validate Application Load Balancer health."""
        logger.info(f"Validating load balancer: {lb_name}")
        
        try:
            # Get load balancer details
            lb_response = self.elbv2_client.describe_load_balancers(
                Names=[lb_name]
            )
            
            if not lb_response['LoadBalancers']:
                logger.error(f"✗ Load balancer {lb_name} not found")
                return {'lb_exists': False}
            
            lb = lb_response['LoadBalancers'][0]
            
            results = {
                'lb_exists': True,
                'lb_active': lb['State']['Code'] == 'active',
                'lb_scheme_correct': lb['Scheme'] == 'internet-facing'
            }
            
            # Check target groups
            tg_response = self.elbv2_client.describe_target_groups(
                LoadBalancerArn=lb['LoadBalancerArn']
            )
            
            if tg_response['TargetGroups']:
                tg_arn = tg_response['TargetGroups'][0]['TargetGroupArn']
                
                # Check target health
                health_response = self.elbv2_client.describe_target_health(
                    TargetGroupArn=tg_arn
                )
                
                healthy_targets = sum(1 for target in health_response['TargetHealthDescriptions']
                                    if target['TargetHealth']['State'] == 'healthy')
                total_targets = len(health_response['TargetHealthDescriptions'])
                
                results['targets_healthy'] = healthy_targets > 0
                logger.info(f"✓ Load balancer targets: {healthy_targets}/{total_targets} healthy")
            else:
                results['targets_healthy'] = False
                logger.error("✗ No target groups found")
            
            for key, value in results.items():
                if value:
                    logger.info(f"✓ Load balancer {key}: passed")
                else:
                    logger.error(f"✗ Load balancer {key}: failed")
                    
            return results
            
        except ClientError as e:
            logger.error(f"✗ Load balancer validation failed: {str(e)}")
            return {'lb_exists': False}
    
    def validate_cloudwatch_metrics(self, namespace: str = 'AWS/ECS') -> Dict[str, bool]:
        """Validate CloudWatch metrics are being collected."""
        logger.info("Validating CloudWatch metrics...")
        
        try:
            # Check for recent metrics
            end_time = time.time()
            start_time = end_time - 300  # Last 5 minutes
            
            metrics_response = self.cloudwatch_client.get_metric_statistics(
                Namespace=namespace,
                MetricName='CPUUtilization',
                StartTime=start_time,
                EndTime=end_time,
                Period=60,
                Statistics=['Average']
            )
            
            results = {
                'metrics_available': len(metrics_response['Datapoints']) > 0
            }
            
            if results['metrics_available']:
                logger.info("✓ CloudWatch metrics: available")
            else:
                logger.error("✗ CloudWatch metrics: no recent data")
                
            return results
            
        except ClientError as e:
            logger.error(f"✗ CloudWatch validation failed: {str(e)}")
            return {'metrics_available': False}
    
    async def run_performance_test(self, duration: int = 60) -> Dict[str, float]:
        """Run basic performance test."""
        logger.info(f"Running performance test for {duration} seconds...")
        
        endpoint = urljoin(self.base_url, '/health/simple')
        request_count = 0
        error_count = 0
        response_times = []
        
        start_time = time.time()
        
        while time.time() - start_time < duration:
            try:
                request_start = time.time()
                async with self.session.get(endpoint) as response:
                    request_time = time.time() - request_start
                    response_times.append(request_time)
                    
                    if response.status != 200:
                        error_count += 1
                    
                    request_count += 1
                    
                # Small delay to avoid overwhelming the service
                await asyncio.sleep(0.1)
                
            except Exception as e:
                error_count += 1
                logger.debug(f"Request error: {str(e)}")
        
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            error_rate = error_count / request_count if request_count > 0 else 1.0
        else:
            avg_response_time = 0
            max_response_time = 0
            error_rate = 1.0
        
        results = {
            'requests_per_second': request_count / duration,
            'average_response_time': avg_response_time,
            'max_response_time': max_response_time,
            'error_rate': error_rate
        }
        
        logger.info(f"Performance results:")
        logger.info(f"  Requests/sec: {results['requests_per_second']:.2f}")
        logger.info(f"  Avg response time: {results['average_response_time']:.3f}s")
        logger.info(f"  Max response time: {results['max_response_time']:.3f}s")
        logger.info(f"  Error rate: {results['error_rate']:.2%}")
        
        return results


async def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(description='Validate production deployment')
    parser.add_argument('--url', required=True, help='Base URL of the deployed application')
    parser.add_argument('--cluster', default='multimodal-librarian-production', 
                       help='ECS cluster name')
    parser.add_argument('--service', default='multimodal-librarian-production',
                       help='ECS service name')
    parser.add_argument('--load-balancer', default='multimodal-librarian-production',
                       help='Load balancer name')
    parser.add_argument('--performance-test', action='store_true',
                       help='Run performance test')
    parser.add_argument('--performance-duration', type=int, default=60,
                       help='Performance test duration in seconds')
    
    args = parser.parse_args()
    
    logger.info("Starting production deployment validation...")
    
    validation_results = {}
    
    async with ProductionValidator(args.url) as validator:
        # Health endpoint validation
        health_results = await validator.validate_health_endpoints()
        validation_results['health'] = health_results
        
        # API endpoint validation
        api_results = await validator.validate_api_endpoints()
        validation_results['api'] = api_results
        
        # ECS service validation
        ecs_results = validator.validate_ecs_service(args.cluster, args.service)
        validation_results['ecs'] = ecs_results
        
        # Load balancer validation
        lb_results = validator.validate_load_balancer(args.load_balancer)
        validation_results['load_balancer'] = lb_results
        
        # CloudWatch metrics validation
        metrics_results = validator.validate_cloudwatch_metrics()
        validation_results['metrics'] = metrics_results
        
        # Performance test (optional)
        if args.performance_test:
            perf_results = await validator.run_performance_test(args.performance_duration)
            validation_results['performance'] = perf_results
    
    # Calculate overall success
    all_checks = []
    for category, results in validation_results.items():
        if category == 'performance':
            # Performance checks have different criteria
            all_checks.extend([
                results['error_rate'] < 0.01,  # Less than 1% error rate
                results['average_response_time'] < 1.0  # Less than 1 second avg
            ])
        else:
            all_checks.extend(results.values())
    
    success_rate = sum(all_checks) / len(all_checks) if all_checks else 0
    overall_success = success_rate >= 0.9  # 90% of checks must pass
    
    logger.info(f"\nValidation Summary:")
    logger.info(f"  Success rate: {success_rate:.1%}")
    logger.info(f"  Overall result: {'PASS' if overall_success else 'FAIL'}")
    
    # Output results as JSON for CI/CD consumption
    output = {
        'success': overall_success,
        'success_rate': success_rate,
        'results': validation_results,
        'timestamp': time.time()
    }
    
    print(json.dumps(output, indent=2))
    
    return 0 if overall_success else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))