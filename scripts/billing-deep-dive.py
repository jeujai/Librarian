#!/usr/bin/env python3
"""
Deep dive into AWS billing to understand the $516/month charges
"""

import boto3
import json
from datetime import datetime, timedelta
import sys

class BillingAnalyzer:
    def __init__(self):
        self.session = boto3.Session()
        
    def get_detailed_costs(self):
        """Get detailed cost breakdown"""
        print("💰 DETAILED BILLING ANALYSIS")
        print("=" * 60)
        
        try:
            ce = self.session.client('ce', region_name='us-east-1')
            
            # Get current month costs with more detail
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now().replace(day=1)).strftime('%Y-%m-%d')
            
            print(f"Analyzing costs from {start_date} to {end_date}")
            
            # Get costs by service with usage type
            response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date,
                    'End': end_date
                },
                Granularity='MONTHLY',
                Metrics=['BlendedCost', 'UsageQuantity'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    },
                    {
                        'Type': 'DIMENSION', 
                        'Key': 'USAGE_TYPE'
                    }
                ]
            )
            
            print(f"\n📊 DETAILED COST BREAKDOWN:")
            
            high_cost_items = []
            
            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    usage_type = group['Keys'][1]
                    cost = float(group['Metrics']['BlendedCost']['Amount'])
                    usage = float(group['Metrics']['UsageQuantity']['Amount'])
                    
                    if cost > 1.0:  # Only show costs > $1
                        high_cost_items.append({
                            'service': service,
                            'usage_type': usage_type,
                            'cost': cost,
                            'usage': usage
                        })
                        print(f"  💰 {service}")
                        print(f"     Usage Type: {usage_type}")
                        print(f"     Cost: ${cost:.2f}")
                        print(f"     Usage: {usage:.2f}")
                        print()
            
            # Get costs by region
            print(f"\n🌍 COSTS BY REGION:")
            region_response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date,
                    'End': end_date
                },
                Granularity='MONTHLY',
                Metrics=['BlendedCost'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'REGION'
                    }
                ]
            )
            
            for result in region_response['ResultsByTime']:
                for group in result['Groups']:
                    region = group['Keys'][0]
                    cost = float(group['Metrics']['BlendedCost']['Amount'])
                    
                    if cost > 1.0:  # Only show costs > $1
                        print(f"  🌍 {region}: ${cost:.2f}")
            
            # Get daily costs to see when charges started
            print(f"\n📅 DAILY COST TREND (Last 7 days):")
            daily_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            daily_response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': daily_start,
                    'End': end_date
                },
                Granularity='DAILY',
                Metrics=['BlendedCost']
            )
            
            for result in daily_response['ResultsByTime']:
                date = result['TimePeriod']['Start']
                cost = float(result['Total']['BlendedCost']['Amount'])
                print(f"  📅 {date}: ${cost:.2f}")
            
            # Save detailed report
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"billing-analysis-{timestamp}.json"
            
            report = {
                'timestamp': timestamp,
                'period': f"{start_date} to {end_date}",
                'high_cost_items': high_cost_items,
                'daily_costs': daily_response['ResultsByTime'],
                'region_costs': region_response['ResultsByTime'][0]['Groups'] if region_response['ResultsByTime'] else []
            }
            
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            print(f"\n📝 Detailed report saved to: {filename}")
            
            return high_cost_items
            
        except Exception as e:
            print(f"❌ Error analyzing billing: {str(e)}")
            return []
    
    def check_permissions(self):
        """Check what permissions we have"""
        print(f"\n🔐 CHECKING AWS PERMISSIONS:")
        
        services_to_check = [
            ('ecs', 'list_clusters'),
            ('neptune', 'describe_db_clusters'),
            ('opensearch', 'list_domain_names'),
            ('elasticache', 'describe_replication_groups'),
            ('rds', 'describe_db_instances'),
            ('ec2', 'describe_nat_gateways'),
            ('elbv2', 'describe_load_balancers'),
            ('ce', 'get_cost_and_usage')
        ]
        
        permissions = {}
        
        for service_name, method_name in services_to_check:
            try:
                client = self.session.client(service_name, region_name='us-east-1')
                method = getattr(client, method_name)
                
                if service_name == 'ce':
                    # Special case for Cost Explorer
                    method(
                        TimePeriod={
                            'Start': '2025-01-01',
                            'End': '2025-01-02'
                        },
                        Granularity='DAILY',
                        Metrics=['BlendedCost']
                    )
                else:
                    method()
                
                permissions[service_name] = "✅ ALLOWED"
                print(f"  ✅ {service_name}: Can access {method_name}")
                
            except Exception as e:
                permissions[service_name] = f"❌ DENIED: {str(e)}"
                print(f"  ❌ {service_name}: {str(e)}")
        
        return permissions
    
    def analyze_billing_mystery(self):
        """Try to solve the billing mystery"""
        print("🕵️ BILLING MYSTERY ANALYSIS")
        print("=" * 60)
        print("Trying to understand why we see $516/month but no resources...")
        print()
        
        # Check permissions first
        permissions = self.check_permissions()
        
        # Get detailed costs
        high_cost_items = self.get_detailed_costs()
        
        # Analysis
        print(f"\n🔍 ANALYSIS:")
        
        permission_issues = [k for k, v in permissions.items() if "DENIED" in v]
        if permission_issues:
            print(f"  ⚠️  Permission issues found for: {', '.join(permission_issues)}")
            print(f"     This could explain why resources aren't visible")
        
        if high_cost_items:
            print(f"  💰 Found {len(high_cost_items)} high-cost items in billing")
            print(f"  🔍 Top cost drivers:")
            sorted_items = sorted(high_cost_items, key=lambda x: x['cost'], reverse=True)
            for item in sorted_items[:5]:
                print(f"     • {item['service']}: ${item['cost']:.2f} ({item['usage_type']})")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        print(f"  1. Check AWS Console manually for resources in all regions")
        print(f"  2. Look for resources with different naming patterns")
        print(f"  3. Check for data transfer or storage costs")
        print(f"  4. Contact AWS Support if resources can't be found")
        print(f"  5. Consider setting up billing alerts immediately")
        
        return len(high_cost_items) > 0

def main():
    analyzer = BillingAnalyzer()
    
    try:
        found_costs = analyzer.analyze_billing_mystery()
        return 0 if found_costs else 1
        
    except Exception as e:
        print(f"❌ Critical error during billing analysis: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())