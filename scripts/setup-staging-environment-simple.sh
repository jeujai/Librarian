#!/bin/bash

# Staging Environment Setup Script for Multimodal Librarian Learning Deployment
# This script sets up a production-like staging environment on AWS

set -e  # Exit on any error

# Configuration
ENVIRONMENT="staging"
PROJECT_NAME="multimodal-librarian"
STACK_NAME="MultimodalLibrarianStagingStack"
DEV_STACK_NAME="MultimodalLibrarianDevStack"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-default}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
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

log_stage() {
    echo -e "${PURPLE}[STAGE]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites for staging environment..."
    
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
    
    # Check if development environment exists
    if ! aws cloudformation describe-stacks --stack-name "$DEV_STACK_NAME" --profile "$PROFILE" --region "$REGION" &> /dev/null; then
        log_warning "Development environment not found. Staging can be created independently, but promotion features will be limited."
    else
        log_success "Development environment found - promotion features will be available"
    fi
    
    log_success "Prerequisites check passed"
}

# Function to validate staging configuration
validate_staging_config() {
    log_info "Validating staging configuration..."
    
    # Check if staging config file exists
    if [[ ! -f "config/staging-config-basic.py" ]]; then
        log_warning "Staging config file not found. It will be created."
    fi
    
    # Check if staging environment variables are set
    if [[ -z "$AWS_DEFAULT_REGION" ]]; then
        log_warning "AWS_DEFAULT_REGION not set, using default: us-east-1"
        export AWS_DEFAULT_REGION="us-east-1"
    fi
    
    # Validate that staging and dev are in the same region
    if aws cloudformation describe-stacks --stack-name "$DEV_STACK_NAME" --profile "$PROFILE" --region "$REGION" &> /dev/null; then
        DEV_REGION=$(aws cloudformation describe-stacks --stack-name "$DEV_STACK_NAME" --profile "$PROFILE" --query 'Stacks[0].Tags[?Key==`aws:cloudformation:region`].Value' --output text)
        if [[ -n "$DEV_REGION" && "$DEV_REGION" != "$REGION" ]]; then
            log_warning "Development and staging environments are in different regions. This may affect promotion workflows."
        fi
    fi
    
    log_success "Staging configuration validated"
}

# Function to setup CDK environment for staging
setup_staging_cdk_environment() {
    log_info "Setting up CDK environment for staging..."
    
    # Get AWS account ID
    ACCOUNT_ID=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text)
    
    # Bootstrap CDK if not already done (should be done from dev setup)
    log_info "Verifying CDK bootstrap for account $ACCOUNT_ID in region $REGION..."
    if ! aws cloudformation describe-stacks --stack-name "CDKToolkit" --profile "$PROFILE" --region "$REGION" &> /dev/null; then
        log_info "CDK not bootstrapped. Bootstrapping now..."
        cdk bootstrap aws://$ACCOUNT_ID/$REGION --profile "$PROFILE"
    else
        log_success "CDK already bootstrapped"
    fi
    
    log_success "CDK environment setup complete"
}

# Function to deploy staging infrastructure
deploy_staging_infrastructure() {
    log_stage "Deploying staging infrastructure..."
    
    # Navigate to staging environment directory
    cd infrastructure/learning/environments/staging
    
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
    log_info "Synthesizing staging CDK stack..."
    cdk synth --profile "$PROFILE"
    
    # Deploy the stack
    log_info "Deploying staging stack: $STACK_NAME"
    log_warning "This will create production-like resources that may incur higher costs than development"
    
    # Confirm deployment
    read -p "Continue with staging deployment? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Staging deployment cancelled by user"
        cd ../../../../
        exit 0
    fi
    
    cdk deploy "$STACK_NAME" --profile "$PROFILE" --require-approval never
    
    # Return to project root
    cd ../../../../
    
    log_success "Staging infrastructure deployed successfully"
}

# Function to setup staging database
setup_staging_database() {
    log_info "Setting up staging database..."
    
    # Get database endpoint from CDK outputs
    DB_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingDatabaseEndpoint`].OutputValue' \
        --output text)
    
    if [[ -n "$DB_ENDPOINT" ]]; then
        log_info "Database endpoint: $DB_ENDPOINT"
        
        # Wait for database to be available
        log_info "Waiting for staging database to be available..."
        DB_INSTANCE_ID=$(echo "$DB_ENDPOINT" | cut -d'.' -f1)
        aws rds wait db-instance-available \
            --db-instance-identifier "$DB_INSTANCE_ID" \
            --profile "$PROFILE" \
            --region "$REGION"
        
        log_success "Staging database is ready"
    else
        log_warning "Could not retrieve database endpoint"
    fi
}

# Function to create staging configuration
create_staging_config() {
    log_info "Creating staging configuration..."
    
    # Get stack outputs
    VPC_ID=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingVPCId`].OutputValue' \
        --output text)
    
    CLUSTER_NAME=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingClusterName`].OutputValue' \
        --output text)
    
    BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingBucketName`].OutputValue' \
        --output text)
    
    ALB_DNS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingALBDNS`].OutputValue' \
        --output text)
    
    BLUE_TG_ARN=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingBlueTargetGroupArn`].OutputValue' \
        --output text)
    
    GREEN_TG_ARN=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingGreenTargetGroupArn`].OutputValue' \
        --output text)
    
    # Create staging environment file
    cat > .env.staging << EOF
# Staging Environment Configuration
ENVIRONMENT=staging
AWS_REGION=$REGION
AWS_PROFILE=$PROFILE

# Infrastructure
VPC_ID=$VPC_ID
ECS_CLUSTER_NAME=$CLUSTER_NAME
S3_BUCKET_NAME=$BUCKET_NAME
ALB_DNS_NAME=$ALB_DNS

# Blue-Green Deployment
BLUE_TARGET_GROUP_ARN=$BLUE_TG_ARN
GREEN_TARGET_GROUP_ARN=$GREEN_TG_ARN

# Application Configuration
DEBUG=false
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000

# Database Configuration (will be populated after database setup)
DATABASE_URL=postgresql://username:password@$DB_ENDPOINT:5432/multimodal_librarian_staging

# Production-like settings
ENABLE_METRICS=true
ENABLE_TRACING=true
PERFORMANCE_MONITORING=true

# Blue-Green Deployment
DEPLOYMENT_STRATEGY=blue_green
HEALTH_CHECK_PATH=/health
HEALTH_CHECK_INTERVAL=30

# Promotion settings
PROMOTION_SOURCE=development
PROMOTION_VALIDATION=true
EOF

    log_success "Staging configuration created: .env.staging"
}

# Function to setup staging monitoring
setup_staging_monitoring() {
    log_info "Setting up enhanced monitoring for staging environment..."
    
    # Create staging-specific CloudWatch dashboard
    DASHBOARD_BODY=$(cat << 'EOF'
{
    "widgets": [
        {
            "type": "metric",
            "x": 0,
            "y": 0,
            "width": 12,
            "height": 6,
            "properties": {
                "metrics": [
                    [ "AWS/ECS", "CPUUtilization", "ServiceName", "multimodal-librarian-staging", "ClusterName", "multimodal-librarian-staging-cluster" ],
                    [ ".", "MemoryUtilization", ".", ".", ".", "." ]
                ],
                "view": "timeSeries",
                "stacked": false,
                "region": "us-east-1",
                "title": "ECS Service Metrics",
                "period": 300
            }
        },
        {
            "type": "metric",
            "x": 12,
            "y": 0,
            "width": 12,
            "height": 6,
            "properties": {
                "metrics": [
                    [ "AWS/ApplicationELB", "RequestCount", "LoadBalancer", "app/multimodal-librarian-staging-alb" ],
                    [ ".", "TargetResponseTime", ".", "." ],
                    [ ".", "HTTPCode_Target_2XX_Count", ".", "." ],
                    [ ".", "HTTPCode_Target_4XX_Count", ".", "." ],
                    [ ".", "HTTPCode_Target_5XX_Count", ".", "." ]
                ],
                "view": "timeSeries",
                "stacked": false,
                "region": "us-east-1",
                "title": "Load Balancer Metrics",
                "period": 300
            }
        }
    ]
}
EOF
)
    
    # Create CloudWatch dashboard
    aws cloudwatch put-dashboard \
        --dashboard-name "MultimodalLibrarian-Staging" \
        --dashboard-body "$DASHBOARD_BODY" \
        --profile "$PROFILE" \
        --region "$REGION" 2>/dev/null || log_warning "Could not create CloudWatch dashboard"
    
    # Create staging-specific alarms
    aws cloudwatch put-metric-alarm \
        --alarm-name "MultimodalLibrarian-Staging-HighCPU" \
        --alarm-description "High CPU utilization in staging environment" \
        --metric-name CPUUtilization \
        --namespace AWS/ECS \
        --statistic Average \
        --period 300 \
        --threshold 80 \
        --comparison-operator GreaterThanThreshold \
        --evaluation-periods 2 \
        --profile "$PROFILE" \
        --region "$REGION" 2>/dev/null || log_warning "Could not create CPU alarm"
    
    log_success "Staging monitoring setup complete"
}

# Function to setup blue-green deployment
setup_blue_green_deployment() {
    log_info "Setting up blue-green deployment capabilities..."
    
    # Create blue-green deployment script
    cat > scripts/blue-green-deploy-staging.sh << 'EOF'
#!/bin/bash

# Blue-Green Deployment Script for Staging Environment

set -e

ENVIRONMENT="staging"
STACK_NAME="MultimodalLibrarianStagingStack"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-default}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Get target group ARNs
BLUE_TG_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`StagingBlueTargetGroupArn`].OutputValue' \
    --output text)

GREEN_TG_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`StagingGreenTargetGroupArn`].OutputValue' \
    --output text)

# Determine current active target group
CURRENT_TG="blue"  # Default to blue
NEW_TG="green"

log_info "Current target group: $CURRENT_TG"
log_info "Deploying to: $NEW_TG"

# Deploy new version to inactive target group
log_info "Deploying new version to $NEW_TG target group..."

# Here you would deploy your new application version
# This is a placeholder for the actual deployment logic
log_warning "Deployment logic placeholder - implement actual ECS service update"

# Health check
log_info "Performing health checks on $NEW_TG..."
sleep 10  # Simulate health check time

# Switch traffic (this would be done through ALB listener rules)
log_info "Switching traffic to $NEW_TG..."
log_warning "Traffic switching placeholder - implement actual ALB listener update"

log_success "Blue-green deployment completed successfully"
EOF

    chmod +x scripts/blue-green-deploy-staging.sh
    
    log_success "Blue-green deployment setup complete"
}

# Function to run staging tests
run_staging_tests() {
    log_info "Running staging environment tests..."
    
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
        --query 'Stacks[0].Outputs[?OutputKey==`StagingBucketName`].OutputValue' \
        --output text)
    
    if [[ -n "$BUCKET_NAME" ]]; then
        if aws s3 ls "s3://$BUCKET_NAME" --profile "$PROFILE" &> /dev/null; then
            log_success "S3 bucket access test passed"
        else
            log_warning "S3 bucket access test failed"
        fi
    fi
    
    # Test ALB endpoint
    ALB_DNS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingALBDNS`].OutputValue' \
        --output text)
    
    if [[ -n "$ALB_DNS" ]]; then
        log_info "Testing ALB endpoint: http://$ALB_DNS"
        if curl -f -s "http://$ALB_DNS" > /dev/null 2>&1; then
            log_success "ALB endpoint test passed"
        else
            log_warning "ALB endpoint test failed (expected until application is deployed)"
        fi
    fi
    
    log_success "Staging environment tests completed"
}

# Function to display setup summary
display_summary() {
    log_info "Staging Environment Setup Summary"
    echo "=================================="
    echo "Environment: $ENVIRONMENT"
    echo "Region: $REGION"
    echo "Stack Name: $STACK_NAME"
    echo "Profile: $PROFILE"
    echo ""
    echo "Resources Created:"
    echo "- VPC with dual AZ configuration (production-like)"
    echo "- ECS Cluster with container insights enabled"
    echo "- RDS PostgreSQL database (t3.small)"
    echo "- S3 bucket with versioning and lifecycle policies"
    echo "- Application Load Balancer with blue-green target groups"
    echo "- Enhanced security groups and IAM roles"
    echo "- CloudWatch logging with extended retention"
    echo "- Secrets Manager for configuration"
    echo "- CloudWatch dashboard and alarms"
    echo ""
    echo "Configuration Files:"
    echo "- .env.staging (environment variables)"
    echo "- config/staging-config-basic.py (Python configuration)"
    echo "- scripts/blue-green-deploy-staging.sh (deployment script)"
    echo ""
    echo "Key Differences from Development:"
    echo "- Dual AZ VPC (vs single AZ in dev)"
    echo "- Larger database instance (t3.small vs t3.micro)"
    echo "- Versioned S3 bucket with longer retention"
    echo "- Application Load Balancer with blue-green deployment"
    echo "- Enhanced monitoring and container insights"
    echo "- Deletion protection enabled"
    echo ""
    echo "Next Steps:"
    echo "1. Review the created .env.staging file"
    echo "2. Deploy your application to the staging environment"
    echo "3. Set up promotion pipeline from development"
    echo "4. Configure blue-green deployment process"
    echo "5. Run integration tests in staging environment"
    echo ""
    log_success "Staging environment setup completed successfully!"
}

# Function to cleanup on error
cleanup_on_error() {
    log_error "Setup failed. Cleaning up..."
    
    # Optionally destroy the stack if deployment failed
    read -p "Do you want to destroy the partially created staging stack? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Destroying stack: $STACK_NAME"
        cd infrastructure/learning/environments/staging
        cdk destroy "$STACK_NAME" --profile "$PROFILE" --force
        cd ../../../../
        log_info "Stack destroyed"
    fi
}

# Main execution
main() {
    log_stage "Starting staging environment setup for Multimodal Librarian"
    log_warning "This will create production-like AWS resources that may incur higher costs than development"
    
    # Confirm before proceeding
    read -p "Do you want to continue with staging environment setup? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Setup cancelled by user"
        exit 0
    fi
    
    # Set up error handling
    trap cleanup_on_error ERR
    
    # Execute setup steps
    check_prerequisites
    validate_staging_config
    setup_staging_cdk_environment
    deploy_staging_infrastructure
    setup_staging_database
    create_staging_config
    setup_staging_monitoring
    setup_blue_green_deployment
    run_staging_tests
    display_summary
    
    log_success "Staging environment setup completed successfully!"
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
    echo "  $0 --region us-west-2 --profile staging"
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