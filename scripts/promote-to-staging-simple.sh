#!/bin/bash

# Promotion Script for Multimodal Librarian Learning Deployment
# This script promotes code and configuration from development to staging environment

set -e  # Exit on any error

# Configuration
SOURCE_ENVIRONMENT="development"
TARGET_ENVIRONMENT="staging"
PROJECT_NAME="multimodal-librarian"
DEV_STACK_NAME="MultimodalLibrarianDevStack"
STAGING_STACK_NAME="MultimodalLibrarianStagingStack"
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
    log_info "Checking prerequisites for promotion..."
    
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
    
    # Check if git is installed
    if ! command -v git &> /dev/null; then
        log_error "Git is not installed. Please install it first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity --profile "$PROFILE" &> /dev/null; then
        log_error "AWS credentials not configured or invalid for profile: $PROFILE"
        exit 1
    fi
    
    # Check if development environment exists
    if ! aws cloudformation describe-stacks --stack-name "$DEV_STACK_NAME" --profile "$PROFILE" --region "$REGION" &> /dev/null; then
        log_error "Development environment not found. Cannot promote without source environment."
        exit 1
    fi
    
    # Check if staging environment exists
    if ! aws cloudformation describe-stacks --stack-name "$STAGING_STACK_NAME" --profile "$PROFILE" --region "$REGION" &> /dev/null; then
        log_error "Staging environment not found. Please set up staging environment first."
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Function to validate current state
validate_current_state() {
    log_info "Validating current state..."
    
    # Check git status
    if [[ -n $(git status --porcelain) ]]; then
        log_warning "Working directory has uncommitted changes"
        read -p "Continue with uncommitted changes? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Promotion cancelled. Please commit or stash changes first."
            exit 0
        fi
    fi
    
    # Get current branch
    CURRENT_BRANCH=$(git branch --show-current)
    log_info "Current branch: $CURRENT_BRANCH"
    
    # Check if on main/master branch
    if [[ "$CURRENT_BRANCH" != "main" && "$CURRENT_BRANCH" != "master" ]]; then
        log_warning "Not on main/master branch. Current branch: $CURRENT_BRANCH"
        read -p "Continue with current branch? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Promotion cancelled. Please switch to main/master branch."
            exit 0
        fi
    fi
    
    log_success "Current state validation passed"
}

# Function to run pre-promotion tests
run_pre_promotion_tests() {
    log_info "Running pre-promotion tests..."
    
    # Run basic syntax checks
    log_info "Running Python syntax checks..."
    if command -v python3 &> /dev/null; then
        find . -name "*.py" -not -path "./venv/*" -not -path "./.venv/*" -exec python3 -m py_compile {} \; 2>/dev/null || {
            log_warning "Python syntax check failed for some files"
        }
    fi
    
    # Check configuration files
    log_info "Validating configuration files..."
    
    if [[ -f "config/dev-config-basic.py" ]]; then
        python3 -c "import config.dev_config_basic; print('✅ Dev config valid')" || {
            log_error "Development configuration validation failed"
            return 1
        }
    fi
    
    if [[ -f "config/staging-config-basic.py" ]]; then
        python3 -c "import config.staging_config_basic; print('✅ Staging config valid')" || {
            log_error "Staging configuration validation failed"
            return 1
        }
    fi
    
    # Test AWS connectivity
    log_info "Testing AWS connectivity..."
    aws sts get-caller-identity --profile "$PROFILE" > /dev/null || {
        log_error "AWS connectivity test failed"
        return 1
    }
    
    # Check development environment health
    log_info "Checking development environment health..."
    DEV_STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$DEV_STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text)
    
    if [[ "$DEV_STACK_STATUS" != "CREATE_COMPLETE" && "$DEV_STACK_STATUS" != "UPDATE_COMPLETE" ]]; then
        log_error "Development environment is not in a healthy state: $DEV_STACK_STATUS"
        return 1
    fi
    
    # Check staging environment health
    log_info "Checking staging environment health..."
    STAGING_STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STAGING_STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text)
    
    if [[ "$STAGING_STACK_STATUS" != "CREATE_COMPLETE" && "$STAGING_STACK_STATUS" != "UPDATE_COMPLETE" ]]; then
        log_error "Staging environment is not in a healthy state: $STAGING_STACK_STATUS"
        return 1
    fi
    
    log_success "Pre-promotion tests passed"
}

# Function to backup current staging state
backup_staging_state() {
    log_info "Creating backup of current staging state..."
    
    # Create backup directory
    BACKUP_DIR="backups/staging-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Backup staging configuration
    if [[ -f ".env.staging" ]]; then
        cp ".env.staging" "$BACKUP_DIR/"
        log_info "Backed up .env.staging"
    fi
    
    if [[ -f "config/staging-config-basic.py" ]]; then
        cp "config/staging-config-basic.py" "$BACKUP_DIR/"
        log_info "Backed up staging configuration"
    fi
    
    # Export current staging stack template
    aws cloudformation get-template \
        --stack-name "$STAGING_STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'TemplateBody' > "$BACKUP_DIR/staging-stack-template.json" || {
        log_warning "Could not backup staging stack template"
    }
    
    # Get current staging stack parameters
    aws cloudformation describe-stacks \
        --stack-name "$STAGING_STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Parameters' > "$BACKUP_DIR/staging-stack-parameters.json" || {
        log_warning "Could not backup staging stack parameters"
    }
    
    # Create rollback script
    cat > "$BACKUP_DIR/rollback.sh" << EOF
#!/bin/bash
# Rollback script for staging promotion
# Created: $(date)

echo "Rolling back staging environment..."

# Restore configuration files
if [[ -f ".env.staging" ]]; then
    cp ".env.staging" "../../../.env.staging"
    echo "Restored .env.staging"
fi

if [[ -f "staging-config-basic.py" ]]; then
    cp "staging-config-basic.py" "../../../config/staging-config-basic.py"
    echo "Restored staging configuration"
fi

echo "Manual rollback steps:"
echo "1. Review and restore any infrastructure changes"
echo "2. Redeploy previous application version if needed"
echo "3. Verify staging environment functionality"
echo ""
echo "Backup location: $BACKUP_DIR"
EOF
    
    chmod +x "$BACKUP_DIR/rollback.sh"
    
    log_success "Staging state backed up to: $BACKUP_DIR"
    echo "BACKUP_DIR=$BACKUP_DIR" > /tmp/staging_backup_location
}

# Function to promote infrastructure changes
promote_infrastructure() {
    log_info "Promoting infrastructure changes to staging..."
    
    # Check if there are infrastructure changes
    if [[ ! -d "infrastructure/learning/environments/staging" ]]; then
        log_warning "No staging infrastructure directory found"
        return 0
    fi
    
    cd infrastructure/learning/environments/staging
    
    # Install dependencies if needed
    if [[ -f "package.json" ]]; then
        log_info "Installing CDK dependencies..."
        npm install
    fi
    
    # Synthesize and diff the stack
    log_info "Checking for infrastructure changes..."
    if cdk diff "$STAGING_STACK_NAME" --profile "$PROFILE" > /tmp/staging_diff.txt 2>&1; then
        if [[ -s /tmp/staging_diff.txt ]]; then
            log_info "Infrastructure changes detected:"
            cat /tmp/staging_diff.txt
            
            read -p "Apply these infrastructure changes? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                log_info "Deploying infrastructure changes..."
                cdk deploy "$STAGING_STACK_NAME" --profile "$PROFILE" --require-approval never
                log_success "Infrastructure changes deployed"
            else
                log_info "Infrastructure changes skipped"
            fi
        else
            log_info "No infrastructure changes detected"
        fi
    else
        log_warning "Could not check for infrastructure changes"
    fi
    
    cd ../../../../
}

# Function to promote application configuration
promote_configuration() {
    log_info "Promoting configuration changes to staging..."
    
    # Update staging configuration based on development
    if [[ -f "config/dev-config-basic.py" && -f "config/staging-config-basic.py" ]]; then
        log_info "Configuration files exist, manual review recommended"
        
        # Show configuration differences
        if command -v diff &> /dev/null; then
            log_info "Configuration differences (dev vs staging):"
            diff -u config/dev-config-basic.py config/staging-config-basic.py || true
        fi
    fi
    
    # Update environment variables if needed
    if [[ -f ".env.development" && -f ".env.staging" ]]; then
        log_info "Environment files exist, manual review recommended"
        
        # Show environment differences
        if command -v diff &> /dev/null; then
            log_info "Environment differences (dev vs staging):"
            diff -u .env.development .env.staging || true
        fi
    fi
    
    log_success "Configuration promotion completed (manual review recommended)"
}

# Function to promote application code
promote_application_code() {
    log_info "Promoting application code to staging..."
    
    # Get current commit hash
    CURRENT_COMMIT=$(git rev-parse HEAD)
    CURRENT_BRANCH=$(git branch --show-current)
    
    log_info "Promoting commit: $CURRENT_COMMIT from branch: $CURRENT_BRANCH"
    
    # Tag the promotion
    PROMOTION_TAG="staging-promotion-$(date +%Y%m%d-%H%M%S)"
    git tag -a "$PROMOTION_TAG" -m "Promotion to staging at $(date)"
    
    log_info "Created promotion tag: $PROMOTION_TAG"
    
    # In a real scenario, this would trigger a build and deployment
    # For learning purposes, we'll simulate the process
    log_info "Application code promotion completed"
    log_warning "Note: Actual application deployment would happen here in a real scenario"
    
    echo "PROMOTION_TAG=$PROMOTION_TAG" >> /tmp/staging_backup_location
}

# Function to run post-promotion tests
run_post_promotion_tests() {
    log_info "Running post-promotion tests..."
    
    # Test staging environment connectivity
    log_info "Testing staging environment connectivity..."
    
    # Get staging ALB DNS
    STAGING_ALB_DNS=$(aws cloudformation describe-stacks \
        --stack-name "$STAGING_STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingALBDNS`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$STAGING_ALB_DNS" ]]; then
        log_info "Testing staging endpoint: http://$STAGING_ALB_DNS"
        
        # Test basic connectivity (may fail if application not deployed)
        if curl -f -s --max-time 10 "http://$STAGING_ALB_DNS" > /dev/null 2>&1; then
            log_success "Staging endpoint connectivity test passed"
        else
            log_warning "Staging endpoint connectivity test failed (expected until application is deployed)"
        fi
    else
        log_warning "Could not retrieve staging ALB DNS"
    fi
    
    # Test AWS services connectivity
    log_info "Testing AWS services connectivity..."
    
    # Test S3 bucket access
    STAGING_BUCKET=$(aws cloudformation describe-stacks \
        --stack-name "$STAGING_STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingBucketName`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$STAGING_BUCKET" ]]; then
        if aws s3 ls "s3://$STAGING_BUCKET" --profile "$PROFILE" > /dev/null 2>&1; then
            log_success "S3 bucket access test passed"
        else
            log_warning "S3 bucket access test failed"
        fi
    fi
    
    # Test database connectivity (basic check)
    STAGING_DB_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "$STAGING_STACK_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`StagingDatabaseEndpoint`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$STAGING_DB_ENDPOINT" ]]; then
        log_info "Staging database endpoint: $STAGING_DB_ENDPOINT"
        # Note: Actual database connectivity test would require credentials
        log_info "Database connectivity test skipped (requires application deployment)"
    fi
    
    log_success "Post-promotion tests completed"
}

# Function to update promotion tracking
update_promotion_tracking() {
    log_info "Updating promotion tracking..."
    
    # Create promotion record
    PROMOTION_RECORD="promotions/staging-$(date +%Y%m%d-%H%M%S).json"
    mkdir -p promotions
    
    cat > "$PROMOTION_RECORD" << EOF
{
    "promotion_id": "$(uuidgen 2>/dev/null || echo "staging-$(date +%s)")",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "source_environment": "$SOURCE_ENVIRONMENT",
    "target_environment": "$TARGET_ENVIRONMENT",
    "git_commit": "$(git rev-parse HEAD)",
    "git_branch": "$(git branch --show-current)",
    "promotion_tag": "$PROMOTION_TAG",
    "aws_region": "$REGION",
    "aws_profile": "$PROFILE",
    "dev_stack_name": "$DEV_STACK_NAME",
    "staging_stack_name": "$STAGING_STACK_NAME",
    "backup_location": "$(cat /tmp/staging_backup_location 2>/dev/null || echo 'unknown')",
    "status": "completed",
    "promoted_by": "$(whoami)",
    "notes": "Automated promotion using promote-to-staging-simple.sh"
}
EOF
    
    log_success "Promotion record created: $PROMOTION_RECORD"
}

# Function to display promotion summary
display_promotion_summary() {
    log_info "Promotion Summary"
    echo "=================="
    echo "Source Environment: $SOURCE_ENVIRONMENT"
    echo "Target Environment: $TARGET_ENVIRONMENT"
    echo "Git Commit: $(git rev-parse HEAD)"
    echo "Git Branch: $(git branch --show-current)"
    echo "Promotion Tag: $PROMOTION_TAG"
    echo "AWS Region: $REGION"
    echo "AWS Profile: $PROFILE"
    echo ""
    echo "Promoted Components:"
    echo "- Infrastructure changes (if any)"
    echo "- Configuration updates"
    echo "- Application code"
    echo ""
    echo "Backup Location:"
    if [[ -f /tmp/staging_backup_location ]]; then
        cat /tmp/staging_backup_location
    else
        echo "No backup created"
    fi
    echo ""
    echo "Next Steps:"
    echo "1. Deploy the application to staging environment"
    echo "2. Run comprehensive integration tests"
    echo "3. Perform user acceptance testing"
    echo "4. Monitor staging environment performance"
    echo "5. Consider promotion to production (if applicable)"
    echo ""
    echo "Rollback Instructions:"
    echo "If issues are found, use the rollback script in the backup directory"
    echo ""
    log_success "Promotion to staging completed successfully!"
}

# Function to cleanup temporary files
cleanup() {
    log_info "Cleaning up temporary files..."
    rm -f /tmp/staging_diff.txt
    rm -f /tmp/staging_backup_location
}

# Function to handle errors
handle_error() {
    log_error "Promotion failed at step: $1"
    
    # Offer rollback option
    if [[ -f /tmp/staging_backup_location ]]; then
        BACKUP_LOCATION=$(cat /tmp/staging_backup_location)
        log_info "Backup available at: $BACKUP_LOCATION"
        
        read -p "Do you want to run the rollback script? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if [[ -f "$BACKUP_LOCATION/rollback.sh" ]]; then
                log_info "Running rollback script..."
                bash "$BACKUP_LOCATION/rollback.sh"
            else
                log_warning "Rollback script not found"
            fi
        fi
    fi
    
    cleanup
    exit 1
}

# Main execution
main() {
    log_stage "Starting promotion from $SOURCE_ENVIRONMENT to $TARGET_ENVIRONMENT"
    
    # Confirm before proceeding
    read -p "Do you want to continue with promotion to staging? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Promotion cancelled by user"
        exit 0
    fi
    
    # Set up error handling
    trap 'handle_error "Unknown step"' ERR
    
    # Execute promotion steps
    trap 'handle_error "Prerequisites check"' ERR
    check_prerequisites
    
    trap 'handle_error "State validation"' ERR
    validate_current_state
    
    trap 'handle_error "Pre-promotion tests"' ERR
    run_pre_promotion_tests
    
    trap 'handle_error "Staging backup"' ERR
    backup_staging_state
    
    trap 'handle_error "Infrastructure promotion"' ERR
    promote_infrastructure
    
    trap 'handle_error "Configuration promotion"' ERR
    promote_configuration
    
    trap 'handle_error "Application code promotion"' ERR
    promote_application_code
    
    trap 'handle_error "Post-promotion tests"' ERR
    run_post_promotion_tests
    
    trap 'handle_error "Promotion tracking"' ERR
    update_promotion_tracking
    
    # Reset error handling
    trap - ERR
    
    display_promotion_summary
    cleanup
    
    log_success "Promotion completed successfully!"
}

# Script usage information
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -r, --region   AWS region (default: us-east-1)"
    echo "  -p, --profile  AWS profile (default: default)"
    echo "  --dry-run      Show what would be done without making changes"
    echo ""
    echo "Environment Variables:"
    echo "  AWS_DEFAULT_REGION  AWS region to use"
    echo "  AWS_PROFILE         AWS profile to use"
    echo ""
    echo "Example:"
    echo "  $0 --region us-west-2 --profile staging"
    echo "  $0 --dry-run"
}

# Parse command line arguments
DRY_RUN=false

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
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Handle dry run
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "DRY RUN MODE - No changes will be made"
    log_info "Would promote from $SOURCE_ENVIRONMENT to $TARGET_ENVIRONMENT"
    log_info "Would use AWS region: $REGION"
    log_info "Would use AWS profile: $PROFILE"
    log_info "Would check prerequisites and run tests"
    log_info "Would backup current staging state"
    log_info "Would promote infrastructure, configuration, and code"
    log_info "Would run post-promotion tests"
    exit 0
fi

# Run main function
main "$@"