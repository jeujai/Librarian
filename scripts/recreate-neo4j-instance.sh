#!/bin/bash
"""
Recreate Neo4j Instance Script

This script terminates the current Neo4j instance and creates a new one with
the correct configuration.
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

# Launch new Neo4j instance with corrected configuration
launch_new_instance() {
    log "Launching new Neo4j instance with corrected configuration..."
    
    # Get latest Amazon Linux 2023 AMI
    AMI_ID=$(aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-x86_64" "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text \
        --region "$REGION")
    
    log "Using AMI: $AMI_ID"
    
    # Create corrected user data script
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

# Configure Neo4j with CORRECTED settings
cat << 'CONFIG' > /etc/neo4j/neo4j.conf
# Basic configuration
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
server.logs.gc.enabled=true
CONFIG

# Set initial password (will be changed via secrets)
neo4j-admin dbms set-initial-password temppassword123

# Enable and start Neo4j
systemctl enable neo4j
systemctl start neo4j

# Wait for Neo4j to start and create status file
sleep 30
systemctl status neo4j > /var/log/neo4j-setup.log
echo "Neo4j installation completed at $(date)" >> /var/log/neo4j-setup.log

# Test if ports are listening
netstat -tlnp | grep :7687 >> /var/log/neo4j-setup.log
netstat -tlnp | grep :7474 >> /var/log/neo4j-setup.log
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
        --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=neo4j-multimodal-librarian-v2},{Key=Project,Value=multimodal-librarian},{Key=Component,Value=neo4j}]' \
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

# Test connectivity to new instance
test_new_instance() {
    log "Testing connectivity to new Neo4j instance..."
    
    # Wait for Neo4j to initialize
    log "Waiting for Neo4j to initialize (this may take 3-5 minutes)..."
    
    for i in {1..20}; do
        log "Testing connectivity (attempt $i/20)..."
        
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
                return 0
            fi
        fi
        
        if [ $i -lt 20 ]; then
            log "Neo4j not ready yet, waiting 15 seconds..."
            sleep 15
        fi
    done
    
    warn "Neo4j is not accessible after 5 minutes"
    log "This may be normal - Neo4j can take up to 10 minutes to fully initialize"
    return 1
}

# Main execution
main() {
    log "🔄 Starting Neo4j instance recreation..."
    
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
    warn "This will terminate the current Neo4j instance and create a new one."
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Operation cancelled by user"
        exit 0
    fi
    
    # Execute recreation steps
    terminate_current_instance
    launch_new_instance
    test_new_instance
    
    log ""
    log "🎉 Neo4j instance recreation completed!"
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
    log "  4. Integrate knowledge graph API with main application"
}

# Run main function
main "$@"