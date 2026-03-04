#!/usr/bin/env python3
"""
Comprehensive AWS Cost and Resource Scanner
Scans all regions for resources and provides cost analysis
"""

import boto3
import json
from datetime import datetime, timedelta
from collections import defaultdict
import sys
from typing import Dict, List, Any

class AWSCostScanner:
    def __init__(self):
        self.session = boto3.Session()
        self.regions = self.get_all_regions()
        self.total_resources = 0
        self.cost_estimates = defaultdict(float)
        
    def get_all_regions(self) -> List[str]:
        """Get all available AWS regions"""
        ec2 = self.session.client('ec2', region_name='us-east-1')
        regions = ec2.describe_regions()['Regions']
        return [region['RegionName'] for region in regions]
    
    def scan_ec2_instances(self) -> Dict[str, List[Dict]]:
        """Scan EC2 instances across all regions"""
        print("🔍 Scanning EC2 instances...")
        instances_by_region = {}
        
        for region in self.regions:
            try:
                ec2 = self.session.client('ec2', region_name=region)
                response = ec2.describe_instances()
                
                instances = []
                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        if instance['State']['Name'] != 'terminated':
                            instances.append({
                                'InstanceId': instance['InstanceId'],
                                'InstanceType': instance['InstanceType'],
                                'State': instance['State']['Name'],
                                'LaunchTime': instance.get('LaunchTime', '').isoformat() if instance.get('LaunchTime') else '',
                                'Region': region
                            })
                            self.total_resources += 1
                
                if instances:
                    instances_by_region[region] = instances
                    print(f"  Found {len(instances)} instances in {region}")
                    
            except Exception as e:
                print(f"  Error scanning {region}: {str(e)}")
                
        return instances_by_region
    
    def scan_rds_instances(self) -> Dict[str, List[Dict]]:
        """Scan RDS instances across all regions"""
        print("🔍 Scanning RDS instances...")
        rds_by_region = {}
        
        for region in self.regions:
            try:
                rds = self.session.client('rds', region_name=region)
                response = rds.describe_db_instances()
                
                instances = []
                for db in response['DBInstances']:
                    instances.append({
                        'DBInstanceIdentifier': db['DBInstanceIdentifier'],
                        'DBInstanceClass': db['DBInstanceClass'],
                        'Engine': db['Engine'],
                        'DBInstanceStatus': db['DBInstanceStatus'],
                        'Region': region
                    })
                    self.total_resources += 1
                
                if instances:
                    rds_by_region[region] = instances
                    print(f"  Found {len(instances)} RDS instances in {region}")
                    
            except Exception as e:
                print(f"  Error scanning RDS in {region}: {str(e)}")
                
        return rds_by_region
    
    def scan_s3_buckets(self) -> List[Dict]:
        """Scan S3 buckets (global service)"""
        print("🔍 Scanning S3 buckets...")
        try:
            s3 = self.session.client('s3')
            response = s3.list_buckets()
            
            buckets = []
            for bucket in response['Buckets']:
                bucket_name = bucket['Name']
                try:
                    # Get bucket region
                    location = s3.get_bucket_location(Bucket=bucket_name)
                    region = location['LocationConstraint'] or 'us-east-1'
                    
                    # Get bucket size (approximate)
                    try:
                        cloudwatch = self.session.client('cloudwatch', region_name=region)
                        metrics = cloudwatch.get_metric_statistics(
                            Namespace='AWS/S3',
                            MetricName='BucketSizeBytes',
                            Dimensions=[
                                {'Name': 'BucketName', 'Value': bucket_name},
                                {'Name': 'StorageType', 'Value': 'StandardStorage'}
                            ],
                            StartTime=datetime.utcnow() - timedelta(days=2),
                            EndTime=datetime.utcnow(),
                            Period=86400,
                            Statistics=['Average']
                        )
                        
                        size_bytes = 0
                        if metrics['Datapoints']:
                            size_bytes = metrics['Datapoints'][-1]['Average']
                            
                    except Exception:
                        size_bytes = 0
                    
                    buckets.append({
                        'Name': bucket_name,
                        'CreationDate': bucket['CreationDate'].isoformat(),
                        'Region': region,
                        'SizeBytes': size_bytes,
                        'SizeMB': round(size_bytes / (1024 * 1024), 2) if size_bytes > 0 else 0
                    })
                    self.total_resources += 1
                    
                except Exception as e:
                    print(f"  Error getting details for bucket {bucket_name}: {str(e)}")
            
            print(f"  Found {len(buckets)} S3 buckets")
            return buckets
            
        except Exception as e:
            print(f"  Error scanning S3: {str(e)}")
            return []
    
    def scan_cloudfront_distributions(self) -> List[Dict]:
        """Scan CloudFront distributions (global service)"""
        print("🔍 Scanning CloudFront distributions...")
        try:
            cloudfront = self.session.client('cloudfront')
            response = cloudfront.list_distributions()
            
            distributions = []
            if 'DistributionList' in response and 'Items' in response['DistributionList']:
                for dist in response['DistributionList']['Items']:
                    distributions.append({
                        'Id': dist['Id'],
                        'DomainName': dist['DomainName'],
                        'Status': dist['Status'],
                        'Enabled': dist['Enabled'],
                        'Comment': dist.get('Comment', ''),
                        'LastModifiedTime': dist['LastModifiedTime'].isoformat()
                    })
                    self.total_resources += 1
            
            print(f"  Found {len(distributions)} CloudFront distributions")
            return distributions
            
        except Exception as e:
            print(f"  Error scanning CloudFront: {str(e)}")
            return []
    
    def scan_load_balancers(self) -> Dict[str, List[Dict]]:
        """Scan Load Balancers across all regions"""
        print("🔍 Scanning Load Balancers...")
        lb_by_region = {}
        
        for region in self.regions:
            try:
                # Application Load Balancers and Network Load Balancers
                elbv2 = self.session.client('elbv2', region_name=region)
                response = elbv2.describe_load_balancers()
                
                load_balancers = []
                for lb in response['LoadBalancers']:
                    load_balancers.append({
                        'LoadBalancerName': lb['LoadBalancerName'],
                        'Type': lb['Type'],
                        'State': lb['State']['Code'],
                        'DNSName': lb['DNSName'],
                        'Region': region
                    })
                    self.total_resources += 1
                
                # Classic Load Balancers
                try:
                    elb = self.session.client('elb', region_name=region)
                    classic_response = elb.describe_load_balancers()
                    
                    for lb in classic_response['LoadBalancerDescriptions']:
                        load_balancers.append({
                            'LoadBalancerName': lb['LoadBalancerName'],
                            'Type': 'classic',
                            'State': 'active',
                            'DNSName': lb['DNSName'],
                            'Region': region
                        })
                        self.total_resources += 1
                        
                except Exception:
                    pass  # Classic ELB might not be available in all regions
                
                if load_balancers:
                    lb_by_region[region] = load_balancers
                    print(f"  Found {len(load_balancers)} load balancers in {region}")
                    
            except Exception as e:
                print(f"  Error scanning load balancers in {region}: {str(e)}")
                
        return lb_by_region
    
    def scan_nat_gateways_and_eips(self) -> Dict[str, Dict]:
        """Scan NAT Gateways and Elastic IPs across all regions"""
        print("🔍 Scanning NAT Gateways and Elastic IPs...")
        resources_by_region = {}
        
        for region in self.regions:
            try:
                ec2 = self.session.client('ec2', region_name=region)
                
                # NAT Gateways
                nat_response = ec2.describe_nat_gateways()
                nat_gateways = []
                for nat in nat_response['NatGateways']:
                    if nat['State'] != 'deleted':
                        nat_gateways.append({
                            'NatGatewayId': nat['NatGatewayId'],
                            'State': nat['State'],
                            'VpcId': nat['VpcId'],
                            'SubnetId': nat['SubnetId']
                        })
                        self.total_resources += 1
                
                # Elastic IPs
                eip_response = ec2.describe_addresses()
                elastic_ips = []
                for eip in eip_response['Addresses']:
                    elastic_ips.append({
                        'AllocationId': eip.get('AllocationId', ''),
                        'PublicIp': eip.get('PublicIp', ''),
                        'AssociationId': eip.get('AssociationId', ''),
                        'InstanceId': eip.get('InstanceId', ''),
                        'Domain': eip.get('Domain', '')
                    })
                    self.total_resources += 1
                
                if nat_gateways or elastic_ips:
                    resources_by_region[region] = {
                        'nat_gateways': nat_gateways,
                        'elastic_ips': elastic_ips
                    }
                    print(f"  Found {len(nat_gateways)} NAT gateways and {len(elastic_ips)} Elastic IPs in {region}")
                    
            except Exception as e:
                print(f"  Error scanning NAT/EIP in {region}: {str(e)}")
                
        return resources_by_region
    
    def get_billing_data(self) -> Dict:
        """Get recent billing data"""
        print("💰 Analyzing billing data...")
        try:
            # Use Cost Explorer API
            ce = self.session.client('ce', region_name='us-east-1')
            
            # Get current month costs
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now().replace(day=1)).strftime('%Y-%m-%d')
            
            response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date,
                    'End': end_date
                },
                Granularity='MONTHLY',
                Metrics=['BlendedCost'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    }
                ]
            )
            
            current_costs = {}
            total_current = 0
            
            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['BlendedCost']['Amount'])
                    if cost > 0:
                        current_costs[service] = cost
                        total_current += cost
            
            # Get last month costs for comparison
            last_month_end = datetime.now().replace(day=1).strftime('%Y-%m-%d')
            last_month_start = (datetime.now().replace(day=1) - timedelta(days=32)).replace(day=1).strftime('%Y-%m-%d')
            
            last_month_response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': last_month_start,
                    'End': last_month_end
                },
                Granularity='MONTHLY',
                Metrics=['BlendedCost']
            )
            
            last_month_total = 0
            if last_month_response['ResultsByTime']:
                last_month_total = float(last_month_response['ResultsByTime'][0]['Total']['BlendedCost']['Amount'])
            
            return {
                'current_month_total': round(total_current, 2),
                'current_month_by_service': current_costs,
                'last_month_total': round(last_month_total, 2)
            }
            
        except Exception as e:
            print(f"  Error getting billing data: {str(e)}")
            return {}
    
    def generate_report(self) -> Dict:
        """Generate comprehensive cost and resource report"""
        print("\n" + "="*60)
        print("🚀 Starting AWS Cost and Resource Scan")
        print("="*60)
        
        report = {
            'scan_timestamp': datetime.now().isoformat(),
            'total_resources_found': 0,
            'billing_data': {},
            'resources': {}
        }
        
        # Scan all resource types
        report['resources']['ec2_instances'] = self.scan_ec2_instances()
        report['resources']['rds_instances'] = self.scan_rds_instances()
        report['resources']['s3_buckets'] = self.scan_s3_buckets()
        report['resources']['cloudfront_distributions'] = self.scan_cloudfront_distributions()
        report['resources']['load_balancers'] = self.scan_load_balancers()
        report['resources']['nat_gateways_and_eips'] = self.scan_nat_gateways_and_eips()
        
        # Get billing data
        report['billing_data'] = self.get_billing_data()
        
        # Update total resources
        report['total_resources_found'] = self.total_resources
        
        return report
    
    def print_summary(self, report: Dict):
        """Print a human-readable summary"""
        print("\n" + "="*60)
        print("📊 AWS COST AND RESOURCE SUMMARY")
        print("="*60)
        
        # Billing Summary
        billing = report.get('billing_data', {})
        if billing:
            print(f"\n💰 BILLING SUMMARY:")
            print(f"  Current Month: ${billing.get('current_month_total', 0):.2f}")
            print(f"  Last Month: ${billing.get('last_month_total', 0):.2f}")
            
            current_services = billing.get('current_month_by_service', {})
            if current_services:
                print(f"\n  Current Month by Service:")
                for service, cost in sorted(current_services.items(), key=lambda x: x[1], reverse=True):
                    if cost > 0.01:  # Only show costs > 1 cent
                        print(f"    {service}: ${cost:.2f}")
        
        # Resource Summary
        print(f"\n🔍 RESOURCE SUMMARY:")
        print(f"  Total Resources Found: {report['total_resources_found']}")
        
        resources = report['resources']
        
        # EC2 Instances
        ec2_total = sum(len(instances) for instances in resources.get('ec2_instances', {}).values())
        if ec2_total > 0:
            print(f"  EC2 Instances: {ec2_total}")
            for region, instances in resources.get('ec2_instances', {}).items():
                for instance in instances:
                    print(f"    {instance['InstanceId']} ({instance['InstanceType']}) - {instance['State']} in {region}")
        
        # RDS Instances
        rds_total = sum(len(instances) for instances in resources.get('rds_instances', {}).values())
        if rds_total > 0:
            print(f"  RDS Instances: {rds_total}")
            for region, instances in resources.get('rds_instances', {}).items():
                for instance in instances:
                    print(f"    {instance['DBInstanceIdentifier']} ({instance['DBInstanceClass']}) - {instance['DBInstanceStatus']} in {region}")
        
        # S3 Buckets
        s3_buckets = resources.get('s3_buckets', [])
        if s3_buckets:
            print(f"  S3 Buckets: {len(s3_buckets)}")
            for bucket in s3_buckets:
                size_info = f" ({bucket['SizeMB']} MB)" if bucket['SizeMB'] > 0 else " (empty)"
                print(f"    {bucket['Name']} in {bucket['Region']}{size_info}")
        
        # CloudFront Distributions
        cf_distributions = resources.get('cloudfront_distributions', [])
        if cf_distributions:
            print(f"  CloudFront Distributions: {len(cf_distributions)}")
            for dist in cf_distributions:
                status = "✅ Enabled" if dist['Enabled'] else "❌ Disabled"
                print(f"    {dist['Id']} - {status} ({dist['Status']})")
        
        # Load Balancers
        lb_total = sum(len(lbs) for lbs in resources.get('load_balancers', {}).values())
        if lb_total > 0:
            print(f"  Load Balancers: {lb_total}")
            for region, lbs in resources.get('load_balancers', {}).items():
                for lb in lbs:
                    print(f"    {lb['LoadBalancerName']} ({lb['Type']}) - {lb['State']} in {region}")
        
        # NAT Gateways and Elastic IPs
        nat_eip_regions = resources.get('nat_gateways_and_eips', {})
        if nat_eip_regions:
            for region, data in nat_eip_regions.items():
                nat_count = len(data.get('nat_gateways', []))
                eip_count = len(data.get('elastic_ips', []))
                if nat_count > 0:
                    print(f"  NAT Gateways in {region}: {nat_count}")
                if eip_count > 0:
                    print(f"  Elastic IPs in {region}: {eip_count}")
        
        # Recommendations
        print(f"\n💡 COST OPTIMIZATION RECOMMENDATIONS:")
        
        # CloudFront recommendations
        disabled_cf = [d for d in cf_distributions if not d['Enabled']]
        if disabled_cf:
            print(f"  • Delete {len(disabled_cf)} disabled CloudFront distributions")
        
        # S3 recommendations
        empty_buckets = [b for b in s3_buckets if b['SizeMB'] == 0]
        if empty_buckets:
            print(f"  • Consider deleting {len(empty_buckets)} empty S3 buckets")
        
        # General recommendations
        if report['total_resources_found'] == 0:
            print(f"  • ✅ No active resources found - costs should be minimal")
        elif billing.get('current_month_total', 0) < 5:
            print(f"  • ✅ Current costs are low (${billing.get('current_month_total', 0):.2f}/month)")
            print(f"  • Consider setting up billing alerts for costs >$5/month")
        
        print(f"\n📝 Full report saved to: aws-cost-scan-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

def main():
    scanner = AWSCostScanner()
    
    try:
        report = scanner.generate_report()
        
        # Save detailed report to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"aws-cost-scan-{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Print summary
        scanner.print_summary(report)
        
        return 0
        
    except Exception as e:
        print(f"❌ Error during scan: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())