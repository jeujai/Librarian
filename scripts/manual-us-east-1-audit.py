#!/usr/bin/env python3
"""
Manual audit of us-east-1 to find all resources
"""

import boto3
import json
from datetime import datetime
import sys

def audit_us_east_1():
    session = boto3.Session()
    region = 'us-east-1'
    
    print("🔍 MANUAL US-EAST-1 AUDIT")
    print("=" * 60)
    print("Checking every possible resource type that could be causing costs...")
    print()
    
    # Neptune
    print("🔍 NEPTUNE:")
    try:
        neptune = session.client('neptune', region_name=region)
        
        clusters = neptune.describe_db_clusters()
        print(f"  Clusters: {len(clusters['DBClusters'])}")
        for cluster in clusters['DBClusters']:
            print(f"    • {cluster['DBClusterIdentifier']} - {cluster['Status']}")
        
        instances = neptune.describe_db_instances()
        print(f"  Instances: {len(instances['DBInstances'])}")
        for instance in instances['DBInstances']:
            print(f"    • {instance['DBInstanceIdentifier']} ({instance['DBInstanceClass']}) - {instance['DBInstanceStatus']}")
            
    except Exception as e:
        print(f"  Error: {e}")
    
    # ECS
    print("\n🔍 ECS:")
    try:
        ecs = session.client('ecs', region_name=region)
        
        clusters = ecs.list_clusters()
        print(f"  Clusters: {len(clusters['clusterArns'])}")
        
        for cluster_arn in clusters['clusterArns']:
            cluster_name = cluster_arn.split('/')[-1]
            print(f"    • Cluster: {cluster_name}")
            
            services = ecs.list_services(cluster=cluster_arn)
            print(f"      Services: {len(services['serviceArns'])}")
            
            for service_arn in services['serviceArns']:
                service_name = service_arn.split('/')[-1]
                service_details = ecs.describe_services(cluster=cluster_arn, services=[service_arn])
                if service_details['services']:
                    service = service_details['services'][0]
                    print(f"        • {service_name}: desired={service.get('desiredCount', 0)}, running={service.get('runningCount', 0)}")
            
            tasks = ecs.list_tasks(cluster=cluster_arn)
            print(f"      Tasks: {len(tasks['taskArns'])}")
            
            if tasks['taskArns']:
                task_details = ecs.describe_tasks(cluster=cluster_arn, tasks=tasks['taskArns'])
                for task in task_details['tasks']:
                    task_id = task['taskArn'].split('/')[-1]
                    print(f"        • {task_id}: {task['lastStatus']} (CPU: {task.get('cpu', 'N/A')}, Memory: {task.get('memory', 'N/A')})")
                    
    except Exception as e:
        print(f"  Error: {e}")
    
    # OpenSearch
    print("\n🔍 OPENSEARCH:")
    try:
        opensearch = session.client('opensearch', region_name=region)
        
        domains = opensearch.list_domain_names()
        print(f"  Domains: {len(domains['DomainNames'])}")
        
        for domain in domains['DomainNames']:
            domain_name = domain['DomainName']
            domain_status = opensearch.describe_domain(DomainName=domain_name)
            domain_info = domain_status['DomainStatus']
            
            instance_type = domain_info.get('ClusterConfig', {}).get('InstanceType', 'N/A')
            instance_count = domain_info.get('ClusterConfig', {}).get('InstanceCount', 0)
            
            print(f"    • {domain_name}: {instance_type} x{instance_count}")
            
    except Exception as e:
        print(f"  Error: {e}")
    
    # ElastiCache
    print("\n🔍 ELASTICACHE:")
    try:
        elasticache = session.client('elasticache', region_name=region)
        
        # Redis
        redis_clusters = elasticache.describe_replication_groups()
        print(f"  Redis clusters: {len(redis_clusters['ReplicationGroups'])}")
        for cluster in redis_clusters['ReplicationGroups']:
            print(f"    • {cluster['ReplicationGroupId']}: {cluster['Status']} ({cluster.get('CacheNodeType', 'N/A')})")
        
        # Memcached
        memcached_clusters = elasticache.describe_cache_clusters()
        print(f"  Memcached clusters: {len(memcached_clusters['CacheClusters'])}")
        for cluster in memcached_clusters['CacheClusters']:
            print(f"    • {cluster['CacheClusterId']}: {cluster['CacheClusterStatus']} ({cluster.get('CacheNodeType', 'N/A')})")
            
    except Exception as e:
        print(f"  Error: {e}")
    
    # RDS
    print("\n🔍 RDS:")
    try:
        rds = session.client('rds', region_name=region)
        
        instances = rds.describe_db_instances()
        print(f"  Instances: {len(instances['DBInstances'])}")
        for instance in instances['DBInstances']:
            print(f"    • {instance['DBInstanceIdentifier']} ({instance['DBInstanceClass']}): {instance['DBInstanceStatus']}")
            
    except Exception as e:
        print(f"  Error: {e}")
    
    # EC2 Instances
    print("\n🔍 EC2 INSTANCES:")
    try:
        ec2 = session.client('ec2', region_name=region)
        
        instances = ec2.describe_instances()
        instance_count = 0
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                if instance['State']['Name'] != 'terminated':
                    instance_count += 1
                    print(f"    • {instance['InstanceId']} ({instance['InstanceType']}): {instance['State']['Name']}")
        
        print(f"  Total instances: {instance_count}")
        
    except Exception as e:
        print(f"  Error: {e}")
    
    # NAT Gateways
    print("\n🔍 NAT GATEWAYS:")
    try:
        ec2 = session.client('ec2', region_name=region)
        
        nat_gateways = ec2.describe_nat_gateways()
        active_nats = [nat for nat in nat_gateways['NatGateways'] if nat['State'] not in ['deleted', 'deleting']]
        print(f"  Active NAT Gateways: {len(active_nats)}")
        
        for nat in active_nats:
            print(f"    • {nat['NatGatewayId']}: {nat['State']} (VPC: {nat.get('VpcId', 'N/A')})")
            
    except Exception as e:
        print(f"  Error: {e}")
    
    # Load Balancers
    print("\n🔍 LOAD BALANCERS:")
    try:
        elbv2 = session.client('elbv2', region_name=region)
        
        load_balancers = elbv2.describe_load_balancers()
        print(f"  Load Balancers: {len(load_balancers['LoadBalancers'])}")
        
        for lb in load_balancers['LoadBalancers']:
            print(f"    • {lb['LoadBalancerName']} ({lb['Type']}): {lb['State']['Code']}")
            
    except Exception as e:
        print(f"  Error: {e}")
    
    # VPC Endpoints (already deleted some)
    print("\n🔍 VPC ENDPOINTS:")
    try:
        ec2 = session.client('ec2', region_name=region)
        
        endpoints = ec2.describe_vpc_endpoints()
        active_endpoints = [ep for ep in endpoints['VpcEndpoints'] if ep['State'] not in ['deleted', 'deleting']]
        print(f"  Active VPC Endpoints: {len(active_endpoints)}")
        
        for endpoint in active_endpoints:
            print(f"    • {endpoint['VpcEndpointId']}: {endpoint['State']} ({endpoint.get('ServiceName', 'N/A')})")
            
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    print("💡 NEXT STEPS:")
    print("1. If resources are found above, they need to be manually deleted")
    print("2. Check AWS Console for any resources not detected by API")
    print("3. Look for resources with different naming patterns")
    print("4. Consider contacting AWS Support if costs persist without visible resources")

if __name__ == "__main__":
    audit_us_east_1()