#!/bin/bash
"""
Fix Neo4j Configuration Script

This script fixes the Neo4j configuration on the running instance by removing
invalid settings and restarting the service.
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

# Fix Neo4j configuration via Systems Manager
fix_config_via_ssm() {
    log "Attempting to fix Neo4j configuration via Systems Manager..."
    
    # Create a corrected Neo4j configuration
    FIXED_CONFIG='# Basic configuration
server.default_listen_address=0.0.0.0
server.bolt.listen_address=0.0.0.0:7687
server.http.listen_address=0.0.0.0:7474

# Memory settings for t3.medium (4GB RAM)
server.memory.heap.initial_size=1G
server.memory.heap.max_size=2G
server.memory.pagecache.size=1G

# Security settings
dbms.security.auth_enabled=true
dbms.security.procedures.unrestricted=jwt.*

# Logging (corrected settings for Neo4j 5.x)
server.logs.debug.level=INFO
server.logs.gc.enabled=true'

    # Try to run command via Systems Manager
    COMMAND_ID=$(aws ssm send-command \
        --region "$REGION" \
        --instance-ids "$INSTANCE_ID" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[
            'echo \"Fixing Neo4j configuration...\"',
            'sudo systemctl stop neo4j || true',
            'sudo cp /etc/neo4j/neo4j.conf /etc/neo4j/neo4j.conf.backup',
            'cat << \"EOF\" | sudo tee /etc/neo4j/neo4j.conf
$FIXED_CONFIG
EOF',
            'echo \"Configuration updated, restarting Neo4j...\"',
            'sudo systemctl start neo4j',
            'sleep 10',
            'sudo systemctl status neo4j',
            'echo \"Neo4j configuration fix completed\"'
        ]" \
        --query 'Command.CommandId' \
        --output text 2>/dev/null || echo "FAILED")
    
    if [ "$COMMAND_ID" = "FAILED" ]; then
        warn "Systems Manager command failed, will provide manual instructions"
        return 1
    fi
    
    log "Systems Manager command sent: $COMMAND_ID"
    log "Waiting for command to complete..."
    
    # Wait for command to complete
    sleep 30
    
    # Get command result
    COMMAND_STATUS=$(aws ssm get-command-invocation \
        --region "$REGION" \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --query 'Status' \
        --output text 2>/dev/null || echo "Unknown")
    
    if [ "$COMMAND_STATUS" = "Success" ]; then
        log "✅ Neo4j configuration fixed successfully via Systems Manager"
        return 0
    else
        warn "Systems Manager command status: $COMMAND_STATUS"
        return 1
    fi
}

# Provide manual fix instructions
provide_manual_instructions() {
    log "Providing manual fix instructions..."
    
    echo ""
    echo "🛠️  Manual Neo4j Configuration Fix Instructions:"
    echo "=============================================="
    echo ""
    echo "1. SSH to the Neo4j instance:"
    echo "   ssh -i migration-key.pem ec2-user@$PUBLIC_IP"
    echo ""
    echo "2. Stop Neo4j service:"
    echo "   sudo systemctl stop neo4j"
    echo ""
    echo "3. Backup current configuration:"
    echo "   sudo cp /etc/neo4j/neo4j.conf /etc/neo4j/neo4j.conf.backup"
    echo ""
    echo "4. Create corrected configuration:"
    echo "   sudo tee /etc/neo4j/neo4j.conf << 'EOF'"
    echo "# Basic configuration"
    echo "server.default_listen_address=0.0.0.0"
    echo "server.bolt.listen_address=0.0.0.0:7687"
    echo "server.http.listen_address=0.0.0.0:7474"
    echo ""
    echo "# Memory settings for t3.medium (4GB RAM)"
    echo "server.memory.heap.initial_size=1G"
    echo "server.memory.heap.max_size=2G"
    echo "server.memory.pagecache.size=1G"
    echo ""
    echo "# Security settings"
    echo "dbms.security.auth_enabled=true"
    echo "dbms.security.procedures.unrestricted=jwt.*"
    echo ""
    echo "# Logging (corrected settings for Neo4j 5.x)"
    echo "server.logs.debug.level=INFO"
    echo "server.logs.gc.enabled=true"
    echo "EOF"
    echo ""
    echo "5. Start Neo4j service:"
    echo "   sudo systemctl start neo4j"
    echo ""
    echo "6. Check Neo4j status:"
    echo "   sudo systemctl status neo4j"
    echo "   sudo journalctl -u neo4j -f"
    echo ""
    echo "7. Test connectivity:"
    echo "   sudo netstat -tlnp | grep :7687"
    echo "   sudo netstat -tlnp | grep :7474"
    echo ""
}

# Test Neo4j connectivity after fix
test_connectivity() {
    log "Testing Neo4j connectivity..."
    
    # Wait for Neo4j to start
    log "Waiting for Neo4j to start..."
    sleep 30
    
    # Test ports
    for i in {1..12}; do
        log "Testing connectivity (attempt $i/12)..."
        
        if nc -z "$PRIVATE_IP" 7687 2>/dev/null; then
            log "✅ Neo4j Bolt port (7687) is accessible"
            BOLT_OK=true
        else
            BOLT_OK=false
        fi
        
        if nc -z "$PRIVATE_IP" 7474 2>/dev/null; then
            log "✅ Neo4j HTTP port (7474) is accessible"
            HTTP_OK=true
        else
            HTTP_OK=false
        fi
        
        if [ "$BOLT_OK" = true ] && [ "$HTTP_OK" = true ]; then
            log "🎉 Neo4j is now accessible on both ports!"
            return 0
        fi
        
        if [ $i -lt 12 ]; then
            log "Ports not ready yet, waiting 10 seconds..."
            sleep 10
        fi
    done
    
    warn "Neo4j ports are still not accessible after 2 minutes"
    return 1
}

# Main execution
main() {
    log "🔧 Starting Neo4j configuration fix..."
    
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
    
    # Try to fix via Systems Manager first
    if fix_config_via_ssm; then
        log "Configuration fixed via Systems Manager"
        
        # Test connectivity
        if test_connectivity; then
            log "🎉 Neo4j configuration fix completed successfully!"
            log "Neo4j is now ready for use."
        else
            warn "Configuration was fixed but connectivity test failed"
            log "Neo4j may need more time to start up"
        fi
    else
        log "Systems Manager fix failed, providing manual instructions"
        provide_manual_instructions
    fi
    
    log ""
    log "📋 Next Steps:"
    log "  1. Verify Neo4j is running: python scripts/test-neo4j-connectivity.py"
    log "  2. Test from application: curl http://your-app/test/neo4j"
    log "  3. If still not working, follow the manual instructions above"
}

# Run main function
main "$@"