#!/usr/bin/env python3
"""
Reduce task memory from 24GB to 8GB and redeploy to AWS ECS.
This script updates the deployment configuration and triggers a rebuild/redeploy.
"""

import boto3
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# New memory configuration
NEW_MEMORY_MB = 8192  # 8GB
NEW_CPU_UNITS = 4096  # 4 vCPUs (required for 8GB memory)

# Configuration file path
CONFIG_FILE = Path(__file__).parent.parent / "config" / "deployment-config.json"

def update_deployment_config():
    """Update deployment configuration file with new memory settings."""
    print("📝 Updating deployment configuration...")
    
    # Ensure config directory exists
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing config or create new one
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            print(f"✅ Loaded existing configuration")
        except Exception as e:
            print(f"⚠️  Error loading config: {e}")
            config = {}
    else:
        print("📝 Creating new configuration file")
        config = {}
    
    # Update memory and CPU settings
    old_memory = config.get('task_memory_mb', 'unknown')
    old_cpu = config.get('task_cpu_units', 'unknown')
    
    config.update({
        'task_memory_mb': NEW_MEMORY_MB,
        'task_cpu_units': NEW_CPU_UNITS,
        'desired_count': config.get('desired_count', 1),
        'cluster_name': config.get('cluster_name', 'multimodal-lib-prod-cluster'),
        'service_name': config.get('service_name', 'multimodal-lib-prod-service'),
        'task_family': config.get('task_family', 'multimodal-lib-prod-app'),
        'container_name': config.get('container_name', 'multimodal-lib-prod-app')
    })
    
    # Save updated configuration
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Configuration updated successfully")
        print(f"   Old Memory: {old_memory} MB")
        print(f"   New Memory: {NEW_MEMORY_MB} MB (8GB)")
        print(f"   Old CPU: {old_cpu} units")
        print(f"   New CPU: {NEW_CPU_UNITS} units (4 vCPUs)")
        print(f"   Config file: {CONFIG_FILE}")
        
        return True
    except Exception as e:
        print(f"❌ Error saving configuration: {e}")
        return False

def trigger_rebuild_and_redeploy():
    """Trigger the rebuild and redeploy script."""
    print("\n🚀 Triggering rebuild and redeploy...")
    
    rebuild_script = Path(__file__).parent / "rebuild-and-redeploy.py"
    
    if not rebuild_script.exists():
        print(f"❌ Rebuild script not found: {rebuild_script}")
        return False
    
    try:
        # Make script executable
        rebuild_script.chmod(0o755)
        
        # Execute rebuild script
        print(f"▶️  Executing: {rebuild_script}")
        result = subprocess.run(
            [sys.executable, str(rebuild_script)],
            capture_output=False,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Rebuild and redeploy completed successfully")
            return True
        else:
            print(f"❌ Rebuild and redeploy failed with exit code: {result.returncode}")
            return False
            
    except Exception as e:
        print(f"❌ Error executing rebuild script: {e}")
        return False

def main():
    """Main execution function."""
    print("🔧 Reduce Memory to 8GB and Redeploy")
    print("=" * 60)
    print(f"Execution Time: {datetime.now().isoformat()}")
    print()
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'target_memory_mb': NEW_MEMORY_MB,
        'target_cpu_units': NEW_CPU_UNITS,
        'steps': [],
        'success': True
    }
    
    try:
        # Step 1: Update deployment configuration
        print("1️⃣ Updating deployment configuration...")
        if update_deployment_config():
            results['steps'].append({
                'step': 'config_update',
                'status': 'success',
                'message': f'Configuration updated to {NEW_MEMORY_MB}MB / {NEW_CPU_UNITS} CPU units'
            })
        else:
            results['steps'].append({
                'step': 'config_update',
                'status': 'failed',
                'message': 'Failed to update configuration'
            })
            results['success'] = False
            return results
        
        # Step 2: Trigger rebuild and redeploy
        print("\n2️⃣ Triggering rebuild and redeploy...")
        if trigger_rebuild_and_redeploy():
            results['steps'].append({
                'step': 'rebuild_redeploy',
                'status': 'success',
                'message': 'Rebuild and redeploy completed successfully'
            })
        else:
            results['steps'].append({
                'step': 'rebuild_redeploy',
                'status': 'failed',
                'message': 'Rebuild and redeploy failed'
            })
            results['success'] = False
            return results
        
        print("\n" + "=" * 60)
        print("✅ Memory reduction and redeployment completed successfully!")
        print(f"📊 New Configuration:")
        print(f"   Memory: {NEW_MEMORY_MB} MB (8GB)")
        print(f"   CPU: {NEW_CPU_UNITS} units (4 vCPUs)")
        print()
        print("📋 Next Steps:")
        print("   1. Monitor the deployment in AWS ECS console")
        print("   2. Check CloudWatch logs for any memory-related issues")
        print("   3. Verify application functionality after deployment")
        print("   4. Monitor memory usage to ensure 8GB is sufficient")
        
        return results
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        results['success'] = False
        results['steps'].append({
            'step': 'fatal_error',
            'status': 'failed',
            'message': str(e)
        })
        return results
    finally:
        # Save results
        timestamp = int(datetime.now().timestamp())
        results_file = f'8gb-memory-reduction-{timestamp}.json'
        
        try:
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n📝 Results saved to: {results_file}")
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")

if __name__ == "__main__":
    results = main()
    sys.exit(0 if results['success'] else 1)
