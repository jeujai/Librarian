#!/bin/bash
# Bootstrap script to create Terraform state management resources
# Run this BEFORE terraform init for production deployment

set -e

# Configuration
PROJECT_NAME="multimodal-librarian"
ENVIRONMENT="production"
AWS_REGION="us-west-2"
BUCKET_NAME="${PROJECT_NAME}-${ENVIRONMENT}-terraform-state"
DYNAMODB_TABLE="${PROJECT_NAME}-${ENVIRONMENT}-terraform-locks"

echo "🚀 Bootstrapping Terraform state management for ${PROJECT_NAME}-${ENVIRONMENT}"
echo "Region: ${AWS_REGION}"
echo "Bucket: ${BUCKET_NAME}"
echo "DynamoDB Table: ${DYNAMODB_TABLE}"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "❌ AWS CLI not configured. Please run 'aws configure' first."
    exit 1
fi

echo "✅ AWS CLI configured"

# Create S3 bucket for Terraform state
echo "📦 Creating S3 bucket for Terraform state..."
if aws s3api head-bucket --bucket "${BUCKET_NAME}" 2>/dev/null; then
    echo "✅ S3 bucket ${BUCKET_NAME} already exists"
else
    # Create bucket
    if [ "${AWS_REGION}" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "${BUCKET_NAME}" --region "${AWS_REGION}"
    else
        aws s3api create-bucket --bucket "${BUCKET_NAME}" --region "${AWS_REGION}" \
            --create-bucket-configuration LocationConstraint="${AWS_REGION}"
    fi
    
    # Enable versioning
    aws s3api put-bucket-versioning --bucket "${BUCKET_NAME}" \
        --versioning-configuration Status=Enabled
    
    # Enable server-side encryption
    aws s3api put-bucket-encryption --bucket "${BUCKET_NAME}" \
        --server-side-encryption-configuration '{
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }
            ]
        }'
    
    # Block public access
    aws s3api put-public-access-block --bucket "${BUCKET_NAME}" \
        --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    
    echo "✅ Created and configured S3 bucket ${BUCKET_NAME}"
fi

# Create DynamoDB table for state locking
echo "🔒 Creating DynamoDB table for state locking..."
if aws dynamodb describe-table --table-name "${DYNAMODB_TABLE}" --region "${AWS_REGION}" > /dev/null 2>&1; then
    echo "✅ DynamoDB table ${DYNAMODB_TABLE} already exists"
else
    aws dynamodb create-table \
        --table-name "${DYNAMODB_TABLE}" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
        --region "${AWS_REGION}"
    
    echo "⏳ Waiting for DynamoDB table to be active..."
    aws dynamodb wait table-exists --table-name "${DYNAMODB_TABLE}" --region "${AWS_REGION}"
    echo "✅ Created DynamoDB table ${DYNAMODB_TABLE}"
fi

# Create backend configuration file
echo "📝 Creating backend configuration file..."
cat > backend.conf << EOF
bucket         = "${BUCKET_NAME}"
key            = "${ENVIRONMENT}/terraform.tfstate"
region         = "${AWS_REGION}"
dynamodb_table = "${DYNAMODB_TABLE}"
encrypt        = true
EOF

echo "✅ Created backend.conf"

# Create terraform.tfvars if it doesn't exist
if [ ! -f "terraform.tfvars" ]; then
    echo "📝 Creating terraform.tfvars template..."
    cat > terraform.tfvars << EOF
# AWS Configuration
aws_region    = "${AWS_REGION}"
backup_region = "us-east-1"

# Project Configuration
project_name = "${PROJECT_NAME}"
environment  = "${ENVIRONMENT}"
cost_center  = "engineering"
owner        = "devops-team"

# Network Configuration
vpc_cidr = "10.0.0.0/16"
availability_zones = ["${AWS_REGION}a", "${AWS_REGION}b", "${AWS_REGION}c"]
public_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
private_subnet_cidrs = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]

# Database Configuration
neptune_instance_type = "db.t3.medium"
neptune_instance_count = 2
neptune_backup_retention = 7

opensearch_instance_type = "t3.medium.search"
opensearch_instance_count = 3

# Application Configuration
container_port = 8000
ecs_cpu = 1024
ecs_memory = 2048
min_capacity = 2
max_capacity = 10

# Security Configuration
kms_key_rotation = true
enable_cloudtrail = true

# Domain Configuration (optional - leave empty for default CloudFront domain)
domain_name = ""
certificate_arn = ""

# Monitoring Configuration
log_retention_days = 30
EOF
    echo "✅ Created terraform.tfvars template"
    echo "📝 Please review and update terraform.tfvars with your specific values"
fi

echo ""
echo "🎉 Bootstrap complete! Next steps:"
echo "1. Review and update terraform.tfvars with your specific configuration"
echo "2. Run: terraform init -backend-config=backend.conf"
echo "3. Run: terraform plan"
echo "4. Run: terraform apply"
echo ""
echo "Backend configuration:"
echo "  Bucket: ${BUCKET_NAME}"
echo "  Key: ${ENVIRONMENT}/terraform.tfstate"
echo "  Region: ${AWS_REGION}"
echo "  DynamoDB Table: ${DYNAMODB_TABLE}"