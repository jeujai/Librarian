#!/usr/bin/env python3
"""
AWS Infrastructure Cleanup Script for Multimodal Librarian

This script identifies and helps clean up old/unused AWS resources to reduce costs:
- ECS clusters and services
- NAT Gateways
- Load balancers
- RDS instances
- OpenSearch domains
- EC2 instances
- Unused VPCs and subnets
"""

import boto3
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

class AWSResourceCleanup:
    """AWS resource cleanup manager for cost optimization."""
    
    def __init__(self, region: str = 'us-east-1'):
        self.region = region
        self.session = boto3.Session()
        
        # Initialize AWS clients
        self.ecs = self.session.client('ecs', region_name=region)
        self.ec2 = self.session.client('ec2', region_name=region)
        self.elbv2 = self.session.client('elbv2', region_name=region)
        self.rds = self.session.client('rds', region_name=region)
        self.opensearch = self.session.client('opensearch', region_name=region)
        self.cloudformation = self.session.client('cloudformation', region_name=region)
        
        self.cleanup_report = {
            'timestamp': datetime.now().isoformat(),
            'region': region,
            'resources_found': {},
            'cleanup_actions': [],
            'cost_savings_estimate': {}
        }
    
    def scan_all_resources(self) -> Dict[str, Any]:
        """Scan all Multimodal Librarian related resources."""
        
        print("🔍 Scanning AWS resources for Multimodal Librarian infrastructure...")
        print("=" * 70)
        
        # Scan different resource types
        self.scan_ecs_resources()
        self.scan_nat_gateways()
        self.scan_load_balancers()
        self.scan_rds_instances()
        self.scan_opensearch_domains()
        self.scan_ec2_instances()
        self.scan_cloudformation_stacks()
        
        return self.cleanup_report
    
    def scan_ecs_resources(self):
        """Scan ECS clusters and services."""
        
        print("\n📦 ECS Resources:")
        print("-" * 20)
        
        try:
            # List all ECS clusters
            clusters_response = self.ecs.list_clusters()
            clusters = []
            
            for cluster_arn in clusters_response.get('clusterArns', []):
                cluster_name = cluster_arn.split('/')[-1]
                
                # Check if it's related to Multimodal Librarian
                if any(keyword in cluster_name.lower() for keyword in 
                       ['multimodal', 'librarian', 'ml-', 'chat-doc']):
                    
                    # Get cluster details
                    cluster_details = self.ecs.describe_clusters(clusters=[cluster_arn])
                    cluster_info = cluster_details['clusters'][0]
                    
                    # Get services in cluster
                    services_response = self.ecs.list_services(cluster=cluster_arn)
                    services = []
                    
                    for service_arn in services_response.get('serviceArns', []):
                        service_name = service_arn.split('/')[-1]
                        service_details = self.ecs.describe_services(
                            cluster=cluster_arn, 
                            services=[service_arn]
                        )
                        service_info = service_details['services'][0]
                        
                        services.append({
                            'name': service_name,
                            'arn': service_arn,
                            'status': service_info.get('status'),
                            'running_count': service_info.get('runningCount', 0),
                            'desired_count': service_info.get('desiredCount', 0),
                            'created_at': service_info.get('createdAt', '').isoformat() if service_info.get('createdAt') else 'Unknown'
                        })
                    
                    cluster_data = {
                        'name': cluster_name,
                        'arn': cluster_arn,
                        'status': cluster_info.get('status'),
                        'active_services': cluster_info.get('activeServicesCount', 0),
                        'running_tasks': cluster_info.get('runningTasksCount', 0),
                        'services': services
                    }
                    
                    clusters.append(cluster_data)
                    
                    print(f"📦 Cluster: {cluster_name}")
                    print(f"   Status: {cluster_info.get('status')}")
                    print(f"   Active services: {cluster_info.get('activeServicesCount', 0)}")
                    print(f"   Running tasks: {cluster_info.get('runningTasksCount', 0)}")
                    
                    for service in services:
                        print(f"   🔧 Service: {service['name']}")
                        print(f"      Status: {service['status']}")
                        print(f"      Running/Desired: {service['running_count']}/{service['desired_count']}")
                        print(f"      Created: {service['created_at']}")
            
            self.cleanup_report['resources_found']['ecs_clusters'] = clusters
            
            if not clusters:
                print("✅ No Multimodal Librarian ECS clusters found")
            
        except Exception as e:
            print(f"❌ Error scanning ECS resources: {e}")
    
    def scan_nat_gateways(self):
        """Scan NAT Gateways."""
        
        print("\n🌐 NAT Gateways:")
        print("-" * 15)
        
        try:
            nat_gateways_response = self.ec2.describe_nat_gateways()
            nat_gateways = []
            
            for nat_gw in nat_gateways_response.get('NatGateways', []):
                # Check tags for Multimodal Librarian
                tags = {tag['Key']: tag['Value'] for tag in nat_gw.get('Tags', [])}
                
                is_ml_related = any(
                    keyword in str(tags).lower() for keyword in 
                    ['multimodal', 'librarian', 'ml-', 'chat-doc']
                ) or any(
                    keyword in nat_gw.get('SubnetId', '').lower() for keyword in 
                    ['multimodal', 'librarian', 'ml-']
                )
                
                if is_ml_related or nat_gw.get('State') in ['available', 'pending']:
                    nat_gw_data = {
                        'id': nat_gw.get('NatGatewayId'),
                        'state': nat_gw.get('State'),
                        'subnet_id': nat_gw.get('SubnetId'),
                        'vpc_id': nat_gw.get('VpcId'),
                        'created_at': nat_gw.get('CreateTime', '').isoformat() if nat_gw.get('CreateTime') else 'Unknown',
                        'tags': tags
                    }
                    
                    nat_gateways.append(nat_gw_data)
                    
                    print(f"🌐 NAT Gateway: {nat_gw.get('NatGatewayId')}")
                    print(f"   State: {nat_gw.get('State')}")
                    print(f"   VPC: {nat_gw.get('VpcId')}")
                    print(f"   Subnet: {nat_gw.get('SubnetId')}")
                    print(f"   Created: {nat_gw_data['created_at']}")
                    if tags:
                        print(f"   Tags: {tags}")
            
            self.cleanup_report['resources_found']['nat_gateways'] = nat_gateways
            
            if not nat_gateways:
                print("✅ No Multimodal Librarian NAT Gateways found")
            
        except Exception as e:
            print(f"❌ Error scanning NAT Gateways: {e}")
    
    def scan_load_balancers(self):
        """Scan Application Load Balancers."""
        
        print("\n⚖️  Load Balancers:")
        print("-" * 17)
        
        try:
            load_balancers_response = self.elbv2.describe_load_balancers()
            load_balancers = []
            
            for lb in load_balancers_response.get('LoadBalancers', []):
                # Check if related to Multimodal Librarian
                lb_name = lb.get('LoadBalancerName', '')
                
                if any(keyword in lb_name.lower() for keyword in 
                       ['multimodal', 'librarian', 'ml-', 'chat-doc']):
                    
                    # Get tags
                    try:
                        tags_response = self.elbv2.describe_tags(ResourceArns=[lb['LoadBalancerArn']])
                        tags = {}
                        for tag_desc in tags_response.get('TagDescriptions', []):
                            for tag in tag_desc.get('Tags', []):
                                tags[tag['Key']] = tag['Value']
                    except:
                        tags = {}
                    
                    lb_data = {
                        'name': lb_name,
                        'arn': lb.get('LoadBalancerArn'),
                        'state': lb.get('State', {}).get('Code'),
                        'type': lb.get('Type'),
                        'scheme': lb.get('Scheme'),
                        'vpc_id': lb.get('VpcId'),
                        'created_at': lb.get('CreatedTime', '').isoformat() if lb.get('CreatedTime') else 'Unknown',
                        'tags': tags
                    }
                    
                    load_balancers.append(lb_data)
                    
                    print(f"⚖️  Load Balancer: {lb_name}")
                    print(f"   State: {lb.get('State', {}).get('Code')}")
                    print(f"   Type: {lb.get('Type')}")
                    print(f"   VPC: {lb.get('VpcId')}")
                    print(f"   Created: {lb_data['created_at']}")
            
            self.cleanup_report['resources_found']['load_balancers'] = load_balancers
            
            if not load_balancers:
                print("✅ No Multimodal Librarian Load Balancers found")
            
        except Exception as e:
            print(f"❌ Error scanning Load Balancers: {e}")
    
    def scan_rds_instances(self):
        """Scan RDS instances."""
        
        print("\n🗄️  RDS Instances:")
        print("-" * 16)
        
        try:
            rds_response = self.rds.describe_db_instances()
            rds_instances = []
            
            for db in rds_response.get('DBInstances', []):
                db_identifier = db.get('DBInstanceIdentifier', '')
                
                if any(keyword in db_identifier.lower() for keyword in 
                       ['multimodal', 'librarian', 'ml-', 'chat-doc']):
                    
                    db_data = {
                        'identifier': db_identifier,
                        'status': db.get('DBInstanceStatus'),
                        'engine': db.get('Engine'),
                        'instance_class': db.get('DBInstanceClass'),
                        'allocated_storage': db.get('AllocatedStorage'),
                        'vpc_id': db.get('DBSubnetGroup', {}).get('VpcId') if db.get('DBSubnetGroup') else None,
                        'created_at': db.get('InstanceCreateTime', '').isoformat() if db.get('InstanceCreateTime') else 'Unknown'
                    }
                    
                    rds_instances.append(db_data)
                    
                    print(f"🗄️  RDS Instance: {db_identifier}")
                    print(f"   Status: {db.get('DBInstanceStatus')}")
                    print(f"   Engine: {db.get('Engine')}")
                    print(f"   Class: {db.get('DBInstanceClass')}")
                    print(f"   Storage: {db.get('AllocatedStorage')}GB")
                    print(f"   Created: {db_data['created_at']}")
            
            self.cleanup_report['resources_found']['rds_instances'] = rds_instances
            
            if not rds_instances:
                print("✅ No Multimodal Librarian RDS instances found")
            
        except Exception as e:
            print(f"❌ Error scanning RDS instances: {e}")
    
    def scan_opensearch_domains(self):
        """Scan OpenSearch domains."""
        
        print("\n🔍 OpenSearch Domains:")
        print("-" * 21)
        
        try:
            opensearch_response = self.opensearch.list_domain_names()
            opensearch_domains = []
            
            for domain in opensearch_response.get('DomainNames', []):
                domain_name = domain.get('DomainName', '')
                
                if any(keyword in domain_name.lower() for keyword in 
                       ['multimodal', 'librarian', 'ml-', 'chat-doc', 'search']):
                    
                    # Get domain details
                    try:
                        domain_details = self.opensearch.describe_domain(DomainName=domain_name)
                        domain_info = domain_details.get('DomainStatus', {})
                        
                        domain_data = {
                            'name': domain_name,
                            'arn': domain_info.get('ARN'),
                            'created': domain_info.get('Created'),
                            'processing': domain_info.get('Processing'),
                            'engine_version': domain_info.get('EngineVersion'),
                            'instance_type': domain_info.get('ClusterConfig', {}).get('InstanceType'),
                            'instance_count': domain_info.get('ClusterConfig', {}).get('InstanceCount')
                        }
                        
                        opensearch_domains.append(domain_data)
                        
                        print(f"🔍 OpenSearch Domain: {domain_name}")
                        print(f"   Created: {domain_info.get('Created')}")
                        print(f"   Processing: {domain_info.get('Processing')}")
                        print(f"   Engine: {domain_info.get('EngineVersion')}")
                        print(f"   Instance: {domain_info.get('ClusterConfig', {}).get('InstanceType')}")
                        
                    except Exception as e:
                        print(f"   ⚠️  Could not get details for {domain_name}: {e}")
            
            self.cleanup_report['resources_found']['opensearch_domains'] = opensearch_domains
            
            if not opensearch_domains:
                print("✅ No Multimodal Librarian OpenSearch domains found")
            
        except Exception as e:
            print(f"❌ Error scanning OpenSearch domains: {e}")
    
    def scan_ec2_instances(self):
        """Scan EC2 instances."""
        
        print("\n💻 EC2 Instances:")
        print("-" * 16)
        
        try:
            ec2_response = self.ec2.describe_instances()
            ec2_instances = []
            
            for reservation in ec2_response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    # Check tags and name
                    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                    instance_name = tags.get('Name', '')
                    
                    if any(keyword in str(tags).lower() for keyword in 
                           ['multimodal', 'librarian', 'ml-', 'chat-doc']) or \
                       any(keyword in instance_name.lower() for keyword in 
                           ['multimodal', 'librarian', 'ml-', 'chat-doc']):
                        
                        instance_data = {
                            'id': instance.get('InstanceId'),
                            'name': instance_name,
                            'state': instance.get('State', {}).get('Name'),
                            'type': instance.get('InstanceType'),
                            'vpc_id': instance.get('VpcId'),
                            'subnet_id': instance.get('SubnetId'),
                            'launch_time': instance.get('LaunchTime', '').isoformat() if instance.get('LaunchTime') else 'Unknown',
                            'tags': tags
                        }
                        
                        ec2_instances.append(instance_data)
                        
                        print(f"💻 EC2 Instance: {instance.get('InstanceId')}")
                        print(f"   Name: {instance_name}")
                        print(f"   State: {instance.get('State', {}).get('Name')}")
                        print(f"   Type: {instance.get('InstanceType')}")
                        print(f"   VPC: {instance.get('VpcId')}")
                        print(f"   Launched: {instance_data['launch_time']}")
            
            self.cleanup_report['resources_found']['ec2_instances'] = ec2_instances
            
            if not ec2_instances:
                print("✅ No Multimodal Librarian EC2 instances found")
            
        except Exception as e:
            print(f"❌ Error scanning EC2 instances: {e}")
    
    def scan_cloudformation_stacks(self):
        """Scan CloudFormation stacks."""
        
        print("\n📚 CloudFormation Stacks:")
        print("-" * 25)
        
        try:
            stacks_response = self.cloudformation.describe_stacks()
            cf_stacks = []
            
            for stack in stacks_response.get('Stacks', []):
                stack_name = stack.get('StackName', '')
                
                if any(keyword in stack_name.lower() for keyword in 
                       ['multimodal', 'librarian', 'ml-', 'chat-doc']):
                    
                    stack_data = {
                        'name': stack_name,
                        'status': stack.get('StackStatus'),
                        'created_at': stack.get('CreationTime', '').isoformat() if stack.get('CreationTime') else 'Unknown',
                        'updated_at': stack.get('LastUpdatedTime', '').isoformat() if stack.get('LastUpdatedTime') else 'Never'
                    }
                    
                    cf_stacks.append(stack_data)
                    
                    print(f"📚 CloudFormation Stack: {stack_name}")
                    print(f"   Status: {stack.get('StackStatus')}")
                    print(f"   Created: {stack_data['created_at']}")
                    print(f"   Updated: {stack_data['updated_at']}")
            
            self.cleanup_report['resources_found']['cloudformation_stacks'] = cf_stacks
            
            if not cf_stacks:
                print("✅ No Multimodal Librarian CloudFormation stacks found")
            
        except Exception as e:
            print(f"❌ Error scanning CloudFormation stacks: {e}")
    
    def generate_cleanup_recommendations(self) -> List[Dict[str, Any]]:
        """Generate cleanup recommendations based on found resources."""
        
        recommendations = []
        
        # ECS Clusters with no running tasks
        for cluster in self.cleanup_report['resources_found'].get('ecs_clusters', []):
            if cluster['running_tasks'] == 0 and cluster['active_services'] == 0:
                recommendations.append({
                    'type': 'ecs_cluster',
                    'resource': cluster['name'],
                    'action': 'delete',
                    'reason': 'No running tasks or active services',
                    'cost_impact': 'Low (no compute costs, but reduces management overhead)',
                    'command': f"aws ecs delete-cluster --cluster {cluster['name']}"
                })
        
        # ECS Services with 0 desired count
        for cluster in self.cleanup_report['resources_found'].get('ecs_clusters', []):
            for service in cluster.get('services', []):
                if service['desired_count'] == 0:
                    recommendations.append({
                        'type': 'ecs_service',
                        'resource': f"{cluster['name']}/{service['name']}",
                        'action': 'delete',
                        'reason': 'Service scaled to 0, no longer needed',
                        'cost_impact': 'Low (no compute costs)',
                        'command': f"aws ecs delete-service --cluster {cluster['name']} --service {service['name']} --force"
                    })
        
        # NAT Gateways (high cost impact)
        for nat_gw in self.cleanup_report['resources_found'].get('nat_gateways', []):
            if nat_gw['state'] == 'available':
                recommendations.append({
                    'type': 'nat_gateway',
                    'resource': nat_gw['id'],
                    'action': 'delete',
                    'reason': 'NAT Gateway incurs hourly charges (~$45/month)',
                    'cost_impact': 'HIGH (~$45/month per NAT Gateway)',
                    'command': f"aws ec2 delete-nat-gateway --nat-gateway-id {nat_gw['id']}"
                })
        
        # Load Balancers
        for lb in self.cleanup_report['resources_found'].get('load_balancers', []):
            if lb['state'] == 'active':
                recommendations.append({
                    'type': 'load_balancer',
                    'resource': lb['name'],
                    'action': 'delete',
                    'reason': 'Load balancer incurs hourly charges (~$20/month)',
                    'cost_impact': 'MEDIUM (~$20/month per ALB)',
                    'command': f"aws elbv2 delete-load-balancer --load-balancer-arn {lb['arn']}"
                })
        
        # RDS Instances
        for rds in self.cleanup_report['resources_found'].get('rds_instances', []):
            if rds['status'] == 'available':
                recommendations.append({
                    'type': 'rds_instance',
                    'resource': rds['identifier'],
                    'action': 'stop_or_delete',
                    'reason': f"RDS {rds['instance_class']} incurs significant costs",
                    'cost_impact': 'HIGH (varies by instance class, typically $50-500/month)',
                    'command': f"aws rds stop-db-instance --db-instance-identifier {rds['identifier']} # or delete-db-instance"
                })
        
        # OpenSearch Domains
        for domain in self.cleanup_report['resources_found'].get('opensearch_domains', []):
            recommendations.append({
                'type': 'opensearch_domain',
                'resource': domain['name'],
                'action': 'delete',
                'reason': 'OpenSearch domains incur significant costs',
                'cost_impact': 'HIGH (typically $100-1000/month depending on instance type)',
                'command': f"aws opensearch delete-domain --domain-name {domain['name']}"
            })
        
        # Running EC2 Instances
        for instance in self.cleanup_report['resources_found'].get('ec2_instances', []):
            if instance['state'] == 'running':
                recommendations.append({
                    'type': 'ec2_instance',
                    'resource': f"{instance['id']} ({instance['name']})",
                    'action': 'stop_or_terminate',
                    'reason': f"Running {instance['type']} instance incurs hourly costs",
                    'cost_impact': 'MEDIUM (varies by instance type)',
                    'command': f"aws ec2 stop-instances --instance-ids {instance['id']} # or terminate-instances"
                })
        
        return recommendations
    
    def estimate_cost_savings(self, recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Estimate potential cost savings from cleanup actions."""
        
        # Rough monthly cost estimates (these vary by region and usage)
        cost_estimates = {
            'nat_gateway': 45,  # ~$45/month per NAT Gateway
            'load_balancer': 20,  # ~$20/month per ALB
            'rds_instance': 100,  # Varies widely, using conservative estimate
            'opensearch_domain': 200,  # Varies widely by instance type
            'ec2_instance': 50  # Varies by instance type
        }
        
        total_monthly_savings = 0
        savings_breakdown = {}
        
        for rec in recommendations:
            resource_type = rec['type']
            if resource_type in cost_estimates:
                cost = cost_estimates[resource_type]
                total_monthly_savings += cost
                
                if resource_type not in savings_breakdown:
                    savings_breakdown[resource_type] = {'count': 0, 'monthly_cost': 0}
                
                savings_breakdown[resource_type]['count'] += 1
                savings_breakdown[resource_type]['monthly_cost'] += cost
        
        return {
            'total_monthly_savings': total_monthly_savings,
            'annual_savings': total_monthly_savings * 12,
            'breakdown': savings_breakdown
        }
    
    def generate_cleanup_report(self) -> str:
        """Generate comprehensive cleanup report."""
        
        recommendations = self.generate_cleanup_recommendations()
        cost_savings = self.estimate_cost_savings(recommendations)
        
        report = []
        report.append("=" * 80)
        report.append("AWS INFRASTRUCTURE CLEANUP REPORT")
        report.append("Multimodal Librarian Cost Optimization")
        report.append("=" * 80)
        report.append("")
        
        # Summary
        total_resources = sum(len(resources) for resources in self.cleanup_report['resources_found'].values())
        report.append(f"📊 Resources Found: {total_resources}")
        report.append(f"💡 Cleanup Recommendations: {len(recommendations)}")
        report.append(f"💰 Estimated Monthly Savings: ${cost_savings['total_monthly_savings']:.2f}")
        report.append(f"💰 Estimated Annual Savings: ${cost_savings['annual_savings']:.2f}")
        report.append("")
        
        # High-impact recommendations first
        high_impact = [r for r in recommendations if 'HIGH' in r['cost_impact']]
        medium_impact = [r for r in recommendations if 'MEDIUM' in r['cost_impact']]
        low_impact = [r for r in recommendations if 'LOW' in r['cost_impact']]
        
        if high_impact:
            report.append("🚨 HIGH IMPACT CLEANUP (Immediate Cost Savings):")
            report.append("-" * 50)
            for rec in high_impact:
                report.append(f"❌ {rec['type'].upper()}: {rec['resource']}")
                report.append(f"   Reason: {rec['reason']}")
                report.append(f"   Impact: {rec['cost_impact']}")
                report.append(f"   Command: {rec['command']}")
                report.append("")
        
        if medium_impact:
            report.append("⚠️  MEDIUM IMPACT CLEANUP:")
            report.append("-" * 30)
            for rec in medium_impact:
                report.append(f"⚠️  {rec['type'].upper()}: {rec['resource']}")
                report.append(f"   Reason: {rec['reason']}")
                report.append(f"   Impact: {rec['cost_impact']}")
                report.append(f"   Command: {rec['command']}")
                report.append("")
        
        if low_impact:
            report.append("ℹ️  LOW IMPACT CLEANUP:")
            report.append("-" * 25)
            for rec in low_impact:
                report.append(f"ℹ️  {rec['type'].upper()}: {rec['resource']}")
                report.append(f"   Reason: {rec['reason']}")
                report.append(f"   Command: {rec['command']}")
                report.append("")
        
        # Cost breakdown
        if cost_savings['breakdown']:
            report.append("💰 Cost Savings Breakdown:")
            report.append("-" * 30)
            for resource_type, savings in cost_savings['breakdown'].items():
                report.append(f"   {resource_type}: {savings['count']} resources = ${savings['monthly_cost']:.2f}/month")
            report.append("")
        
        # Safety warnings
        report.append("⚠️  SAFETY WARNINGS:")
        report.append("-" * 20)
        report.append("   • Always backup data before deleting RDS instances")
        report.append("   • Verify no applications depend on resources before deletion")
        report.append("   • Consider stopping resources first, then deleting after verification")
        report.append("   • Some resources may have dependencies that need to be removed first")
        report.append("")
        
        # Next steps
        report.append("🎯 RECOMMENDED NEXT STEPS:")
        report.append("-" * 30)
        report.append("   1. Review each recommendation carefully")
        report.append("   2. Start with HIGH impact items (NAT Gateways, RDS, OpenSearch)")
        report.append("   3. Stop resources first, monitor for issues, then delete")
        report.append("   4. Use AWS Cost Explorer to verify savings")
        report.append("   5. Set up billing alerts to monitor ongoing costs")
        report.append("")
        
        report.append("=" * 80)
        
        return "\n".join(report)


def main():
    """Main cleanup execution."""
    
    print("🧹 AWS Infrastructure Cleanup for Multimodal Librarian")
    print("This script will identify resources that can be cleaned up to reduce costs.")
    print()
    
    # Initialize cleanup manager
    cleanup_manager = AWSResourceCleanup()
    
    # Scan all resources
    cleanup_report = cleanup_manager.scan_all_resources()
    
    # Generate and display report
    print("\n" + cleanup_manager.generate_cleanup_report())
    
    # Save detailed report
    report_file = f"aws-cleanup-report-{int(time.time())}.json"
    with open(report_file, 'w') as f:
        json.dump(cleanup_report, f, indent=2, default=str)
    
    print(f"📄 Detailed report saved to: {report_file}")
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)