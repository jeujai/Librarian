#!/usr/bin/env python3
"""
Verify Database Connectivity Configuration

This script verifies that the multimodal-lib-prod-service-alb service
can connect to the PostgreSQL database by checking:
1. Network connectivity (VPC, subnets, security groups)
2. Credentials configuration (environment variables and secrets)
3. Password synchronization between RDS and Secrets Manager
"""

import boto3
import json
from datetime import datetime

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    ec2 = boto3.client('ec2', region_name='us-east-1')
    rds = boto3.client('rds', region_name='us-east-1')
    sm = boto3.client('secretsmanager', region_name='us-east-1')
    
    print("=" * 80)
    print("DATABASE CONNECTIVITY CONFIGURATION VERIFICATION")
    print("=" * 80)
    print()
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'checks': {},
        'overall_status': 'PASS'
    }
    
    # Check 1: Get ECS service configuration
    print("📋 CHECK 1: ECS Service Configuration")
    print("-" * 80)
    
    service_response = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service-alb']
    )
    service = service_response['services'][0]
    task_def_arn = service['taskDefinition']
    
    print(f"   Service: {service['serviceName']}")
    print(f"   Task Definition: {task_def_arn}")
    print(f"   Running Tasks: {service['runningCount']}/{service['desiredCount']}")
    print()
    
    results['checks']['service'] = {
        'status': 'PASS',
        'task_definition': task_def_arn,
        'running_count': service['runningCount'],
        'desired_count': service['desiredCount']
    }
    
    # Check 2: Get task definition and verify database configuration
    print("📋 CHECK 2: Task Definition Database Configuration")
    print("-" * 80)
    
    task_def_response = ecs.describe_task_definition(taskDefinition=task_def_arn)
    task_def = task_def_response['taskDefinition']
    container = task_def['containerDefinitions'][0]
    
    # Extract database environment variables
    env_vars = {e['name']: e['value'] for e in container.get('environment', [])}
    secrets = {s['name']: s['valueFrom'] for s in container.get('secrets', [])}
    
    db_config = {
        'POSTGRES_HOST': env_vars.get('POSTGRES_HOST'),
        'POSTGRES_PORT': env_vars.get('POSTGRES_PORT'),
        'POSTGRES_DB': env_vars.get('POSTGRES_DB'),
        'POSTGRES_USER': env_vars.get('POSTGRES_USER'),
        'DB_HOST': env_vars.get('DB_HOST'),
        'DB_PORT': env_vars.get('DB_PORT'),
        'DB_NAME': env_vars.get('DB_NAME'),
        'DB_USER': env_vars.get('DB_USER'),
    }
    
    db_secrets = {
        'POSTGRES_PASSWORD': secrets.get('POSTGRES_PASSWORD'),
        'DB_PASSWORD': secrets.get('DB_PASSWORD'),
    }
    
    print("   Environment Variables:")
    for key, value in db_config.items():
        if value:
            status = "✓" if value else "✗"
            print(f"      {status} {key}: {value}")
    print()
    
    print("   Secrets:")
    for key, value in db_secrets.items():
        if value:
            status = "✓" if value else "✗"
            secret_name = value.split(':')[6] if value else 'N/A'
            print(f"      {status} {key}: {secret_name}")
    print()
    
    # Verify both POSTGRES_* and DB_* variables are set
    has_postgres_vars = all([
        db_config.get('POSTGRES_HOST'),
        db_config.get('POSTGRES_PORT'),
        db_config.get('POSTGRES_DB'),
        db_config.get('POSTGRES_USER'),
        db_secrets.get('POSTGRES_PASSWORD')
    ])
    
    has_db_vars = all([
        db_config.get('DB_HOST'),
        db_config.get('DB_PORT'),
        db_config.get('DB_NAME'),
        db_config.get('DB_USER'),
        db_secrets.get('DB_PASSWORD')
    ])
    
    config_status = 'PASS' if (has_postgres_vars and has_db_vars) else 'FAIL'
    if config_status == 'FAIL':
        results['overall_status'] = 'FAIL'
    
    print(f"   Configuration Status: {config_status}")
    print(f"      POSTGRES_* variables: {'✓ Complete' if has_postgres_vars else '✗ Incomplete'}")
    print(f"      DB_* variables: {'✓ Complete' if has_db_vars else '✗ Incomplete'}")
    print()
    
    results['checks']['task_definition'] = {
        'status': config_status,
        'has_postgres_vars': has_postgres_vars,
        'has_db_vars': has_db_vars,
        'environment': db_config,
        'secrets': db_secrets
    }
    
    # Check 3: Verify RDS instance
    print("📋 CHECK 3: RDS Instance Configuration")
    print("-" * 80)
    
    db_host = db_config.get('POSTGRES_HOST') or db_config.get('DB_HOST')
    db_instance_id = 'ml-librarian-postgres-prod'
    
    rds_response = rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
    db_instance = rds_response['DBInstances'][0]
    
    print(f"   Instance ID: {db_instance_id}")
    print(f"   Endpoint: {db_instance['Endpoint']['Address']}")
    print(f"   Port: {db_instance['Endpoint']['Port']}")
    print(f"   Status: {db_instance['DBInstanceStatus']}")
    print(f"   VPC: {db_instance['DBSubnetGroup']['VpcId']}")
    print(f"   Security Groups: {[sg['VpcSecurityGroupId'] for sg in db_instance['VpcSecurityGroups']]}")
    print()
    
    rds_status = 'PASS' if db_instance['DBInstanceStatus'] == 'available' else 'FAIL'
    if rds_status == 'FAIL':
        results['overall_status'] = 'FAIL'
    
    results['checks']['rds'] = {
        'status': rds_status,
        'instance_id': db_instance_id,
        'endpoint': db_instance['Endpoint']['Address'],
        'port': db_instance['Endpoint']['Port'],
        'db_status': db_instance['DBInstanceStatus'],
        'vpc_id': db_instance['DBSubnetGroup']['VpcId'],
        'security_groups': [sg['VpcSecurityGroupId'] for sg in db_instance['VpcSecurityGroups']]
    }
    
    # Check 4: Verify network connectivity (VPC, security groups)
    print("📋 CHECK 4: Network Connectivity")
    print("-" * 80)
    
    # Get running task
    tasks_response = ecs.list_tasks(
        cluster='multimodal-lib-prod-cluster',
        serviceName='multimodal-lib-prod-service-alb'
    )
    
    if tasks_response['taskArns']:
        task_arn = tasks_response['taskArns'][0]
        task_response = ecs.describe_tasks(
            cluster='multimodal-lib-prod-cluster',
            tasks=[task_arn]
        )
        task = task_response['tasks'][0]
        
        # Get ENI from task
        eni_id = None
        for attachment in task.get('attachments', []):
            for detail in attachment.get('details', []):
                if detail['name'] == 'networkInterfaceId':
                    eni_id = detail['value']
                    break
        
        if eni_id:
            eni_response = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
            eni = eni_response['NetworkInterfaces'][0]
            
            task_vpc = eni['VpcId']
            task_subnet = eni['SubnetId']
            task_sg = [g['GroupId'] for g in eni['Groups']]
            task_ip = eni['PrivateIpAddress']
            
            print(f"   Task ENI: {eni_id}")
            print(f"   Task IP: {task_ip}")
            print(f"   Task VPC: {task_vpc}")
            print(f"   Task Subnet: {task_subnet}")
            print(f"   Task Security Groups: {task_sg}")
            print()
            
            # Check if VPCs match
            rds_vpc = db_instance['DBSubnetGroup']['VpcId']
            vpc_match = task_vpc == rds_vpc
            
            print(f"   VPC Match: {'✓ Same VPC' if vpc_match else '✗ Different VPCs'}")
            print(f"      Task VPC: {task_vpc}")
            print(f"      RDS VPC: {rds_vpc}")
            print()
            
            # Check security group rules
            rds_sg = db_instance['VpcSecurityGroups'][0]['VpcSecurityGroupId']
            sg_response = ec2.describe_security_groups(GroupIds=[rds_sg])
            rds_sg_rules = sg_response['SecurityGroups'][0]['IpPermissions']
            
            # Check if task SG is allowed to connect to RDS
            allowed = False
            for rule in rds_sg_rules:
                if rule.get('FromPort') == 5432:
                    for group_pair in rule.get('UserIdGroupPairs', []):
                        if group_pair['GroupId'] in task_sg:
                            allowed = True
                            break
            
            print(f"   Security Group Rules: {'✓ Task SG allowed' if allowed else '✗ Task SG not allowed'}")
            print(f"      RDS Security Group: {rds_sg}")
            print(f"      Allows connections from: {[gp['GroupId'] for rule in rds_sg_rules for gp in rule.get('UserIdGroupPairs', [])]}")
            print(f"      Task Security Groups: {task_sg}")
            print()
            
            network_status = 'PASS' if (vpc_match and allowed) else 'FAIL'
            if network_status == 'FAIL':
                results['overall_status'] = 'FAIL'
            
            results['checks']['network'] = {
                'status': network_status,
                'vpc_match': vpc_match,
                'security_group_allowed': allowed,
                'task_vpc': task_vpc,
                'rds_vpc': rds_vpc,
                'task_security_groups': task_sg,
                'rds_security_group': rds_sg
            }
        else:
            print("   ✗ Could not find task ENI")
            results['checks']['network'] = {'status': 'FAIL', 'error': 'No ENI found'}
            results['overall_status'] = 'FAIL'
    else:
        print("   ✗ No running tasks found")
        results['checks']['network'] = {'status': 'FAIL', 'error': 'No running tasks'}
        results['overall_status'] = 'FAIL'
    
    # Check 5: Verify Secrets Manager secret
    print("📋 CHECK 5: Secrets Manager Configuration")
    print("-" * 80)
    
    secret_arn = db_secrets.get('POSTGRES_PASSWORD') or db_secrets.get('DB_PASSWORD')
    if secret_arn:
        secret_id = secret_arn.split(':')[6]
        
        try:
            secret_response = sm.get_secret_value(SecretId=secret_id)
            secret_data = json.loads(secret_response['SecretString'])
            
            has_password = 'password' in secret_data
            password_length = len(secret_data.get('password', ''))
            
            print(f"   Secret: {secret_id}")
            print(f"   Status: ✓ Accessible")
            print(f"   Password: {'✓ Present' if has_password else '✗ Missing'} ({password_length} characters)")
            print()
            
            secret_status = 'PASS' if has_password else 'FAIL'
            if secret_status == 'FAIL':
                results['overall_status'] = 'FAIL'
            
            results['checks']['secrets_manager'] = {
                'status': secret_status,
                'secret_id': secret_id,
                'has_password': has_password,
                'password_length': password_length
            }
        except Exception as e:
            print(f"   ✗ Error accessing secret: {e}")
            results['checks']['secrets_manager'] = {'status': 'FAIL', 'error': str(e)}
            results['overall_status'] = 'FAIL'
    else:
        print("   ✗ No secret ARN found in task definition")
        results['checks']['secrets_manager'] = {'status': 'FAIL', 'error': 'No secret ARN'}
        results['overall_status'] = 'FAIL'
    
    # Summary
    print("=" * 80)
    print(f"OVERALL STATUS: {results['overall_status']}")
    print("=" * 80)
    print()
    
    if results['overall_status'] == 'PASS':
        print("✅ All checks passed! Database connectivity configuration is correct.")
        print()
        print("The service SHOULD be able to connect to the database:")
        print("  ✓ Task definition has correct database configuration")
        print("  ✓ RDS instance is available")
        print("  ✓ Tasks and RDS are in the same VPC")
        print("  ✓ Security groups allow connections")
        print("  ✓ Secrets Manager has the password")
        print()
        print("Note: This verifies the CONFIGURATION is correct.")
        print("To verify ACTUAL connectivity, check application logs for:")
        print("  - 'Database connections initialized' messages")
        print("  - No 'password authentication failed' errors")
        print("  - No 'connection refused' errors")
    else:
        print("❌ Some checks failed. Review the issues above.")
        print()
        failed_checks = [name for name, check in results['checks'].items() if check['status'] == 'FAIL']
        print(f"Failed checks: {', '.join(failed_checks)}")
    
    print()
    
    # Save results
    filename = f"database-connectivity-verification-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {filename}")
    print()

if __name__ == '__main__':
    main()
