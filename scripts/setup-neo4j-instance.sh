#!/bin/bash
"""
Neo4j EC2 Instance Setup Script

This script creates and configures a Neo4j instance for the multimodal-librarian system.
"""

set -e

# Configuration
INSTANCE_TYPE="t3.medium"
NEO4J_VERSION="5.15.0"
KEY_NAME="migration-key"  # Update with your key pair name
SECURITY_GROUP_NAME="neo4j-security-group"
VOLUME_SIZE=50
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

# Get VPC and subnet information from existing ECS cluster
get_vpc_info() {
    log "Getting VPC information from existing ECS cluster..."
    
    # Get the ECS cluster's VPC
    CLUSTER_ARN=$(aws ecs describe-clusters --clusters multimodal-librarian-full-ml --query 'clusters[0].clusterArn' --output text)
    
    if [ "$CLUSTER_ARN" = "None" ] || [ -z "$CLUSTER_ARN" ]; then
        error "Could not find ECS cluster multimodal-librarian-full-ml"
        exit 1
    fi
    
    # Get VPC ID from the load balancer (since ECS tasks use it)
    VPC_ID=$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?contains(LoadBalancerName, `multimodal-librarian-full-ml`)].VpcId' --output text)
    
    if [ -z "$VPC_ID" ] || [ "$VPC_ID" = "None" ]; then
        error "Could not determine VPC ID from load balancer"
        exit 1
    fi
    
    # Get a public subnet in the VPC
    SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" "Name=map-public-ip-on-launch,Values=true" --query 'Subnets[0].SubnetId' --output text)
    
    if [ -z "$SUBNET_ID" ] || [ "$SUBNET_ID" = "None" ]; then
        error "Could not find a public subnet in VPC $VPC_ID"
        exit 1
    fi
    
    log "Using VPC: $VPC_ID"
    log "Using Subnet: $SUBNET_ID"
}

# Create security group for Neo4j
create_security_group() {
    log "Creating security group for Neo4j..."
    
    # Check if security group already exists
    EXISTING_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")
    
    if [ "$EXISTING_SG" != "None" ] && [ -n "$EXISTING_SG" ]; then
        log "Security group $SECURITY_GROUP_NAME already exists: $EXISTING_SG"
        SECURITY_GROUP_ID="$EXISTING_SG"
    else
        # Create new security group
        SECURITY_GROUP_ID=$(aws ec2 create-security-group \
            --group-name "$SECURITY_GROUP_NAME" \
            --description "Security group for Neo4j database" \
            --vpc-id "$VPC_ID" \
            --query 'GroupId' --output text)
        
        log "Created security group: $SECURITY_GROUP_ID"
        
        # Add rules for Neo4j ports
        # Bolt protocol (7687) - from ECS security group
        ECS_SG=$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?contains(LoadBalancerName, `multimodal-librarian-full-ml`)].SecurityGroups[0]' --output text)
        
        if [ -n "$ECS_SG" ] && [ "$ECS_SG" != "None" ]; then
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
            
            log "Added ingress rules for ECS security group: $ECS_SG"
        else
            warn "Could not find ECS security group, adding rules for VPC CIDR"
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
        fi
    fi
}

# Launch Neo4j EC2 instance
launch_instance() {
    log "Launching Neo4j EC2 instance..."
    
    # Get latest Amazon Linux 2023 AMI
    AMI_ID=$(aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-x86_64" "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text)
    
    log "Using AMI: $AMI_ID"
    
    # Create user data script for Neo4j installation
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

# Configure Neo4j
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

# Logging
server.logs.user.stdout_enabled=true
CONFIG

# Set initial password (will be changed via secrets)
neo4j-admin dbms set-initial-password temppassword123

# Enable and start Neo4j
systemctl enable neo4j
systemctl start neo4j

# Wait for Neo4j to start
sleep 30

# Create a status file
echo "Neo4j installation completed at $(date)" > /var/log/neo4j-setup.log
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
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=neo4j-multimodal-librarian},{Key=Project,Value=multimodal-librarian},{Key=Component,Value=neo4j}]" \
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

# Update Neo4j secret with instance details
update_secret() {
    log "Updating Neo4j secret with instance details..."
    
    # Get current secret
    CURRENT_SECRET=$(aws secretsmanager get-secret-value --secret-id "multimodal-librarian/full-ml/neo4j" --query 'SecretString' --output text)
    
    # Update with instance IP
    UPDATED_SECRET=$(echo "$CURRENT_SECRET" | jq --arg host "$PRIVATE_IP" '.host = $host')
    
    # Update the secret
    aws secretsmanager update-secret \
        --secret-id "multimodal-librarian/full-ml/neo4j" \
        --secret-string "$UPDATED_SECRET"
    
    log "Updated Neo4j secret with host: $PRIVATE_IP"
}

# Test Neo4j connectivity
test_connectivity() {
    log "Testing Neo4j connectivity..."
    
    # Wait a bit more for Neo4j to fully start
    log "Waiting for Neo4j to fully initialize..."
    sleep 60
    
    # Test connection using cypher-shell (if available)
    # For now, just check if the port is open
    if command -v nc >/dev/null 2>&1; then
        if nc -z "$PRIVATE_IP" 7687; then
            log "✅ Neo4j Bolt port (7687) is accessible"
        else
            warn "❌ Neo4j Bolt port (7687) is not accessible yet"
        fi
        
        if nc -z "$PRIVATE_IP" 7474; then
            log "✅ Neo4j HTTP port (7474) is accessible"
        else
            warn "❌ Neo4j HTTP port (7474) is not accessible yet"
        fi
    else
        log "netcat not available, skipping port checks"
    fi
}

# Main execution
main() {
    log "🚀 Starting Neo4j EC2 instance setup..."
    
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
    test_connectivity
    
    log "🎉 Neo4j EC2 instance setup completed successfully!"
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
    log "⏳ Note: Neo4j may take a few more minutes to fully initialize."
    log "   You can check the status by SSH'ing to the instance and running:"
    log "   sudo systemctl status neo4j"
    log ""
    log "🔗 Next steps:"
    log "  1. Wait for Neo4j to fully start (5-10 minutes)"
    log "  2. Update the application configuration to use Neo4j"
    log "  3. Test the connection from the application"
}

# Run main function
main "$@"