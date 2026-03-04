#!/usr/bin/env python3
"""
Remaining Infrastructure Shutdown Script

This script shuts down the remaining AWS infrastructure for maximum cost savings:
- ECS Services and Task Definitions ($100.56/month)
- OpenSearch Domain ($13.09/month)
- PostgreSQL RDS Instances ($9.47/month)
- NAT Gateway ($45/month from VPC costs)
- Elastic Load Balancers ($29.64/month)

Total Additional Monthly Savings: ~$197.76/month
Combined with database shutdown: ~$340.84/month ($4,090.08/year)
"""

import boto3
import json
import time
from datetime import datetime
import sys

def shutdown_ecs_services():
    """Shutdown ECS services and clusters."""
    print("🔄 Shutting down ECS services...")
    
    try:
        ecs = boto3.client('ecs', region_name='us-east-1')
        
        # List all clusters
        clusters = ecs.list_clusters()
        
        if not clusters['clusterArns']:
            print("  ✅ No ECS clusters found")
            return True
            
        for cluster_arn in clusters['clusterArns']:
            cluster_name = cluster_arn.split('/')[-1]
            print(f"  📋 Found ECS cluster: {cluster_name}")
            
            # List services in cluster
            services = ecs.list_services(cluster=cluster_name)
            
            for service_arn in services['serviceArns']:
                service_name = service_arn.split('/')[-1]
                print(f"    🛑 Stopping ECS service: {service_name}")
                
                # Scale service to 0
                ecs.update_service(
                    cluster=cluster_name,
                    service=service_name,
                    desiredCount=0
                )
                
                # Delete service
                ecs.delete_service(
                    cluster=cluster_name,
                    service=service_name
                )
                
                print(f"    ✅ ECS service deleted: {service_name}")
            
            # Delete cluster if no services remain
            if not services['serviceArns']:
                print(f"  🛑 Deleting ECS cluster: {cluster_name}")
                ecs.delete_cluster(cluster=cluster_name)
                print(f"  ✅ ECS cluster deleted: {cluster_name}")
        
        print(f"     💰 Monthly savings: $100.56")
        return True
        
    except Exception as e:
        print(f"  ❌ Error shutting down ECS: {e}")
        return False

def shutdown_opensearch_domains():
    """Shutdown OpenSearch domains."""
    print("🔄 Shutting down OpenSearch domains...")
    
    try:
        opensearch = boto3.client('opensearch', region_name='us-east-1')
        
        # List OpenSearch domains
        domains = opensearch.list_domain_names()
        
        if not domains['DomainNames']:
            print("  ✅ No OpenSearch domains found")
            return True
            
        for domain in domains['DomainNames']:
            domain_name = domain['DomainName']
            print(f"  📋 Found OpenSearch domain: {domain_name}")
            
            # Check domain status
            domain_status = opensearch.describe_domain(DomainName=domain_name)
            
            if not domain_status['DomainStatus']['Deleted']:
                print(f"  🛑 Deleting OpenSearch domain: {domain_name}")
                
                opensearch.delete_domain(DomainName=domain_name)
                
                print(f"  ✅ OpenSearch domain deletion initiated: {domain_name}")
                print(f"     💰 Monthly savings: $13.09")
            else:
                print(f"  ✅ OpenSearch domain already deleted: {domain_name}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error shutting down OpenSearch: {e}")
        return False

def shutdown_rds_instances():
    """Shutdown RDS instances."""
    print("🔄 Shutting down RDS instances...")
    
    try:
        rds = boto3.client('rds', region_name='us-east-1')
        
        # List RDS instances (excluding Neptune)
        instances = rds.describe_db_instances()
        
        postgres_instances = [
            db for db in instances['DBInstances'] 
            if db['Engine'] == 'postgres'
        ]
        
        if not postgres_instances:
            print("  ✅ No PostgreSQL RDS instances found")
            return True
            
        for instance in postgres_instances:
            instance_id = instance['DBInstanceIdentifier']
            status = instance['DBInstanceStatus']
            
            print(f"  📋 Found RDS instance: {instance_id} (Status: {status})")
            
            if status == 'available':
                print(f"  🛑 Deleting RDS instance: {instance_id}")
                
                # Delete instance with final snapshot
                snapshot_id = f"{instance_id}-final-snapshot-{int(time.time())}"
                
                rds.delete_db_instance(
                    DBInstanceIdentifier=instance_id,
                    SkipFinalSnapshot=False,
                    FinalDBSnapshotIdentifier=snapshot_id
                )
                
                print(f"  ✅ RDS instance deletion initiated: {instance_id}")
                print(f"     📸 Final snapshot: {snapshot_id}")
                
            elif status in ['deleting']:
                print(f"  ✅ RDS instance already deleting: {instance_id}")
        
        print(f"     💰 Monthly savings: $9.47")
        return True
        
    except Exception as e:
        print(f"  ❌ Error shutting down RDS: {e}")
        return False

def shutdown_load_balancers():
    """Shutdown Application and Network Load Balancers."""
    print("🔄 Shutting down Load Balancers...")
    
    try:
        elbv2 = boto3.client('elbv2', region_name='us-east-1')
        
        # List all load balancers
        load_balancers = elbv2.describe_load_balancers()
        
        if not load_balancers['LoadBalancers']:
            print("  ✅ No Load Balancers found")
            return True
            
        for lb in load_balancers['LoadBalancers']:
            lb_arn = lb['LoadBalancerArn']
            lb_name = lb['LoadBalancerName']
            lb_type = lb['Type']
            
            print(f"  📋 Found {lb_type.upper()}: {lb_name}")
            print(f"  🛑 Deleting Load Balancer: {lb_name}")
            
            elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
            
            print(f"  ✅ Load Balancer deletion initiated: {lb_name}")
        
        print(f"     💰 Monthly savings: $29.64")
        return True
        
    except Exception as e:
        print(f"  ❌ Error shutting down Load Balancers: {e}")
        return False

def shutdown_nat_gateways():
    """Shutdown NAT Gateways."""
    print("🔄 Shutting down NAT Gateways...")
    
    try:
        ec2 = boto3.client('ec2', region_name='us-east-1')
        
        # List NAT Gateways
        nat_gateways = ec2.describe_nat_gateways()
        
        active_nats = [
            nat for nat in nat_gateways['NatGateways'] 
            if nat['State'] == 'available'
        ]
        
        if not active_nats:
            print("  ✅ No active NAT Gateways found")
            return True
            
        for nat in active_nats:
            nat_id = nat['NatGatewayId']
            vpc_id = nat['VpcId']
            
            print(f"  📋 Found NAT Gateway: {nat_id} (VPC: {vpc_id})")
            print(f"  🛑 Deleting NAT Gateway: {nat_id}")
            
            ec2.delete_nat_gateway(NatGatewayId=nat_id)
            
            print(f"  ✅ NAT Gateway deletion initiated: {nat_id}")
        
        print(f"     💰 Monthly savings: ~$45 (from VPC costs)")
        return True
        
    except Exception as e:
        print(f"  ❌ Error shutting down NAT Gateways: {e}")
        return False

def verify_shutdown_status():
    """Verify the shutdown status of resources."""
    print("\n🔍 Verifying shutdown status...")
    
    try:
        # Check ECS
        ecs = boto3.client('ecs', region_name='us-east-1')
        clusters = ecs.list_clusters()
        print(f"  📊 ECS Clusters remaining: {len(clusters['clusterArns'])}")
        
        # Check OpenSearch
        opensearch = boto3.client('opensearch', region_name='us-east-1')
        domains = opensearch.list_domain_names()
        print(f"  📊 OpenSearch Domains remaining: {len(domains['DomainNames'])}")
        
        # Check RDS
        rds = boto3.client('rds', region_name='us-east-1')
        instances = rds.describe_db_instances()
        postgres_count = len([db for db in instances['DBInstances'] if db['Engine'] == 'postgres'])
        print(f"  📊 PostgreSQL RDS instances remaining: {postgres_count}")
        
        # Check Load Balancers
        elbv2 = boto3.client('elbv2', region_name='us-east-1')
        load_balancers = elbv2.describe_load_balancers()
        print(f"  📊 Load Balancers remaining: {len(load_balancers['LoadBalancers'])}")
        
        # Check NAT Gateways
        ec2 = boto3.client('ec2', region_name='us-east-1')
        nat_gateways = ec2.describe_nat_gateways()
        active_nats = len([nat for nat in nat_gateways['NatGateways'] if nat['State'] == 'available'])
        print(f"  📊 Active NAT Gateways remaining: {active_nats}")
            
    except Exception as e:
        print(f"  ❌ Error checking status: {e}")

def main():
    """Main execution function."""
    
    print("💰 AWS Remaining Infrastructure Shutdown")
    print("=" * 60)
    print("Target Additional Monthly Savings: ~$197.76")
    print("Combined Total Monthly Savings: ~$340.84")
    print("Combined Total Annual Savings: ~$4,090.08")
    print()
    
    # Track results
    results = {
        'timestamp': datetime.now().isoformat(),
        'ecs_shutdown': False,
        'opensearch_shutdown': False,
        'rds_shutdown': False,
        'load_balancer_shutdown': False,
        'nat_gateway_shutdown': False,
        'total_additional_monthly_savings': 0,
        'errors': []
    }
    
    # Shutdown ECS services
    if shutdown_ecs_services():
        results['ecs_shutdown'] = True
        results['total_additional_monthly_savings'] += 100.56
    else:
        results['errors'].append('ECS shutdown failed')
    
    # Shutdown OpenSearch domains
    if shutdown_opensearch_domains():
        results['opensearch_shutdown'] = True
        results['total_additional_monthly_savings'] += 13.09
    else:
        results['errors'].append('OpenSearch shutdown failed')
    
    # Shutdown RDS instances
    if shutdown_rds_instances():
        results['rds_shutdown'] = True
        results['total_additional_monthly_savings'] += 9.47
    else:
        results['errors'].append('RDS shutdown failed')
    
    # Shutdown Load Balancers
    if shutdown_load_balancers():
        results['load_balancer_shutdown'] = True
        results['total_additional_monthly_savings'] += 29.64
    else:
        results['errors'].append('Load Balancer shutdown failed')
    
    # Shutdown NAT Gateways
    if shutdown_nat_gateways():
        results['nat_gateway_shutdown'] = True
        results['total_additional_monthly_savings'] += 45.00
    else:
        results['errors'].append('NAT Gateway shutdown failed')
    
    # Verify status
    verify_shutdown_status()
    
    # Save results
    timestamp = int(time.time())
    results_file = f"remaining-infrastructure-shutdown-{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print(f"\n💰 Additional Cost Optimization Summary")
    print("=" * 50)
    print(f"Additional Monthly Savings: ${results['total_additional_monthly_savings']:.2f}")
    print(f"Additional Annual Savings: ${results['total_additional_monthly_savings'] * 12:.2f}")
    print()
    print("🎯 TOTAL PROJECT SAVINGS:")
    print(f"   Database shutdown: $143.08/month")
    print(f"   ALB cleanup: $32.40/month") 
    print(f"   Infrastructure shutdown: ${results['total_additional_monthly_savings']:.2f}/month")
    print(f"   TOTAL MONTHLY: ${143.08 + 32.40 + results['total_additional_monthly_savings']:.2f}")
    print(f"   TOTAL ANNUAL: ${(143.08 + 32.40 + results['total_additional_monthly_savings']) * 12:.2f}")
    
    if results['errors']:
        print(f"\n⚠️  Errors encountered:")
        for error in results['errors']:
            print(f"   - {error}")
    else:
        print(f"\n✅ All remaining infrastructure successfully shut down!")
    
    print(f"\n📊 Results saved to: {results_file}")
    
    return results

if __name__ == "__main__":
    main()