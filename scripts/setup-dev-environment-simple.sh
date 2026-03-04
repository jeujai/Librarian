#!/bin/bash

# Development Environment Setup Script for Multimodal Librarian Learning Deployment
# This script sets up a cost-optimized development environment on AWS

set -e  # Exit on any error

# Configuration
ENVIRONMENT="development"
PROJECT_NAME="multimodal-librarian"
STACK_NAME="MultimodalLibrarianDevStack"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-default}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if CDK is installed
    if ! command -v cdk &> /dev/null; then
        log_error "AWS CDK is not installed. Please install it first: npm install -g aws-cdk"
        exit 1
    fi
    
    # Check if Node.js is installed
    if ! command -v node &> /dev/null; then
        log_error "Node.js is not installed. Please install it first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity --profile "$PROFILE" &> /dev/null; then
        log_error "AWS credentials not configured or invalid for profile: $PROFILE"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Function to setup CDK environment
setup_cdk_environment() {
    log_info "Setting up CDK environment..."
    
    # Get AWS account ID
    ACCOUNT_ID=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text)
    
    # Bootstrap CDK if not already done
    log_info "Bootstrapping CDK for account $ACCOUNT_ID in region $REGION..."
    cdk bootstrap aws://$ACCOUNT_ID/$REGION --profile "$PROFILE"
    
    log_success "CDK environment setup complete"
}

# Function to validate development configuration
validate_dev_config() {
    log_info "Validating development configuration..."
    
    # Check if development config file exists
    if [[ ! -f "config/dev-config-basic.py" ]]; then
        log_warning "Development config file not found. It will be created."
    fi
    
    # Check if development environment variables are set
    if [[ -z "$AWS_DEFAULT_REGION" ]]; then
        log_warning "AWS_DEFAULT_REGION not set, using default: us-east-1"
        export AWS_DEFAULT_REGION="us-east-1"
    fi
    
    log_success "Development configuration validated"
}

# Function to deploy development infrastructure
deploy_dev_infrastructure() {
    log_info "Deploying development infrastructure..."
    
    # Navigate to development environment directory
    cd infrastructure/learning/environments/dev
    
    # Install CDK dependencies
    if [[ -f "package.json" ]]; then
        log_info "Installing CDK dependencies..."
        npm install
    else
        log_info "Initializing CDK project..."
        npm init -y
        npm install aws-cdk-lib constructs
    fi
    
    # Synthesize CDK stack
    log_info "Synthesizing CDK stack..."
    cdk synth --profile "$PROFILE"
    
    # Deploy the stack
    log_info "Deploying development stack: $STACK_NAME"
    cdk deploy "$STACK_NAME" --profile "$PROFILE" --require-approval never
    
    # Return to project root
    cd ../../../../
    
    log_success "Development infrastructure deployed successfully"
}

# Function to setup development database
setup_dev_database() {
    log_info "Setting up development database..."
    
    # Get database endpoint from CDK outputs
    DB_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DevDatabaseEndpoint`].OutputValue' \
        --output text)
    
    if [[ -n "$DB_ENDPOINT" ]]; then
        log_info "Database endpoint: $DB_ENDPOINT"
        
        # Wait for database to be available
        log_info "Waiting for database to be available..."
        aws rds wait db-instance-available \
            --db-instance-identifier $(echo "$DB_ENDPOINT" | cut -d'.' -f1) \
            --profile "$PROFILE" \
            --region "$REGION"
        
        log_success "Development database is ready"
    else
        log_warning "Could not retrieve database endpoint"
    fi
}

# Function to create development configuration
create_dev_config() {
    log_info "Creating development configuration..."
    
    # Get stack outputs
    VPC_ID=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DevVPCId`].OutputValue' \
        --output text)
    
    CLUSTER_NAME=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DevClusterName`].OutputValue' \
        --output text)
    
    BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DevBucketName`].OutputValue' \
        --output text)
    
    # Create development environment file
    cat > .env.dev << EOF
# Development Environment Configuration
ENVIRONMENT=development
AWS_REGION=$REGION
AWS_PROFILE=$PROFILE

# Infrastructure
VPC_ID=$VPC_ID
ECS_CLUSTER_NAME=$CLUSTER_NAME
S3_BUCKET_NAME=$BUCKET_NAME

# Application Configuration
DEBUG=true
LOG_LEVEL=DEBUG
API_HOST=0.0.0.0
API_PORT=8000

# Database Configuration (will be populated after database setup)
DATABASE_URL=postgresql://username:password@$DB_ENDPOINT:5432/multimodal_librarian_dev

# Cost Optimization
AUTO_SHUTDOWN_ENABLED=true
COST_MONITORING_ENABLED=true
EOF

    log_success "Development configuration created: .env.dev"
}

# Function to setup cost monitoring
setup_cost_monitoring() {
    log_info "Setting up cost monitoring for development environment..."
    
    # Create cost budget for development environment
    aws budgets create-budget \
        --account-id $(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text) \
        --budget '{
            "BudgetName": "multimodal-librarian-dev-budget",
            "BudgetLimit": {
                "Amount": "50.0",
                "Unit": "USD"
            },
            "TimeUnit": "MONTHLY",
            "BudgetType": "COST",
            "CostFilters": {
                "TagKey": ["Environment"],
                "TagValue": ["development"]
            }
        }' \
        --notifications-with-subscribers '[
            {
                "Notification": {
                    "NotificationType": "ACTUAL",
                    "ComparisonOperator": "GREATER_THAN",
                    "Threshold": 80.0,
                    "ThresholdType": "PERCENTAGE"
                },
                "Subscribers": [
                    {
                        "SubscriptionType": "EMAIL",
                        "Address": "developer@example.com"
                    }
                ]
            }
        ]' \
        --profile "$PROFILE" 2>/dev/null || log_warning "Budget already exists or could not be created"
    
    log_success "Cost monitoring setup complete"
}

# Function to run development tests
run_dev_tests() {
    log_info "Running development environment tests..."
    
    # Test AWS connectivity
    if aws sts get-caller-identity --profile "$PROFILE" &> /dev/null; then
        log_success "AWS connectivity test passed"
    else
        log_error "AWS connectivity test failed"
        return 1
    fi
    
    # Test S3 bucket access
    BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DevBucketName`].OutputValue' \
        --output text)
    
    if [[ -n "$BUCKET_NAME" ]]; then
        if aws s3 ls "s3://$BUCKET_NAME" --profile "$PROFILE" &> /dev/null; then
            log_success "S3 bucket access test passed"
        else
            log_warning "S3 bucket access test failed"
        fi
    fi
    
    log_success "Development environment tests completed"
}

# Function to display setup summary
display_summary() {
    log_info "Development Environment Setup Summary"
    echo "=================================="
    echo "Environment: $ENVIRONMENT"
    echo "Region: $REGION"
    echo "Stack Name: $STACK_NAME"
    echo "Profile: $PROFILE"
    echo ""
    echo "Resources Created:"
    echo "- VPC with single AZ configuration"
    echo "- ECS Cluster for containerized applications"
    echo "- RDS PostgreSQL database (t3.micro)"
    echo "- S3 bucket with lifecycle policies"
    echo "- Security groups and IAM roles"
    echo "- CloudWatch log groups"
    echo "- Secrets Manager for configuration"
    echo ""
    echo "Configuration Files:"
    echo "- .env.dev (environment variables)"
    echo "- config/dev-config-basic.py (Python configuration)"
    echo ""
    echo "Next Steps:"
    echo "1. Review the created .env.dev file"
    echo "2. Run the data seeding script: ./scripts/seed-dev-data-simple.py"
    echo "3. Deploy your application to the development environment"
    echo "4. Monitor costs using AWS Cost Explorer"
    echo ""
    log_success "Development environment setup completed successfully!"
}

# Function to cleanup on error
cleanup_on_error() {
    log_error "Setup failed. Cleaning up..."
    
    # Optionally destroy the stack if deployment failed
    read -p "Do you want to destroy the partially created stack? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Destroying stack: $STACK_NAME"
        cd infrastructure/learning/environments/dev
        cdk destroy "$STACK_NAME" --profile "$PROFILE" --force
        cd ../../../../
        log_info "Stack destroyed"
    fi
}

# Main execution
main() {
    log_info "Starting development environment setup for Multimodal Librarian"
    log_info "This will create AWS resources that may incur costs"
    
    # Confirm before proceeding
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Setup cancelled by user"
        exit 0
    fi
    
    # Set up error handling
    trap cleanup_on_error ERR
    
    # Execute setup steps
    check_prerequisites
    validate_dev_config
    setup_cdk_environment
    deploy_dev_infrastructure
    setup_dev_database
    create_dev_config
    setup_cost_monitoring
    run_dev_tests
    display_summary
    
    log_success "Development environment setup completed successfully!"
}

# Script usage information
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -r, --region   AWS region (default: us-east-1)"
    echo "  -p, --profile  AWS profile (default: default)"
    echo ""
    echo "Environment Variables:"
    echo "  AWS_DEFAULT_REGION  AWS region to use"
    echo "  AWS_PROFILE         AWS profile to use"
    echo ""
    echo "Example:"
    echo "  $0 --region us-west-2 --profile dev"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -p|--profile)
            PROFILE="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Run main function
main "$@"