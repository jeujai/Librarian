#!/usr/bin/env python3
"""
Monitor Neo4j startup progress and diagnose issues.
"""

import json
import boto3
import socket
import time
import subprocess
import sys
from datetime import datetime, timedelta

def get_instance_info():
    """Get Neo4j instance information."""
    try:
        with open('neo4j-instance-info.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ neo4j-instance-info.json not found")
        return None

def check_instance_status(instance_id):
    """Check EC2 instance status."""
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    try:
        response = ec2.describe-instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        
        return {
            "state": instance['State']['Name'],
            "status_checks": ec2.describe_instance_status(InstanceIds=[instance_id])
        }
    except Exception as e:
        return {"error": str(e)}

def test_port_connectivity(host, port, timeout=5):
    """Test if a port is accessible."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def check_neo4j_logs_via_ssh(instance_info):
    """Check Neo4j logs via SSH (if key is available)."""
    try:
        # This would require SSH key access
        print("📋 To check Neo4j logs manually, SSH to the instance:")
        print(f"   ssh -i migration-key.pem ec2-user@{instance_info['public_ip']}")
        print("   sudo journalctl -u neo4j -f")
        print("   sudo systemctl status neo4j")
        print("   sudo tail -f /var/log/neo4j/neo4j.log")
        return None
    except Exception as e:
        return f"SSH check failed: {e}"

def estimate_startup_progress(created_at_str):
    """Estimate startup progress based on time elapsed."""
    try:
        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        now = datetime.now(created_at.tzinfo)
        elapsed = now - created_at
        elapsed_minutes = elapsed.total_seconds() / 60
        
        # Neo4j startup phases
        phases = [
            (1, "EC2 instance boot"),
            (2, "Java installation"),
            (3, "Neo4j installation"),
            (4, "Neo4j configuration"),
            (5, "Neo4j service start"),
            (8, "Database initialization"),
            (10, "Ready for connections")
        ]
        
        current_phase = "Unknown"
        progress = 0
        
        for minutes, phase in phases:
            if elapsed_minutes >= minutes:
                current_phase = phase
                progress = min(100, (elapsed_minutes / 10) * 100)
            else:
                break
        
        return {
            "elapsed_minutes": elapsed_minutes,
            "current_phase": current_phase,
            "progress_percent": progress,
            "expected_ready_in": max(0, 10 - elapsed_minutes)
        }
    except Exception as e:
        return {"error": str(e)}

def diagnose_connectivity_issues(host):
    """Diagnose potential connectivity issues."""
    issues = []
    
    # Check if host is reachable
    try:
        response = subprocess.run(['ping', '-c', '1', host], 
                                capture_output=True, text=True, timeout=10)
        if response.returncode != 0:
            issues.append("Host is not reachable via ping")
    except subprocess.TimeoutExpired:
        issues.append("Ping timeout - possible network issues")
    except Exception:
        issues.append("Cannot test ping connectivity")
    
    # Check common ports
    common_ports = [22, 80, 443]  # SSH, HTTP, HTTPS
    reachable_ports = []
    
    for port in common_ports:
        if test_port_connectivity(host, port, timeout=3):
            reachable_ports.append(port)
    
    if not reachable_ports:
        issues.append("No common ports are reachable")
    
    return issues

def main():
    print("🔍 Neo4j Startup Monitor")
    print("=" * 50)
    
    # Get instance info
    instance_info = get_instance_info()
    if not instance_info:
        sys.exit(1)
    
    instance_id = instance_info['instance_id']
    host = instance_info['private_ip']
    created_at = instance_info['created_at']
    
    print(f"📍 Instance: {instance_id}")
    print(f"🌐 Host: {host}")
    print(f"⏰ Created: {created_at}")
    print()
    
    # Check instance status
    print("🖥️  EC2 Instance Status:")
    instance_status = check_instance_status(instance_id)
    if "error" in instance_status:
        print(f"   ❌ Error: {instance_status['error']}")
    else:
        print(f"   ✅ State: {instance_status['state']}")
    print()
    
    # Estimate progress
    print("📊 Startup Progress Estimation:")
    progress = estimate_startup_progress(created_at)
    if "error" in progress:
        print(f"   ❌ Error: {progress['error']}")
    else:
        elapsed = progress['elapsed_minutes']
        phase = progress['current_phase']
        percent = progress['progress_percent']
        remaining = progress['expected_ready_in']
        
        print(f"   ⏱️  Elapsed: {elapsed:.1f} minutes")
        print(f"   🔄 Current phase: {phase}")
        print(f"   📈 Progress: {percent:.0f}%")
        
        if remaining > 0:
            print(f"   ⏳ Expected ready in: {remaining:.1f} minutes")
        else:
            print(f"   ✅ Should be ready now!")
    print()
    
    # Test connectivity
    print("🔌 Connectivity Tests:")
    
    # Test Neo4j ports
    bolt_accessible = test_port_connectivity(host, 7687, timeout=5)
    http_accessible = test_port_connectivity(host, 7474, timeout=5)
    
    print(f"   Neo4j Bolt (7687): {'✅ Accessible' if bolt_accessible else '❌ Not accessible'}")
    print(f"   Neo4j HTTP (7474): {'✅ Accessible' if http_accessible else '❌ Not accessible'}")
    
    if bolt_accessible and http_accessible:
        print("   🎉 Neo4j appears to be ready!")
        
        # Test actual Neo4j connection
        print("\n🗄️  Testing Neo4j Database Connection:")
        try:
            from src.multimodal_librarian.clients.neo4j_client import get_neo4j_client
            client = get_neo4j_client()
            health = client.health_check(force=True)
            
            if health["status"] == "healthy":
                print("   ✅ Neo4j database connection successful!")
                
                # Get database info
                db_info = client.get_database_info()
                print(f"   📊 Nodes: {db_info.get('node_count', 0)}")
                print(f"   🔗 Relationships: {db_info.get('relationship_count', 0)}")
                
                return True
            else:
                print(f"   ❌ Neo4j health check failed: {health.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"   ❌ Neo4j connection test failed: {e}")
    
    elif elapsed > 15:  # If more than 15 minutes
        print("\n⚠️  Neo4j startup is taking longer than expected")
        
        # Diagnose issues
        print("\n🔧 Diagnosing potential issues:")
        issues = diagnose_connectivity_issues(host)
        
        if issues:
            for issue in issues:
                print(f"   ❌ {issue}")
        else:
            print("   ✅ No obvious connectivity issues detected")
        
        # Provide troubleshooting steps
        print("\n🛠️  Troubleshooting Steps:")
        print("   1. Check Neo4j service status:")
        check_neo4j_logs_via_ssh(instance_info)
        print()
        print("   2. Check security groups:")
        print("      aws ec2 describe-security-groups --group-ids sg-02945459e124cf00b")
        print()
        print("   3. Restart Neo4j service (if needed):")
        print(f"      ssh -i migration-key.pem ec2-user@{instance_info['public_ip']}")
        print("      sudo systemctl restart neo4j")
        print()
        print("   4. Check Neo4j configuration:")
        print("      sudo cat /etc/neo4j/neo4j.conf")
        
    else:
        print(f"\n⏳ Neo4j is still starting up. Please wait {remaining:.1f} more minutes.")
    
    return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Monitoring error: {e}")
        sys.exit(1)