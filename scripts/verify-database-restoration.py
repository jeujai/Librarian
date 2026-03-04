#!/usr/bin/env python3
"""
Verify that OpenSearch, Vector Store, and Neptune are properly restored and accessible
"""

import boto3
import json
import sys
from datetime import datetime, timedelta

# AWS clients
ecs = boto3.client('ecs')
logs = boto3.client('logs')
neptune = boto3.client('neptune')
opensearch = boto3.client('opensearch')
ec2 = boto3.client('ec2')

# Configuration
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
LOG_GROUP = '/ecs/multimodal-lib-prod-app'
NEPTUNE_CLUSTER_ID = 'multimodal-lib-prod-neptune'
OPENSEARCH_DOMAIN = 'multimodal-lib-prod-search'

def check_task_definition():
    """Check the current task definition"""
    print("=" * 80)
    print("📋 Checking Task Definition")
    print("=" * 80)
    
    response = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    service = response['services'][0]
    task_def_arn = service['taskDefinition']
    
    print(f"✅ Service: {service['serviceName']}")
    print(f"   Status: {service['status']}")
    print(f"   Task Definition: {task_def_arn}")
    
    # Get task definition details
    task_def_response = ecs.describe_task_definition(
        taskDefinition=task_def_arn
    )
    
    task_def = task_def_response['taskDefinition']
    env_vars = task_def['containerDefinitions'][0].get('environment', [])
    
    # Check for database-related environment variables
    database_vars = {}
    skip_vars = []
    
    for var in env_vars:
        name = var['name']
        value = var['value']
        
        if 'SKIP_' in name and ('OPENSEARCH' in name or 'NEPTUNE' in name or 'VECTOR' in name or 'KNOWLEDGE' in name):
            skip_vars.append(f"{name}={value}")
        elif any(keyword in name for keyword in ['OPENSEARCH', 'NEPTUNE', 'VECTOR_STORE', 'KNOWLEDGE_GRAPH', 'USE_AWS']):
            database_vars[name] = value
    
    print(f"\n📊 Database Configuration:")
    print(f"   Database variables: {len(database_vars)}")
    print(f"   SKIP variables: {len(skip_vars)}")
    
    if skip_vars:
        print(f"\n⚠️  Warning: Found SKIP variables:")
        for var in skip_vars:
            print(f"      {var}")
    else:
        print(f"\n✅ No SKIP variables found (databases enabled)")
    
    print(f"\n🔧 Database Configuration Variables:")
    for name, value in sorted(database_vars.items()):
        print(f"   {name}={value}")
    
    return database_vars, skip_vars

def check_neptune_status():
    """Check Neptune cluster status"""
    print("\n" + "=" * 80)
    print("🔍 Checking Neptune Status")
    print("=" * 80)
    
    try:
        response = neptune.describe_db_clusters(
            DBClusterIdentifier=NEPTUNE_CLUSTER_ID
        )
        
        cluster = response['DBClusters'][0]
        
        print(f"✅ Neptune Cluster: {cluster['DBClusterIdentifier']}")
        print(f"   Status: {cluster['Status']}")
        print(f"   Endpoint: {cluster['Endpoint']}:{cluster['Port']}")
        print(f"   Engine: {cluster['Engine']} {cluster['EngineVersion']}")
        print(f"   Multi-AZ: {cluster.get('MultiAZ', False)}")
        
        # Check instances
        instances = cluster.get('DBClusterMembers', [])
        print(f"\n   Instances: {len(instances)}")
        for instance in instances:
            print(f"      - {instance['DBInstanceIdentifier']}")
            print(f"        Writer: {instance['IsClusterWriter']}")
        
        # Check VPC
        vpc_sg = cluster.get('VpcSecurityGroups', [])
        print(f"\n   VPC Security Groups: {len(vpc_sg)}")
        for sg in vpc_sg:
            print(f"      - {sg['VpcSecurityGroupId']}: {sg['Status']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking Neptune: {e}")
        return False

def check_opensearch_status():
    """Check OpenSearch domain status"""
    print("\n" + "=" * 80)
    print("🔍 Checking OpenSearch Status")
    print("=" * 80)
    
    try:
        response = opensearch.describe_domain(
            DomainName=OPENSEARCH_DOMAIN
        )
        
        domain = response['DomainStatus']
        
        print(f"✅ OpenSearch Domain: {domain['DomainName']}")
        print(f"   Status: Processing={domain['Processing']}, Created={domain['Created']}, Deleted={domain['Deleted']}")
        
        if 'Endpoints' in domain and 'vpc' in domain['Endpoints']:
            endpoint = domain['Endpoints']['vpc']
            print(f"   Endpoint: https://{endpoint}")
        else:
            print(f"   ⚠️  No VPC endpoint found")
        
        print(f"   Engine: {domain['EngineVersion']}")
        
        # Check cluster config
        cluster_config = domain['ClusterConfig']
        print(f"\n   Cluster Configuration:")
        print(f"      Instance Type: {cluster_config['InstanceType']}")
        print(f"      Instance Count: {cluster_config['InstanceCount']}")
        print(f"      Dedicated Master: {cluster_config.get('DedicatedMasterEnabled', False)}")
        print(f"      Zone Awareness: {cluster_config.get('ZoneAwarenessEnabled', False)}")
        
        # Check VPC
        if 'VPCOptions' in domain:
            vpc_options = domain['VPCOptions']
            print(f"\n   VPC Configuration:")
            print(f"      VPC ID: {vpc_options.get('VPCId', 'N/A')}")
            print(f"      Subnets: {len(vpc_options.get('SubnetIds', []))}")
            print(f"      Security Groups: {len(vpc_options.get('SecurityGroupIds', []))}")
            
            for sg_id in vpc_options.get('SecurityGroupIds', []):
                print(f"         - {sg_id}")
        
        # Check encryption
        print(f"\n   Security:")
        print(f"      Encryption at Rest: {domain.get('EncryptionAtRestOptions', {}).get('Enabled', False)}")
        print(f"      Node-to-Node Encryption: {domain.get('NodeToNodeEncryptionOptions', {}).get('Enabled', False)}")
        print(f"      HTTPS Enforced: {domain.get('DomainEndpointOptions', {}).get('EnforceHTTPS', False)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking OpenSearch: {e}")
        return False

def check_network_connectivity():
    """Check network connectivity between ECS and databases"""
    print("\n" + "=" * 80)
    print("🌐 Checking Network Connectivity")
    print("=" * 80)
    
    try:
        # Get ECS service details
        ecs_response = ecs.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        service = ecs_response['services'][0]
        
        # Get task details
        tasks_response = ecs.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            desiredStatus='RUNNING'
        )
        
        if not tasks_response['taskArns']:
            print("⚠️  No running tasks found")
            return False
        
        task_details = ecs.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=[tasks_response['taskArns'][0]]
        )
        
        task = task_details['tasks'][0]
        
        # Get network configuration
        attachments = task.get('attachments', [])
        eni_id = None
        
        for attachment in attachments:
            if attachment['type'] == 'ElasticNetworkInterface':
                for detail in attachment['details']:
                    if detail['name'] == 'networkInterfaceId':
                        eni_id = detail['value']
                        break
        
        if eni_id:
            print(f"✅ ECS Task Network Interface: {eni_id}")
            
            # Get ENI details
            eni_response = ec2.describe_network_interfaces(
                NetworkInterfaceIds=[eni_id]
            )
            
            eni = eni_response['NetworkInterfaces'][0]
            
            print(f"   VPC: {eni['VpcId']}")
            print(f"   Subnet: {eni['SubnetId']}")
            print(f"   Private IP: {eni.get('PrivateIpAddress', 'N/A')}")
            
            print(f"\n   Security Groups:")
            for sg in eni['Groups']:
                print(f"      - {sg['GroupId']}: {sg['GroupName']}")
        else:
            print("⚠️  Could not find network interface")
        
        # Get Neptune VPC info
        neptune_response = neptune.describe_db_clusters(
            DBClusterIdentifier=NEPTUNE_CLUSTER_ID
        )
        neptune_cluster = neptune_response['DBClusters'][0]
        
        print(f"\n✅ Neptune Network:")
        neptune_sg = neptune_cluster.get('VpcSecurityGroups', [])
        for sg in neptune_sg:
            print(f"      - {sg['VpcSecurityGroupId']}")
        
        # Get OpenSearch VPC info
        opensearch_response = opensearch.describe_domain(
            DomainName=OPENSEARCH_DOMAIN
        )
        opensearch_domain = opensearch_response['DomainStatus']
        
        if 'VPCOptions' in opensearch_domain:
            print(f"\n✅ OpenSearch Network:")
            print(f"   VPC: {opensearch_domain['VPCOptions'].get('VPCId', 'N/A')}")
            for sg_id in opensearch_domain['VPCOptions'].get('SecurityGroupIds', []):
                print(f"      - {sg_id}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking network connectivity: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_application_logs():
    """Check application logs for database initialization"""
    print("\n" + "=" * 80)
    print("📝 Checking Application Logs")
    print("=" * 80)
    
    try:
        # Get the most recent log stream
        streams_response = logs.describe_log_streams(
            logGroupName=LOG_GROUP,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        
        if not streams_response['logStreams']:
            print("⚠️  No log streams found")
            return False
        
        log_stream = streams_response['logStreams'][0]['logStreamName']
        print(f"✅ Log Stream: {log_stream}")
        
        # Get recent log events
        start_time = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
        
        events_response = logs.get_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=log_stream,
            startTime=start_time,
            limit=100
        )
        
        events = events_response['events']
        print(f"   Recent events: {len(events)}")
        
        # Look for database-related messages
        database_messages = []
        error_messages = []
        
        for event in events:
            message = event['message']
            
            if any(keyword in message.lower() for keyword in ['opensearch', 'neptune', 'vector', 'knowledge', 'database']):
                database_messages.append(message)
            
            if any(keyword in message.lower() for keyword in ['error', 'exception', 'failed', 'timeout']):
                if any(keyword in message.lower() for keyword in ['opensearch', 'neptune', 'vector', 'knowledge', 'database']):
                    error_messages.append(message)
        
        if database_messages:
            print(f"\n📊 Database-related log messages ({len(database_messages)}):")
            for msg in database_messages[-10:]:  # Show last 10
                print(f"   {msg[:200]}")
        else:
            print(f"\n⚠️  No database-related log messages found")
        
        if error_messages:
            print(f"\n❌ Database errors found ({len(error_messages)}):")
            for msg in error_messages:
                print(f"   {msg[:200]}")
            return False
        else:
            print(f"\n✅ No database errors found in recent logs")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking logs: {e}")
        return False

def main():
    """Main execution"""
    print("\n" + "=" * 80)
    print("🔍 Database Restoration Verification")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        'task_definition': False,
        'neptune': False,
        'opensearch': False,
        'network': False,
        'logs': False
    }
    
    try:
        # Check task definition
        database_vars, skip_vars = check_task_definition()
        results['task_definition'] = len(skip_vars) == 0 and len(database_vars) > 0
        
        # Check Neptune
        results['neptune'] = check_neptune_status()
        
        # Check OpenSearch
        results['opensearch'] = check_opensearch_status()
        
        # Check network connectivity
        results['network'] = check_network_connectivity()
        
        # Check application logs
        results['logs'] = check_application_logs()
        
        # Summary
        print("\n" + "=" * 80)
        print("📊 Verification Summary")
        print("=" * 80)
        
        for check, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} - {check.replace('_', ' ').title()}")
        
        all_passed = all(results.values())
        
        if all_passed:
            print("\n✅ All checks passed! Databases are properly restored.")
            return 0
        else:
            print("\n⚠️  Some checks failed. Review the details above.")
            return 1
        
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
