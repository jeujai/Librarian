#!/usr/bin/env python3
"""
AWS Infrastructure Assessment Script

This script checks what AWS resources are currently running and what needs
to be restored after the cleanup operations. It provides a comprehensive
assessment of the current state and recommendations for restoration.
"""

import boto3
import json
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
import sys

class AWSInfrastructureAssessment:
    """Comprehensive AWS infrastructure assessment."""
    
    def __init__(self):
        self.session = boto3.Session()
        self.regions = ['us-east-1', 'us-west-2']  # Primary regions
        self.assessment_results = {}
        
    def run_comprehensive_assessment(self) -> Dict[str, Any]:
        """Run comprehensive infrastructure assessment."""
        
        print("🔍 AWS Infrastructure Assessment")
        print("=" * 60)
        print("Checking current state after cleanup operations...")
        print()
        
        assessment_categories = [
            ("Compute Resources", self.assess_compute_resources),
            ("Database Services", self.assess_database_services),
            ("Storage Services", self.assess_storage_services),
            ("Networking", self.assess_networking),
            ("Load Balancers", self.assess_load_balancers),
            ("Security Groups", self.assess_security_groups),
            ("IAM Resources", self.assess_iam_resources),
            ("Cost Analysis", self.assess_current_costs)
        ]
        
        for category_name, assessment_function in assessment_categories:
            print(f"\n📋 Assessing: {category_name}")
            print("-" * 40)
            
            try:
                category_result = assessment_function()
                self.assessment_results[category_name] = category_result
                self._print_category_summary(category_name, category_result)
                
            except Exception as e:
                print(f"❌ Error assessing {category_name}: {e}")
                self.assessment_results[category_name] = {
                    'error': str(e),
                    'status': 'error'
                }
        
        # Generate restoration recommendations
        self.assessment_results['restoration_plan'] = self._generate_restoration_plan()
        self.assessment_results['assessment_timestamp'] = datetime.now().isoformat()
        
        return self.assessment_results
    
    def assess_compute_resources(self) -> Dict[str, Any]:
        """Assess EC2 instances, ECS services, and Lambda functions."""
        
        results = {
            'ec2_instances': {},
            'ecs_services': {},
            'lambda_functions': {},
            'status': 'healthy'
        }
        
        for region in self.regions:
            try:
                # EC2 Assessment
                ec2 = self.session.client('ec2', region_name=region)
                instances = ec2.describe_instances()
                
                running_instances = []
                stopped_instances = []
                
                for reservation in instances['Reservations']:
                    for instance in reservation['Instances']:
                        instance_info = {
                            'id': instance['InstanceId'],
                            'type': instance['InstanceType'],
                            'state': instance['State']['Name'],
                            'launch_time': instance.get('LaunchTime', '').isoformat() if instance.get('LaunchTime') else None,
                            'tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                        }
                        
                        if instance['State']['Name'] == 'running':
                            running_instances.append(instance_info)
                        elif instance['State']['Name'] == 'stopped':
                            stopped_instances.append(instance_info)
                
                results['ec2_instances'][region] = {
                    'running': running_instances,
                    'stopped': stopped_instances,
                    'total': len(running_instances) + len(stopped_instances)
                }
                
                print(f"  {region}: {len(running_instances)} running, {len(stopped_instances)} stopped EC2 instances")
                
                # ECS Assessment
                ecs = self.session.client('ecs', region_name=region)
                clusters = ecs.list_clusters()
                
                ecs_services = []
                for cluster_arn in clusters['clusterArns']:
                    cluster_name = cluster_arn.split('/')[-1]
                    services = ecs.list_services(cluster=cluster_arn)
                    
                    for service_arn in services['serviceArns']:
                        service_name = service_arn.split('/')[-1]
                        service_details = ecs.describe_services(
                            cluster=cluster_arn,
                            services=[service_arn]
                        )
                        
                        if service_details['services']:
                            service = service_details['services'][0]
                            ecs_services.append({
                                'name': service_name,
                                'cluster': cluster_name,
                                'status': service['status'],
                                'running_count': service['runningCount'],
                                'desired_count': service['desiredCount'],
                                'task_definition': service['taskDefinition']
                            })
                
                results['ecs_services'][region] = ecs_services
                print(f"  {region}: {len(ecs_services)} ECS services found")
                
                # Lambda Assessment
                lambda_client = self.session.client('lambda', region_name=region)
                functions = lambda_client.list_functions()
                
                lambda_functions = []
                for func in functions['Functions']:
                    lambda_functions.append({
                        'name': func['FunctionName'],
                        'runtime': func['Runtime'],
                        'last_modified': func['LastModified'],
                        'memory_size': func['MemorySize'],
                        'timeout': func['Timeout']
                    })
                
                results['lambda_functions'][region] = lambda_functions
                print(f"  {region}: {len(lambda_functions)} Lambda functions found")
                
            except Exception as e:
                print(f"  ❌ Error assessing compute in {region}: {e}")
                results['status'] = 'error'
        
        return results
    
    def assess_database_services(self) -> Dict[str, Any]:
        """Assess RDS, OpenSearch, and Neptune databases."""
        
        results = {
            'rds_instances': {},
            'opensearch_domains': {},
            'neptune_clusters': {},
            'status': 'healthy'
        }
        
        for region in self.regions:
            try:
                # RDS Assessment
                rds = self.session.client('rds', region_name=region)
                db_instances = rds.describe_db_instances()
                
                rds_list = []
                for db in db_instances['DBInstances']:
                    rds_list.append({
                        'identifier': db['DBInstanceIdentifier'],
                        'engine': db['Engine'],
                        'status': db['DBInstanceStatus'],
                        'instance_class': db['DBInstanceClass'],
                        'allocated_storage': db['AllocatedStorage'],
                        'endpoint': db.get('Endpoint', {}).get('Address', 'N/A')
                    })
                
                results['rds_instances'][region] = rds_list
                print(f"  {region}: {len(rds_list)} RDS instances found")
                
                # OpenSearch Assessment
                opensearch = self.session.client('opensearch', region_name=region)
                domains = opensearch.list_domain_names()
                
                opensearch_list = []
                for domain in domains['DomainNames']:
                    domain_status = opensearch.describe_domain(DomainName=domain['DomainName'])
                    domain_info = domain_status['DomainStatus']
                    
                    opensearch_list.append({
                        'name': domain_info['DomainName'],
                        'engine_version': domain_info['EngineVersion'],
                        'processing': domain_info['Processing'],
                        'created': domain_info['Created'],
                        'deleted': domain_info['Deleted'],
                        'endpoint': domain_info.get('Endpoint', 'N/A')
                    })
                
                results['opensearch_domains'][region] = opensearch_list
                print(f"  {region}: {len(opensearch_list)} OpenSearch domains found")
                
                # Neptune Assessment
                neptune = self.session.client('neptune', region_name=region)
                clusters = neptune.describe_db_clusters()
                
                neptune_list = []
                for cluster in clusters['DBClusters']:
                    if cluster['Engine'] == 'neptune':
                        neptune_list.append({
                            'identifier': cluster['DBClusterIdentifier'],
                            'status': cluster['Status'],
                            'engine_version': cluster['EngineVersion'],
                            'endpoint': cluster.get('Endpoint', 'N/A'),
                            'reader_endpoint': cluster.get('ReaderEndpoint', 'N/A')
                        })
                
                results['neptune_clusters'][region] = neptune_list
                print(f"  {region}: {len(neptune_list)} Neptune clusters found")
                
            except Exception as e:
                print(f"  ❌ Error assessing databases in {region}: {e}")
                results['status'] = 'error'
        
        return results
    
    def assess_storage_services(self) -> Dict[str, Any]:
        """Assess S3 buckets and EBS volumes."""
        
        results = {
            's3_buckets': [],
            'ebs_volumes': {},
            'status': 'healthy'
        }
        
        try:
            # S3 Assessment (global service)
            s3 = self.session.client('s3')
            buckets = s3.list_buckets()
            
            s3_list = []
            for bucket in buckets['Buckets']:
                try:
                    # Get bucket location
                    location = s3.get_bucket_location(Bucket=bucket['Name'])
                    region = location['LocationConstraint'] or 'us-east-1'
                    
                    # Get bucket size (approximate)
                    try:
                        cloudwatch = self.session.client('cloudwatch', region_name=region)
                        metrics = cloudwatch.get_metric_statistics(
                            Namespace='AWS/S3',
                            MetricName='BucketSizeBytes',
                            Dimensions=[
                                {'Name': 'BucketName', 'Value': bucket['Name']},
                                {'Name': 'StorageType', 'Value': 'StandardStorage'}
                            ],
                            StartTime=datetime.now().replace(hour=0, minute=0, second=0),
                            EndTime=datetime.now(),
                            Period=86400,
                            Statistics=['Average']
                        )
                        
                        size_bytes = metrics['Datapoints'][0]['Average'] if metrics['Datapoints'] else 0
                        size_gb = round(size_bytes / (1024**3), 2)
                    except:
                        size_gb = 'Unknown'
                    
                    s3_list.append({
                        'name': bucket['Name'],
                        'creation_date': bucket['CreationDate'].isoformat(),
                        'region': region,
                        'size_gb': size_gb
                    })
                    
                except Exception as e:
                    s3_list.append({
                        'name': bucket['Name'],
                        'creation_date': bucket['CreationDate'].isoformat(),
                        'region': 'Unknown',
                        'size_gb': 'Unknown',
                        'error': str(e)
                    })
            
            results['s3_buckets'] = s3_list
            print(f"  Global: {len(s3_list)} S3 buckets found")
            
        except Exception as e:
            print(f"  ❌ Error assessing S3: {e}")
            results['status'] = 'error'
        
        # EBS Assessment
        for region in self.regions:
            try:
                ec2 = self.session.client('ec2', region_name=region)
                volumes = ec2.describe_volumes()
                
                ebs_list = []
                for volume in volumes['Volumes']:
                    ebs_list.append({
                        'id': volume['VolumeId'],
                        'size': volume['Size'],
                        'state': volume['State'],
                        'volume_type': volume['VolumeType'],
                        'encrypted': volume['Encrypted'],
                        'attachments': len(volume['Attachments'])
                    })
                
                results['ebs_volumes'][region] = ebs_list
                print(f"  {region}: {len(ebs_list)} EBS volumes found")
                
            except Exception as e:
                print(f"  ❌ Error assessing EBS in {region}: {e}")
                results['status'] = 'error'
        
        return results
    
    def assess_networking(self) -> Dict[str, Any]:
        """Assess VPCs, subnets, NAT gateways, and internet gateways."""
        
        results = {
            'vpcs': {},
            'nat_gateways': {},
            'internet_gateways': {},
            'status': 'healthy'
        }
        
        for region in self.regions:
            try:
                ec2 = self.session.client('ec2', region_name=region)
                
                # VPC Assessment
                vpcs = ec2.describe_vpcs()
                vpc_list = []
                
                for vpc in vpcs['Vpcs']:
                    # Get subnets for this VPC
                    subnets = ec2.describe_subnets(
                        Filters=[{'Name': 'vpc-id', 'Values': [vpc['VpcId']]}]
                    )
                    
                    vpc_info = {
                        'id': vpc['VpcId'],
                        'cidr_block': vpc['CidrBlock'],
                        'state': vpc['State'],
                        'is_default': vpc['IsDefault'],
                        'subnets': len(subnets['Subnets']),
                        'tags': {tag['Key']: tag['Value'] for tag in vpc.get('Tags', [])}
                    }
                    vpc_list.append(vpc_info)
                
                results['vpcs'][region] = vpc_list
                print(f"  {region}: {len(vpc_list)} VPCs found")
                
                # NAT Gateway Assessment
                nat_gateways = ec2.describe_nat_gateways()
                nat_list = []
                
                for nat in nat_gateways['NatGateways']:
                    nat_list.append({
                        'id': nat['NatGatewayId'],
                        'state': nat['State'],
                        'vpc_id': nat['VpcId'],
                        'subnet_id': nat['SubnetId'],
                        'create_time': nat['CreateTime'].isoformat()
                    })
                
                results['nat_gateways'][region] = nat_list
                print(f"  {region}: {len(nat_list)} NAT Gateways found")
                
                # Internet Gateway Assessment
                igws = ec2.describe_internet_gateways()
                igw_list = []
                
                for igw in igws['InternetGateways']:
                    igw_list.append({
                        'id': igw['InternetGatewayId'],
                        'attachments': len(igw['Attachments']),
                        'tags': {tag['Key']: tag['Value'] for tag in igw.get('Tags', [])}
                    })
                
                results['internet_gateways'][region] = igw_list
                print(f"  {region}: {len(igw_list)} Internet Gateways found")
                
            except Exception as e:
                print(f"  ❌ Error assessing networking in {region}: {e}")
                results['status'] = 'error'
        
        return results
    
    def assess_load_balancers(self) -> Dict[str, Any]:
        """Assess Application Load Balancers and Network Load Balancers."""
        
        results = {
            'application_load_balancers': {},
            'network_load_balancers': {},
            'status': 'healthy'
        }
        
        for region in self.regions:
            try:
                elbv2 = self.session.client('elbv2', region_name=region)
                load_balancers = elbv2.describe_load_balancers()
                
                alb_list = []
                nlb_list = []
                
                for lb in load_balancers['LoadBalancers']:
                    lb_info = {
                        'name': lb['LoadBalancerName'],
                        'arn': lb['LoadBalancerArn'],
                        'dns_name': lb['DNSName'],
                        'state': lb['State']['Code'],
                        'type': lb['Type'],
                        'scheme': lb['Scheme'],
                        'vpc_id': lb['VpcId']
                    }
                    
                    if lb['Type'] == 'application':
                        alb_list.append(lb_info)
                    elif lb['Type'] == 'network':
                        nlb_list.append(lb_info)
                
                results['application_load_balancers'][region] = alb_list
                results['network_load_balancers'][region] = nlb_list
                
                print(f"  {region}: {len(alb_list)} ALBs, {len(nlb_list)} NLBs found")
                
            except Exception as e:
                print(f"  ❌ Error assessing load balancers in {region}: {e}")
                results['status'] = 'error'
        
        return results
    
    def assess_security_groups(self) -> Dict[str, Any]:
        """Assess security groups."""
        
        results = {
            'security_groups': {},
            'status': 'healthy'
        }
        
        for region in self.regions:
            try:
                ec2 = self.session.client('ec2', region_name=region)
                security_groups = ec2.describe_security_groups()
                
                sg_list = []
                for sg in security_groups['SecurityGroups']:
                    sg_list.append({
                        'id': sg['GroupId'],
                        'name': sg['GroupName'],
                        'description': sg['Description'],
                        'vpc_id': sg.get('VpcId', 'EC2-Classic'),
                        'inbound_rules': len(sg['IpPermissions']),
                        'outbound_rules': len(sg['IpPermissionsEgress'])
                    })
                
                results['security_groups'][region] = sg_list
                print(f"  {region}: {len(sg_list)} Security Groups found")
                
            except Exception as e:
                print(f"  ❌ Error assessing security groups in {region}: {e}")
                results['status'] = 'error'
        
        return results
    
    def assess_iam_resources(self) -> Dict[str, Any]:
        """Assess IAM roles, policies, and users."""
        
        results = {
            'roles': [],
            'policies': [],
            'users': [],
            'status': 'healthy'
        }
        
        try:
            iam = self.session.client('iam')
            
            # Roles Assessment
            roles = iam.list_roles()
            role_list = []
            
            for role in roles['Roles']:
                # Filter for multimodal-librarian related roles
                if 'multimodal' in role['RoleName'].lower() or 'librarian' in role['RoleName'].lower():
                    role_list.append({
                        'name': role['RoleName'],
                        'arn': role['Arn'],
                        'create_date': role['CreateDate'].isoformat(),
                        'path': role['Path']
                    })
            
            results['roles'] = role_list
            print(f"  Global: {len(role_list)} relevant IAM roles found")
            
            # Policies Assessment
            policies = iam.list_policies(Scope='Local')  # Only customer-managed policies
            policy_list = []
            
            for policy in policies['Policies']:
                if 'multimodal' in policy['PolicyName'].lower() or 'librarian' in policy['PolicyName'].lower():
                    policy_list.append({
                        'name': policy['PolicyName'],
                        'arn': policy['Arn'],
                        'create_date': policy['CreateDate'].isoformat(),
                        'attachment_count': policy['AttachmentCount']
                    })
            
            results['policies'] = policy_list
            print(f"  Global: {len(policy_list)} relevant IAM policies found")
            
            # Users Assessment (if any)
            users = iam.list_users()
            user_list = []
            
            for user in users['Users']:
                if 'multimodal' in user['UserName'].lower() or 'librarian' in user['UserName'].lower():
                    user_list.append({
                        'name': user['UserName'],
                        'arn': user['Arn'],
                        'create_date': user['CreateDate'].isoformat()
                    })
            
            results['users'] = user_list
            print(f"  Global: {len(user_list)} relevant IAM users found")
            
        except Exception as e:
            print(f"  ❌ Error assessing IAM: {e}")
            results['status'] = 'error'
        
        return results
    
    def assess_current_costs(self) -> Dict[str, Any]:
        """Assess current AWS costs."""
        
        results = {
            'monthly_costs': {},
            'daily_costs': {},
            'status': 'healthy'
        }
        
        try:
            # Cost Explorer is only available in us-east-1
            ce = self.session.client('ce', region_name='us-east-1')
            
            # Get current month costs
            from datetime import datetime, timedelta
            
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
            
            monthly_costs = ce.get_cost_and_usage(
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
            
            monthly_breakdown = {}
            total_monthly = 0
            
            for result in monthly_costs['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['BlendedCost']['Amount'])
                    monthly_breakdown[service] = cost
                    total_monthly += cost
            
            results['monthly_costs'] = {
                'total': round(total_monthly, 2),
                'by_service': monthly_breakdown,
                'period': f"{start_date} to {end_date}"
            }
            
            print(f"  Current month cost: ${total_monthly:.2f}")
            
            # Get yesterday's costs
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            today = datetime.now().strftime('%Y-%m-%d')
            
            daily_costs = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': yesterday,
                    'End': today
                },
                Granularity='DAILY',
                Metrics=['BlendedCost']
            )
            
            daily_total = 0
            if daily_costs['ResultsByTime']:
                daily_total = float(daily_costs['ResultsByTime'][0]['Total']['BlendedCost']['Amount'])
            
            results['daily_costs'] = {
                'yesterday': round(daily_total, 2),
                'date': yesterday
            }
            
            print(f"  Yesterday's cost: ${daily_total:.2f}")
            
        except Exception as e:
            print(f"  ❌ Error assessing costs: {e}")
            results['status'] = 'error'
        
        return results
    
    def _print_category_summary(self, category_name: str, category_result: Dict[str, Any]):
        """Print summary for each assessment category."""
        
        if category_result.get('status') == 'error':
            print(f"  ❌ Assessment failed: {category_result.get('error', 'Unknown error')}")
            return
        
        # Print key metrics based on category
        if category_name == "Compute Resources":
            total_running = sum(len(region_data.get('running', [])) 
                              for region_data in category_result.get('ec2_instances', {}).values())
            total_ecs = sum(len(services) 
                          for services in category_result.get('ecs_services', {}).values())
            total_lambda = sum(len(functions) 
                             for functions in category_result.get('lambda_functions', {}).values())
            
            print(f"  📊 Summary: {total_running} running EC2, {total_ecs} ECS services, {total_lambda} Lambda functions")
            
        elif category_name == "Database Services":
            total_rds = sum(len(instances) 
                          for instances in category_result.get('rds_instances', {}).values())
            total_opensearch = sum(len(domains) 
                                 for domains in category_result.get('opensearch_domains', {}).values())
            total_neptune = sum(len(clusters) 
                              for clusters in category_result.get('neptune_clusters', {}).values())
            
            print(f"  📊 Summary: {total_rds} RDS instances, {total_opensearch} OpenSearch domains, {total_neptune} Neptune clusters")
            
        elif category_name == "Storage Services":
            s3_count = len(category_result.get('s3_buckets', []))
            total_ebs = sum(len(volumes) 
                          for volumes in category_result.get('ebs_volumes', {}).values())
            
            print(f"  📊 Summary: {s3_count} S3 buckets, {total_ebs} EBS volumes")
            
        elif category_name == "Networking":
            total_vpcs = sum(len(vpcs) 
                           for vpcs in category_result.get('vpcs', {}).values())
            total_nats = sum(len(nats) 
                           for nats in category_result.get('nat_gateways', {}).values())
            
            print(f"  📊 Summary: {total_vpcs} VPCs, {total_nats} NAT Gateways")
            
        elif category_name == "Cost Analysis":
            monthly_cost = category_result.get('monthly_costs', {}).get('total', 0)
            daily_cost = category_result.get('daily_costs', {}).get('yesterday', 0)
            
            print(f"  📊 Summary: ${monthly_cost:.2f} this month, ${daily_cost:.2f} yesterday")
    
    def _generate_restoration_plan(self) -> Dict[str, Any]:
        """Generate restoration plan based on assessment results."""
        
        plan = {
            'critical_missing': [],
            'recommended_actions': [],
            'estimated_costs': {},
            'priority_order': []
        }
        
        # Check for critical missing components
        
        # 1. Check for running compute resources
        total_running_ec2 = 0
        total_ecs_services = 0
        
        compute_results = self.assessment_results.get('Compute Resources', {})
        for region_data in compute_results.get('ec2_instances', {}).values():
            total_running_ec2 += len(region_data.get('running', []))
        
        for services in compute_results.get('ecs_services', {}).values():
            total_ecs_services += len(services)
        
        if total_running_ec2 == 0 and total_ecs_services == 0:
            plan['critical_missing'].append({
                'component': 'Application Hosting',
                'description': 'No running EC2 instances or ECS services found',
                'impact': 'Application cannot run',
                'priority': 'CRITICAL'
            })
        
        # 2. Check for databases
        db_results = self.assessment_results.get('Database Services', {})
        total_rds = sum(len(instances) for instances in db_results.get('rds_instances', {}).values())
        total_opensearch = sum(len(domains) for domains in db_results.get('opensearch_domains', {}).values())
        
        if total_rds == 0:
            plan['critical_missing'].append({
                'component': 'PostgreSQL Database',
                'description': 'No RDS instances found',
                'impact': 'Application data storage unavailable',
                'priority': 'CRITICAL'
            })
        
        if total_opensearch == 0:
            plan['critical_missing'].append({
                'component': 'OpenSearch Domain',
                'description': 'No OpenSearch domains found',
                'impact': 'Vector search and RAG functionality unavailable',
                'priority': 'HIGH'
            })
        
        # 3. Check for networking
        network_results = self.assessment_results.get('Networking', {})
        total_nats = sum(len(nats) for nats in network_results.get('nat_gateways', {}).values())
        
        if total_nats == 0:
            plan['recommended_actions'].append({
                'action': 'Create NAT Gateway',
                'description': 'NAT Gateway needed for private subnet internet access',
                'estimated_cost': '$45/month',
                'priority': 'MEDIUM'
            })
        
        # 4. Check for load balancers
        lb_results = self.assessment_results.get('Load Balancers', {})
        total_albs = sum(len(albs) for albs in lb_results.get('application_load_balancers', {}).values())
        
        if total_albs == 0:
            plan['recommended_actions'].append({
                'action': 'Create Application Load Balancer',
                'description': 'ALB needed for application traffic distribution',
                'estimated_cost': '$20/month',
                'priority': 'HIGH'
            })
        
        # Generate priority order
        critical_items = [item for item in plan['critical_missing'] if item['priority'] == 'CRITICAL']
        high_items = [item for item in plan['critical_missing'] if item['priority'] == 'HIGH']
        
        plan['priority_order'] = [
            'Restore PostgreSQL Database (RDS)',
            'Deploy Application (ECS/EC2)',
            'Create OpenSearch Domain',
            'Set up Load Balancer',
            'Configure NAT Gateway',
            'Verify Security Groups',
            'Test End-to-End Connectivity'
        ]
        
        # Estimate total restoration costs
        base_costs = {
            'RDS (db.t3.micro)': 15,
            'OpenSearch (t3.small.search)': 25,
            'ECS Fargate': 30,
            'ALB': 20,
            'NAT Gateway': 45,
            'Data Transfer': 10
        }
        
        plan['estimated_costs'] = {
            'monthly_minimum': sum(base_costs.values()),
            'breakdown': base_costs,
            'note': 'Costs are estimates and may vary based on usage'
        }
        
        return plan

def main():
    """Main execution function."""
    
    assessment = AWSInfrastructureAssessment()
    
    try:
        results = assessment.run_comprehensive_assessment()
        
        # Save results to file
        timestamp = int(time.time())
        results_file = f"aws-infrastructure-assessment-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Assessment Results Summary")
        print("=" * 50)
        
        # Print restoration plan
        restoration_plan = results.get('restoration_plan', {})
        critical_missing = restoration_plan.get('critical_missing', [])
        
        if critical_missing:
            print(f"\n🚨 Critical Missing Components: {len(critical_missing)}")
            for item in critical_missing:
                print(f"   ❌ {item['component']}: {item['description']}")
                print(f"      Impact: {item['impact']}")
                print(f"      Priority: {item['priority']}")
        else:
            print("\n✅ No critical components missing")
        
        # Print cost estimates
        estimated_costs = restoration_plan.get('estimated_costs', {})
        if estimated_costs:
            print(f"\n💰 Estimated Restoration Costs:")
            print(f"   Monthly minimum: ${estimated_costs.get('monthly_minimum', 0)}")
            
            breakdown = estimated_costs.get('breakdown', {})
            for service, cost in breakdown.items():
                print(f"   - {service}: ${cost}/month")
        
        # Print priority order
        priority_order = restoration_plan.get('priority_order', [])
        if priority_order:
            print(f"\n📋 Recommended Restoration Order:")
            for i, action in enumerate(priority_order, 1):
                print(f"   {i}. {action}")
        
        print(f"\n📊 Full assessment results saved to: {results_file}")
        
        return results
        
    except Exception as e:
        print(f"❌ Assessment failed: {e}")
        return None

if __name__ == "__main__":
    main()