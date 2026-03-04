#!/usr/bin/env python3
"""
Network Configuration Validator

Validates VPC, subnet, and load balancer configuration compatibility
discovered during deployment debugging.

This validator addresses the specific network configuration issues encountered:
- VPC mismatches between load balancer and ECS service
- Target group mapping issues with load balancer listeners
- Subnet incompatibility problems
- Security group rule validation for required ports
"""

import boto3
import logging
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from .base_validator import BaseValidator, ValidationError
from .models import ValidationResult, ValidationStatus, NetworkConfiguration

logger = logging.getLogger(__name__)


@dataclass
class SubnetInfo:
    """Information about a subnet"""
    subnet_id: str
    vpc_id: str
    availability_zone: str
    cidr_block: str
    is_public: bool


@dataclass
class LoadBalancerInfo:
    """Information about a load balancer"""
    arn: str
    vpc_id: str
    subnets: List[str]
    availability_zones: List[str]
    security_groups: List[str]
    listeners: List[Dict]


@dataclass
class TargetGroupInfo:
    """Information about a target group"""
    arn: str
    vpc_id: str
    port: int
    protocol: str
    health_check_path: str


class NetworkConfigValidator(BaseValidator):
    """Validates network configuration for deployment compatibility"""
    
    def __init__(self, region: str = "us-east-1"):
        super().__init__()
        self.region = region
        self.ec2_client = boto3.client('ec2', region_name=region)
        self.elbv2_client = boto3.client('elbv2', region_name=region)
        self.ecs_client = boto3.client('ecs', region_name=region)
    
    def validate_vpc_compatibility(self, lb_arn: str, service_config: dict) -> ValidationResult:
        """
        Validate VPC compatibility between load balancer and ECS service
        
        This addresses the VPC mismatch issues discovered during debugging
        where load balancer and ECS service were in different VPCs.
        """
        try:
            logger.info(f"Validating VPC compatibility for load balancer: {lb_arn}")
            
            # Get load balancer VPC
            lb_info = self._get_load_balancer_info(lb_arn)
            if not lb_info:
                return ValidationResult(
                    check_name="VPC Compatibility",
                    status=ValidationStatus.FAILED,
                    message=f"Load balancer not found: {lb_arn}",
                    remediation_steps=[
                        "Verify load balancer ARN is correct",
                        "Check if load balancer exists in the specified region"
                    ]
                )
            
            # Get service VPC from subnets
            service_subnets = service_config.get('subnets', [])
            if not service_subnets:
                return ValidationResult(
                    check_name="VPC Compatibility",
                    status=ValidationStatus.FAILED,
                    message="No subnets specified for ECS service",
                    remediation_steps=[
                        "Add subnet configuration to service definition",
                        "Ensure subnets are in the same VPC as load balancer"
                    ]
                )
            
            service_vpc_ids = set()
            for subnet_id in service_subnets:
                subnet_info = self._get_subnet_info(subnet_id)
                if subnet_info:
                    service_vpc_ids.add(subnet_info.vpc_id)
            
            if len(service_vpc_ids) > 1:
                return ValidationResult(
                    check_name="VPC Compatibility",
                    status=ValidationStatus.FAILED,
                    message=f"Service subnets span multiple VPCs: {service_vpc_ids}",
                    remediation_steps=[
                        "Ensure all service subnets are in the same VPC",
                        f"Use subnets from VPC: {lb_info.vpc_id}"
                    ]
                )
            
            service_vpc_id = service_vpc_ids.pop() if service_vpc_ids else None
            
            if service_vpc_id != lb_info.vpc_id:
                return ValidationResult(
                    check_name="VPC Compatibility",
                    status=ValidationStatus.FAILED,
                    message=f"VPC mismatch: Load balancer in {lb_info.vpc_id}, service in {service_vpc_id}",
                    remediation_steps=[
                        f"Move ECS service to VPC: {lb_info.vpc_id}",
                        f"Or move load balancer to VPC: {service_vpc_id}",
                        "Use scripts/fix-vpc-security-group-mismatch.py for automated fix"
                    ],
                    fix_scripts=["scripts/fix-vpc-security-group-mismatch.py"]
                )
            
            logger.info(f"VPC compatibility validated: {lb_info.vpc_id}")
            return ValidationResult(
                check_name="VPC Compatibility",
                status=ValidationStatus.PASSED,
                message=f"VPC compatibility confirmed: {lb_info.vpc_id}"
            )
            
        except Exception as e:
            logger.error(f"Error validating VPC compatibility: {str(e)}")
            return ValidationResult(
                check_name="VPC Compatibility",
                status=ValidationStatus.ERROR,
                message=f"VPC validation failed: {str(e)}",
                remediation_steps=[
                    "Check AWS credentials and permissions",
                    "Verify resource ARNs are correct"
                ]
            )
    
    def validate_target_group_mapping(self, lb_arn: str, service_name: str) -> ValidationResult:
        """
        Validate target group mapping to load balancer listeners
        
        This addresses target group mapping issues discovered during debugging.
        """
        try:
            logger.info(f"Validating target group mapping for service: {service_name}")
            
            lb_info = self._get_load_balancer_info(lb_arn)
            if not lb_info:
                return ValidationResult(
                    check_name="Target Group Mapping",
                    status=ValidationStatus.FAILED,
                    message=f"Load balancer not found: {lb_arn}"
                )
            
            # Check if load balancer has listeners
            if not lb_info.listeners:
                return ValidationResult(
                    check_name="Target Group Mapping",
                    status=ValidationStatus.FAILED,
                    message="Load balancer has no listeners configured",
                    remediation_steps=[
                        "Add HTTP/HTTPS listeners to load balancer",
                        "Configure target group for port 8000",
                        "Use scripts/add-https-ssl-support-fixed.py for SSL setup"
                    ],
                    fix_scripts=["scripts/add-https-ssl-support-fixed.py"]
                )
            
            # Find target groups for this service
            target_groups = self._find_target_groups_for_service(service_name, lb_info.vpc_id)
            
            if not target_groups:
                return ValidationResult(
                    check_name="Target Group Mapping",
                    status=ValidationStatus.FAILED,
                    message=f"No target groups found for service: {service_name}",
                    remediation_steps=[
                        "Create target group for the service",
                        "Configure target group to forward to port 8000",
                        "Associate target group with load balancer listener"
                    ]
                )
            
            # Validate target group is referenced by listeners
            listener_target_groups = set()
            for listener in lb_info.listeners:
                for action in listener.get('DefaultActions', []):
                    if action.get('Type') == 'forward':
                        tg_arn = action.get('TargetGroupArn')
                        if tg_arn:
                            listener_target_groups.add(tg_arn)
            
            service_target_group_arns = {tg.arn for tg in target_groups}
            
            if not service_target_group_arns.intersection(listener_target_groups):
                return ValidationResult(
                    check_name="Target Group Mapping",
                    status=ValidationStatus.FAILED,
                    message="Service target groups not referenced by load balancer listeners",
                    remediation_steps=[
                        "Update load balancer listeners to forward to service target groups",
                        "Use scripts/fix-load-balancer-target-registration.py for automated fix",
                        f"Target groups to associate: {list(service_target_group_arns)}"
                    ],
                    fix_scripts=["scripts/fix-load-balancer-target-registration.py"]
                )
            
            logger.info(f"Target group mapping validated for service: {service_name}")
            return ValidationResult(
                check_name="Target Group Mapping",
                status=ValidationStatus.PASSED,
                message=f"Target group mapping confirmed for service: {service_name}"
            )
            
        except Exception as e:
            logger.error(f"Error validating target group mapping: {str(e)}")
            return ValidationResult(
                check_name="Target Group Mapping",
                status=ValidationStatus.ERROR,
                message=f"Target group validation failed: {str(e)}"
            )
    
    def validate_subnet_configuration(self, lb_arn: str, service_subnets: List[str]) -> ValidationResult:
        """
        Validate subnet configuration and availability zone compatibility
        
        This addresses subnet incompatibility issues discovered during debugging.
        """
        try:
            logger.info(f"Validating subnet configuration for {len(service_subnets)} subnets")
            
            lb_info = self._get_load_balancer_info(lb_arn)
            if not lb_info:
                return ValidationResult(
                    check_name="Subnet Configuration",
                    status=ValidationStatus.FAILED,
                    message=f"Load balancer not found: {lb_arn}"
                )
            
            # Get subnet information
            service_subnet_infos = []
            for subnet_id in service_subnets:
                subnet_info = self._get_subnet_info(subnet_id)
                if subnet_info:
                    service_subnet_infos.append(subnet_info)
                else:
                    return ValidationResult(
                        check_name="Subnet Configuration",
                        status=ValidationStatus.FAILED,
                        message=f"Subnet not found: {subnet_id}",
                        remediation_steps=[
                            "Verify subnet ID is correct",
                            "Check if subnet exists in the specified region"
                        ]
                    )
            
            # Check availability zone compatibility
            service_azs = {subnet.availability_zone for subnet in service_subnet_infos}
            lb_azs = set(lb_info.availability_zones)
            
            if not service_azs.intersection(lb_azs):
                compatible_subnets = self._find_compatible_subnets(lb_info.vpc_id, lb_azs)
                return ValidationResult(
                    check_name="Subnet Configuration",
                    status=ValidationStatus.FAILED,
                    message=f"No overlapping availability zones. LB AZs: {lb_azs}, Service AZs: {service_azs}",
                    remediation_steps=[
                        f"Use subnets in load balancer availability zones: {lb_azs}",
                        "Use scripts/fix-subnet-mismatch.py for automated fix",
                        f"Compatible subnets: {compatible_subnets}"
                    ],
                    fix_scripts=["scripts/fix-subnet-mismatch.py"]
                )
            
            # Check for sufficient availability zone coverage
            if len(service_azs) < 2:
                return ValidationResult(
                    check_name="Subnet Configuration",
                    status=ValidationStatus.FAILED,
                    message=f"Insufficient availability zone coverage: {service_azs}",
                    remediation_steps=[
                        "Use subnets in at least 2 availability zones for high availability",
                        f"Add subnets from these AZs: {lb_azs - service_azs}"
                    ]
                )
            
            logger.info(f"Subnet configuration validated: {service_azs}")
            return ValidationResult(
                check_name="Subnet Configuration",
                status=ValidationStatus.PASSED,
                message=f"Subnet configuration validated across AZs: {service_azs}"
            )
            
        except Exception as e:
            logger.error(f"Error validating subnet configuration: {str(e)}")
            return ValidationResult(
                check_name="Subnet Configuration",
                status=ValidationStatus.ERROR,
                message=f"Subnet validation failed: {str(e)}"
            )
    
    def validate_security_group_rules(self, security_groups: List[str], required_port: int = 8000) -> ValidationResult:
        """
        Validate security group rules allow required port access
        
        This addresses security group configuration issues discovered during debugging.
        """
        try:
            logger.info(f"Validating security group rules for port {required_port}")
            
            for sg_id in security_groups:
                response = self.ec2_client.describe_security_groups(
                    GroupIds=[sg_id]
                )
                
                if not response['SecurityGroups']:
                    return ValidationResult(
                        check_name="Security Group Rules",
                        status=ValidationStatus.FAILED,
                        message=f"Security group not found: {sg_id}"
                    )
                
                sg = response['SecurityGroups'][0]
                
                # Check ingress rules for required port
                port_allowed = False
                for rule in sg['IpPermissions']:
                    from_port = rule.get('FromPort')
                    to_port = rule.get('ToPort')
                    
                    if (from_port is None or from_port <= required_port) and \
                       (to_port is None or to_port >= required_port):
                        port_allowed = True
                        break
                
                if not port_allowed:
                    return ValidationResult(
                        check_name="Security Group Rules",
                        status=ValidationStatus.FAILED,
                        message=f"Security group {sg_id} does not allow access to port {required_port}",
                        remediation_steps=[
                            f"Add ingress rule to allow port {required_port}",
                            "Use scripts/comprehensive-networking-fix.py for automated fix",
                            f"Example: aws ec2 authorize-security-group-ingress --group-id {sg_id} --protocol tcp --port {required_port} --cidr 0.0.0.0/0"
                        ],
                        fix_scripts=["scripts/comprehensive-networking-fix.py"]
                    )
            
            logger.info(f"Security group rules validated for port {required_port}")
            return ValidationResult(
                check_name="Security Group Rules",
                status=ValidationStatus.PASSED,
                message=f"Security group rules allow access to port {required_port}"
            )
            
        except Exception as e:
            logger.error(f"Error validating security group rules: {str(e)}")
            return ValidationResult(
                check_name="Security Group Rules",
                status=ValidationStatus.ERROR,
                message=f"Security group validation failed: {str(e)}"
            )
    
    def validate(self, deployment_config) -> ValidationResult:
        """
        Main validation method that orchestrates all network configuration checks
        """
        logger.info("Starting comprehensive network configuration validation")
        
        # Extract network configuration from deployment config
        if hasattr(deployment_config, 'vpc_id') and deployment_config.vpc_id:
            # Create NetworkConfiguration from DeploymentConfig
            from .models import NetworkConfiguration
            config = NetworkConfiguration(
                vpc_id=deployment_config.vpc_id,
                load_balancer_subnets=[],  # Will be populated by validator
                service_subnets=deployment_config.service_subnets or [],
                security_groups=deployment_config.security_groups or [],
                availability_zones=[],  # Will be populated by validator
                load_balancer_arn=deployment_config.load_balancer_arn,
                service_name=deployment_config.service_name
            )
        else:
            # Skip network validation if network details not provided
            logger.info("Network configuration not provided, skipping network validation")
            return ValidationResult(
                check_name="Network Configuration",
                status=ValidationStatus.PASSED,
                message="Network configuration validation skipped (no network details provided)"
            )
        
        results = []
        
        # Validate VPC compatibility
        if config.load_balancer_arn and config.service_subnets:
            service_config = {'subnets': config.service_subnets}
            vpc_result = self.validate_vpc_compatibility(config.load_balancer_arn, service_config)
            results.append(vpc_result)
        
        # Validate target group mapping
        if config.load_balancer_arn and config.service_name:
            tg_result = self.validate_target_group_mapping(config.load_balancer_arn, config.service_name)
            results.append(tg_result)
        
        # Validate subnet configuration
        if config.load_balancer_arn and config.service_subnets:
            subnet_result = self.validate_subnet_configuration(config.load_balancer_arn, config.service_subnets)
            results.append(subnet_result)
        
        # Validate security group rules
        if config.security_groups:
            sg_result = self.validate_security_group_rules(config.security_groups, 8000)
            results.append(sg_result)
        
        # Aggregate results
        failed_results = [r for r in results if not r.passed]
        
        if failed_results:
            all_errors = []
            all_remediation_steps = []
            all_fix_scripts = []
            
            for result in failed_results:
                all_errors.append(result.message)
                all_remediation_steps.extend(result.remediation_steps or [])
                all_fix_scripts.extend(result.fix_scripts or [])
            
            return ValidationResult(
                check_name="Network Configuration",
                status=ValidationStatus.FAILED,
                message="Network configuration validation failed: " + "; ".join(all_errors),
                remediation_steps=all_remediation_steps,
                fix_scripts=list(set(all_fix_scripts))  # Remove duplicates
            )
        
        logger.info("Network configuration validation completed successfully")
        return ValidationResult(
            check_name="Network Configuration",
            status=ValidationStatus.PASSED,
            message="All network configuration validations passed"
        )
    
    def _get_load_balancer_info(self, lb_arn: str) -> Optional[LoadBalancerInfo]:
        """Get load balancer information"""
        try:
            response = self.elbv2_client.describe_load_balancers(
                LoadBalancerArns=[lb_arn]
            )
            
            if not response['LoadBalancers']:
                return None
            
            lb = response['LoadBalancers'][0]
            
            # Get listeners
            listeners_response = self.elbv2_client.describe_listeners(
                LoadBalancerArn=lb_arn
            )
            
            return LoadBalancerInfo(
                arn=lb['LoadBalancerArn'],
                vpc_id=lb['VpcId'],
                subnets=lb['Subnets'],
                availability_zones=[az['ZoneName'] for az in lb['AvailabilityZones']],
                security_groups=lb.get('SecurityGroups', []),
                listeners=listeners_response['Listeners']
            )
            
        except Exception as e:
            logger.error(f"Error getting load balancer info: {str(e)}")
            return None
    
    def _get_subnet_info(self, subnet_id: str) -> Optional[SubnetInfo]:
        """Get subnet information"""
        try:
            response = self.ec2_client.describe_subnets(
                SubnetIds=[subnet_id]
            )
            
            if not response['Subnets']:
                return None
            
            subnet = response['Subnets'][0]
            
            # Check if subnet is public (has route to internet gateway)
            is_public = self._is_subnet_public(subnet_id)
            
            return SubnetInfo(
                subnet_id=subnet['SubnetId'],
                vpc_id=subnet['VpcId'],
                availability_zone=subnet['AvailabilityZone'],
                cidr_block=subnet['CidrBlock'],
                is_public=is_public
            )
            
        except Exception as e:
            logger.error(f"Error getting subnet info: {str(e)}")
            return None
    
    def _is_subnet_public(self, subnet_id: str) -> bool:
        """Check if subnet is public (has route to internet gateway)"""
        try:
            # Get route table for subnet
            response = self.ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                ]
            )
            
            for route_table in response['RouteTables']:
                for route in route_table['Routes']:
                    if route.get('GatewayId', '').startswith('igw-'):
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if subnet is public: {str(e)}")
            return False
    
    def _find_target_groups_for_service(self, service_name: str, vpc_id: str) -> List[TargetGroupInfo]:
        """Find target groups for a service"""
        try:
            response = self.elbv2_client.describe_target_groups()
            
            target_groups = []
            for tg in response['TargetGroups']:
                # Match by name pattern or VPC
                if (service_name.lower() in tg['TargetGroupName'].lower() or 
                    tg['VpcId'] == vpc_id):
                    
                    target_groups.append(TargetGroupInfo(
                        arn=tg['TargetGroupArn'],
                        vpc_id=tg['VpcId'],
                        port=tg['Port'],
                        protocol=tg['Protocol'],
                        health_check_path=tg['HealthCheckPath']
                    ))
            
            return target_groups
            
        except Exception as e:
            logger.error(f"Error finding target groups: {str(e)}")
            return []
    
    def _find_compatible_subnets(self, vpc_id: str, availability_zones: Set[str]) -> List[str]:
        """Find compatible subnets for display in remediation steps"""
        try:
            response = self.ec2_client.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'availability-zone', 'Values': list(availability_zones)}
                ]
            )
            
            compatible_subnets = []
            for subnet in response['Subnets']:
                compatible_subnets.append(subnet['SubnetId'])
            
            return compatible_subnets[:3]  # Return first 3 for brevity
            
        except Exception as e:
            logger.error(f"Error finding compatible subnets: {str(e)}")
            return []