#!/usr/bin/env python3
"""
Setup Application Load Balancer with HTTPS for Multimodal Librarian

This script creates:
1. Application Load Balancer (ALB)
2. Target Group for ECS service
3. HTTPS Listener with SSL certificate
4. HTTP to HTTPS redirect
5. Security groups for ALB
6. Updates ECS service to use ALB
"""

import boto3
import json
import time
import sys
from datetime import datetime

# AWS clients
ecs = boto3.client('ecs', region_name='us-east-1')
elbv2 = boto3.client('elbv2', region_name='us-east-1')
ec2 = boto3.client('ec2', region_name='us-east-1')
acm = boto3.client('acm', region_name='us-east-1')

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
ALB_NAME = "multimodal-lib-prod-alb"
TARGET_GROUP_NAME = "multimodal-lib-prod-tg"
CONTAINER_NAME = "multimodal-lib-prod-app"
CONTAINER_PORT = 8000

def log(message):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def get_vpc_and_subnets():
    """Get VPC and public subnets for the ECS service."""
    log("Getting VPC and subnet information...")
    
    # Get VPC from ECS service
    service_response = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    if not service_response['services']:
        raise Exception(f"Service {SERVICE_NAME} not found")
    
    service = service_response['services'][0]
    network_config = service['networkConfiguration']['awsvpcConfiguration']
    
    vpc_id = None
    subnets = network_config['subnets']
    
    # Get VPC ID from subnet
    subnet_response = ec2.describe_subnets(SubnetIds=[subnets[0]])
    vpc_id = subnet_response['Subnets'][0]['VpcId']
    
    log(f"VPC ID: {vpc_id}")
    log(f"Subnets: {subnets}")
    
    # Get all public subnets in the VPC (for ALB)
    all_subnets = ec2.describe_subnets(
        Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]},
            {'Name': 'map-public-ip-on-launch', 'Values': ['true']}
        ]
    )
    
    public_subnet_ids = [subnet['SubnetId'] for subnet in all_subnets['Subnets']]
    
    if len(public_subnet_ids) < 2:
        log("WARNING: Less than 2 public subnets found. ALB requires at least 2 subnets in different AZs.")
        log(f"Found public subnets: {public_subnet_ids}")
        log("Using all available subnets from service...")
        public_subnet_ids = subnets
    
    log(f"Using subnets for ALB: {public_subnet_ids}")
    
    return vpc_id, public_subnet_ids

def create_alb_security_group(vpc_id):
    """Create security group for ALB."""
    log("Creating security group for ALB...")
    
    try:
        # Check if security group already exists
        existing_sgs = ec2.describe_security_groups(
            Filters=[
                {'Name': 'group-name', 'Values': [f'{ALB_NAME}-sg']},
                {'Name': 'vpc-id', 'Values': [vpc_id]}
            ]
        )
        
        if existing_sgs['SecurityGroups']:
            sg_id = existing_sgs['SecurityGroups'][0]['GroupId']
            log(f"Security group already exists: {sg_id}")
            return sg_id
        
        # Create new security group
        response = ec2.create_security_group(
            GroupName=f'{ALB_NAME}-sg',
            Description='Security group for Multimodal Librarian ALB',
            VpcId=vpc_id
        )
        
        sg_id = response['GroupId']
        log(f"Created security group: {sg_id}")
        
        # Add inbound rules for HTTP and HTTPS
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 80,
                    'ToPort': 80,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTP from anywhere'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 443,
                    'ToPort': 443,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS from anywhere'}]
                }
            ]
        )
        
        log("Added inbound rules for HTTP (80) and HTTPS (443)")
        
        # Tag the security group
        ec2.create_tags(
            Resources=[sg_id],
            Tags=[
                {'Key': 'Name', 'Value': f'{ALB_NAME}-sg'},
                {'Key': 'Application', 'Value': 'multimodal-librarian'},
                {'Key': 'Environment', 'Value': 'production'}
            ]
        )
        
        return sg_id
        
    except Exception as e:
        log(f"Error creating security group: {e}")
        raise

def update_ecs_security_group(vpc_id, alb_sg_id):
    """Update ECS service security group to allow traffic from ALB."""
    log("Updating ECS service security group...")
    
    try:
        # Get ECS service security group
        service_response = ecs.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        service = service_response['services'][0]
        ecs_sg_ids = service['networkConfiguration']['awsvpcConfiguration']['securityGroups']
        
        if not ecs_sg_ids:
            log("WARNING: No security groups found on ECS service")
            return
        
        ecs_sg_id = ecs_sg_ids[0]
        log(f"ECS security group: {ecs_sg_id}")
        
        # Add inbound rule from ALB security group
        try:
            ec2.authorize_security_group_ingress(
                GroupId=ecs_sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': CONTAINER_PORT,
                        'ToPort': CONTAINER_PORT,
                        'UserIdGroupPairs': [
                            {
                                'GroupId': alb_sg_id,
                                'Description': 'Allow traffic from ALB'
                            }
                        ]
                    }
                ]
            )
            log(f"Added inbound rule to allow traffic from ALB on port {CONTAINER_PORT}")
        except ec2.exceptions.ClientError as e:
            if 'InvalidPermission.Duplicate' in str(e):
                log("Inbound rule already exists")
            else:
                raise
        
    except Exception as e:
        log(f"Error updating ECS security group: {e}")
        raise

def request_certificate():
    """Request or find existing ACM certificate."""
    log("Checking for existing SSL certificate...")
    
    try:
        # List existing certificates
        response = acm.list_certificates(
            CertificateStatuses=['ISSUED', 'PENDING_VALIDATION']
        )
        
        if response['CertificateSummaryList']:
            cert_arn = response['CertificateSummaryList'][0]['CertificateArn']
            log(f"Found existing certificate: {cert_arn}")
            return cert_arn
        
        log("No existing certificate found.")
        log("You need to request a certificate in AWS Certificate Manager (ACM):")
        log("1. Go to AWS Certificate Manager in us-east-1")
        log("2. Request a public certificate")
        log("3. Enter your domain name (e.g., multimodal-librarian.example.com)")
        log("4. Validate the certificate via DNS or email")
        log("5. Once issued, run this script again")
        
        return None
        
    except Exception as e:
        log(f"Error checking certificates: {e}")
        return None

def create_target_group(vpc_id):
    """Create target group for ECS service."""
    log("Creating target group...")
    
    try:
        # Check if target group already exists
        try:
            existing_tgs = elbv2.describe_target_groups(
                Names=[TARGET_GROUP_NAME]
            )
            if existing_tgs['TargetGroups']:
                tg_arn = existing_tgs['TargetGroups'][0]['TargetGroupArn']
                log(f"Target group already exists: {tg_arn}")
                return tg_arn
        except elbv2.exceptions.TargetGroupNotFoundException:
            pass
        
        # Create new target group
        response = elbv2.create_target_group(
            Name=TARGET_GROUP_NAME,
            Protocol='HTTP',
            Port=CONTAINER_PORT,
            VpcId=vpc_id,
            TargetType='ip',  # For Fargate
            HealthCheckEnabled=True,
            HealthCheckProtocol='HTTP',
            HealthCheckPath='/health/minimal',
            HealthCheckIntervalSeconds=30,
            HealthCheckTimeoutSeconds=10,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=3,
            Matcher={'HttpCode': '200,201'},
            Tags=[
                {'Key': 'Name', 'Value': TARGET_GROUP_NAME},
                {'Key': 'Application', 'Value': 'multimodal-librarian'},
                {'Key': 'Environment', 'Value': 'production'}
            ]
        )
        
        tg_arn = response['TargetGroups'][0]['TargetGroupArn']
        log(f"Created target group: {tg_arn}")
        
        return tg_arn
        
    except Exception as e:
        log(f"Error creating target group: {e}")
        raise

def create_load_balancer(subnet_ids, sg_id):
    """Create Application Load Balancer."""
    log("Creating Application Load Balancer...")
    
    try:
        # Check if ALB already exists
        try:
            existing_lbs = elbv2.describe_load_balancers(
                Names=[ALB_NAME]
            )
            if existing_lbs['LoadBalancers']:
                lb_arn = existing_lbs['LoadBalancers'][0]['LoadBalancerArn']
                lb_dns = existing_lbs['LoadBalancers'][0]['DNSName']
                log(f"Load balancer already exists: {lb_arn}")
                log(f"DNS Name: {lb_dns}")
                return lb_arn, lb_dns
        except elbv2.exceptions.LoadBalancerNotFoundException:
            pass
        
        # Create new ALB
        response = elbv2.create_load_balancer(
            Name=ALB_NAME,
            Subnets=subnet_ids,
            SecurityGroups=[sg_id],
            Scheme='internet-facing',
            Type='application',
            IpAddressType='ipv4',
            Tags=[
                {'Key': 'Name', 'Value': ALB_NAME},
                {'Key': 'Application', 'Value': 'multimodal-librarian'},
                {'Key': 'Environment', 'Value': 'production'}
            ]
        )
        
        lb_arn = response['LoadBalancers'][0]['LoadBalancerArn']
        lb_dns = response['LoadBalancers'][0]['DNSName']
        
        log(f"Created load balancer: {lb_arn}")
        log(f"DNS Name: {lb_dns}")
        
        # Wait for ALB to be active
        log("Waiting for load balancer to become active...")
        waiter = elbv2.get_waiter('load_balancer_available')
        waiter.wait(LoadBalancerArns=[lb_arn])
        log("Load balancer is now active")
        
        return lb_arn, lb_dns
        
    except Exception as e:
        log(f"Error creating load balancer: {e}")
        raise

def create_listeners(lb_arn, tg_arn, cert_arn=None):
    """Create HTTP and HTTPS listeners."""
    log("Creating listeners...")
    
    try:
        # Create HTTP listener (redirect to HTTPS if cert available, otherwise forward)
        if cert_arn:
            log("Creating HTTP listener with redirect to HTTPS...")
            elbv2.create_listener(
                LoadBalancerArn=lb_arn,
                Protocol='HTTP',
                Port=80,
                DefaultActions=[
                    {
                        'Type': 'redirect',
                        'RedirectConfig': {
                            'Protocol': 'HTTPS',
                            'Port': '443',
                            'StatusCode': 'HTTP_301'
                        }
                    }
                ]
            )
            log("Created HTTP listener with redirect to HTTPS")
            
            # Create HTTPS listener
            log("Creating HTTPS listener...")
            elbv2.create_listener(
                LoadBalancerArn=lb_arn,
                Protocol='HTTPS',
                Port=443,
                Certificates=[{'CertificateArn': cert_arn}],
                DefaultActions=[
                    {
                        'Type': 'forward',
                        'TargetGroupArn': tg_arn
                    }
                ]
            )
            log("Created HTTPS listener")
        else:
            log("Creating HTTP listener (no certificate available)...")
            elbv2.create_listener(
                LoadBalancerArn=lb_arn,
                Protocol='HTTP',
                Port=80,
                DefaultActions=[
                    {
                        'Type': 'forward',
                        'TargetGroupArn': tg_arn
                    }
                ]
            )
            log("Created HTTP listener")
            log("NOTE: HTTPS not configured. Request a certificate in ACM and run this script again.")
        
    except Exception as e:
        if 'DuplicateListener' in str(e):
            log("Listeners already exist")
        else:
            log(f"Error creating listeners: {e}")
            raise

def update_ecs_service(tg_arn):
    """Update ECS service to use the load balancer."""
    log("Updating ECS service to use load balancer...")
    
    try:
        # Get current service configuration
        service_response = ecs.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        service = service_response['services'][0]
        
        # Check if already configured
        if service.get('loadBalancers'):
            log("Service already configured with load balancer")
            return
        
        # Update service with load balancer configuration
        ecs.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            loadBalancers=[
                {
                    'targetGroupArn': tg_arn,
                    'containerName': CONTAINER_NAME,
                    'containerPort': CONTAINER_PORT
                }
            ],
            healthCheckGracePeriodSeconds=120
        )
        
        log("Updated ECS service with load balancer configuration")
        log("Waiting for service to stabilize...")
        
        # Wait for service to stabilize
        waiter = ecs.get_waiter('services_stable')
        waiter.wait(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        log("Service is now stable")
        
    except Exception as e:
        log(f"Error updating ECS service: {e}")
        log("NOTE: You may need to recreate the service to attach the load balancer")
        log("This is a known limitation when adding a load balancer to an existing service")
        raise

def main():
    """Main execution function."""
    log("=" * 80)
    log("Setting up Application Load Balancer with HTTPS")
    log("=" * 80)
    
    try:
        # Step 1: Get VPC and subnets
        vpc_id, subnet_ids = get_vpc_and_subnets()
        
        # Step 2: Create ALB security group
        alb_sg_id = create_alb_security_group(vpc_id)
        
        # Step 3: Update ECS security group
        update_ecs_security_group(vpc_id, alb_sg_id)
        
        # Step 4: Check for SSL certificate
        cert_arn = request_certificate()
        
        # Step 5: Create target group
        tg_arn = create_target_group(vpc_id)
        
        # Step 6: Create load balancer
        lb_arn, lb_dns = create_load_balancer(subnet_ids, alb_sg_id)
        
        # Step 7: Create listeners
        create_listeners(lb_arn, tg_arn, cert_arn)
        
        # Step 8: Update ECS service
        try:
            update_ecs_service(tg_arn)
        except Exception as e:
            log("=" * 80)
            log("IMPORTANT: Service update failed")
            log("=" * 80)
            log("To attach the load balancer, you need to recreate the service:")
            log("")
            log("1. Note the current task definition revision")
            log("2. Update the service desired count to 0")
            log("3. Delete the service")
            log("4. Recreate the service with the load balancer configuration")
            log("")
            log("Or use the provided script: scripts/attach-alb-to-service.py")
            log("=" * 80)
        
        # Summary
        log("=" * 80)
        log("ALB Setup Complete!")
        log("=" * 80)
        log(f"Load Balancer DNS: {lb_dns}")
        log(f"HTTP URL: http://{lb_dns}")
        if cert_arn:
            log(f"HTTPS URL: https://{lb_dns}")
            log("HTTP requests will automatically redirect to HTTPS")
        else:
            log("HTTPS: Not configured (no certificate)")
            log("To enable HTTPS:")
            log("1. Request a certificate in AWS Certificate Manager")
            log("2. Run this script again")
        log("=" * 80)
        
        # Save configuration
        config = {
            'timestamp': datetime.now().isoformat(),
            'vpc_id': vpc_id,
            'subnet_ids': subnet_ids,
            'alb_security_group_id': alb_sg_id,
            'load_balancer_arn': lb_arn,
            'load_balancer_dns': lb_dns,
            'target_group_arn': tg_arn,
            'certificate_arn': cert_arn,
            'http_url': f'http://{lb_dns}',
            'https_url': f'https://{lb_dns}' if cert_arn else None
        }
        
        with open(f'alb-setup-{int(time.time())}.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        log(f"Configuration saved to alb-setup-{int(time.time())}.json")
        
        return 0
        
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
