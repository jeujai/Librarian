#!/bin/bash
"""
Reliable Neo4j EC2 Instance Setup Script

This script creates a Neo4j instance with improved error handling and monitoring.
"""

set -e

# Configuration
INSTANCE_TYPE="t3.medium"
KEY_NAME="migration-key"
SECURITY_GROUP_NAME="neo4j-security-group"
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
    
    # Use the existing VPC from the previous instance info if available
    if [ -f "neo4j-instance-info.json" ]; then
        VPC_ID=$(jq -r '.vpc_id' neo4j-instance-info.json)
        SUBNET_ID=$(jq -r '.subnet_id' neo4j-instance-info.json)
        log "Using VPC from previous instance: $VPC_ID"
        log "Using Subnet from previous instance: $SUBNET_ID"
    else
        # Fallback to discovery
        VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=false" --query 'Vpcs[0].VpcId' --output text)
        SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" "Name=map-public-ip-on-launch,Values=true" --query 'Subnets[0].SubnetId' --output text)
        log "Discovered VPC: $VPC_ID"
        log "Discovered Subnet: $SUBNET_ID"
    fi
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
            --description "Security group for Neo4j database" \
            --vpc-id "$VPC_ID" \
            --query 'GroupId' --output text)
        
        log "Created security group: $SECURITY_GROUP_ID"
        
        # Add rules for Neo4j ports from VPC CIDR
        VPC_CIDR=$(aws ec2 describe-vpcs --vpc-ids "$VPC_ID" --query 'Vpcs[0].CidrBlock' --output text)
        
        aws ec2 authorize-security-group-ingress \
            --group-id "$SECURITY_GROUP_ID" \
            --protocol tcp \
            --port 7687 \
            --cidr "$VPC_CIDR"
        
        aws ec2 authorize-security-group-ingress \
            --group-id "$SECURITY_GROUP_ID" \
            --protocol tcp \
            --port 7474 \
            --cidr "$VPC_CIDR"
        
        # Add SSH access for debugging
        aws ec2 authorize-security-group-ingress \
            --group-id "$SECURITY_GROUP_ID" \
            --protocol tcp \
            --port 22 \
            --cidr "0.0.0.0/0"
        
        log "Added security group rules for VPC CIDR: $VPC_CIDR"
    fi
}

# Launch Neo4j instance with improved user data
launch_instance() {
    log "Launching Neo4j EC2 instance..."
    
    # Get latest Amazon Linux 2023 AMI
    AMI_ID=$(aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-x86_64" "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text)
    
    log "Using AMI: $AMI_ID"
    
    # Create comprehensive user data script
    USER_DATA=$(cat << 'EOF'
#!/bin/bash
exec > >(tee /var/log/user-data.log) 2>&1
echo "Starting Neo4j installation at $(date)"

# Update system
yum update -y

# Install required packages
yum install -y java-17-amazon-corretto wget curl netcat

# Verify Java installation
java -version
echo "JAVA_HOME: $JAVA_HOME"

# Add Neo4j repository
echo "Adding Neo4j repository..."
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

# Create Neo4j configuration
echo "Configuring Neo4j..."
cat << 'CONFIG' > /etc/neo4j/neo4j.conf
# Network configuration
server.default_listen_address=0.0.0.0
server.bolt.listen_address=0.0.0.0:7687
server.http.listen_address=0.0.0.0:7474

# Memory settings for t3.medium (4GB RAM)
server.memory.heap.initial_size=1G
server.memory.heap.max_size=1G
server.memory.pagecache.size=512M

# Security settings
dbms.security.auth_enabled=true

# Logging
server.logs.user.stdout_enabled=true
server.logs.debug.level=INFO

# Database settings
dbms.default_database=neo4j
CONFIG

# Set permissions
chown -R neo4j:neo4j /var/lib/neo4j
chown -R neo4j:neo4j /var/log/neo4j
chown -R neo4j:neo4j /etc/neo4j

# Set initial password
echo "Setting initial password..."
sudo -u neo4j neo4j-admin dbms set-initial-password temppassword123

# Enable and start Neo4j
echo "Starting Neo4j service..."
systemctl enable neo4j
systemctl start neo4j

# Wait and check status
sleep 10
systemctl status neo4j

# Wait for Neo4j to be ready
echo "Waiting for Neo4j to be ready..."
for i in {1..30}; do
    if netstat -tlnp | grep -q ":7687"; then
        echo "Neo4j Bolt port is listening!"
        break
    fi
    echo "Waiting for Neo4j... attempt $i/30"
    sleep 10
done

# Final status check
echo "Final status check at $(date):"
systemctl status neo4j
netstat -tlnp | grep -E ":(7687|7474)"
ps aux | grep neo4j

echo "Neo4j installation completed at $(date)"
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
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=neo4j-multimodal-librarian-v2},{Key=Project,Value=multimodal-librarian},{Key=Component,Value=neo4j}]" \
        --query 'Instances[0].InstanceId' \
        --output text)
    
    if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
        error "Failed to launch EC2 instance"
        exit 1
    fi
    
    log "Launched Neo4j instance: $INSTANCE_ID"
    
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
    cat > neo4j-instance-info.json << EOF
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
    
    log "Instance information saved to neo4j-instance-info.json"
}

# Update Neo4j secret
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

# Monitor Neo4j startup
monitor_startup() {
    log "Monitoring Neo4j startup progress..."
    
    for i in {1..20}; do
        log "Startup check $i/20..."
        
        # Test port connectivity
        if nc -z "$PRIVATE_IP" 7687 2>/dev/null; then
            log "✅ Neo4j Bolt port (7687) is accessible!"
            
            # Test actual connection
            if python3 scripts/test-neo4j-connectivity.py 2>/dev/null; then
                log "🎉 Neo4j database connection successful!"
                return 0
            fi
        fi
        
        if [ $i -lt 20 ]; then
            log "Neo4j not ready yet, waiting 30 seconds..."
            sleep 30
        fi
    done
    
    warn "Neo4j startup monitoring completed, but service may still be initializing"
    log "You can check the status manually with:"
    log "  aws ssm start-session --target $INSTANCE_ID --region $REGION"
    log "  sudo tail -f /var/log/user-data.log"
    log "  sudo systemctl status neo4j"
}

# Main execution
main() {
    log "🚀 Creating reliable Neo4j EC2 instance..."
    
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
    monitor_startup
    
    log "🎉 Neo4j EC2 instance setup completed!"
    log ""
    log "📋 Summary:"
    log "  Instance ID: $INSTANCE_ID"
    log "  Private IP: $PRIVATE_IP"
    log "  Public IP: $PUBLIC_IP"
    log "  Security Group: $SECURITY_GROUP_ID"
    log ""
    log "📁 Instance details saved to: neo4j-instance-info.json"
    log "🔐 Neo4j secret updated with host information"
    log ""
    log "🔗 Next steps:"
    log "  1. Test Neo4j connectivity: python3 scripts/test-neo4j-connectivity.py"
    log "  2. Test application integration: curl http://localhost:8000/test/neo4j"
    log "  3. Deploy updated application to AWS ECS"
}

# Run main function
main "$@"