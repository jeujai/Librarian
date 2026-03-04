#!/usr/bin/env python3
"""
Phase 1 Safe Shutdown - Reversible cost optimization actions.

This script performs only safe, reversible actions:
- Stop RDS instances (can restart within 7 days)
- Scale ECS services to 0 (can scale back up)
- Stop EC2 instances (can restart anytime)

Estimated savings: ~$150/month
"""

import boto3
import sys
import time

def safe_shutdown_phase1():
    """Execute Phase 1 safe shutdown actions."""
    
    print("🛡️  Phase 1: Safe Shutdown (Reversible Actions)")
    print("=" * 50)
    print("This will stop/scale resources that can be restarted later")
    print("Estimated savings: ~$150/month")
    print()
    
    # Initialize AWS clients
    session = boto3.Session()
    rds = session.client('rds', region_name='us-east-1')
    ecs = session.client('ecs', region_name='us-east-1')
    ec2 = session.client('ec2', region_name='us-east-1')
    
    actions_completed = []
    
    # 1. Stop RDS instance
    print("🗄️  Stopping RDS instance...")
    try:
        rds_identifier = "multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro"
        
        # Check current status
        response = rds.describe_db_instances(DBInstanceIdentifier=rds_identifier)
        current_status = response['DBInstances'][0]['DBInstanceStatus']
        
        if current_status == 'available':
            rds.stop_db_instance(DBInstanceIdentifier=rds_identifier)
            print(f"   ✅ Stopping RDS instance: {rds_identifier}")
            print(f"   💡 Can be restarted within 7 days")
            actions_completed.append(f"Stopped RDS: {rds_identifier}")
        else:
            print(f"   ℹ️  RDS instance already in state: {current_status}")
            
    except Exception as e:
        print(f"   ⚠️  RDS stop failed: {e}")
    
    # 2. Scale down ECS services
    print("\n📦 Scaling down ECS services...")
    
    ecs_services = [
        ("multimodal-lib-prod-cluster", "multimodal-lib-prod-service"),
        ("multimodal-librarian-full-ml", "multimodal-librarian-full-ml-web"),
        ("multimodal-librarian-full-ml", "multimodal-librarian-full-ml-service")
    ]
    
    for cluster_name, service_name in ecs_services:
        try:
            # Check current desired count
            response = ecs.describe_services(cluster=cluster_name, services=[service_name])
            
            if response['services']:
                current_count = response['services'][0]['desiredCount']
                
                if current_count > 0:
                    ecs.update_service(
                        cluster=cluster_name,
                        service=service_name,
                        desiredCount=0
                    )
                    print(f"   ✅ Scaled down: {cluster_name}/{service_name} (was {current_count})")
                    print(f"   💡 Can be scaled back up anytime")
                    actions_completed.append(f"Scaled down ECS: {cluster_name}/{service_name}")
                else:
                    print(f"   ℹ️  Service already scaled to 0: {cluster_name}/{service_name}")
            else:
                print(f"   ⚠️  Service not found: {cluster_name}/{service_name}")
                
        except Exception as e:
            print(f"   ⚠️  ECS scale down failed for {service_name}: {e}")
    
    # 3. Stop EC2 instances
    print("\n💻 Stopping EC2 instances...")
    try:
        instance_id = "i-0255d25fd1950ed2d"  # neo4j-simple-multimodal-librarian
        
        # Check current state
        response = ec2.describe_instances(InstanceIds=[instance_id])
        current_state = response['Reservations'][0]['Instances'][0]['State']['Name']
        
        if current_state == 'running':
            ec2.stop_instances(InstanceIds=[instance_id])
            print(f"   ✅ Stopping EC2 instance: {instance_id}")
            print(f"   💡 Can be restarted anytime")
            actions_completed.append(f"Stopped EC2: {instance_id}")
        else:
            print(f"   ℹ️  EC2 instance already in state: {current_state}")
            
    except Exception as e:
        print(f"   ⚠️  EC2 stop failed: {e}")
    
    # Summary
    print(f"\n📊 Phase 1 Complete!")
    print(f"Actions completed: {len(actions_completed)}")
    for action in actions_completed:
        print(f"   ✅ {action}")
    
    if actions_completed:
        print(f"\n💰 Estimated monthly savings: ~$150")
        print(f"💡 All actions are reversible - resources can be restarted")
        print(f"⏰ RDS can be restarted within 7 days, others anytime")
    else:
        print(f"\n✅ No actions needed - resources already in optimal state")
    
    return len(actions_completed)


def main():
    """Main execution."""
    
    print("🧹 Multimodal Librarian - Phase 1 Safe Shutdown")
    print()
    
    try:
        actions_count = safe_shutdown_phase1()
        
        if actions_count > 0:
            print(f"\n🎉 Successfully completed {actions_count} cost optimization actions!")
            print(f"💰 You should see reduced AWS costs starting immediately")
            
            # Generate restart commands
            print(f"\n🔄 To restart resources later:")
            print(f"   RDS: aws rds start-db-instance --db-instance-identifier multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro")
            print(f"   ECS: aws ecs update-service --cluster <cluster> --service <service> --desired-count 1")
            print(f"   EC2: aws ec2 start-instances --instance-ids i-0255d25fd1950ed2d")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error during shutdown: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)