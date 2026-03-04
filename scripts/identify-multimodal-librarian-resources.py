#!/usr/bin/env python3
"""
Identify Multimodal Librarian Resources

This script specifically identifies AWS resources that belong to the Multimodal Librarian project
and separates them from other applications like CollaborativeEditorProdStack.
"""

import boto3
import json
import time
from typing import Dict, List, Any
from datetime import datetime

class MultimodalLibrarianResourceIdentifier:
    """Identify resources specifically belonging to Multimodal Librarian project."""
    
    def __init__(self):
        self.session = boto3.Session()
        self.multimodal_keywords = [
            'multimodal-lib',
            'multimodal-librarian',
            'multimodal_librarian',
            'MultimodalLibrarian'
        ]
        
    def identify_multimodal_resources(self) -> Dict[str, Any]:
        """Identify all resources belonging to Multimodal Librarian project."""
        
        results = {
            'multimodal_librarian_resources': {},
            'other_application_resources': {},
            'summary': {},
            'cost_breakdown': {}
        }
        
        try:
            print("🔍 Identifying Multimodal Librarian Resources")
            print("=" * 60)
            
            # Analyze ECS Services
            results['multimodal_librarian_resources']['ecs'] = self._identify_ecs_resources()
            results['other_application_resources']['ecs'] = self._identify_other_ecs_resources()
            
            # Analyze RDS/Database Resources
            results['multimodal_librarian_resources']['databases'] = self._identify_database_resources()
            results['other_application_resources']['databases'] = self._identify_other_database_resources()
            
            # Analyze S3 Buckets
            results['multimodal_librarian_resources']['s3'] = self._identify_s3_resources()
            results['other_application_resources']['s3'] = self._identify_other_s3_resources()
            
            # Analyze VPCs and Networking
            results['multimodal_librarian_resources']['networking'] = self._identify_networking_resources()
            results['other_application_resources']['networking'] = self._identify_other_networking_resources()
            
            # Analyze Load Balancers
            results['multimodal_librarian_resources']['load_balancers'] = self._identify_load_balancer_resources()
            results['other_application_resources']['load_balancers'] = self._identify_other_load_balancer_resources()
            
            # Generate summary
            results['summary'] = self._generate_summary(results)
            
            self._print_results(results)
            
        except Exception as e:
            print(f"❌ Error during resource identification: {e}")
            results['error'] = str(e)
        
        return results
    
    def _is_multimodal_resource(self, resource_name: str, tags: Dict = None) -> bool:
        """Check if a resource belongs to Multimodal Librarian project."""
        
        # Check resource name
        for keyword in self.multimodal_keywords:
            if keyword.lower() in resource_name.lower():
                return True
        
        # Check tags if available
        if tags:
            for key, value in tags.items():
                if isinstance(value, str):
                    for keyword in self.multimodal_keywords:
                        if keyword.lower() in value.lower():
                            return True
        
        return False
    
    def _identify_ecs_resources(self) -> Dict[str, Any]:
        """Identify ECS resources belonging to Multimodal Librarian."""
        
        ecs = self.session.client('ecs', region_name='us-east-1')
        multimodal_ecs = {
            'clusters': [],
            'services': [],
            'task_definitions': []
        }
        
        try:
            # Get clusters
            clusters_response = ecs.list_clusters()
            for cluster_arn in clusters_response['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                if self._is_multimodal_resource(cluster_name):
                    
                    # Get cluster details
                    cluster_details = ecs.describe_clusters(clusters=[cluster_arn])
                    if cluster_details['clusters']:
                        cluster = cluster_details['clusters'][0]
                        multimodal_ecs['clusters'].append({
                            'name': cluster['clusterName'],
                            'arn': cluster['clusterArn'],
                            'status': cluster['status'],
                            'running_tasks': cluster['runningTasksCount'],
                            'pending_tasks': cluster['pendingTasksCount'],
                            'active_services': cluster['activeServicesCount']
                        })
                        
                        # Get services in this cluster
                        services_response = ecs.list_services(cluster=cluster_arn)
                        for service_arn in services_response['serviceArns']:
                            service_name = service_arn.split('/')[-1]
                            if self._is_multimodal_resource(service_name):
                                
                                service_details = ecs.describe_services(
                                    cluster=cluster_arn,
                                    services=[service_arn]
                                )
                                
                                if service_details['services']:
                                    service = service_details['services'][0]
                                    multimodal_ecs['services'].append({
                                        'name': service['serviceName'],
                                        'cluster': cluster_name,
                                        'status': service['status'],
                                        'desired_count': service['desiredCount'],
                                        'running_count': service['runningCount'],
                                        'task_definition': service['taskDefinition']
                                    })
            
        except Exception as e:
            print(f"⚠️  Error identifying ECS resources: {e}")
        
        return multimodal_ecs
    
    def _identify_other_ecs_resources(self) -> Dict[str, Any]:
        """Identify ECS resources NOT belonging to Multimodal Librarian."""
        
        ecs = self.session.client('ecs', region_name='us-east-1')
        other_ecs = {
            'clusters': [],
            'services': []
        }
        
        try:
            # Get clusters
            clusters_response = ecs.list_clusters()
            for cluster_arn in clusters_response['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                if not self._is_multimodal_resource(cluster_name):
                    
                    # Get cluster details
                    cluster_details = ecs.describe_clusters(clusters=[cluster_arn])
                    if cluster_details['clusters']:
                        cluster = cluster_details['clusters'][0]
                        other_ecs['clusters'].append({
                            'name': cluster['clusterName'],
                            'arn': cluster['clusterArn'],
                            'status': cluster['status'],
                            'running_tasks': cluster['runningTasksCount'],
                            'pending_tasks': cluster['pendingTasksCount'],
                            'active_services': cluster['activeServicesCount']
                        })
                        
                        # Get services in this cluster
                        services_response = ecs.list_services(cluster=cluster_arn)
                        for service_arn in services_response['serviceArns']:
                            service_details = ecs.describe_services(
                                cluster=cluster_arn,
                                services=[service_arn]
                            )
                            
                            if service_details['services']:
                                service = service_details['services'][0]
                                other_ecs['services'].append({
                                    'name': service['serviceName'],
                                    'cluster': cluster_name,
                                    'status': service['status'],
                                    'desired_count': service['desiredCount'],
                                    'running_count': service['runningCount'],
                                    'task_definition': service['taskDefinition']
                                })
            
        except Exception as e:
            print(f"⚠️  Error identifying other ECS resources: {e}")
        
        return other_ecs
    
    def _identify_database_resources(self) -> Dict[str, Any]:
        """Identify database resources belonging to Multimodal Librarian."""
        
        multimodal_dbs = {
            'rds_instances': [],
            'neptune_clusters': [],
            'opensearch_domains': []
        }
        
        try:
            # RDS instances
            rds = self.session.client('rds', region_name='us-east-1')
            rds_response = rds.describe_db_instances()
            
            for instance in rds_response['DBInstances']:
                instance_id = instance['DBInstanceIdentifier']
                tags = instance.get('TagList', [])
                tag_dict = {tag['Key']: tag['Value'] for tag in tags}
                
                if self._is_multimodal_resource(instance_id, tag_dict):
                    multimodal_dbs['rds_instances'].append({
                        'identifier': instance_id,
                        'engine': instance['Engine'],
                        'status': instance['DBInstanceStatus'],
                        'instance_class': instance['DBInstanceClass'],
                        'endpoint': instance.get('Endpoint', {}).get('Address', 'N/A')
                    })
            
            # Neptune clusters
            neptune = self.session.client('neptune', region_name='us-east-1')
            neptune_response = neptune.describe_db_clusters()
            
            for cluster in neptune_response['DBClusters']:
                cluster_id = cluster['DBClusterIdentifier']
                tags = cluster.get('TagList', [])
                tag_dict = {tag['Key']: tag['Value'] for tag in tags}
                
                if self._is_multimodal_resource(cluster_id, tag_dict):
                    multimodal_dbs['neptune_clusters'].append({
                        'identifier': cluster_id,
                        'status': cluster['Status'],
                        'engine_version': cluster['EngineVersion'],
                        'endpoint': cluster['Endpoint']
                    })
            
            # OpenSearch domains
            opensearch = self.session.client('opensearch', region_name='us-east-1')
            opensearch_response = opensearch.list_domain_names()
            
            for domain_info in opensearch_response['DomainNames']:
                domain_name = domain_info['DomainName']
                
                if self._is_multimodal_resource(domain_name):
                    domain_details = opensearch.describe_domain(DomainName=domain_name)
                    domain = domain_details['DomainStatus']
                    
                    multimodal_dbs['opensearch_domains'].append({
                        'name': domain_name,
                        'engine_version': domain['EngineVersion'],
                        'processing': domain['Processing'],
                        'created': domain['Created'],
                        'deleted': domain['Deleted']
                    })
            
        except Exception as e:
            print(f"⚠️  Error identifying database resources: {e}")
        
        return multimodal_dbs
    
    def _identify_other_database_resources(self) -> Dict[str, Any]:
        """Identify database resources NOT belonging to Multimodal Librarian."""
        
        other_dbs = {
            'rds_instances': [],
            'neptune_clusters': [],
            'opensearch_domains': []
        }
        
        try:
            # RDS instances
            rds = self.session.client('rds', region_name='us-east-1')
            rds_response = rds.describe_db_instances()
            
            for instance in rds_response['DBInstances']:
                instance_id = instance['DBInstanceIdentifier']
                tags = instance.get('TagList', [])
                tag_dict = {tag['Key']: tag['Value'] for tag in tags}
                
                if not self._is_multimodal_resource(instance_id, tag_dict):
                    other_dbs['rds_instances'].append({
                        'identifier': instance_id,
                        'engine': instance['Engine'],
                        'status': instance['DBInstanceStatus'],
                        'instance_class': instance['DBInstanceClass'],
                        'endpoint': instance.get('Endpoint', {}).get('Address', 'N/A')
                    })
            
            # Neptune clusters
            neptune = self.session.client('neptune', region_name='us-east-1')
            neptune_response = neptune.describe_db_clusters()
            
            for cluster in neptune_response['DBClusters']:
                cluster_id = cluster['DBClusterIdentifier']
                tags = cluster.get('TagList', [])
                tag_dict = {tag['Key']: tag['Value'] for tag in tags}
                
                if not self._is_multimodal_resource(cluster_id, tag_dict):
                    other_dbs['neptune_clusters'].append({
                        'identifier': cluster_id,
                        'status': cluster['Status'],
                        'engine_version': cluster['EngineVersion'],
                        'endpoint': cluster['Endpoint']
                    })
            
            # OpenSearch domains
            opensearch = self.session.client('opensearch', region_name='us-east-1')
            opensearch_response = opensearch.list_domain_names()
            
            for domain_info in opensearch_response['DomainNames']:
                domain_name = domain_info['DomainName']
                
                if not self._is_multimodal_resource(domain_name):
                    domain_details = opensearch.describe_domain(DomainName=domain_name)
                    domain = domain_details['DomainStatus']
                    
                    other_dbs['opensearch_domains'].append({
                        'name': domain_name,
                        'engine_version': domain['EngineVersion'],
                        'processing': domain['Processing'],
                        'created': domain['Created'],
                        'deleted': domain['Deleted']
                    })
            
        except Exception as e:
            print(f"⚠️  Error identifying other database resources: {e}")
        
        return other_dbs
    
    def _identify_s3_resources(self) -> List[Dict[str, Any]]:
        """Identify S3 buckets belonging to Multimodal Librarian."""
        
        multimodal_s3 = []
        
        try:
            s3 = self.session.client('s3')
            buckets_response = s3.list_buckets()
            
            for bucket in buckets_response['Buckets']:
                bucket_name = bucket['Name']
                
                if self._is_multimodal_resource(bucket_name):
                    multimodal_s3.append({
                        'name': bucket_name,
                        'creation_date': bucket['CreationDate'].isoformat()
                    })
        
        except Exception as e:
            print(f"⚠️  Error identifying S3 resources: {e}")
        
        return multimodal_s3
    
    def _identify_other_s3_resources(self) -> List[Dict[str, Any]]:
        """Identify S3 buckets NOT belonging to Multimodal Librarian."""
        
        other_s3 = []
        
        try:
            s3 = self.session.client('s3')
            buckets_response = s3.list_buckets()
            
            for bucket in buckets_response['Buckets']:
                bucket_name = bucket['Name']
                
                if not self._is_multimodal_resource(bucket_name):
                    other_s3.append({
                        'name': bucket_name,
                        'creation_date': bucket['CreationDate'].isoformat()
                    })
        
        except Exception as e:
            print(f"⚠️  Error identifying other S3 resources: {e}")
        
        return other_s3
    
    def _identify_networking_resources(self) -> Dict[str, Any]:
        """Identify networking resources belonging to Multimodal Librarian."""
        
        multimodal_networking = {
            'vpcs': [],
            'nat_gateways': [],
            'internet_gateways': []
        }
        
        try:
            ec2 = self.session.client('ec2', region_name='us-east-1')
            
            # VPCs
            vpcs_response = ec2.describe_vpcs()
            for vpc in vpcs_response['Vpcs']:
                vpc_id = vpc['VpcId']
                tags = {tag['Key']: tag['Value'] for tag in vpc.get('Tags', [])}
                
                if self._is_multimodal_resource(vpc_id, tags):
                    multimodal_networking['vpcs'].append({
                        'id': vpc_id,
                        'cidr_block': vpc['CidrBlock'],
                        'state': vpc['State'],
                        'tags': tags
                    })
            
            # NAT Gateways
            nat_response = ec2.describe_nat_gateways()
            for nat in nat_response['NatGateways']:
                nat_id = nat['NatGatewayId']
                vpc_id = nat['VpcId']
                tags = {tag['Key']: tag['Value'] for tag in nat.get('Tags', [])}
                
                if self._is_multimodal_resource(nat_id, tags) or any(
                    self._is_multimodal_resource(vpc['id']) 
                    for vpc in multimodal_networking['vpcs'] 
                    if vpc['id'] == vpc_id
                ):
                    multimodal_networking['nat_gateways'].append({
                        'id': nat_id,
                        'state': nat['State'],
                        'vpc_id': vpc_id,
                        'subnet_id': nat['SubnetId']
                    })
            
            # Internet Gateways
            igw_response = ec2.describe_internet_gateways()
            for igw in igw_response['InternetGateways']:
                igw_id = igw['InternetGatewayId']
                tags = {tag['Key']: tag['Value'] for tag in igw.get('Tags', [])}
                
                if self._is_multimodal_resource(igw_id, tags):
                    multimodal_networking['internet_gateways'].append({
                        'id': igw_id,
                        'attachments': len(igw['Attachments']),
                        'tags': tags
                    })
        
        except Exception as e:
            print(f"⚠️  Error identifying networking resources: {e}")
        
        return multimodal_networking
    
    def _identify_other_networking_resources(self) -> Dict[str, Any]:
        """Identify networking resources NOT belonging to Multimodal Librarian."""
        
        other_networking = {
            'vpcs': [],
            'nat_gateways': [],
            'internet_gateways': []
        }
        
        try:
            ec2 = self.session.client('ec2', region_name='us-east-1')
            
            # VPCs
            vpcs_response = ec2.describe_vpcs()
            for vpc in vpcs_response['Vpcs']:
                vpc_id = vpc['VpcId']
                tags = {tag['Key']: tag['Value'] for tag in vpc.get('Tags', [])}
                
                if not self._is_multimodal_resource(vpc_id, tags):
                    other_networking['vpcs'].append({
                        'id': vpc_id,
                        'cidr_block': vpc['CidrBlock'],
                        'state': vpc['State'],
                        'tags': tags,
                        'project': tags.get('Project', 'Unknown')
                    })
            
            # NAT Gateways
            nat_response = ec2.describe_nat_gateways()
            for nat in nat_response['NatGateways']:
                nat_id = nat['NatGatewayId']
                vpc_id = nat['VpcId']
                tags = {tag['Key']: tag['Value'] for tag in nat.get('Tags', [])}
                
                if not self._is_multimodal_resource(nat_id, tags):
                    # Check if VPC belongs to multimodal
                    vpc_is_multimodal = False
                    for vpc in other_networking['vpcs']:
                        if vpc['id'] == vpc_id and self._is_multimodal_resource(vpc['id'], vpc['tags']):
                            vpc_is_multimodal = True
                            break
                    
                    if not vpc_is_multimodal:
                        other_networking['nat_gateways'].append({
                            'id': nat_id,
                            'state': nat['State'],
                            'vpc_id': vpc_id,
                            'subnet_id': nat['SubnetId']
                        })
            
            # Internet Gateways
            igw_response = ec2.describe_internet_gateways()
            for igw in igw_response['InternetGateways']:
                igw_id = igw['InternetGatewayId']
                tags = {tag['Key']: tag['Value'] for tag in igw.get('Tags', [])}
                
                if not self._is_multimodal_resource(igw_id, tags):
                    other_networking['internet_gateways'].append({
                        'id': igw_id,
                        'attachments': len(igw['Attachments']),
                        'tags': tags,
                        'project': tags.get('Project', 'Unknown')
                    })
        
        except Exception as e:
            print(f"⚠️  Error identifying other networking resources: {e}")
        
        return other_networking
    
    def _identify_load_balancer_resources(self) -> List[Dict[str, Any]]:
        """Identify load balancers belonging to Multimodal Librarian."""
        
        multimodal_lbs = []
        
        try:
            elbv2 = self.session.client('elbv2', region_name='us-east-1')
            lbs_response = elbv2.describe_load_balancers()
            
            for lb in lbs_response['LoadBalancers']:
                lb_name = lb['LoadBalancerName']
                
                if self._is_multimodal_resource(lb_name):
                    multimodal_lbs.append({
                        'name': lb_name,
                        'arn': lb['LoadBalancerArn'],
                        'dns_name': lb['DNSName'],
                        'state': lb['State']['Code'],
                        'type': lb['Type'],
                        'scheme': lb['Scheme'],
                        'vpc_id': lb['VpcId']
                    })
        
        except Exception as e:
            print(f"⚠️  Error identifying load balancer resources: {e}")
        
        return multimodal_lbs
    
    def _identify_other_load_balancer_resources(self) -> List[Dict[str, Any]]:
        """Identify load balancers NOT belonging to Multimodal Librarian."""
        
        other_lbs = []
        
        try:
            elbv2 = self.session.client('elbv2', region_name='us-east-1')
            lbs_response = elbv2.describe_load_balancers()
            
            for lb in lbs_response['LoadBalancers']:
                lb_name = lb['LoadBalancerName']
                
                if not self._is_multimodal_resource(lb_name):
                    other_lbs.append({
                        'name': lb_name,
                        'arn': lb['LoadBalancerArn'],
                        'dns_name': lb['DNSName'],
                        'state': lb['State']['Code'],
                        'type': lb['Type'],
                        'scheme': lb['Scheme'],
                        'vpc_id': lb['VpcId']
                    })
        
        except Exception as e:
            print(f"⚠️  Error identifying other load balancer resources: {e}")
        
        return other_lbs
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of resource identification."""
        
        multimodal = results['multimodal_librarian_resources']
        other = results['other_application_resources']
        
        summary = {
            'multimodal_librarian': {
                'ecs_clusters': len(multimodal['ecs']['clusters']),
                'ecs_services': len(multimodal['ecs']['services']),
                'rds_instances': len(multimodal['databases']['rds_instances']),
                'neptune_clusters': len(multimodal['databases']['neptune_clusters']),
                'opensearch_domains': len(multimodal['databases']['opensearch_domains']),
                's3_buckets': len(multimodal['s3']),
                'vpcs': len(multimodal['networking']['vpcs']),
                'nat_gateways': len(multimodal['networking']['nat_gateways']),
                'load_balancers': len(multimodal['load_balancers'])
            },
            'other_applications': {
                'ecs_clusters': len(other['ecs']['clusters']),
                'ecs_services': len(other['ecs']['services']),
                'rds_instances': len(other['databases']['rds_instances']),
                'neptune_clusters': len(other['databases']['neptune_clusters']),
                'opensearch_domains': len(other['databases']['opensearch_domains']),
                's3_buckets': len(other['s3']),
                'vpcs': len(other['networking']['vpcs']),
                'nat_gateways': len(other['networking']['nat_gateways']),
                'load_balancers': len(other['load_balancers'])
            }
        }
        
        return summary
    
    def _print_results(self, results: Dict[str, Any]):
        """Print formatted results."""
        
        print("\n🎯 MULTIMODAL LIBRARIAN RESOURCES")
        print("=" * 50)
        
        multimodal = results['multimodal_librarian_resources']
        
        # ECS Resources
        if multimodal['ecs']['clusters'] or multimodal['ecs']['services']:
            print("\n📦 ECS Resources:")
            for cluster in multimodal['ecs']['clusters']:
                print(f"   Cluster: {cluster['name']} ({cluster['status']})")
                print(f"      Running Tasks: {cluster['running_tasks']}")
                print(f"      Active Services: {cluster['active_services']}")
            
            for service in multimodal['ecs']['services']:
                print(f"   Service: {service['name']}")
                print(f"      Cluster: {service['cluster']}")
                print(f"      Status: {service['status']}")
                print(f"      Desired/Running: {service['desired_count']}/{service['running_count']}")
        
        # Database Resources
        databases = multimodal['databases']
        if databases['rds_instances'] or databases['neptune_clusters'] or databases['opensearch_domains']:
            print("\n🗄️  Database Resources:")
            for rds in databases['rds_instances']:
                print(f"   RDS: {rds['identifier']} ({rds['engine']}, {rds['status']})")
            
            for neptune in databases['neptune_clusters']:
                print(f"   Neptune: {neptune['identifier']} ({neptune['status']})")
            
            for opensearch in databases['opensearch_domains']:
                print(f"   OpenSearch: {opensearch['name']} ({opensearch['engine_version']})")
        
        # S3 Resources
        if multimodal['s3']:
            print(f"\n🪣 S3 Buckets ({len(multimodal['s3'])}):")
            for bucket in multimodal['s3']:
                print(f"   {bucket['name']}")
        
        # Networking Resources
        networking = multimodal['networking']
        if networking['vpcs'] or networking['nat_gateways'] or networking['internet_gateways']:
            print("\n🌐 Networking Resources:")
            for vpc in networking['vpcs']:
                print(f"   VPC: {vpc['id']} ({vpc['cidr_block']})")
            
            for nat in networking['nat_gateways']:
                print(f"   NAT Gateway: {nat['id']} ({nat['state']})")
            
            for igw in networking['internet_gateways']:
                print(f"   Internet Gateway: {igw['id']}")
        
        # Load Balancers
        if multimodal['load_balancers']:
            print("\n⚖️  Load Balancers:")
            for lb in multimodal['load_balancers']:
                print(f"   {lb['name']} ({lb['type']}, {lb['state']})")
        
        print("\n🔄 OTHER APPLICATION RESOURCES")
        print("=" * 50)
        
        other = results['other_application_resources']
        
        # Other ECS Resources
        if other['ecs']['clusters'] or other['ecs']['services']:
            print("\n📦 Other ECS Resources:")
            for cluster in other['ecs']['clusters']:
                print(f"   Cluster: {cluster['name']} ({cluster['status']})")
            
            for service in other['ecs']['services']:
                print(f"   Service: {service['name']} (Cluster: {service['cluster']})")
        
        # Other Database Resources
        other_dbs = other['databases']
        if other_dbs['rds_instances'] or other_dbs['neptune_clusters'] or other_dbs['opensearch_domains']:
            print("\n🗄️  Other Database Resources:")
            for rds in other_dbs['rds_instances']:
                print(f"   RDS: {rds['identifier']} ({rds['engine']})")
            
            for neptune in other_dbs['neptune_clusters']:
                print(f"   Neptune: {neptune['identifier']}")
            
            for opensearch in other_dbs['opensearch_domains']:
                print(f"   OpenSearch: {opensearch['name']}")
        
        # Other Networking
        other_net = other['networking']
        if other_net['vpcs']:
            print("\n🌐 Other Networking Resources:")
            for vpc in other_net['vpcs']:
                project = vpc.get('project', 'Unknown')
                print(f"   VPC: {vpc['id']} (Project: {project})")
        
        # Summary
        summary = results['summary']
        print(f"\n📊 SUMMARY")
        print("=" * 30)
        print(f"Multimodal Librarian Resources:")
        print(f"   ECS Clusters: {summary['multimodal_librarian']['ecs_clusters']}")
        print(f"   ECS Services: {summary['multimodal_librarian']['ecs_services']}")
        print(f"   Databases: {summary['multimodal_librarian']['rds_instances'] + summary['multimodal_librarian']['neptune_clusters'] + summary['multimodal_librarian']['opensearch_domains']}")
        print(f"   S3 Buckets: {summary['multimodal_librarian']['s3_buckets']}")
        print(f"   VPCs: {summary['multimodal_librarian']['vpcs']}")
        print(f"   Load Balancers: {summary['multimodal_librarian']['load_balancers']}")
        
        print(f"\nOther Application Resources:")
        print(f"   ECS Clusters: {summary['other_applications']['ecs_clusters']}")
        print(f"   ECS Services: {summary['other_applications']['ecs_services']}")
        print(f"   Databases: {summary['other_applications']['rds_instances'] + summary['other_applications']['neptune_clusters'] + summary['other_applications']['opensearch_domains']}")
        print(f"   S3 Buckets: {summary['other_applications']['s3_buckets']}")
        print(f"   VPCs: {summary['other_applications']['vpcs']}")
        print(f"   Load Balancers: {summary['other_applications']['load_balancers']}")

def main():
    """Main execution function."""
    
    identifier = MultimodalLibrarianResourceIdentifier()
    
    try:
        results = identifier.identify_multimodal_resources()
        
        # Save detailed results
        timestamp = int(time.time())
        results_file = f"multimodal-librarian-resources-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Resource identification failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())