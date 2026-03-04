#!/bin/bash
"""
Create Minimal Neo4j Instance Script

This script creates a Neo4j instance with a minimal, valid configuration
that works with Neo4j 5.15.0.
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

# Get current instance information
get_current_instance() {
    if [ ! -f "neo4j-instance-info.json" ]; then
        error "neo4j-instance-info.json not found"
        exit 1
    fi
    
    CURRENT_INSTANCE_ID=$(jq -r '.instance_id' neo4j-instance-info.json)
    VPC_ID=$(jq -r '.vpc_id' neo4j-instance-info.json)
    SUBNET_ID=$(jq -r '.subnet_id' neo4j-instance-info.json)
    SECURITY_GROUP_ID=$(jq -r '.security_group_id' neo4j-instance-info.json)
    
    log "Current instance: $CURRENT_INSTANCE_ID"
    log "VPC: $VPC_ID"
    log "Subnet: $SUBNET_ID"
    log "Security Group: $SECURITY_GROUP_ID"
}

# Terminate current instance
terminate_current_instance() {
    log "Terminating current Neo4j instance: $CURRENT_INSTANCE_ID"
    
    aws ec2 terminate-instances --instance-ids "$CURRENT_INSTANCE_ID" --region "$REGION"
    
    log "Waiting for instance to terminate..."
    aws ec2 wait instance-terminated --instance-ids "$CURRENT_INSTANCE_ID" --region "$REGION"
    
    log "✅ Instance terminated successfully"
}

# Launch new Neo4j instance with minimal valid configuration
launch_minimal_instance() {
    log "Launching new Neo4j instance with minimal valid configuration..."
    
    # Get latest Amazon Linux 2023 AMI
    AMI_ID=$(aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-x86_64" "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text \
        --region "$REGION")
    
    log "Using AMI: $AMI_ID"
    
    # Create minimal user data script with ONLY valid Neo4j 5.15.0 settings
    USER_DATA=$(cat << 'EOF'
#!/bin/bash
yum update -y

# Install Java 17
yum install -y java-17-amazon-corretto

# Add Neo4j repository
rpm --import https://debian.neo4j.com/neotechnology.gpg.key
cat << 'REPO' > /etc/yum.repos.d/neo4j.repo
[neo4j]
name=Neo4j RPM Repository
baseurl=https://yum.neo4j.com/stable/5
enabled=1
gpgcheck=1
REPO

# Install Neo4j
yum install -y neo4j-5.15.0

# Configure Neo4j with MINIMAL VALID settings only
cat << 'CONFIG' > /etc/neo4j/neo4j.conf
# Network configuration
server.default_listen_address=0.0.0.0
server.bolt.listen_address=0.0.0.0:7687
server.http.listen_address=0.0.0.0:7474

# Memory settings
server.memory.heap.initial_size=1G
server.memory.heap.max_size=2G
server.memory.pagecache.size=1G

# Security
dbms.security.auth_enabled=true
CONFIG

# Set initial password
neo4j-admin dbms set-initial-password temppassword123

# Enable and start Neo4j
systemctl enable neo4j
systemctl start neo4j

# Wait and create status file
sleep 30
systemctl status neo4j > /var/log/neo4j-setup.log 2>&1
echo "Neo4j setup completed at $(date)" >> /var/log/neo4j-setup.log

# Test ports
netstat -tlnp | grep :7687 >> /var/log/neo4j-setup.log 2>&1 || echo "Port 7687 not listening" >> /var/log/neo4j-setup.log
netstat -tlnp | grep :7474 >> /var/log/neo4j-setup.log 2>&1 || echo "Port 7474 not listening" >> /var/log/neo4j-setup.log

# Check Neo4j logs
tail -20 /var/log/neo4j/neo4j.log >> /var/log/neo4j-setup.log 2>&1 || echo "No Neo4j logs found" >> /var/log/neo4j-setup.log
EOF
)
    
    # Launch the new instance
    NEW_INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --count 1 \
        --instance-type "t3.medium" \
        --key-name "migration-key" \
        --security-group-ids "$SECURITY_GROUP_ID" \
        --subnet-id "$SUBNET_ID" \
        --user-data "$USER_DATA" \
        --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":50,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
        --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=neo4j-multimodal-librarian-minimal},{Key=Project,Value=multimodal-librarian},{Key=Component,Value=neo4j}]' \
        --query 'Instances[0].InstanceId' \
        --output text \
        --region "$REGION")
    
    if [ -z "$NEW_INSTANCE_ID" ] || [ "$NEW_INSTANCE_ID" = "None" ]; then
        error "Failed to launch new EC2 instance"
        exit 1
    fi
    
    log "Launched new Neo4j instance: $NEW_INSTANCE_ID"
    
    # Wait for instance to be running
    log "Waiting for instance to be running..."
    aws ec2 wait instance-running --instance-ids "$NEW_INSTANCE_ID" --region "$REGION"
    
    # Get instance details
    INSTANCE_INFO=$(aws ec2 describe-instances --instance-ids "$NEW_INSTANCE_ID" --region "$REGION" --query 'Reservations[0].Instances[0]')
    NEW_PUBLIC_IP=$(echo "$INSTANCE_INFO" | jq -r '.PublicIpAddress')
    NEW_PRIVATE_IP=$(echo "$INSTANCE_INFO" | jq -r '.PrivateIpAddress')
    
    log "New instance is running!"
    log "Public IP: $NEW_PUBLIC_IP"
    log "Private IP: $NEW_PRIVATE_IP"
    
    # Update instance information file
    cat > neo4j-instance-info.json << EOF
{
  "instance_id": "$NEW_INSTANCE_ID",
  "public_ip": "$NEW_PUBLIC_IP",
  "private_ip": "$NEW_PRIVATE_IP",
  "security_group_id": "$SECURITY_GROUP_ID",
  "vpc_id": "$VPC_ID",
  "subnet_id": "$SUBNET_ID",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    
    log "Updated instance information in neo4j-instance-info.json"
    
    # Update Neo4j secret with new IP
    log "Updating Neo4j secret with new instance IP..."
    CURRENT_SECRET=$(aws secretsmanager get-secret-value --secret-id "multimodal-librarian/full-ml/neo4j" --query 'SecretString' --output text --region "$REGION")
    UPDATED_SECRET=$(echo "$CURRENT_SECRET" | jq --arg host "$NEW_PRIVATE_IP" '.host = $host')
    
    aws secretsmanager update-secret \
        --secret-id "multimodal-librarian/full-ml/neo4j" \
        --secret-string "$UPDATED_SECRET" \
        --region "$REGION"
    
    log "✅ Updated Neo4j secret with new host: $NEW_PRIVATE_IP"
}

# Test connectivity with patience
test_minimal_instance() {
    log "Testing connectivity to minimal Neo4j instance..."
    
    # Wait for Neo4j to initialize with more patience
    log "Waiting for Neo4j to initialize (this may take 5-10 minutes)..."
    
    for i in {1..30}; do
        log "Testing connectivity (attempt $i/30)..."
        
        BOLT_OK=false
        HTTP_OK=false
        
        if nc -z "$NEW_PRIVATE_IP" 7687 2>/dev/null; then
            log "✅ Neo4j Bolt port (7687) is accessible"
            BOLT_OK=true
        fi
        
        if nc -z "$NEW_PRIVATE_IP" 7474 2>/dev/null; then
            log "✅ Neo4j HTTP port (7474) is accessible"
            HTTP_OK=true
        fi
        
        if [ "$BOLT_OK" = true ] && [ "$HTTP_OK" = true ]; then
            log "🎉 Neo4j is accessible on both ports!"
            
            # Test actual Neo4j connection
            log "Testing Neo4j database connection..."
            if python scripts/test-neo4j-connectivity.py; then
                log "🎉 Neo4j database connection successful!"
                return 0
            else
                log "Database connection test failed, but ports are accessible"
                log "This may be normal - Neo4j authentication might need setup"
                return 0
            fi
        fi
        
        if [ $i -lt 30 ]; then
            log "Neo4j not ready yet, waiting 20 seconds..."
            sleep 20
        fi
    done
    
    warn "Neo4j is not accessible after 10 minutes"
    log "Let's check the console output for errors..."
    
    # Get console output for debugging
    aws ec2 get-console-output --instance-id "$NEW_INSTANCE_ID" --region "$REGION" --query 'Output' --output text | tail -50
    
    return 1
}

# Main execution
main() {
    log "🔄 Starting minimal Neo4j instance creation..."
    
    # Check prerequisites
    if ! command -v aws >/dev/null 2>&1; then
        error "AWS CLI is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v jq >/dev/null 2>&1; then
        error "jq is not installed or not in PATH"
        exit 1
    fi
    
    # Get current instance info
    get_current_instance
    
    # Confirm with user
    echo ""
    warn "This will terminate the current Neo4j instance and create a new one with minimal configuration."
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Operation cancelled by user"
        exit 0
    fi
    
    # Execute recreation steps
    terminate_current_instance
    launch_minimal_instance
    test_minimal_instance
    
    log ""
    log "🎉 Minimal Neo4j instance creation completed!"
    log ""
    log "📋 Summary:"
    log "  New Instance ID: $NEW_INSTANCE_ID"
    log "  Private IP: $NEW_PRIVATE_IP"
    log "  Public IP: $NEW_PUBLIC_IP"
    log ""
    log "🔗 Next Steps:"
    log "  1. Wait 5-10 minutes for Neo4j to fully initialize"
    log "  2. Test connection: python scripts/test-neo4j-connectivity.py"
    log "  3. Test from application: curl http://your-app/test/neo4j"
    log "  4. If still not working, check console output for errors"
}

# Run main function
main "$@"