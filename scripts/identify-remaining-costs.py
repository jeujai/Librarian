#!/usr/bin/env python3
"""
Identify Remaining AWS Costs
Analyzes current AWS resources to identify all remaining cost sources.
"""

import boto3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

class RemainingCostAnalyzer:
    def __init__(self):
        self.regions = ['us-east-1', 'us-west-2']
        self.cost_analysis = {
            'timestamp': datetime.now().isoformat(),
            'total_estimated_monthly_cost': 0,
            'cost_breakdown': {},
            'cleanup_opportunities': [],
            'recommendations': []
        }
    
    def analyze_compute_costs(self) -> Dict[str, Any]:
        """Analyze compute-related costs"""
        print("🔍 Analyzing compute costs...")
        
        compute_costs = {
            'ec2_instances': 0,
            'lambda_functions': 0,
            'elastic_beanstalk': 0
        }
        
        for region in self.regions:
            # EC2 Instances
            try:
                ec2_client = boto3.client('ec2', region_name=region)
                response = ec2_client.describe_instances(
                    Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]
                )
                
                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        instance_type = instance['InstanceType']
                        state = instance['State']['Name']
                        
                        # Estimate costs based on instance type
                        if instance_type == 't3.micro':
                            monthly_cost = 8.5 if state == 'running' else 2.5  # EBS cost when stopped
                        elif instance_type == 't3.medium':
                            monthly_cost = 30 if state == 'running' else 8  # EBS cost when stopped
                        else:
                            monthly_cost = 20  # Generic estimate
                        
                        compute_costs['ec2_instances'] += monthly_cost
                        
                        if state == 'stopped':
                            self.cost_analysis['cleanup_opportunities'].append({
                                'type': 'stopped_ec2_instance',
                                'resource': instance['InstanceId'],
                                'estimated_monthly_cost': monthly_cost,
                                'recommendation': 'Terminate if no longer needed'
                            })
                        
            except Exception as e:
                print(f"  Error analyzing EC2 in {region}: {str(e)}")
            
            # Lambda Functions
            try:
                lambda_client = boto3.client('lambda', region_name=region)
                response = lambda_client.list_functions()
                
                for function in response['Functions']:
                    # Estimate based on memory and likely usage
                    memory_mb = function['MemorySize']
                    estimated_monthly = max(0.5, memory_mb / 1024 * 2)  # Rough estimate
                    compute_costs['lambda_functions'] += estimated_monthly
                    
                    # Check if function is old/unused
                    last_modified = datetime.fromisoformat(function['LastModified'].replace('Z', '+00:00'))
                    if last_modified < datetime.now().replace(tzinfo=last_modified.tzinfo) - timedelta(days=365):
                        self.cost_analysis['cleanup_opportunities'].append({
                            'type': 'old_lambda_function',
                            'resource': function['FunctionName'],
                            'estimated_monthly_cost': estimated_monthly,
                            'last_modified': function['LastModified'],
                            'recommendation': 'Delete if unused (created > 1 year ago)'
                        })
                        
            except Exception as e:
                print(f"  Error analyzing Lambda in {region}: {str(e)}")
        
        # Elastic Beanstalk
        try:
            eb_client = boto3.client('elasticbeanstalk', region_name='us-west-2')
            response = eb_client.describe_environments()
            
            for env in response['Environments']:
                if env['Status'] not in ['Terminated', 'Terminating']:
                    # Estimate EB environment cost
                    estimated_monthly = 15  # t3.micro + ALB + misc
                    compute_costs['elastic_beanstalk'] += estimated_monthly
                    
                    self.cost_analysis['cleanup_opportunities'].append({
                        'type': 'elastic_beanstalk_environment',
                        'resource': env['EnvironmentName'],
                        'estimated_monthly_cost': estimated_monthly,
                        'recommendation': 'Terminate if no longer needed'
                    })
                    
        except Exception as e:
            print(f"  Error analyzing Elastic Beanstalk: {str(e)}")
        
        return compute_costs
    
    def analyze_storage_costs(self) -> Dict[str, Any]:
        """Analyze storage-related costs"""
        print("🔍 Analyzing storage costs...")
        
        storage_costs = {
            's3_buckets': 0,
            'ebs_volumes': 0
        }
        
        # S3 Buckets
        try:
            s3_client = boto3.client('s3')
            response = s3_client.list_buckets()
            
            for bucket in response['Buckets']:
                bucket_name = bucket['Name']
                
                # Get bucket size
                try:
                    objects = s3_client.list_objects_v2(Bucket=bucket_name)
                    total_size_gb = sum(obj.get('Size', 0) for obj in objects.get('Contents', [])) / (1024**3)
                    
                    # Estimate cost ($0.023 per GB per month for Standard)
                    monthly_cost = total_size_gb * 0.023
                    storage_costs['s3_buckets'] += monthly_cost
                    
                    if total_size_gb < 0.1 and monthly_cost < 0.5:  # Very small buckets
                        self.cost_analysis['cleanup_opportunities'].append({
                            'type': 'small_s3_bucket',
                            'resource': bucket_name,
                            'size_gb': round(total_size_gb, 3),
                            'estimated_monthly_cost': round(monthly_cost, 2),
                            'recommendation': 'Consider deleting if unused'
                        })
                        
                except Exception:
                    # Bucket might be empty or inaccessible
                    continue
                    
        except Exception as e:
            print(f"  Error analyzing S3: {str(e)}")
        
        # EBS Volumes
        for region in self.regions:
            try:
                ec2_client = boto3.client('ec2', region_name=region)
                response = ec2_client.describe_volumes()
                
                for volume in response['Volumes']:
                    size_gb = volume['Size']
                    volume_type = volume['VolumeType']
                    state = volume['State']
                    
                    # Estimate cost based on volume type
                    if volume_type == 'gp3':
                        monthly_cost = size_gb * 0.08  # $0.08 per GB per month
                    elif volume_type == 'gp2':
                        monthly_cost = size_gb * 0.10  # $0.10 per GB per month
                    else:
                        monthly_cost = size_gb * 0.125  # Conservative estimate
                    
                    storage_costs['ebs_volumes'] += monthly_cost
                    
                    if state == 'available':  # Unattached volume
                        self.cost_analysis['cleanup_opportunities'].append({
                            'type': 'unattached_ebs_volume',
                            'resource': volume['VolumeId'],
                            'size_gb': size_gb,
                            'estimated_monthly_cost': round(monthly_cost, 2),
                            'recommendation': 'Delete if no longer needed'
                        })
                        
            except Exception as e:
                print(f"  Error analyzing EBS in {region}: {str(e)}")
        
        return storage_costs
    
    def analyze_networking_costs(self) -> Dict[str, Any]:
        """Analyze networking-related costs"""
        print("🔍 Analyzing networking costs...")
        
        networking_costs = {
            'nat_gateways': 0,
            'load_balancers': 0,
            'elastic_ips': 0,
            'vpc_endpoints': 0
        }
        
        for region in self.regions:
            # NAT Gateways
            try:
                ec2_client = boto3.client('ec2', region_name=region)
                response = ec2_client.describe_nat_gateways()
                
                for nat_gw in response['NatGateways']:
                    if nat_gw['State'] == 'available':
                        monthly_cost = 45  # $45/month per NAT Gateway
                        networking_costs['nat_gateways'] += monthly_cost
                        
                        self.cost_analysis['cleanup_opportunities'].append({
                            'type': 'nat_gateway',
                            'resource': nat_gw['NatGatewayId'],
                            'estimated_monthly_cost': monthly_cost,
                            'recommendation': 'Delete if no private subnets need internet access'
                        })
                        
            except Exception as e:
                print(f"  Error analyzing NAT Gateways in {region}: {str(e)}")
            
            # Load Balancers
            try:
                elb_client = boto3.client('elbv2', region_name=region)
                response = elb_client.describe_load_balancers()
                
                for lb in response['LoadBalancers']:
                    if lb['State']['Code'] == 'active':
                        monthly_cost = 20  # ~$20/month per ALB
                        networking_costs['load_balancers'] += monthly_cost
                        
                        # Check if load balancer has targets
                        target_groups = elb_client.describe_target_groups(
                            LoadBalancerArn=lb['LoadBalancerArn']
                        )
                        
                        has_healthy_targets = False
                        for tg in target_groups['TargetGroups']:
                            targets = elb_client.describe_target_health(
                                TargetGroupArn=tg['TargetGroupArn']
                            )
                            if any(t['TargetHealth']['State'] == 'healthy' for t in targets['TargetHealthDescriptions']):
                                has_healthy_targets = True
                                break
                        
                        if not has_healthy_targets:
                            self.cost_analysis['cleanup_opportunities'].append({
                                'type': 'unused_load_balancer',
                                'resource': lb['LoadBalancerName'],
                                'estimated_monthly_cost': monthly_cost,
                                'recommendation': 'Delete if no healthy targets'
                            })
                            
            except Exception as e:
                print(f"  Error analyzing Load Balancers in {region}: {str(e)}")
            
            # Elastic IPs
            try:
                response = ec2_client.describe_addresses()
                
                for eip in response['Addresses']:
                    if 'InstanceId' not in eip and 'NetworkInterfaceId' not in eip:
                        monthly_cost = 3.65  # $0.005 per hour for unattached EIP
                        networking_costs['elastic_ips'] += monthly_cost
                        
                        self.cost_analysis['cleanup_opportunities'].append({
                            'type': 'unattached_elastic_ip',
                            'resource': eip['PublicIp'],
                            'estimated_monthly_cost': monthly_cost,
                            'recommendation': 'Release if not needed'
                        })
                        
            except Exception as e:
                print(f"  Error analyzing Elastic IPs in {region}: {str(e)}")
        
        return networking_costs
    
    def analyze_service_costs(self) -> Dict[str, Any]:
        """Analyze other AWS service costs"""
        print("🔍 Analyzing other service costs...")
        
        service_costs = {
            'cloudwatch': 2.19,  # From cost analysis
            'secrets_manager': 2.08,  # From cost analysis
            'kms': 0.45,  # From cost analysis
            'cloudtrail': 0.03,  # From cost analysis
            'waf': 4.50,  # From cost analysis
            'ecr': 2.99  # From cost analysis
        }
        
        # These are mostly necessary services, but we can identify optimization opportunities
        if service_costs['waf'] > 0:
            self.cost_analysis['recommendations'].append({
                'service': 'AWS WAF',
                'current_cost': service_costs['waf'],
                'recommendation': 'Review WAF rules - may be able to reduce if not actively needed'
            })
        
        if service_costs['ecr'] > 2:
            self.cost_analysis['recommendations'].append({
                'service': 'ECR',
                'current_cost': service_costs['ecr'],
                'recommendation': 'Clean up old container images to reduce storage costs'
            })
        
        return service_costs
    
    def generate_cost_report(self) -> str:
        """Generate comprehensive cost analysis report"""
        print("📊 Generating cost analysis report...")
        
        # Run all analyses
        compute_costs = self.analyze_compute_costs()
        storage_costs = self.analyze_storage_costs()
        networking_costs = self.analyze_networking_costs()
        service_costs = self.analyze_service_costs()
        
        # Combine all costs
        self.cost_analysis['cost_breakdown'] = {
            'compute': compute_costs,
            'storage': storage_costs,
            'networking': networking_costs,
            'services': service_costs
        }
        
        # Calculate total
        total_compute = sum(compute_costs.values())
        total_storage = sum(storage_costs.values())
        total_networking = sum(networking_costs.values())
        total_services = sum(service_costs.values())
        
        self.cost_analysis['total_estimated_monthly_cost'] = (
            total_compute + total_storage + total_networking + total_services
        )
        
        # Calculate potential savings
        potential_savings = sum(
            opp['estimated_monthly_cost'] 
            for opp in self.cost_analysis['cleanup_opportunities']
        )
        
        self.cost_analysis['potential_monthly_savings'] = potential_savings
        self.cost_analysis['potential_annual_savings'] = potential_savings * 12
        
        # Save report
        timestamp = int(datetime.now().timestamp())
        filename = f"remaining-cost-analysis-{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.cost_analysis, f, indent=2)
        
        return filename
    
    def print_summary(self):
        """Print cost analysis summary"""
        print("\n" + "=" * 60)
        print("💰 REMAINING AWS COST ANALYSIS")
        print("=" * 60)
        
        print(f"Current Estimated Monthly Cost: ${self.cost_analysis['total_estimated_monthly_cost']:.2f}")
        print(f"Potential Additional Savings: ${self.cost_analysis.get('potential_monthly_savings', 0):.2f}/month")
        print(f"Potential Annual Savings: ${self.cost_analysis.get('potential_annual_savings', 0):.2f}/year")
        
        print("\n📋 Cost Breakdown:")
        for category, costs in self.cost_analysis['cost_breakdown'].items():
            if isinstance(costs, dict):
                total = sum(costs.values())
                print(f"  {category.title()}: ${total:.2f}/month")
                for service, cost in costs.items():
                    if cost > 0:
                        print(f"    - {service.replace('_', ' ').title()}: ${cost:.2f}")
            else:
                print(f"  {category.title()}: ${costs:.2f}/month")
        
        print(f"\n🎯 Cleanup Opportunities ({len(self.cost_analysis['cleanup_opportunities'])}):")
        for opp in self.cost_analysis['cleanup_opportunities'][:10]:  # Show top 10
            print(f"  - {opp['type'].replace('_', ' ').title()}: ${opp['estimated_monthly_cost']:.2f}/month")
            print(f"    Resource: {opp['resource']}")
            print(f"    Action: {opp['recommendation']}")
        
        if len(self.cost_analysis['cleanup_opportunities']) > 10:
            print(f"  ... and {len(self.cost_analysis['cleanup_opportunities']) - 10} more opportunities")

def main():
    """Main execution function"""
    analyzer = RemainingCostAnalyzer()
    report_file = analyzer.generate_cost_report()
    analyzer.print_summary()
    
    print(f"\n📄 Detailed report saved to: {report_file}")

if __name__ == "__main__":
    main()