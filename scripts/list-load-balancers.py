#!/usr/bin/env python3
"""
List Application Load Balancers

This script lists all Application Load Balancers in your AWS account with detailed information.
"""

import boto3
import json
import sys
from datetime import datetime
from typing import Dict, List, Any

class LoadBalancerLister:
    """Lists and displays Application Load Balancers."""
    
    def __init__(self):
        self.elbv2_client = boto3.client('elbv2', region_name='us-east-1')
        self.ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'list_load_balancers',
            'load_balancers': [],
            'summary': {}
        }
    
    def list_load_balancers(self) -> Dict[str, Any]:
        """List all Application Load Balancers."""
        
        print("⚖️  Application Load Balancers Inventory")
        print("=" * 45)
        print()
        
        try:
            # Get list of load balancers
            response = self.elbv2_client.describe_load_balancers()
            
            load_balancers = response.get('LoadBalancers', [])
            
            if not load_balancers:
                print("📭 No Application Load Balancers found in your account.")
                self.results['summary'] = {
                    'total_load_balancers': 0,
                    'active_load_balancers': 0,
                    'inactive_load_balancers': 0
                }
                return self.results
            
            print(f"📊 Found {len(load_balancers)} Application Load Balancer(s)")
            print()
            
            active_count = 0
            inactive_count = 0
            
            for i, lb in enumerate(load_balancers, 1):
                lb_info = self._extract_load_balancer_info(lb)
                self.results['load_balancers'].append(lb_info)
                
                if lb_info['state'] == 'active':
                    active_count += 1
                else:
                    inactive_count += 1
                
                self._print_load_balancer_info(i, lb_info)
                print()
            
            # Summary
            self.results['summary'] = {
                'total_load_balancers': len(load_balancers),
                'active_load_balancers': active_count,
                'inactive_load_balancers': inactive_count
            }
            
            print("📈 Summary:")
            print(f"   Total Load Balancers: {len(load_balancers)}")
            print(f"   Active: {active_count}")
            print(f"   Inactive: {inactive_count}")
            
        except Exception as e:
            print(f"❌ Error listing load balancers: {e}")
            self.results['error'] = str(e)
        
        return self.results
    
    def _extract_load_balancer_info(self, lb: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key information from a load balancer."""
        
        # Get target groups for this load balancer
        target_groups = self._get_target_groups(lb['LoadBalancerArn'])
        
        # Get listeners
        listeners = self._get_listeners(lb['LoadBalancerArn'])
        
        return {
            'name': lb.get('LoadBalancerName', 'Unknown'),
            'arn': lb.get('LoadBalancerArn', 'Unknown'),
            'dns_name': lb.get('DNSName', 'Unknown'),
            'state': lb.get('State', {}).get('Code', 'Unknown'),
            'type': lb.get('Type', 'Unknown'),
            'scheme': lb.get('Scheme', 'Unknown'),
            'vpc_id': lb.get('VpcId', 'Unknown'),
            'availability_zones': [az.get('ZoneName', 'Unknown') for az in lb.get('AvailabilityZones', [])],
            'security_groups': lb.get('SecurityGroups', []),
            'created_time': str(lb.get('CreatedTime', 'Unknown')),
            'target_groups': target_groups,
            'listeners': listeners,
            'canonical_hosted_zone_id': lb.get('CanonicalHostedZoneId', 'Unknown')
        }
    
    def _get_target_groups(self, lb_arn: str) -> List[Dict[str, Any]]:
        """Get target groups for a load balancer."""
        
        try:
            response = self.elbv2_client.describe_target_groups(
                LoadBalancerArn=lb_arn
            )
            
            target_groups = []
            for tg in response.get('TargetGroups', []):
                # Get target health
                targets = self._get_target_health(tg['TargetGroupArn'])
                
                target_groups.append({
                    'name': tg.get('TargetGroupName', 'Unknown'),
                    'arn': tg.get('TargetGroupArn', 'Unknown'),
                    'port': tg.get('Port', 'Unknown'),
                    'protocol': tg.get('Protocol', 'Unknown'),
                    'health_check_path': tg.get('HealthCheckPath', 'Unknown'),
                    'target_type': tg.get('TargetType', 'Unknown'),
                    'targets': targets
                })
            
            return target_groups
            
        except Exception as e:
            return [{'error': str(e)}]
    
    def _get_target_health(self, tg_arn: str) -> List[Dict[str, Any]]:
        """Get target health for a target group."""
        
        try:
            response = self.elbv2_client.describe_target_health(
                TargetGroupArn=tg_arn
            )
            
            targets = []
            for target in response.get('TargetHealthDescriptions', []):
                targets.append({
                    'id': target.get('Target', {}).get('Id', 'Unknown'),
                    'port': target.get('Target', {}).get('Port', 'Unknown'),
                    'health_status': target.get('TargetHealth', {}).get('State', 'Unknown'),
                    'description': target.get('TargetHealth', {}).get('Description', '')
                })
            
            return targets
            
        except Exception as e:
            return [{'error': str(e)}]
    
    def _get_listeners(self, lb_arn: str) -> List[Dict[str, Any]]:
        """Get listeners for a load balancer."""
        
        try:
            response = self.elbv2_client.describe_listeners(
                LoadBalancerArn=lb_arn
            )
            
            listeners = []
            for listener in response.get('Listeners', []):
                listeners.append({
                    'port': listener.get('Port', 'Unknown'),
                    'protocol': listener.get('Protocol', 'Unknown'),
                    'ssl_policy': listener.get('SslPolicy', 'N/A'),
                    'certificate_arn': listener.get('Certificates', [{}])[0].get('CertificateArn', 'N/A') if listener.get('Certificates') else 'N/A'
                })
            
            return listeners
            
        except Exception as e:
            return [{'error': str(e)}]
    
    def _print_load_balancer_info(self, index: int, lb_info: Dict[str, Any]):
        """Print formatted load balancer information."""
        
        status_emoji = "✅" if lb_info['state'] == 'active' else "⚠️"
        
        print(f"{status_emoji} Load Balancer #{index}")
        print(f"   Name: {lb_info['name']}")
        print(f"   DNS Name: {lb_info['dns_name']}")
        print(f"   State: {lb_info['state']}")
        print(f"   Type: {lb_info['type']}")
        print(f"   Scheme: {lb_info['scheme']}")
        print(f"   VPC ID: {lb_info['vpc_id']}")
        print(f"   Created: {lb_info['created_time']}")
        
        # Availability Zones
        if lb_info['availability_zones']:
            print(f"   Availability Zones: {', '.join(lb_info['availability_zones'])}")
        
        # Security Groups
        if lb_info['security_groups']:
            print(f"   Security Groups: {len(lb_info['security_groups'])} group(s)")
        
        # Listeners
        if lb_info['listeners']:
            print(f"   Listeners:")
            for listener in lb_info['listeners']:
                ssl_info = f" (SSL: {listener['ssl_policy']})" if listener['ssl_policy'] != 'N/A' else ""
                cert_info = f" [Cert: {listener['certificate_arn'][:20]}...]" if listener['certificate_arn'] != 'N/A' else ""
                print(f"     - {listener['protocol']}:{listener['port']}{ssl_info}{cert_info}")
        
        # Target Groups
        if lb_info['target_groups']:
            print(f"   Target Groups:")
            for tg in lb_info['target_groups']:
                if 'error' in tg:
                    print(f"     - Error: {tg['error']}")
                    continue
                
                healthy_targets = sum(1 for t in tg['targets'] if t.get('health_status') == 'healthy')
                total_targets = len(tg['targets'])
                
                print(f"     - {tg['name']} ({tg['protocol']}:{tg['port']})")
                print(f"       Health Check: {tg['health_check_path']}")
                print(f"       Targets: {healthy_targets}/{total_targets} healthy")
                
                if tg['targets']:
                    for target in tg['targets']:
                        if 'error' in target:
                            print(f"         • Error: {target['error']}")
                        else:
                            status_icon = "🟢" if target['health_status'] == 'healthy' else "🔴"
                            print(f"         • {status_icon} {target['id']}:{target['port']} ({target['health_status']})")
    
    def save_results(self) -> str:
        """Save results to file."""
        
        filename = f"load-balancers-list-{int(datetime.now().timestamp())}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        return filename


def main():
    """Main execution function."""
    
    print("⚖️  Application Load Balancers Inventory")
    print("Listing all Application Load Balancers in your AWS account")
    print()
    
    lister = LoadBalancerLister()
    results = lister.list_load_balancers()
    
    # Save results
    results_file = lister.save_results()
    print(f"\n📄 Results saved to: {results_file}")
    
    # Final summary
    if results.get('summary'):
        summary = results['summary']
        print(f"\n🎯 Final Summary:")
        print(f"   Total Application Load Balancers: {summary['total_load_balancers']}")
        if summary['total_load_balancers'] > 0:
            print(f"   Active: {summary['active_load_balancers']}")
            print(f"   Inactive: {summary['inactive_load_balancers']}")
            
            # Cost estimate
            if summary['active_load_balancers'] > 0:
                print(f"\n💰 Estimated Monthly Cost:")
                print(f"   Base cost per ALB: ~$16.20/month")
                print(f"   Estimated total: ~${summary['active_load_balancers'] * 16.20:.2f}/month")
                print(f"   (Plus data processing charges)")
        
        return 0 if summary['total_load_balancers'] >= 0 else 1
    else:
        print("\n❌ Failed to retrieve load balancer information")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)