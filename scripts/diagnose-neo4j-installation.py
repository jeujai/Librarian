#!/usr/bin/env python3
"""
Comprehensive Neo4j Installation Diagnostics

This script performs detailed diagnostics of the Neo4j installation
to identify why the service isn't accessible.
"""

import json
import socket
import time
import boto3
import subprocess
import sys
from typing import Dict, Any, List

def log(message: str, level: str = "INFO"):
    """Log message with timestamp."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")

def test_port_connectivity(host: str, port: int, timeout: int = 5) -> Dict[str, Any]:
    """Test if a port is accessible."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start_time = time.time()
        result = sock.connect_ex((host, port))
        end_time = time.time()
        sock.close()
        
        return {
            "accessible": result == 0,
            "response_time_ms": round((end_time - start_time) * 1000, 2),
            "error_code": result if result != 0 else None
        }
    except Exception as e:
        return {
            "accessible": False,
            "error": str(e),
            "response_time_ms": None
        }

def get_instance_info() -> Dict[str, Any]:
    """Get Neo4j instance information."""
    try:
        with open('neo4j-simple-instance-info.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        log("Neo4j instance info file not found", "ERROR")
        return {}
    except Exception as e:
        log(f"Error reading instance info: {e}", "ERROR")
        return {}

def check_instance_status(instance_id: str) -> Dict[str, Any]:
    """Check EC2 instance status."""
    try:
        ec2 = boto3.client('ec2', region_name='us-east-1')
        
        # Get instance details
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        
        # Get instance status checks
        status_response = ec2.describe_instance_status(InstanceIds=[instance_id])
        status_checks = status_response.get('InstanceStatuses', [])
        
        return {
            "state": instance['State']['Name'],
            "launch_time": instance['LaunchTime'].isoformat(),
            "public_ip": instance.get('PublicIpAddress'),
            "private_ip": instance.get('PrivateIpAddress'),
            "instance_type": instance['InstanceType'],
            "status_checks": status_checks[0] if status_checks else None,
            "uptime_minutes": (time.time() - instance['LaunchTime'].timestamp()) / 60
        }
    except Exception as e:
        log(f"Error checking instance status: {e}", "ERROR")
        return {"error": str(e)}

def check_security_groups(instance_info: Dict[str, Any]) -> Dict[str, Any]:
    """Check security group configuration."""
    try:
        ec2 = boto3.client('ec2', region_name='us-east-1')
        
        sg_id = instance_info.get('security_group_id')
        if not sg_id:
            return {"error": "No security group ID found"}
        
        response = ec2.describe_security_groups(GroupIds=[sg_id])
        sg = response['SecurityGroups'][0]
        
        # Check for Neo4j ports
        neo4j_rules = []
        for rule in sg['IpPermissions']:
            if rule.get('FromPort') in [7687, 7474]:
                neo4j_rules.append({
                    "port": rule['FromPort'],
                    "protocol": rule['IpProtocol'],
                    "sources": {
                        "security_groups": [sg['GroupId'] for sg in rule.get('UserIdGroupPairs', [])],
                        "cidr_blocks": [cidr['CidrIp'] for cidr in rule.get('IpRanges', [])]
                    }
                })
        
        return {
            "security_group_id": sg_id,
            "neo4j_rules": neo4j_rules,
            "total_rules": len(sg['IpPermissions'])
        }
    except Exception as e:
        log(f"Error checking security groups: {e}", "ERROR")
        return {"error": str(e)}

def test_from_ecs_perspective(host: str) -> Dict[str, Any]:
    """Test connectivity from ECS task perspective using curl."""
    results = {}
    
    # Test HTTP endpoint (7474)
    try:
        result = subprocess.run([
            'curl', '-s', '-m', '10', f'http://{host}:7474'
        ], capture_output=True, text=True, timeout=15)
        
        results['http_test'] = {
            "return_code": result.returncode,
            "stdout": result.stdout[:200] if result.stdout else None,
            "stderr": result.stderr[:200] if result.stderr else None,
            "accessible": result.returncode == 0
        }
    except Exception as e:
        results['http_test'] = {"error": str(e), "accessible": False}
    
    # Test if we can reach the host at all
    try:
        result = subprocess.run([
            'ping', '-c', '3', '-W', '3000', host
        ], capture_output=True, text=True, timeout=15)
        
        results['ping_test'] = {
            "return_code": result.returncode,
            "accessible": result.returncode == 0,
            "output": result.stdout.split('\n')[-2:] if result.stdout else None
        }
    except Exception as e:
        results['ping_test'] = {"error": str(e), "accessible": False}
    
    return results

def check_neo4j_secret() -> Dict[str, Any]:
    """Check Neo4j secret configuration."""
    try:
        secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
        response = secrets_client.get_secret_value(SecretId='multimodal-librarian/full-ml/neo4j')
        secret_data = json.loads(response['SecretString'])
        
        return {
            "secret_exists": True,
            "host": secret_data.get('host'),
            "port": secret_data.get('port'),
            "username": secret_data.get('username'),
            "has_password": bool(secret_data.get('password')),
            "last_updated": response.get('CreatedDate', '').isoformat() if response.get('CreatedDate') else None
        }
    except Exception as e:
        log(f"Error checking Neo4j secret: {e}", "ERROR")
        return {"error": str(e), "secret_exists": False}

def run_comprehensive_diagnostics() -> Dict[str, Any]:
    """Run all diagnostic tests."""
    log("🔍 Starting comprehensive Neo4j diagnostics...")
    
    diagnostics = {
        "timestamp": time.time(),
        "test_duration_seconds": 0
    }
    
    start_time = time.time()
    
    # Get instance info
    log("📋 Getting instance information...")
    instance_info = get_instance_info()
    diagnostics['instance_info'] = instance_info
    
    if not instance_info:
        log("❌ Cannot proceed without instance information", "ERROR")
        return diagnostics
    
    instance_id = instance_info.get('instance_id')
    private_ip = instance_info.get('private_ip')
    
    # Check instance status
    log(f"🖥️  Checking instance status for {instance_id}...")
    diagnostics['instance_status'] = check_instance_status(instance_id)
    
    # Check security groups
    log("🔒 Checking security group configuration...")
    diagnostics['security_groups'] = check_security_groups(instance_info)
    
    # Check Neo4j secret
    log("🔐 Checking Neo4j secret configuration...")
    diagnostics['neo4j_secret'] = check_neo4j_secret()
    
    # Test port connectivity
    log(f"🔌 Testing port connectivity to {private_ip}...")
    diagnostics['port_tests'] = {
        "bolt_7687": test_port_connectivity(private_ip, 7687),
        "http_7474": test_port_connectivity(private_ip, 7474),
        "ssh_22": test_port_connectivity(private_ip, 22)
    }
    
    # Test from ECS perspective
    log("🌐 Testing from ECS perspective...")
    diagnostics['ecs_perspective'] = test_from_ecs_perspective(private_ip)
    
    diagnostics['test_duration_seconds'] = round(time.time() - start_time, 2)
    
    return diagnostics

def analyze_results(diagnostics: Dict[str, Any]) -> List[str]:
    """Analyze diagnostic results and provide recommendations."""
    issues = []
    recommendations = []
    
    # Check instance status
    instance_status = diagnostics.get('instance_status', {})
    if instance_status.get('state') != 'running':
        issues.append(f"Instance is not running: {instance_status.get('state')}")
    
    uptime = instance_status.get('uptime_minutes', 0)
    if uptime < 10:
        issues.append(f"Instance is very new ({uptime:.1f} minutes old) - Neo4j may still be installing")
    
    # Check port accessibility
    port_tests = diagnostics.get('port_tests', {})
    bolt_accessible = port_tests.get('bolt_7687', {}).get('accessible', False)
    http_accessible = port_tests.get('http_7474', {}).get('accessible', False)
    
    if not bolt_accessible and not http_accessible:
        issues.append("Neither Neo4j port (7687, 7474) is accessible")
        
        # Check if SSH is accessible to determine if it's a Neo4j issue or networking issue
        ssh_accessible = port_tests.get('ssh_22', {}).get('accessible', False)
        if ssh_accessible:
            issues.append("SSH is accessible but Neo4j ports are not - likely Neo4j installation issue")
            recommendations.append("SSH into instance to check Neo4j service status")
        else:
            issues.append("SSH is also not accessible - likely networking/security group issue")
    
    # Check security groups
    sg_info = diagnostics.get('security_groups', {})
    neo4j_rules = sg_info.get('neo4j_rules', [])
    if len(neo4j_rules) < 2:
        issues.append(f"Insufficient security group rules for Neo4j (found {len(neo4j_rules)}, need 2)")
    
    # Check secret configuration
    secret_info = diagnostics.get('neo4j_secret', {})
    if not secret_info.get('secret_exists'):
        issues.append("Neo4j secret does not exist or is not accessible")
    elif secret_info.get('host') != diagnostics.get('instance_info', {}).get('private_ip'):
        issues.append("Neo4j secret host does not match instance private IP")
    
    # Generate recommendations
    if uptime < 15:
        recommendations.append("Wait 10-15 minutes for Neo4j installation to complete")
    
    if not bolt_accessible:
        recommendations.append("Check Neo4j service status on the instance")
        recommendations.append("Review Neo4j installation logs")
    
    if len(neo4j_rules) < 2:
        recommendations.append("Verify security group rules allow access from ECS security group")
    
    return issues, recommendations

def print_summary(diagnostics: Dict[str, Any]):
    """Print diagnostic summary."""
    print("\n" + "="*80)
    print("🔍 NEO4J DIAGNOSTIC SUMMARY")
    print("="*80)
    
    # Instance info
    instance_info = diagnostics.get('instance_info', {})
    instance_status = diagnostics.get('instance_status', {})
    
    print(f"\n📋 INSTANCE INFORMATION:")
    print(f"   Instance ID: {instance_info.get('instance_id', 'Unknown')}")
    print(f"   Private IP: {instance_info.get('private_ip', 'Unknown')}")
    print(f"   State: {instance_status.get('state', 'Unknown')}")
    print(f"   Uptime: {instance_status.get('uptime_minutes', 0):.1f} minutes")
    
    # Port tests
    port_tests = diagnostics.get('port_tests', {})
    print(f"\n🔌 PORT CONNECTIVITY:")
    for port_name, result in port_tests.items():
        status = "✅ Accessible" if result.get('accessible') else "❌ Not accessible"
        response_time = result.get('response_time_ms')
        time_info = f" ({response_time}ms)" if response_time else ""
        print(f"   {port_name}: {status}{time_info}")
    
    # Security groups
    sg_info = diagnostics.get('security_groups', {})
    neo4j_rules = sg_info.get('neo4j_rules', [])
    print(f"\n🔒 SECURITY GROUPS:")
    print(f"   Security Group: {sg_info.get('security_group_id', 'Unknown')}")
    print(f"   Neo4j Rules: {len(neo4j_rules)}")
    for rule in neo4j_rules:
        print(f"     Port {rule['port']}: {rule['sources']}")
    
    # Secret info
    secret_info = diagnostics.get('neo4j_secret', {})
    print(f"\n🔐 SECRET CONFIGURATION:")
    print(f"   Secret exists: {secret_info.get('secret_exists', False)}")
    print(f"   Host: {secret_info.get('host', 'Unknown')}")
    print(f"   Port: {secret_info.get('port', 'Unknown')}")
    
    # Analysis
    issues, recommendations = analyze_results(diagnostics)
    
    if issues:
        print(f"\n❌ ISSUES IDENTIFIED ({len(issues)}):")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
    
    if recommendations:
        print(f"\n💡 RECOMMENDATIONS ({len(recommendations)}):")
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
    
    # Overall status
    bolt_accessible = port_tests.get('bolt_7687', {}).get('accessible', False)
    http_accessible = port_tests.get('http_7474', {}).get('accessible', False)
    
    print(f"\n🎯 OVERALL STATUS:")
    if bolt_accessible and http_accessible:
        print("   ✅ Neo4j appears to be working correctly")
    elif bolt_accessible or http_accessible:
        print("   ⚠️  Neo4j is partially accessible - may still be starting")
    else:
        print("   ❌ Neo4j is not accessible - requires investigation")
    
    print(f"\n⏱️  Diagnostic completed in {diagnostics.get('test_duration_seconds', 0)} seconds")
    print("="*80)

def main():
    """Main diagnostic function."""
    try:
        diagnostics = run_comprehensive_diagnostics()
        
        # Save results
        with open('neo4j-diagnostics.json', 'w') as f:
            json.dump(diagnostics, f, indent=2, default=str)
        
        print_summary(diagnostics)
        
        # Return appropriate exit code
        port_tests = diagnostics.get('port_tests', {})
        bolt_accessible = port_tests.get('bolt_7687', {}).get('accessible', False)
        
        if bolt_accessible:
            log("✅ Neo4j Bolt port is accessible - diagnostics PASSED", "SUCCESS")
            return 0
        else:
            log("❌ Neo4j Bolt port is not accessible - diagnostics FAILED", "ERROR")
            return 1
            
    except Exception as e:
        log(f"Diagnostic script failed: {e}", "ERROR")
        return 2

if __name__ == "__main__":
    sys.exit(main())