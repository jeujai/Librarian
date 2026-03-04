#!/bin/bash
"""
Docker-based Neo4j EC2 Instance Setup Script

This script creates a Neo4j instance using Docker for maximum reliability.
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

# Launch Neo4j instance with Docker
launch_instance() {
    log "Launching Docker-based Neo4j EC2 instance..."
    
    # Get latest Amazon Linux 2023 AMI
    AMI_ID=$(aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-x86_64" "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text)
    
    log "Using AMI: $AMI_ID"
    
    # Create Docker-based user data script
    USER_DATA=$(cat << 'EOF'
#!/bin/bash
exec > >(tee /var/log/user-data.log) 2>&1
echo "Starting Docker-based Neo4j installation at $(date)"

# Update system
yum update -y

# Install Docker
yum install -y docker
systemctl start docker
systemctl enable docker

# Add ec2-user to docker group
usermod -a -G docker ec2-user

# Install docker-compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Create Neo4j data directory
mkdir -p /opt/neo4j/data
mkdir -p /opt/neo4j/logs
mkdir -p /opt/neo4j/conf

# Create Neo4j configuration
cat << 'CONFIG' > /opt/neo4j/conf/neo4j.conf
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

# Create docker-compose file
cat << 'COMPOSE' > /opt/neo4j/docker-compose.yml
version: '3.8'
services:
  neo4j:
    image: neo4j:5.15.0
    container_name: neo4j
    restart: unless-stopped
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/temppassword123
      - NEO4J_server_default_listen__address=0.0.0.0
      - NEO4J_server_bolt_listen__address=0.0.0.0:7687
      - NEO4J_server_http_listen__address=0.0.0.0:7474
      - NEO4J_server_memory_heap_initial__size=1G
      - NEO4J_server_memory_heap_max__size=1G
      - NEO4J_server_memory_pagecache_size=512M
      - NEO4J_dbms_security_auth__enabled=true
    volumes:
      - /opt/neo4j/data:/data
      - /opt/neo4j/logs:/logs
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p temppassword123 'RETURN 1'"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
COMPOSE

# Set permissions
chown -R 7474:7474 /opt/neo4j/data
chown -R 7474:7474 /opt/neo4j/logs

# Start Neo4j with Docker Compose
cd /opt/neo4j
docker-compose up -d

# Wait for Neo4j to be ready
echo "Waiting for Neo4j to be ready..."
for i in {1..30}; do
    if docker-compose ps | grep -q "healthy"; then
        echo "Neo4j is healthy!"
        break
    elif docker-compose ps | grep -q "Up"; then
        echo "Neo4j is starting... attempt $i/30"
    else
        echo "Neo4j container not running, checking logs..."
        docker-compose logs neo4j
    fi
    sleep 10
done

# Final status check
echo "Final status check at $(date):"
docker-compose ps
docker-compose logs --tail=20 neo4j
netstat -tlnp | grep -E ":(7687|7474)"

echo "Docker-based Neo4j installation completed at $(date)"
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
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=neo4j-docker-multimodal-librarian},{Key=Project,Value=multimodal-librarian},{Key=Component,Value=neo4j}]" \
        --query 'Instances[0].InstanceId' \
        --output text)
    
    if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
        error "Failed to launch EC2 instance"
        exit 1
    fi
    
    log "Launched Docker-based Neo4j instance: $INSTANCE_ID"
    
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
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "deployment_type": "docker"
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

# Monitor Neo4j startup with shorter intervals
monitor_startup() {
    log "Monitoring Docker-based Neo4j startup progress..."
    
    for i in {1..15}; do
        log "Startup check $i/15..."
        
        # Test port connectivity
        if nc -z "$PRIVATE_IP" 7687 2>/dev/null; then
            log "✅ Neo4j Bolt port (7687) is accessible!"
            
            # Test actual connection
            if python3 scripts/test-neo4j-connectivity.py 2>/dev/null; then
                log "🎉 Neo4j database connection successful!"
                return 0
            else
                log "Port accessible but connection test failed, Neo4j may still be initializing..."
            fi
        fi
        
        if [ $i -lt 15 ]; then
            log "Neo4j not ready yet, waiting 20 seconds..."
            sleep 20
        fi
    done
    
    warn "Neo4j startup monitoring completed"
    log "Docker-based Neo4j should be more reliable. You can check the status with:"
    log "  ssh -i migration-key.pem ec2-user@$PUBLIC_IP"
    log "  cd /opt/neo4j && docker-compose ps"
    log "  cd /opt/neo4j && docker-compose logs neo4j"
}

# Main execution
main() {
    log "🚀 Creating Docker-based Neo4j EC2 instance..."
    
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
    
    log "🎉 Docker-based Neo4j EC2 instance setup completed!"
    log ""
    log "📋 Summary:"
    log "  Instance ID: $INSTANCE_ID"
    log "  Private IP: $PRIVATE_IP"
    log "  Public IP: $PUBLIC_IP"
    log "  Security Group: $SECURITY_GROUP_ID"
    log "  Deployment: Docker-based"
    log ""
    log "📁 Instance details saved to: neo4j-instance-info.json"
    log "🔐 Neo4j secret updated with host information"
    log ""
    log "🔗 Next steps:"
    log "  1. Test Neo4j connectivity: python3 scripts/test-neo4j-connectivity.py"
    log "  2. Test application integration: curl http://localhost:8000/test/neo4j"
    log "  3. Deploy updated application to AWS ECS"
    log ""
    log "🐳 Docker commands for troubleshooting:"
    log "  ssh -i migration-key.pem ec2-user@$PUBLIC_IP"
    log "  cd /opt/neo4j && docker-compose ps"
    log "  cd /opt/neo4j && docker-compose logs neo4j"
    log "  cd /opt/neo4j && docker-compose restart neo4j"
}

# Run main function
main "$@"