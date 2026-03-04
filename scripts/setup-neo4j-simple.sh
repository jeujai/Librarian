#!/bin/bash
"""
Simple Neo4j EC2 Instance Setup Script

This script creates a minimal Neo4j instance with better error handling.
"""

set -e

# Configuration
INSTANCE_TYPE="t3.medium"
KEY_NAME="migration-key"
SECURITY_GROUP_NAME="neo4j-security-group-simple"
VOLUME_SIZE=30
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

# Get VPC and subnet information
get_vpc_info() {
    log "Getting VPC information..."
    
    # Use the same VPC as the existing Neo4j instance
    VPC_ID="vpc-0bc85162dcdbcc986"
    SUBNET_ID="subnet-043a481c9298b710d"
    
    log "Using VPC: $VPC_ID"
    log "Using Subnet: $SUBNET_ID"
}

# Create or get security group
create_security_group() {
    log "Setting up security group..."
    
    # Check if security group already exists
    EXISTING_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")
    
    if [ "$EXISTING_SG" != "None" ] && [ -n "$EXISTING_SG" ]; then
        log "Using existing security group: $EXISTING_SG"
        SECURITY_GROUP_ID="$EXISTING_SG"
    else
        # Create new security group
        SECURITY_GROUP_ID=$(aws ec2 create-security-group \
            --group-name "$SECURITY_GROUP_NAME" \
            --description "Simple security group for Neo4j database" \
            --vpc-id "$VPC_ID" \
            --query 'GroupId' --output text)
        
        log "Created security group: $SECURITY_GROUP_ID"
        
        # Add rules for Neo4j ports from ECS security group
        ECS_SG="sg-07efd393129cae5d7"  # The actual ECS security group we found
        
        aws ec2 authorize-security-group-ingress \
            --group-id "$SECURITY_GROUP_ID" \
            --protocol tcp \
            --port 7687 \
            --source-group "$ECS_SG"
        
        aws ec2 authorize-security-group-ingress \
            --group-id "$SECURITY_GROUP_ID" \
            --protocol tcp \
            --port 7474 \
            --source-group "$ECS_SG"
        
        # Also add SSH access for debugging (optional)
        aws ec2 authorize-security-group-ingress \
            --group-id "$SECURITY_GROUP_ID" \
            --protocol tcp \
            --port 22 \
            --cidr "0.0.0.0/0" || true
        
        log "Added ingress rules for ECS security group: $ECS_SG"
    fi
}

# Launch Neo4j EC2 instance
launch_instance() {
    log "Launching simple Neo4j EC2 instance..."
    
    # Get latest Amazon Linux 2023 AMI
    AMI_ID=$(aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-x86_64" "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text)
    
    log "Using AMI: $AMI_ID"
    
    # Create simplified user data script
    USER_DATA=$(cat << 'EOF'
#!/bin/bash
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "Starting Neo4j installation at $(date)"

# Update system
yum update -y

# Install Java 17
yum install -y java-17-amazon-corretto

# Verify Java installation
java -version

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
echo "Installing Neo4j..."
yum install -y neo4j-5.15.0

# Create basic Neo4j configuration
echo "Configuring Neo4j..."
cat << 'CONFIG' > /etc/neo4j/neo4j.conf
# Network settings
server.default_listen_address=0.0.0.0
server.bolt.listen_address=0.0.0.0:7687
server.http.listen_address=0.0.0.0:7474

# Memory settings for t3.medium (4GB RAM)
server.memory.heap.initial_size=512M
server.memory.heap.max_size=1G
server.memory.pagecache.size=512M

# Security settings
dbms.security.auth_enabled=true

# Logging
server.logs.user.stdout_enabled=true
server.logs.debug.level=INFO
CONFIG

# Set initial password
echo "Setting initial password..."
neo4j-admin dbms set-initial-password temppassword123

# Set proper ownership
chown -R neo4j:neo4j /var/lib/neo4j
chown -R neo4j:neo4j /var/log/neo4j
chown -R neo4j:neo4j /etc/neo4j

# Enable and start Neo4j
echo "Starting Neo4j service..."
systemctl enable neo4j
systemctl start neo4j

# Wait for Neo4j to start
echo "Waiting for Neo4j to start..."
sleep 30

# Check Neo4j status
systemctl status neo4j

# Test if Neo4j is responding
echo "Testing Neo4j connectivity..."
for i in {1..10}; do
    if nc -z localhost 7687; then
        echo "Neo4j is responding on port 7687"
        break
    else
        echo "Waiting for Neo4j to respond... attempt $i"
        sleep 10
    fi
done

# Create status file
echo "Neo4j installation completed at $(date)" > /var/log/neo4j-setup-complete.log
echo "Neo4j status: $(systemctl is-active neo4j)" >> /var/log/neo4j-setup-complete.log

echo "User data script completed at $(date)"
EOF
)
    
    # Launch the instance
    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --count 1 \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SECURITY_GROUP_ID" \
        --subnet-id "$SUBNET_ID" \
        --user-data "$USER_DATA" \
        --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":$VOLUME_SIZE,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=neo4j-simple-multimodal-librarian},{Key=Project,Value=multimodal-librarian},{Key=Component,Value=neo4j-simple}]" \
        --query 'Instances[0].InstanceId' \
        --output text)
    
    if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
        error "Failed to launch EC2 instance"
        exit 1
    fi
    
    log "Launched simple Neo4j instance: $INSTANCE_ID"
    
    # Wait for instance to be running
    log "Waiting for instance to be running..."
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
    
    # Get instance details
    INSTANCE_INFO=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0]')
    PUBLIC_IP=$(echo "$INSTANCE_INFO" | jq -r '.PublicIpAddress')
    PRIVATE_IP=$(echo "$INSTANCE_INFO" | jq -r '.PrivateIpAddress')
    
    log "Instance is running!"
    log "Public IP: $PUBLIC_IP"
    log "Private IP: $PRIVATE_IP"
    
    # Save instance information
    cat > neo4j-simple-instance-info.json << EOF
{
  "instance_id": "$INSTANCE_ID",
  "public_ip": "$PUBLIC_IP",
  "private_ip": "$PRIVATE_IP",
  "security_group_id": "$SECURITY_GROUP_ID",
  "vpc_id": "$VPC_ID",
  "subnet_id": "$SUBNET_ID",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    
    log "Instance information saved to neo4j-simple-instance-info.json"
}

# Update Neo4j secret with new instance details
update_secret() {
    log "Updating Neo4j secret with new instance details..."
    
    # Get current secret
    CURRENT_SECRET=$(aws secretsmanager get-secret-value --secret-id "multimodal-librarian/full-ml/neo4j" --query 'SecretString' --output text)
    
    # Update with new instance IP
    UPDATED_SECRET=$(echo "$CURRENT_SECRET" | jq --arg host "$PRIVATE_IP" '.host = $host')
    
    # Update the secret
    aws secretsmanager update-secret \
        --secret-id "multimodal-librarian/full-ml/neo4j" \
        --secret-string "$UPDATED_SECRET"
    
    log "Updated Neo4j secret with host: $PRIVATE_IP"
}

# Main execution
main() {
    log "🚀 Starting simple Neo4j EC2 instance setup..."
    
    # Check prerequisites
    if ! command -v aws >/dev/null 2>&1; then
        error "AWS CLI is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v jq >/dev/null 2>&1; then
        error "jq is not installed or not in PATH"
        exit 1
    fi
    
    # Execute setup steps
    get_vpc_info
    create_security_group
    launch_instance
    update_secret
    
    log "🎉 Simple Neo4j EC2 instance setup completed successfully!"
    log ""
    log "📋 Summary:"
    log "  Instance ID: $INSTANCE_ID"
    log "  Private IP: $PRIVATE_IP"
    log "  Public IP: $PUBLIC_IP"
    log "  Security Group: $SECURITY_GROUP_ID"
    log ""
    log "📁 Instance details saved to: neo4j-simple-instance-info.json"
    log "🔐 Neo4j secret updated with host information"
    log ""
    log "⏳ Note: Neo4j installation will take 5-10 minutes."
    log "   You can monitor progress by checking the instance logs."
    log ""
    log "🔗 Next steps:"
    log "  1. Wait for Neo4j to fully start (10-15 minutes)"
    log "  2. Test connectivity using the test script"
    log "  3. Enable knowledge graph feature in the application"
}

# Run main function
main "$@"