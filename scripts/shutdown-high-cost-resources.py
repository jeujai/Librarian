#!/usr/bin/env python3
"""
Quick shutdown script for high-cost AWS resources.

This script provides safe shutdown commands for the most expensive resources
typically found in Multimodal Librarian deployments.
"""

import boto3
import json
import sys
from typing import List, Dict, Any

class QuickShutdown:
    """Quick shutdown manager for high-cost resources."""
    
    def __init__(self, region: str = 'us-east-1'):
        self.region = region
        self.session = boto3.Session()
        
        # Initialize AWS clients
        self.ecs = self.session.client('ecs', region_name=region)
        self.ec2 = self.session.client('ec2', region_name=region)
        self.rds = self.session.client('rds', region_name=region)
        self.opensearch = self.session.client('opensearch', region_name=region)
    
    def shutdown_nat_gateways(self, dry_run: bool = True) -> List[str]:
        """Shutdown NAT Gateways (highest cost impact)."""
        
        print("🌐 Shutting down NAT Gateways...")
        actions = []
        
        try:
            nat_gateways = self.ec2.describe_nat_gateways()
            
            for nat_gw in nat_gateways.get('NatGateways', []):
                if nat_gw.get('State') == 'available':
                    nat_gw_id = nat_gw.get('NatGatewayId')
                    
                    # Check if it's related to ML project
                    tags = {tag['Key']: tag['Value'] for tag in nat_gw.get('Tags', [])}
                    
                    if any(keyword in str(tags).lower() for keyword in 
                           ['multimodal', 'librarian', 'ml-', 'chat-doc']):
                        
                        action = f"aws ec2 delete-nat-gateway --nat-gateway-id {nat_gw_id}"
                        actions.append(action)
                        
                        if dry_run:
                            print(f"   [DRY RUN] Would delete: {nat_gw_id}")
                            print(f"   Command: {action}")
                        else:
                            try:
                                self.ec2.delete_nat_gateway(NatGatewayId=nat_gw_id)
                                print(f"   ✅ Deleted NAT Gateway: {nat_gw_id}")
                            except Exception as e:
                                print(f"   ❌ Failed to delete {nat_gw_id}: {e}")
        
        except Exception as e:
            print(f"❌ Error with NAT Gateways: {e}")
        
        return actions
    
    def stop_rds_instances(self, dry_run: bool = True) -> List[str]:
        """Stop RDS instances (can be restarted later)."""
        
        print("🗄️  Stopping RDS instances...")
        actions = []
        
        try:
            rds_instances = self.rds.describe_db_instances()
            
            for db in rds_instances.get('DBInstances', []):
                db_id = db.get('DBInstanceIdentifier', '')
                status = db.get('DBInstanceStatus')
                
                if (any(keyword in db_id.lower() for keyword in 
                        ['multimodal', 'librarian', 'ml-', 'chat-doc']) and 
                    status == 'available'):
                    
                    action = f"aws rds stop-db-instance --db-instance-identifier {db_id}"
                    actions.append(action)
                    
                    if dry_run:
                        print(f"   [DRY RUN] Would stop: {db_id}")
                        print(f"   Command: {action}")
                    else:
                        try:
                            self.rds.stop_db_instance(DBInstanceIdentifier=db_id)
                            print(f"   ✅ Stopped RDS instance: {db_id}")
                        except Exception as e:
                            print(f"   ❌ Failed to stop {db_id}: {e}")
        
        except Exception as e:
            print(f"❌ Error with RDS instances: {e}")
        
        return actions
    
    def scale_down_ecs_services(self, dry_run: bool = True) -> List[str]:
        """Scale down ECS services to 0."""
        
        print("📦 Scaling down ECS services...")
        actions = []
        
        try:
            clusters = self.ecs.list_clusters()
            
            for cluster_arn in clusters.get('clusterArns', []):
                cluster_name = cluster_arn.split('/')[-1]
                
                if any(keyword in cluster_name.lower() for keyword in 
                       ['multimodal', 'librarian', 'ml-', 'chat-doc']):
                    
                    services = self.ecs.list_services(cluster=cluster_arn)
                    
                    for service_arn in services.get('serviceArns', []):
                        service_name = service_arn.split('/')[-1]
                        
                        action = f"aws ecs update-service --cluster {cluster_name} --service {service_name} --desired-count 0"
                        actions.append(action)
                        
                        if dry_run:
                            print(f"   [DRY RUN] Would scale down: {cluster_name}/{service_name}")
                            print(f"   Command: {action}")
                        else:
                            try:
                                self.ecs.update_service(
                                    cluster=cluster_arn,
                                    service=service_arn,
                                    desiredCount=0
                                )
                                print(f"   ✅ Scaled down service: {cluster_name}/{service_name}")
                            except Exception as e:
                                print(f"   ❌ Failed to scale down {service_name}: {e}")
        
        except Exception as e:
            print(f"❌ Error with ECS services: {e}")
        
        return actions
    
    def stop_ec2_instances(self, dry_run: bool = True) -> List[str]:
        """Stop EC2 instances."""
        
        print("💻 Stopping EC2 instances...")
        actions = []
        
        try:
            reservations = self.ec2.describe_instances()
            
            for reservation in reservations.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instance_id = instance.get('InstanceId')
                    state = instance.get('State', {}).get('Name')
                    
                    # Check tags
                    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                    instance_name = tags.get('Name', '')
                    
                    if (any(keyword in str(tags).lower() for keyword in 
                            ['multimodal', 'librarian', 'ml-', 'chat-doc']) and 
                        state == 'running'):
                        
                        action = f"aws ec2 stop-instances --instance-ids {instance_id}"
                        actions.append(action)
                        
                        if dry_run:
                            print(f"   [DRY RUN] Would stop: {instance_id} ({instance_name})")
                            print(f"   Command: {action}")
                        else:
                            try:
                                self.ec2.stop_instances(InstanceIds=[instance_id])
                                print(f"   ✅ Stopped instance: {instance_id} ({instance_name})")
                            except Exception as e:
                                print(f"   ❌ Failed to stop {instance_id}: {e}")
        
        except Exception as e:
            print(f"❌ Error with EC2 instances: {e}")
        
        return actions
    
    def generate_shutdown_script(self, actions: List[str]) -> str:
        """Generate a shell script with all shutdown commands."""
        
        script_lines = [
            "#!/bin/bash",
            "# AWS Resource Shutdown Script",
            "# Generated automatically for Multimodal Librarian cleanup",
            "",
            "set -e  # Exit on any error",
            "",
            "echo '🧹 Starting AWS resource shutdown...'",
            ""
        ]
        
        for action in actions:
            script_lines.append(f"echo 'Executing: {action}'")
            script_lines.append(action)
            script_lines.append("echo 'Done.'")
            script_lines.append("")
        
        script_lines.extend([
            "echo '✅ Shutdown complete!'",
            "echo 'Monitor AWS console to verify resources are stopped/deleted.'"
        ])
        
        return "\n".join(script_lines)


def main():
    """Main shutdown execution."""
    
    print("🚨 Quick Shutdown for High-Cost AWS Resources")
    print("=" * 50)
    print()
    
    # Check if this is a dry run
    dry_run = '--execute' not in sys.argv
    
    if dry_run:
        print("🔍 DRY RUN MODE - No resources will be modified")
        print("   Add --execute flag to actually perform shutdown")
    else:
        print("⚠️  EXECUTION MODE - Resources will be modified!")
        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return 1
    
    print()
    
    # Initialize shutdown manager
    shutdown_manager = QuickShutdown()
    
    all_actions = []
    
    # Shutdown high-cost resources
    print("🎯 Targeting high-cost resources for immediate savings...")
    print()
    
    # 1. NAT Gateways (highest cost)
    nat_actions = shutdown_manager.shutdown_nat_gateways(dry_run=dry_run)
    all_actions.extend(nat_actions)
    
    # 2. RDS instances (stop, don't delete)
    rds_actions = shutdown_manager.stop_rds_instances(dry_run=dry_run)
    all_actions.extend(rds_actions)
    
    # 3. ECS services (scale to 0)
    ecs_actions = shutdown_manager.scale_down_ecs_services(dry_run=dry_run)
    all_actions.extend(ecs_actions)
    
    # 4. EC2 instances (stop)
    ec2_actions = shutdown_manager.stop_ec2_instances(dry_run=dry_run)
    all_actions.extend(ec2_actions)
    
    # Generate script file
    if all_actions:
        script_content = shutdown_manager.generate_shutdown_script(all_actions)
        script_file = "shutdown-resources.sh"
        
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        print(f"\n📄 Shutdown script saved to: {script_file}")
        print(f"   Make executable with: chmod +x {script_file}")
        print(f"   Execute with: ./{script_file}")
    else:
        print("\n✅ No high-cost resources found to shutdown")
    
    # Cost savings estimate
    if nat_actions or rds_actions:
        print("\n💰 Estimated Monthly Savings:")
        if nat_actions:
            print(f"   NAT Gateways: ~${len(nat_actions) * 45:.2f}/month")
        if rds_actions:
            print(f"   RDS Instances: ~${len(rds_actions) * 100:.2f}/month (varies by instance type)")
        if ecs_actions:
            print(f"   ECS Services: Variable (depends on task size and count)")
        if ec2_actions:
            print(f"   EC2 Instances: Variable (depends on instance types)")
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)