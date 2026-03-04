#!/usr/bin/env python3
"""
Check VPC Endpoints Status and Restart Service

This script checks the status of VPC endpoints and forces a new deployment
of the ECS service to use the new network configuration.
"""

import boto3
import json
import time
from typing import Dict, List, Any

class VPCEndpointChecker:
    """Check VPC endpoints and restart ECS service."""
    
    def __init__(self):
        self.session = boto3.Session()
        self.prod_vpc_id = "vpc-0b2186b38779e77f6"
        self.cluster_name = "multimodal-lib-prod-cluster"
        self.service_name = "multimodal-lib-prod-service"
        self.region = "us-east-1"
        
    def check_and_restart(self) -> Dict[str, Any]:
        """Check VPC endpoints and restart service."""
        
        results = {
            'vpc_endpoints_status': [],
            'service_restart': {},
            'task_monitoring': {},
            'summary': {}
        }
        
        try:
            print("🔍 Checking VPC Endpoints and Restarting Service")
            print("=" * 60)
            
            # Step 1: Check VPC endpoint status
            results['vpc_endpoints_status'] = self._check_vpc_endpoints()
            
            # Step 2: Force new deployment
            results['service_restart'] = self._force_new_deployment()
            
            # Step 3: Monitor task startup
            results['task_monitoring'] = self._monitor_task_startup()
            
            # Step 4: Generate summary
            results['summary'] = self._generate_summary(results)
            
            self._print_results(results)
            
        except Exception as e:
            print(f"❌ Error during check and restart: {e}")
            results['error'] = str(e)
        
        return results
    
    def _check_vpc_endpoints(self) -> List[Dict[str, Any]]:
        """Check the status of VPC endpoints."""
        
        endpoints_status = []
        
        try:
            ec2 = self.session.client('ec2', region_name=self.region)
            
            print("📋 Checking VPC Endpoints Status...")
            
            # Get VPC endpoints
            endpoints_response = ec2.describe_vpc_endpoints(
                Filters=[{'Name': 'vpc-id', 'Values': [self.prod_vpc_id]}]
            )
            
            for endpoint in endpoints_response['VpcEndpoints']:
                service_name = endpoint['ServiceName'].split('.')[-1]
                
                endpoint_info = {
                    'service': service_name,
                    'endpoint_id': endpoint['VpcEndpointId'],
                    'state': endpoint['State'],
                    'type': endpoint['VpcEndpointType'],
                    'creation_timestamp': endpoint['CreationTimestamp'].isoformat()
                }
                
                endpoints_status.append(endpoint_info)
                
                status_icon = "✅" if endpoint['State'] == 'available' else "⚠️"
                print(f"   {status_icon} {service_name}: {endpoint['State']} ({endpoint['VpcEndpointId']})")
                
                # Check DNS names for interface endpoints
                if endpoint['VpcEndpointType'] == 'Interface' and 'DnsEntries' in endpoint:
                    for dns_entry in endpoint['DnsEntries']:
                        print(f"      DNS: {dns_entry['DnsName']}")
            
        except Exception as e:
            print(f"❌ Error checking VPC endpoints: {e}")
        
        return endpoints_status
    
    def _force_new_deployment(self) -> Dict[str, Any]:
        """Force a new deployment of the ECS service."""
        
        deployment_result = {
            'success': False,
            'deployment_id': None,
            'previous_task_count': 0,
            'new_task_count': 0
        }
        
        try:
            ecs = self.session.client('ecs', region_name=self.region)
            
            print(f"\n🚀 Forcing New Service Deployment...")
            
            # Get current service status
            service_response = ecs.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            
            if service_response['services']:
                service = service_response['services'][0]
                deployment_result['previous_task_count'] = service['runningCount']
                
                print(f"   Current running tasks: {service['runningCount']}")
                print(f"   Current desired count: {service['desiredCount']}")
            
            # Force new deployment
            update_response = ecs.update_service(
                cluster=self.cluster_name,
                service=self.service_name,
                forceNewDeployment=True
            )
            
            deployment_result.update({
                'success': True,
                'deployment_id': update_response['service']['deployments'][0]['id'],
                'new_task_count': update_response['service']['desiredCount'],
                'status': update_response['service']['status']
            })
            
            print(f"✅ New deployment initiated!")
            print(f"   Deployment ID: {deployment_result['deployment_id'][:8]}...")
            print(f"   Service Status: {deployment_result['status']}")
            
        except Exception as e:
            print(f"❌ Error forcing new deployment: {e}")
            deployment_result['error'] = str(e)
        
        return deployment_result
    
    def _monitor_task_startup(self) -> Dict[str, Any]:
        """Monitor task startup for up to 10 minutes."""
        
        monitoring_result = {
            'startup_successful': False,
            'monitoring_duration': 0,
            'final_status': {},
            'events': [],
            'task_details': []
        }
        
        try:
            ecs = self.session.client('ecs', region_name=self.region)
            
            print(f"\n👀 Monitoring Task Startup (up to 10 minutes)...")
            
            start_time = time.time()
            max_wait_time = 600  # 10 minutes
            last_event_time = None
            
            while time.time() - start_time < max_wait_time:
                # Check service status
                service_response = ecs.describe_services(
                    cluster=self.cluster_name,
                    services=[self.service_name]
                )
                
                if service_response['services']:
                    service = service_response['services'][0]
                    
                    running_count = service['runningCount']
                    desired_count = service['desiredCount']
                    pending_count = service['pendingCount']
                    
                    print(f"   Status: {running_count}/{desired_count} running, {pending_count} pending")
                    
                    # Check recent events
                    recent_events = service.get('events', [])[:5]
                    for event in recent_events:
                        event_time = event['createdAt']
                        if last_event_time is None or event_time > last_event_time:
                            print(f"   Event: {event['message']}")
                            monitoring_result['events'].append({
                                'time': event_time.isoformat(),
                                'message': event['message']
                            })
                            last_event_time = event_time
                    
                    # Get task details
                    if pending_count > 0 or running_count > 0:
                        tasks_response = ecs.list_tasks(
                            cluster=self.cluster_name,
                            serviceName=self.service_name
                        )
                        
                        if tasks_response['taskArns']:
                            task_details_response = ecs.describe_tasks(
                                cluster=self.cluster_name,
                                tasks=tasks_response['taskArns']
                            )
                            
                            for task in task_details_response['tasks']:
                                task_id = task['taskArn'].split('/')[-1]
                                task_status = task['lastStatus']
                                
                                # Check for stopped reason
                                if task_status == 'STOPPED' and 'stoppedReason' in task:
                                    print(f"   Task {task_id[:8]}: {task_status} - {task['stoppedReason']}")
                                    
                                    monitoring_result['task_details'].append({
                                        'task_id': task_id,
                                        'status': task_status,
                                        'stopped_reason': task['stoppedReason'],
                                        'stopped_at': task.get('stoppedAt', '').isoformat() if task.get('stoppedAt') else None
                                    })
                                else:
                                    print(f"   Task {task_id[:8]}: {task_status}")
                                    
                                    monitoring_result['task_details'].append({
                                        'task_id': task_id,
                                        'status': task_status
                                    })
                    
                    # Check if service is running
                    if running_count >= desired_count and desired_count > 0:
                        monitoring_result['startup_successful'] = True
                        monitoring_result['final_status'] = {
                            'running_count': running_count,
                            'desired_count': desired_count,
                            'pending_count': pending_count,
                            'status': service['status']
                        }
                        print(f"✅ Service startup successful!")
                        break
                
                time.sleep(30)  # Wait 30 seconds before next check
            
            monitoring_result['monitoring_duration'] = time.time() - start_time
            
            if not monitoring_result['startup_successful']:
                print(f"⚠️  Service startup still in progress after {monitoring_result['monitoring_duration']:.1f} seconds")
                
                # Get final status
                service_response = ecs.describe_services(
                    cluster=self.cluster_name,
                    services=[self.service_name]
                )
                
                if service_response['services']:
                    service = service_response['services'][0]
                    monitoring_result['final_status'] = {
                        'running_count': service['runningCount'],
                        'desired_count': service['desiredCount'],
                        'pending_count': service['pendingCount'],
                        'status': service['status']
                    }
            
        except Exception as e:
            print(f"❌ Error monitoring task startup: {e}")
            monitoring_result['error'] = str(e)
        
        return monitoring_result
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of operations."""
        
        endpoints_status = results['vpc_endpoints_status']
        
        summary = {
            'endpoints_available': len([ep for ep in endpoints_status if ep['state'] == 'available']),
            'endpoints_total': len(endpoints_status),
            'deployment_successful': results['service_restart'].get('success', False),
            'service_running': results['task_monitoring'].get('startup_successful', False),
            'issues_found': [],
            'next_steps': []
        }
        
        # Check for issues
        if summary['endpoints_available'] < summary['endpoints_total']:
            summary['issues_found'].append("Some VPC endpoints are not available")
        
        if not summary['deployment_successful']:
            summary['issues_found'].append("Service deployment failed")
        
        if not summary['service_running']:
            summary['issues_found'].append("Service tasks are not running")
        
        # Generate next steps
        if summary['service_running']:
            summary['next_steps'].extend([
                "✅ Service is running successfully",
                "🧪 Run end-to-end tests to validate functionality",
                "📊 Monitor service health and performance"
            ])
        elif summary['deployment_successful']:
            summary['next_steps'].extend([
                "⚠️  Service deployment initiated but tasks not yet running",
                "👀 Continue monitoring task startup",
                "🔍 Check CloudWatch logs for detailed error messages",
                "🔧 Consider checking task definition configuration"
            ])
        else:
            summary['next_steps'].extend([
                "❌ Service deployment failed",
                "🔍 Check IAM permissions and network configuration",
                "🔧 Verify VPC endpoints are properly configured"
            ])
        
        return summary
    
    def _print_results(self, results: Dict[str, Any]):
        """Print formatted results."""
        
        summary = results['summary']
        
        print(f"\n📊 CHECK AND RESTART SUMMARY")
        print("=" * 40)
        
        print(f"VPC Endpoints Available: {summary['endpoints_available']}/{summary['endpoints_total']}")
        print(f"Deployment Successful: {'✅ Yes' if summary['deployment_successful'] else '❌ No'}")
        print(f"Service Running: {'✅ Yes' if summary['service_running'] else '❌ No'}")
        
        if summary['issues_found']:
            print(f"\n⚠️  Issues Found:")
            for issue in summary['issues_found']:
                print(f"   • {issue}")
        
        print(f"\n🎯 Next Steps:")
        for step in summary['next_steps']:
            print(f"   {step}")

def main():
    """Main execution function."""
    
    checker = VPCEndpointChecker()
    
    try:
        results = checker.check_and_restart()
        
        # Save detailed results
        timestamp = int(time.time())
        results_file = f"vpc-endpoints-check-restart-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        # Return appropriate exit code
        summary = results.get('summary', {})
        if summary.get('service_running'):
            print("\n✅ Service is running successfully")
            return 0
        elif summary.get('deployment_successful'):
            print("\n⚠️  Service deployment initiated, monitoring required")
            return 1
        else:
            print("\n❌ Service deployment failed")
            return 2
        
    except Exception as e:
        print(f"❌ Check and restart failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())