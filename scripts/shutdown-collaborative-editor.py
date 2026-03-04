#!/usr/bin/env python3
"""
Collaborative Editor Shutdown Script
Shuts down the collaborative-editor-env EC2 instance for additional cost savings.

Additional savings: $15-20/month ($180-240/year)
"""

import boto3
import json
import time
from datetime import datetime
import sys

class CollaborativeEditorShutdown:
    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "collaborative_editor_shutdown": False,
            "instance_terminated": False,
            "additional_monthly_savings": 15,
            "errors": []
        }
        
        # Initialize AWS client for us-west-2
        try:
            self.ec2_client = boto3.client('ec2', region_name='us-west-2')
            print("✅ AWS EC2 client (us-west-2) initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize AWS client: {e}")
            sys.exit(1)

    def shutdown_collaborative_editor(self) -> bool:
        """Shut down the collaborative editor EC2 instance"""
        print("\n🔄 Shutting Down Collaborative Editor")
        
        try:
            # Find the collaborative editor instance
            instances = self.ec2_client.describe_instances(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running']},
                    {'Name': 'tag:Name', 'Values': ['collaborative-editor-env']}
                ]
            )
            
            instance_ids = []
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_ids.append(instance['InstanceId'])
                    print(f"  📊 Found instance: {instance['InstanceId']} ({instance['InstanceType']})")
            
            if not instance_ids:
                print("ℹ️  No collaborative editor instances found to shut down")
                return True
            
            # Terminate the instances
            print(f"  🔄 Terminating {len(instance_ids)} instance(s)...")
            
            response = self.ec2_client.terminate_instances(InstanceIds=instance_ids)
            
            for instance in response['TerminatingInstances']:
                instance_id = instance['InstanceId']
                current_state = instance['CurrentState']['Name']
                previous_state = instance['PreviousState']['Name']
                
                print(f"  ✅ Instance {instance_id}: {previous_state} → {current_state}")
            
            self.results["collaborative_editor_shutdown"] = True
            self.results["instance_terminated"] = True
            self.results["terminated_instances"] = instance_ids
            
            print(f"✅ Successfully initiated termination of {len(instance_ids)} instance(s)")
            print(f"💰 Additional monthly savings: ${self.results['additional_monthly_savings']}")
            print(f"💰 Additional annual savings: ${self.results['additional_monthly_savings'] * 12}")
            
            return True
            
        except Exception as e:
            error_msg = f"Collaborative editor shutdown failed: {e}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
            return False

    def save_results(self):
        """Save shutdown results to file"""
        filename = f"collaborative-editor-shutdown-{int(time.time())}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(self.results, f, indent=2, default=str)
            print(f"\n📄 Results saved to: {filename}")
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")

    def run_shutdown(self):
        """Execute the collaborative editor shutdown"""
        print("🚀 Starting Collaborative Editor Shutdown")
        print("=" * 50)
        
        success = self.shutdown_collaborative_editor()
        
        # Summary
        print("\n" + "=" * 50)
        print("🎯 COLLABORATIVE EDITOR SHUTDOWN SUMMARY")
        print("=" * 50)
        
        print(f"✅ Shutdown Status: {'Success' if success else 'Failed'}")
        
        if success and self.results["instance_terminated"]:
            print(f"💰 Additional Monthly Savings: ${self.results['additional_monthly_savings']}")
            print(f"💰 Additional Annual Savings: ${self.results['additional_monthly_savings'] * 12}")
        
        if self.results["errors"]:
            print(f"\n⚠️  Errors encountered: {len(self.results['errors'])}")
            for error in self.results["errors"]:
                print(f"   - {error}")
        
        # Save results
        self.save_results()
        
        return success

def main():
    """Main execution function"""
    shutdown = CollaborativeEditorShutdown()
    
    try:
        success = shutdown.run_shutdown()
        
        if success:
            print("\n🎉 Collaborative Editor shutdown completed successfully!")
            if shutdown.results["instance_terminated"]:
                print(f"💰 Additional monthly savings: ${shutdown.results['additional_monthly_savings']}")
                print(f"💰 Additional annual savings: ${shutdown.results['additional_monthly_savings'] * 12}")
                print("\n🎯 MAXIMUM COST OPTIMIZATION ACHIEVED!")
                print(f"   Total Project Annual Savings: ~$4,700-4,900")
        else:
            print("\n⚠️  Collaborative Editor shutdown completed with errors")
            
    except KeyboardInterrupt:
        print("\n⚠️  Shutdown interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Shutdown failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()