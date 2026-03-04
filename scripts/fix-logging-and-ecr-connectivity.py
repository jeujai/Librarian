#!/usr/bin/env python3
"""
Fix logging and ECR connectivity issues.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def fix_logging_and_ecr_connectivity():
    """Fix logging and ECR connectivity issues."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        logs_client = boto3.client('logs', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 Fixing Logging and ECR Connectivity Issues")
        print("=" * 50)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Create missing log group
        print("\n1. Creating CloudWatch Log Group:")
        print("-" * 34)
        
        log_group_name = "/ecs/multimodal-lib-prod-app"
        
        try:
            logs_client.create_log_group(
                logGroupName=log_group_name
            )
            print(f"✅ Created log group: {log_group_name}")
            result['fix_actions'].append(f"Created log group {log_group_name}")
        except logs_client.exceptions.ResourceAlreadyExistsException:
            print(f"✅ Log group already exists: {log_group_name}")
        except Exception as e:
            print(f"❌ Error creating log group: {e}")
            result['fix_actions'].append(f"Error creating log group: {e}")
        
        # 2. Check and fix VPC endpoint for S3 (needed for ECR layer downloads)
        print("\n2. Checking S3 VPC Endpoint:")
        print("-" * 27)
        
        # Get target VPC ID
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        lb_response = elb_client.describe_load_balancers()
        
        target_vpc_id = None
        for lb in lb_response['LoadBalancers']:
            if 'multimodal' in lb['LoadBalancerName'].lower():
                target_vpc_id = lb['VpcId']
                break
        
        if not target_vpc_id:
            print("❌ Could not find target VPC")
            return result
        
        print(f"🌐 Target VPC: {target_vpc_id}")
        
        # Check for S3 VPC endpoint (needed for ECR layer downloads)
        endpoints_response = ec2_client.describe_vpc_endpoints(
            Filters=[
                {'Name': 'vpc-id', 'Values': [target_vpc_id]},
                {'Name': 'service-name', 'Values': ['com.amazonaws.us-east-1.s3']}
            ]
        )
        
        s3_endpoint_exists = len(endpoints_response['VpcEndpoints']) > 0
        
        if not s3_endpoint_exists:
            print("⚠️  S3 VPC endpoint missing - creating gateway endpoint")
            
            # Get route tables for private subnets
            route_tables_response = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [target_vpc_id]}
                ]
            )
            
            private_route_tables = []
            for rt in route_tables_response['RouteTables']:
                # Check if route table has no internet gateway route (private)
                has_igw = False
                for route in rt['Routes']:
                    if route.get('GatewayId', '').startswith('igw-'):
                        has_igw = True
                        break
                
                if not has_igw:
                    private_route_tables.append(rt['RouteTableId'])
            
            if private_route_tables:
                try:
                    s3_endpoint_response = ec2_client.create_vpc_endpoint(
                        VpcId=target_vpc_id,
                        ServiceName='com.amazonaws.us-east-1.s3',
                        VpcEndpointType='Gateway',
                        RouteTableIds=private_route_tables[:2]  # Use first 2 route tables
                    )
                    
                    s3_endpoint_id = s3_endpoint_response['VpcEndpoint']['VpcEndpointId']
                    print(f"✅ Created S3 gateway endpoint: {s3_endpoint_id}")
                    result['fix_actions'].append(f"Created S3 gateway endpoint {s3_endpoint_id}")
                    
                except Exception as e:
                    print(f"❌ Error creating S3 endpoint: {e}")
                    result['fix_actions'].append(f"Error creating S3 endpoint: {e}")
            else:
                print("❌ No private route tables found")
        else:
            print("✅ S3 VPC endpoint already exists")
        
        # 3. Update task definition to remove logging temporarily (for testing)
        print("\n3. Creating Simplified Task Definition:")
        print("-" * 38)
        
        # Get current task definition
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_details['services'][0]
        current_task_def_arn = service['taskDefinition']
        
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=current_task_def_arn
        )
        
        current_task_def = task_def_response['taskDefinition']
        
        # Create simplified task definition for testing
        new_task_def = {
            'family': current_task_def['family'],
            'networkMode': current_task_def.get('networkMode', 'awsvpc'),
            'requiresCompatibilities': current_task_def.get('requiresCompatibilities', ['FARGATE']),
            'cpu': current_task_def.get('cpu', '2048'),
            'memory': current_task_def.get('memory', '4096'),
            'executionRoleArn': current_task_def.get('executionRoleArn'),
            'taskRoleArn': current_task_def.get('taskRoleArn'),
            'containerDefinitions': []
        }
        
        # Simplify container definition
        for container_def in current_task_def['containerDefinitions']:
            simplified_container = {
                'name': container_def['name'],
                'image': container_def['image'],
                'essential': container_def.get('essential', True),
                'portMappings': container_def.get('portMappings', []),
                'environment': container_def.get('environment', []),
                'secrets': container_def.get('secrets', []),
                'logConfiguration': {
                    'logDriver': 'awslogs',
                    'options': {
                        'awslogs-group': log_group_name,
                        'awslogs-region': 'us-east-1',
                        'awslogs-stream-prefix': 'ecs'
                    }
                }
            }
            
            new_task_def['containerDefinitions'].append(simplified_container)
        
        # Register new task definition
        try:
            register_response = ecs_client.register_task_definition(**new_task_def)
            
            new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
            new_revision = register_response['taskDefinition']['revision']
            
            print(f"✅ Registered simplified task definition: {current_task_def['family']}:{new_revision}")
            result['fix_actions'].append(f"Registered simplified task definition revision {new_revision}")
            
        except Exception as e:
            print(f"❌ Error registering task definition: {e}")
            result['fix_actions'].append(f"Error registering task definition: {e}")
            return result
        
        # 4. Update service with new task definition
        print("\n4. Updating Service:")
        print("-" * 18)
        
        try:
            update_response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=new_task_def_arn,
                forceNewDeployment=True
            )
            
            print("✅ Service updated with simplified task definition")
            result['fix_actions'].append("Updated service with simplified task definition")
            
            # 5. Monitor deployment
            print("\n5. Monitoring Deployment:")
            print("-" * 25)
            
            print("⏳ Waiting for deployment to start...")
            time.sleep(60)
            
            # Check service status
            max_attempts = 10
            attempt = 0
            
            while attempt < max_attempts:
                attempt += 1
                
                service_details = ecs_client.describe_services(
                    cluster=cluster_name,
                    services=[service_name]
                )
                
                service = service_details['services'][0]
                running_count = service['runningCount']
                desired_count = service['desiredCount']
                
                print(f"   Attempt {attempt}: Running {running_count}/{desired_count} tasks")
                
                if running_count == desired_count and running_count > 0:
                    print("✅ Service deployment successful")
                    result['success'] = True
                    result['fix_actions'].append("Service deployment successful")
                    break
                
                # Check recent events for errors
                recent_events = service.get('events', [])[:2]
                for event in recent_events:
                    message = event['message']
                    if 'unable to place' in message.lower() or 'error' in message.lower():
                        print(f"   ⚠️  Recent issue: {message[:80]}...")
                
                time.sleep(30)
            
            if attempt >= max_attempts:
                print("⚠️  Deployment taking longer than expected")
                result['fix_actions'].append("Deployment in progress but not yet complete")
            
        except Exception as e:
            print(f"❌ Error updating service: {e}")
            result['fix_actions'].append(f"Error updating service: {e}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = fix_logging_and_ecr_connectivity()
    
    # Save result to file
    result_file = f"logging-ecr-connectivity-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Logging and ECR connectivity issues fixed!")
        print("🚀 Production environment should now be ready")
        sys.exit(0)
    else:
        print("\n⚠️  Logging and ECR connectivity fix needs attention")
        sys.exit(1)