#!/bin/bash

# Setup Model Cache Infrastructure
# This script sets up EFS-based model cache infrastructure for the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${ENVIRONMENT:-prod}"
AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT_NAME="${PROJECT_NAME:-multimodal-librarian}"

echo -e "${GREEN}Setting up Model Cache Infrastructure${NC}"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Project: $PROJECT_NAME"
echo ""

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo -e "${RED}Error: Terraform is not installed${NC}"
    exit 1
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Check AWS credentials
echo -e "${YELLOW}Checking AWS credentials...${NC}"
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured${NC}"
    exit 1
fi
echo -e "${GREEN}✓ AWS credentials configured${NC}"

# Navigate to infrastructure directory
cd infrastructure/aws-native

# Initialize Terraform if needed
if [ ! -d ".terraform" ]; then
    echo -e "${YELLOW}Initializing Terraform...${NC}"
    terraform init
    echo -e "${GREEN}✓ Terraform initialized${NC}"
fi

# Validate Terraform configuration
echo -e "${YELLOW}Validating Terraform configuration...${NC}"
terraform validate
echo -e "${GREEN}✓ Terraform configuration valid${NC}"

# Plan infrastructure changes
echo -e "${YELLOW}Planning infrastructure changes...${NC}"
terraform plan \
    -target=module.storage \
    -target=module.security.aws_security_group.efs \
    -target=module.security.aws_iam_role_policy.ecs_task_efs \
    -out=model-cache-plan.tfplan

echo ""
echo -e "${YELLOW}Review the plan above. Do you want to apply these changes? (yes/no)${NC}"
read -r response

if [ "$response" != "yes" ]; then
    echo -e "${YELLOW}Deployment cancelled${NC}"
    rm -f model-cache-plan.tfplan
    exit 0
fi

# Apply infrastructure changes
echo -e "${YELLOW}Applying infrastructure changes...${NC}"
terraform apply model-cache-plan.tfplan

# Clean up plan file
rm -f model-cache-plan.tfplan

# Get EFS information
echo ""
echo -e "${GREEN}Model Cache Infrastructure Setup Complete!${NC}"
echo ""
echo "EFS File System Details:"
terraform output -json storage | jq -r '
  "  File System ID: \(.efs_file_system_id)",
  "  Access Point ID: \(.efs_access_point_id)",
  "  DNS Name: \(.efs_dns_name)",
  "  Mount Path: \(.model_cache_path)"
'

echo ""
echo -e "${GREEN}Next Steps:${NC}"
echo "1. Update ECS task definition to mount EFS volume"
echo "2. Deploy updated application container"
echo "3. Verify model cache is accessible from application"
echo "4. Test model download and caching functionality"
echo ""
echo "To mount EFS in your application:"
echo "  - EFS will be mounted at: /efs/model-cache"
echo "  - Set MODEL_CACHE_DIR environment variable to: /efs/model-cache"
echo ""
