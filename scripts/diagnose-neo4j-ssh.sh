#!/bin/bash
"""
Diagnose Neo4j Service via SSH/SSM

This script connects to the Neo4j instance to diagnose why the service
is not starting properly.
"""

set -e

# Configuration
REGION="us-east-1"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# Get instance information
get_instance_info() {
    if [ ! -f "neo4j-instance-info.json" ]; then
        error "neo4j-instance-info.json not found"
        exit 1
    fi
    
    INSTANCE_ID=$(jq -r '.instance_id' neo4j-instance-info.json)
    PUBLIC_IP=$(jq -r '.public_ip' neo4j-instance-info.json)
    PRIVATE_IP=$(jq -r '.private_ip' neo4j-instance-info.json)
    
    log "Instance ID: $INSTANCE_ID"
    log "Public IP: $PUBLIC_IP"
    log "Private IP: $PRIVATE_IP"
}

# Run diagnostic commands via Systems Manager
run_ssm_diagnostics() {
    log "Running Neo4j diagnostics via Systems Manager..."
    
    # Create comprehensive diagnostic script
    DIAGNOSTIC_SCRIPT='#!/bin/bash
echo "=== Neo4j Service Diagnostics ==="
echo "Timestamp: $(date)"
echo

echo "=== System Information ==="
uname -a
uptime
free -h
df -h
echo

echo "=== Neo4j Service Status ==="
systemctl status neo4j --no-pager -l
echo

echo "=== Neo4j Service Logs (last 50 lines) ==="
journalctl -u neo4j --no-pager -n 50
echo

echo "=== Neo4j Configuration ==="
echo "--- /etc/neo4j/neo4j.conf ---"
cat /etc/neo4j/neo4j.conf 2>/dev/null || echo "Config file not found"
echo

echo "=== Neo4j Log Files ==="
echo "--- Neo4j debug log (last 20 lines) ---"
tail -20 /var/log/neo4j/debug.log 2>/dev/null || echo "Debug log not found"
echo
echo "--- Neo4j neo4j.log (last 20 lines) ---"
tail -20 /var/log/neo4j/neo4j.log 2>/dev/null || echo "Neo4j log not found"
echo

echo "=== Network Status ==="
echo "--- Listening ports ---"
netstat -tlnp | grep -E ":(7687|7474)"
echo
echo "--- All listening ports ---"
netstat -tlnp
echo

echo "=== Java Information ==="
java -version 2>&1
echo "JAVA_HOME: $JAVA_HOME"
which java
echo

echo "=== Neo4j Installation ==="
echo "--- Neo4j version ---"
neo4j version 2>/dev/null || echo "Neo4j command not found"
echo
echo "--- Neo4j files ---"
ls -la /var/lib/neo4j/ 2>/dev/null || echo "Neo4j data directory not found"
ls -la /etc/neo4j/ 2>/dev/null || echo "Neo4j config directory not found"
echo

echo "=== Process Information ==="
ps aux | grep -i neo4j
echo

echo "=== Disk Space ==="
df -h /var/lib/neo4j 2>/dev/null || echo "Neo4j data directory not found"
echo

echo "=== Recent System Logs ==="
journalctl --since "1 hour ago" --no-pager | tail -30
echo

echo "=== Manual Neo4j Start Attempt ==="
echo "Attempting to start Neo4j manually..."
systemctl stop neo4j 2>/dev/null || true
sleep 2
systemctl start neo4j
sleep 5
systemctl status neo4j --no-pager -l
echo

echo "=== Final Port Check ==="
netstat -tlnp | grep -E ":(7687|7474)" || echo "Neo4j ports not listening"
echo

echo "=== Diagnostics Complete ==="'

    # Send diagnostic command via SSM
    COMMAND_ID=$(aws ssm send-command \
        --region "$REGION" \
        --instance-ids "$INSTANCE_ID" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[\"$DIAGNOSTIC_SCRIPT\"]" \
        --query 'Command.CommandId' \
        --output text 2>/dev/null || echo "FAILED")
    
    if [ "$COMMAND_ID" = "FAILED" ]; then
        warn "Systems Manager command failed, trying alternative approaches..."
        return 1
    fi
    
    log "Systems Manager diagnostic command sent: $COMMAND_ID"
    log "Waiting for diagnostics to complete..."
    
    # Wait for command to complete
    sleep 45
    
    # Get command result
    log "Retrieving diagnostic results..."
    aws ssm get-command-invocation \
        --region "$REGION" \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --query 'StandardOutputContent' \
        --output text 2>/dev/null || {
        warn "Failed to retrieve SSM command output"
        return 1
    }
    
    return 0
}

# Try SSH access as fallback
try_ssh_diagnostics() {
    log "Attempting SSH diagnostics as fallback..."
    
    # Check if we have SSH key
    if [ ! -f "migration-key.pem" ]; then
        warn "SSH key migration-key.pem not found"
        log "To use SSH, you need to:"
        log "1. Download the migration-key.pem from AWS EC2 console"
        log "2. Place it in the current directory"
        log "3. Run: chmod 600 migration-key.pem"
        return 1
    fi
    
    log "Attempting SSH connection to $PUBLIC_IP..."
    
    # Test SSH connectivity first
    if ! ssh -i migration-key.pem -o ConnectTimeout=10 -o StrictHostKeyChecking=no ec2-user@"$PUBLIC_IP" "echo 'SSH connection successful'" 2>/dev/null; then
        warn "SSH connection failed"
        return 1
    fi
    
    log "SSH connection successful, running diagnostics..."
    
    # Run diagnostics via SSH
    ssh -i migration-key.pem -o StrictHostKeyChecking=no ec2-user@"$PUBLIC_IP" << 'EOF'
echo "=== Neo4j SSH Diagnostics ==="
echo "Timestamp: $(date)"
echo

echo "=== Neo4j Service Status ==="
sudo systemctl status neo4j --no-pager -l
echo

echo "=== Neo4j Service Logs ==="
sudo journalctl -u neo4j --no-pager -n 30
echo

echo "=== Neo4j Configuration ==="
sudo cat /etc/neo4j/neo4j.conf
echo

echo "=== Neo4j Logs ==="
sudo tail -20 /var/log/neo4j/neo4j.log 2>/dev/null || echo "Neo4j log not found"
echo

echo "=== Network Status ==="
sudo netstat -tlnp | grep -E ":(7687|7474)" || echo "Neo4j ports not listening"
echo

echo "=== Manual Start Attempt ==="
sudo systemctl stop neo4j
sleep 2
sudo systemctl start neo4j
sleep 5
sudo systemctl status neo4j --no-pager -l
echo

echo "=== Final Check ==="
sudo netstat -tlnp | grep -E ":(7687|7474)" || echo "Still not listening"
EOF
    
    return 0
}

# Provide manual diagnostic instructions
provide_manual_instructions() {
    log "Providing manual diagnostic instructions..."
    
    echo ""
    echo "🔧 Manual Neo4j Diagnostic Instructions:"
    echo "========================================"
    echo ""
    echo "Since automated diagnostics failed, please manually connect to the instance:"
    echo ""
    echo "1. Connect via AWS Systems Manager Session Manager:"
    echo "   aws ssm start-session --target $INSTANCE_ID --region $REGION"
    echo ""
    echo "2. Or connect via SSH (if you have the key):"
    echo "   ssh -i migration-key.pem ec2-user@$PUBLIC_IP"
    echo ""
    echo "3. Once connected, run these diagnostic commands:"
    echo ""
    echo "   # Check Neo4j service status"
    echo "   sudo systemctl status neo4j"
    echo ""
    echo "   # Check Neo4j logs"
    echo "   sudo journalctl -u neo4j -n 50"
    echo ""
    echo "   # Check Neo4j configuration"
    echo "   sudo cat /etc/neo4j/neo4j.conf"
    echo ""
    echo "   # Check if Neo4j log files exist"
    echo "   sudo ls -la /var/log/neo4j/"
    echo "   sudo tail -20 /var/log/neo4j/neo4j.log"
    echo ""
    echo "   # Check network ports"
    echo "   sudo netstat -tlnp | grep -E ':(7687|7474)'"
    echo ""
    echo "   # Try manual start"
    echo "   sudo systemctl stop neo4j"
    echo "   sudo systemctl start neo4j"
    echo "   sudo systemctl status neo4j"
    echo ""
    echo "   # Check Java"
    echo "   java -version"
    echo "   which java"
    echo ""
    echo "   # Check disk space"
    echo "   df -h"
    echo "   sudo ls -la /var/lib/neo4j/"
    echo ""
    echo "4. Common issues to check:"
    echo "   - Java not properly installed"
    echo "   - Neo4j configuration syntax errors"
    echo "   - Insufficient disk space"
    echo "   - Permission issues"
    echo "   - Port conflicts"
    echo ""
}

# Attempt to fix common issues
attempt_remote_fix() {
    log "Attempting to fix common Neo4j issues remotely..."
    
    # Create fix script
    FIX_SCRIPT='#!/bin/bash
echo "=== Neo4j Remote Fix Attempt ==="

# Stop Neo4j
systemctl stop neo4j

# Check Java installation
echo "Checking Java..."
java -version

# Verify Neo4j configuration
echo "Verifying Neo4j configuration..."
neo4j-admin check-config || echo "Config check failed"

# Check permissions
echo "Checking permissions..."
chown -R neo4j:neo4j /var/lib/neo4j/
chown -R neo4j:neo4j /var/log/neo4j/
chmod 755 /var/lib/neo4j/
chmod 755 /var/log/neo4j/

# Clear any lock files
echo "Clearing lock files..."
rm -f /var/lib/neo4j/data/databases/*/store_lock
rm -f /var/lib/neo4j/data/databases/*/neostore.id

# Try to start Neo4j
echo "Starting Neo4j..."
systemctl start neo4j

# Wait and check status
sleep 10
systemctl status neo4j

# Check ports
netstat -tlnp | grep -E ":(7687|7474)"

echo "=== Fix attempt complete ==="'

    # Send fix command via SSM
    COMMAND_ID=$(aws ssm send-command \
        --region "$REGION" \
        --instance-ids "$INSTANCE_ID" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[\"$FIX_SCRIPT\"]" \
        --query 'Command.CommandId' \
        --output text 2>/dev/null || echo "FAILED")
    
    if [ "$COMMAND_ID" = "FAILED" ]; then
        warn "Remote fix command failed"
        return 1
    fi
    
    log "Remote fix command sent: $COMMAND_ID"
    log "Waiting for fix to complete..."
    
    # Wait for command to complete
    sleep 30
    
    # Get command result
    log "Retrieving fix results..."
    aws ssm get-command-invocation \
        --region "$REGION" \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --query 'StandardOutputContent' \
        --output text 2>/dev/null || {
        warn "Failed to retrieve fix command output"
        return 1
    }
    
    return 0
}

# Test connectivity after diagnostics
test_connectivity_after_fix() {
    log "Testing Neo4j connectivity after diagnostics/fix..."
    
    for i in {1..5}; do
        log "Testing connectivity (attempt $i/5)..."
        
        if nc -z "$PRIVATE_IP" 7687 2>/dev/null; then
            log "✅ Neo4j Bolt port (7687) is now accessible!"
            
            # Test actual connection
            if python scripts/test-neo4j-connectivity.py; then
                log "🎉 Neo4j database connection successful!"
                return 0
            fi
        fi
        
        if [ $i -lt 5 ]; then
            log "Not ready yet, waiting 10 seconds..."
            sleep 10
        fi
    done
    
    warn "Neo4j is still not accessible after diagnostics"
    return 1
}

# Main execution
main() {
    log "🔍 Starting Neo4j SSH diagnostics..."
    
    # Check prerequisites
    if ! command -v aws >/dev/null 2>&1; then
        error "AWS CLI is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v jq >/dev/null 2>&1; then
        error "jq is not installed or not in PATH"
        exit 1
    fi
    
    # Get instance information
    get_instance_info
    
    # Try different diagnostic approaches
    if run_ssm_diagnostics; then
        log "✅ SSM diagnostics completed successfully"
    elif try_ssh_diagnostics; then
        log "✅ SSH diagnostics completed successfully"
    else
        warn "Automated diagnostics failed, providing manual instructions"
        provide_manual_instructions
        
        # Ask user if they want to try remote fix
        echo ""
        read -p "Would you like to attempt an automated remote fix? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if attempt_remote_fix; then
                log "Remote fix attempt completed"
            else
                warn "Remote fix failed"
            fi
        fi
    fi
    
    # Test connectivity after diagnostics
    echo ""
    log "Testing connectivity after diagnostics..."
    if test_connectivity_after_fix; then
        log "🎉 Neo4j diagnostics and fix successful!"
    else
        log "Neo4j still needs manual intervention"
        provide_manual_instructions
    fi
    
    log ""
    log "📋 Next Steps:"
    log "  1. Review diagnostic output above"
    log "  2. If Neo4j is working: python scripts/test-neo4j-connectivity.py"
    log "  3. If still broken: Follow manual diagnostic instructions"
    log "  4. Common fixes: restart service, check permissions, verify Java"
}

# Run main function
main "$@"