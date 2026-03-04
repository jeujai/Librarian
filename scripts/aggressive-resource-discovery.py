#!/usr/bin/env python3
"""
Aggressive AWS Resource Discovery
Finds ALL resources that could be causing costs, including hidden ones
"""

import boto3
import json
from datetime import datetime
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

class AggressiveDiscovery:
    def __init__(self):
        self.session = boto3.Session()
        self.regions = self.get_all_regions()
        self.resources_found = []
        
    def get_all_regions(self):
        """Get all AWS regions"""
        ec2 = self.session.client('ec2', region_name='us-east-1')
        regions = ec2.describe_regions()['Regions']
        return [region['RegionName'] for region in regions]
    
    def log_resource(self, service: str, resource_type: str, resource_id: str, region: str, status: str, details: dict = None):
        """Log discovered resource"""
        resource = {
            'service': service,
            'type': resource_type,
            'id': resource_id,
            'region': region,
            'status': status,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        self.resources_found.append(resource)
        print(f"🔍 Found {service} {resource_type}: {resource_id} ({status}) in {region}")
    
    def scan_region_comprehensive(self, region):
        """Comprehensive scan of a single region"""
        print(f"\n🔍 Scanning {region}...")
        region_resources = []
        
        try:
            # ECS - All clusters, services, tasks
            try:
                ecs = self.session.client('ecs', region_name=region)
                
                # Clusters
                clusters = ecs.list_clusters()
                for cluster_arn in clusters['clusterArns']:
                    cluster_name = cluster_arn.split('/')[-1]
                    cluster_details = ecs.describe_clusters(clusters=[cluster_arn])
                    if cluster_details['clusters']:
                        cluster = cluster_details['clusters'][0]
                        self.log_resource('ECS', 'Cluster', cluster_name, region, cluster['status'], {
                            'runningTasksCount': cluster.get('runningTasksCount', 0),
                            'activeServicesCount': cluster.get('activeServicesCount', 0)
                        })
                        
                        # Services in cluster
                        services = ecs.list_services(cluster=cluster_arn)
                        for service_arn in services['serviceArns']:
                            service_name = service_arn.split('/')[-1]
                            service_details = ecs.describe_services(cluster=cluster_arn, services=[service_arn])
                            if service_details['services']:
                                service = service_details['services'][0]
                                self.log_resource('ECS', 'Service', service_name, region, service['status'], {
                                    'desiredCount': service.get('desiredCount', 0),
                                    'runningCount': service.get('runningCount', 0),
                                    'taskDefinition': service.get('taskDefinition', '')
                                })
                        
                        # Tasks in cluster
                        tasks = ecs.list_tasks(cluster=cluster_arn)
                        for task_arn in tasks['taskArns']:
                            task_id = task_arn.split('/')[-1]
                            task_details = ecs.describe_tasks(cluster=cluster_arn, tasks=[task_arn])
                            if task_details['tasks']:
                                task = task_details['tasks'][0]
                                self.log_resource('ECS', 'Task', task_id, region, task['lastStatus'], {
                                    'cpu': task.get('cpu', ''),
                                    'memory': task.get('memory', ''),
                                    'createdAt': str(task.get('createdAt', ''))
                                })
                                
            except Exception as e:
                print(f"  ECS scan error in {region}: {str(e)}")
            
            # Neptune - All clusters and instances
            try:
                neptune = self.session.client('neptune', region_name=region)
                
                # Neptune clusters
                clusters = neptune.describe_db_clusters()
                for cluster in clusters['DBClusters']:
                    self.log_resource('Neptune', 'Cluster', cluster['DBClusterIdentifier'], region, cluster['Status'], {
                        'engine': cluster.get('Engine', ''),
                        'engineVersion': cluster.get('EngineVersion', ''),
                        'dbClusterMembers': len(cluster.get('DBClusterMembers', []))
                    })
                
                # Neptune instances
                instances = neptune.describe_db_instances()
                for instance in instances['DBInstances']:
                    self.log_resource('Neptune', 'Instance', instance['DBInstanceIdentifier'], region, instance['DBInstanceStatus'], {
                        'instanceClass': instance.get('DBInstanceClass', ''),
                        'engine': instance.get('Engine', ''),
                        'multiAZ': instance.get('MultiAZ', False)
                    })
                    
            except Exception as e:
                print(f"  Neptune scan error in {region}: {str(e)}")
            
            # OpenSearch
            try:
                opensearch = self.session.client('opensearch', region_name=region)
                domains = opensearch.list_domain_names()
                
                for domain in domains['DomainNames']:
                    domain_name = domain['DomainName']
                    domain_status = opensearch.describe_domain(DomainName=domain_name)
                    domain_info = domain_status['DomainStatus']
                    
                    self.log_resource('OpenSearch', 'Domain', domain_name, region, 'Active' if domain_info.get('Created') else 'Unknown', {
                        'instanceType': domain_info.get('ClusterConfig', {}).get('InstanceType', ''),
                        'instanceCount': domain_info.get('ClusterConfig', {}).get('InstanceCount', 0),
                        'dedicatedMasterEnabled': domain_info.get('ClusterConfig', {}).get('DedicatedMasterEnabled', False)
                    })
                    
            except Exception as e:
                print(f"  OpenSearch scan error in {region}: {str(e)}")
            
            # ElastiCache
            try:
                elasticache = self.session.client('elasticache', region_name=region)
                
                # Redis clusters
                redis_clusters = elasticache.describe_replication_groups()
                for cluster in redis_clusters['ReplicationGroups']:
                    self.log_resource('ElastiCache', 'Redis', cluster['ReplicationGroupId'], region, cluster['Status'], {
                        'nodeType': cluster.get('CacheNodeType', ''),
                        'numCacheClusters': cluster.get('NumCacheClusters', 0)
                    })
                
                # Memcached clusters
                memcached_clusters = elasticache.describe_cache_clusters()
                for cluster in memcached_clusters['CacheClusters']:
                    self.log_resource('ElastiCache', 'Memcached', cluster['CacheClusterId'], region, cluster['CacheClusterStatus'], {
                        'nodeType': cluster.get('CacheNodeType', ''),
                        'numCacheNodes': cluster.get('NumCacheNodes', 0)
                    })
                    
            except Exception as e:
                print(f"  ElastiCache scan error in {region}: {str(e)}")
            
            # RDS
            try:
                rds = self.session.client('rds', region_name=region)
                instances = rds.describe_db_instances()
                
                for instance in instances['DBInstances']:
                    self.log_resource('RDS', 'Instance', instance['DBInstanceIdentifier'], region, instance['DBInstanceStatus'], {
                        'instanceClass': instance.get('DBInstanceClass', ''),
                        'engine': instance.get('Engine', ''),
                        'multiAZ': instance.get('MultiAZ', False),
                        'storageType': instance.get('StorageType', ''),
                        'allocatedStorage': instance.get('AllocatedStorage', 0)
                    })
                    
            except Exception as e:
                print(f"  RDS scan error in {region}: {str(e)}")
            
            # NAT Gateways
            try:
                ec2 = self.session.client('ec2', region_name=region)
                nat_gateways = ec2.describe_nat_gateways()
                
                for nat in nat_gateways['NatGateways']:
                    if nat['State'] not in ['deleted']:
                        self.log_resource('EC2', 'NAT Gateway', nat['NatGatewayId'], region, nat['State'], {
                            'vpcId': nat.get('VpcId', ''),
                            'subnetId': nat.get('SubnetId', '')
                        })
                        
            except Exception as e:
                print(f"  NAT Gateway scan error in {region}: {str(e)}")
            
            # Load Balancers
            try:
                elbv2 = self.session.client('elbv2', region_name=region)
                load_balancers = elbv2.describe_load_balancers()
                
                for lb in load_balancers['LoadBalancers']:
                    self.log_resource('ELB', 'Load Balancer', lb['LoadBalancerName'], region, lb['State']['Code'], {
                        'type': lb.get('Type', ''),
                        'scheme': lb.get('Scheme', ''),
                        'vpcId': lb.get('VpcId', '')
                    })
                    
            except Exception as e:
                print(f"  Load Balancer scan error in {region}: {str(e)}")
                
        except Exception as e:
            print(f"  Region {region} scan error: {str(e)}")
        
        return region_resources
    
    def discover_all_resources(self):
        """Discover all resources across all regions using parallel processing"""
        print("🚀 AGGRESSIVE RESOURCE DISCOVERY")
        print("=" * 60)
        print("Scanning ALL regions for ANY resources that could be causing costs...")
        print("=" * 60)
        
        # Use parallel processing to scan all regions faster
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_region = {executor.submit(self.scan_region_comprehensive, region): region for region in self.regions}
            
            for future in as_completed(future_to_region):
                region = future_to_region[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"❌ Error scanning {region}: {str(e)}")
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"aggressive-discovery-{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.resources_found, f, indent=2, default=str)
        
        # Summary
        print(f"\n📊 DISCOVERY SUMMARY:")
        print(f"  Total resources found: {len(self.resources_found)}")
        
        # Group by service
        by_service = {}
        for resource in self.resources_found:
            service = resource['service']
            if service not in by_service:
                by_service[service] = []
            by_service[service].append(resource)
        
        for service, resources in by_service.items():
            print(f"  {service}: {len(resources)} resources")
            for resource in resources:
                status_emoji = "🟢" if resource['status'] in ['running', 'available', 'active'] else "🔴"
                print(f"    {status_emoji} {resource['type']} {resource['id']} ({resource['status']}) in {resource['region']}")
        
        print(f"\n📝 Full report saved to: {filename}")
        
        # Identify cost-causing resources
        high_cost_resources = []
        for resource in self.resources_found:
            if resource['service'] in ['Neptune', 'ECS', 'OpenSearch', 'ElastiCache', 'RDS'] and resource['status'] in ['running', 'available', 'active']:
                high_cost_resources.append(resource)
        
        if high_cost_resources:
            print(f"\n🚨 HIGH-COST RESOURCES FOUND:")
            for resource in high_cost_resources:
                print(f"  💰 {resource['service']} {resource['type']} {resource['id']} in {resource['region']}")
        else:
            print(f"\n❓ NO HIGH-COST RESOURCES FOUND - This suggests:")
            print(f"    • Resources may be in regions not scanned")
            print(f"    • Resources may have different naming/types")
            print(f"    • There may be permission issues")
            print(f"    • Costs may be from data transfer or storage")
        
        return len(high_cost_resources) > 0

def main():
    discovery = AggressiveDiscovery()
    
    try:
        found_resources = discovery.discover_all_resources()
        return 0 if found_resources else 1
        
    except Exception as e:
        print(f"❌ Critical error during discovery: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())