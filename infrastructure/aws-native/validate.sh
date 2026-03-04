#!/bin/bash

# Terraform Infrastructure Validation Script
# This script validates the Terraform configuration and performs basic checks

set -e

echo "🔍 Terraform Infrastructure Validation"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        "INFO")
            echo -e "${BLUE}ℹ️  ${message}${NC}"
            ;;
        "SUCCESS")
            echo -e "${GREEN}✅ ${message}${NC}"
            ;;
        "WARNING")
            echo -e "${YELLOW}⚠️  ${message}${NC}"
            ;;
        "ERROR")
            echo -e "${RED}❌ ${message}${NC}"
            ;;
    esac
}

# Check if required tools are installed
check_prerequisites() {
    print_status "INFO" "Checking prerequisites..."
    
    # Check Terraform
    if command -v terraform &> /dev/null; then
        TERRAFORM_VERSION=$(terraform version -json | jq -r '.terraform_version')
        print_status "SUCCESS" "Terraform found: v${TERRAFORM_VERSION}"
    else
        print_status "ERROR" "Terraform not found. Please install Terraform >= 1.0"
        exit 1
    fi
    
    # Check AWS CLI
    if command -v aws &> /dev/null; then
        AWS_VERSION=$(aws --version | cut -d/ -f2 | cut -d' ' -f1)
        print_status "SUCCESS" "AWS CLI found: v${AWS_VERSION}"
    else
        print_status "WARNING" "AWS CLI not found. Some validations may be skipped"
    fi
    
    # Check jq
    if command -v jq &> /dev/null; then
        print_status "SUCCESS" "jq found"
    else
        print_status "WARNING" "jq not found. JSON parsing may be limited"
    fi
}

# Validate Terraform configuration
validate_terraform() {
    print_status "INFO" "Validating Terraform configuration..."
    
    # Initialize Terraform (without backend)
    if terraform init -backend=false > /dev/null 2>&1; then
        print_status "SUCCESS" "Terraform initialization successful"
    else
        print_status "ERROR" "Terraform initialization failed"
        return 1
    fi
    
    # Validate configuration
    if terraform validate > /dev/null 2>&1; then
        print_status "SUCCESS" "Terraform configuration is valid"
    else
        print_status "ERROR" "Terraform configuration validation failed"
        terraform validate
        return 1
    fi
    
    # Check formatting
    if terraform fmt -check > /dev/null 2>&1; then
        print_status "SUCCESS" "Terraform formatting is correct"
    else
        print_status "WARNING" "Terraform formatting issues found. Run 'terraform fmt' to fix"
    fi
}

# Check for required files
check_required_files() {
    print_status "INFO" "Checking required files..."
    
    local required_files=(
        "terraform.tf"
        "main.tf"
        "variables.tf"
        "outputs.tf"
        "terraform.tfvars.example"
        "backend.tf.example"
        "modules/vpc/main.tf"
        "modules/security/main.tf"
    )
    
    for file in "${required_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_status "SUCCESS" "Found: $file"
        else
            print_status "ERROR" "Missing: $file"
        fi
    done
}

# Validate variable files
validate_variables() {
    print_status "INFO" "Validating variable configuration..."
    
    # Check if terraform.tfvars exists
    if [[ -f "terraform.tfvars" ]]; then
        print_status "SUCCESS" "terraform.tfvars found"
        
        # Check for sensitive values
        if grep -q "REPLACE-WITH" terraform.tfvars 2>/dev/null; then
            print_status "WARNING" "Found placeholder values in terraform.tfvars"
        fi
    else
        print_status "WARNING" "terraform.tfvars not found. Using defaults from terraform.tfvars.example"
    fi
    
    # Validate example file
    if [[ -f "terraform.tfvars.example" ]]; then
        print_status "SUCCESS" "terraform.tfvars.example found"
    else
        print_status "ERROR" "terraform.tfvars.example missing"
    fi
}

# Check AWS credentials and permissions
check_aws_credentials() {
    if ! command -v aws &> /dev/null; then
        print_status "WARNING" "AWS CLI not available, skipping credential check"
        return 0
    fi
    
    print_status "INFO" "Checking AWS credentials..."
    
    # Check if credentials are configured
    if aws sts get-caller-identity > /dev/null 2>&1; then
        ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        USER_ARN=$(aws sts get-caller-identity --query Arn --output text)
        print_status "SUCCESS" "AWS credentials valid"
        print_status "INFO" "Account ID: ${ACCOUNT_ID}"
        print_status "INFO" "User/Role: ${USER_ARN}"
    else
        print_status "ERROR" "AWS credentials not configured or invalid"
        print_status "INFO" "Run 'aws configure' to set up credentials"
        return 1
    fi
}

# Validate module structure
validate_modules() {
    print_status "INFO" "Validating module structure..."
    
    local modules=("vpc" "security")
    
    for module in "${modules[@]}"; do
        local module_path="modules/${module}"
        
        if [[ -d "$module_path" ]]; then
            print_status "SUCCESS" "Module directory found: $module"
            
            # Check required module files
            local module_files=("main.tf" "variables.tf" "outputs.tf")
            for file in "${module_files[@]}"; do
                if [[ -f "${module_path}/${file}" ]]; then
                    print_status "SUCCESS" "  Found: ${module}/${file}"
                else
                    print_status "ERROR" "  Missing: ${module}/${file}"
                fi
            done
        else
            print_status "ERROR" "Module directory missing: $module"
        fi
    done
}

# Security checks
security_checks() {
    print_status "INFO" "Performing security checks..."
    
    # Check for hardcoded secrets
    if grep -r "password\|secret\|key" --include="*.tf" . | grep -v "variable\|output\|description" > /dev/null 2>&1; then
        print_status "WARNING" "Potential hardcoded secrets found. Review carefully."
    else
        print_status "SUCCESS" "No obvious hardcoded secrets found"
    fi
    
    # Check for public access
    if grep -r "0.0.0.0/0" --include="*.tf" . > /dev/null 2>&1; then
        print_status "WARNING" "Found 0.0.0.0/0 CIDR blocks. Ensure they are intentional."
    fi
    
    # Check encryption settings
    if grep -r "encrypt" --include="*.tf" . > /dev/null 2>&1; then
        print_status "SUCCESS" "Encryption configurations found"
    else
        print_status "WARNING" "No encryption configurations found"
    fi
}

# Plan validation (dry run)
validate_plan() {
    print_status "INFO" "Validating Terraform plan (dry run)..."
    
    # Only run if terraform.tfvars exists
    if [[ ! -f "terraform.tfvars" ]]; then
        print_status "WARNING" "Skipping plan validation - terraform.tfvars not found"
        return 0
    fi
    
    # Run terraform plan
    if terraform plan -detailed-exitcode > /dev/null 2>&1; then
        print_status "SUCCESS" "Terraform plan validation successful"
    else
        local exit_code=$?
        if [[ $exit_code -eq 2 ]]; then
            print_status "INFO" "Terraform plan shows changes (expected for new deployment)"
        else
            print_status "ERROR" "Terraform plan validation failed"
            return 1
        fi
    fi
}

# Cost estimation
estimate_costs() {
    print_status "INFO" "Estimating infrastructure costs..."
    
    # This is a basic estimation - in production, use tools like Infracost
    print_status "INFO" "Production environment estimated monthly costs:"
    echo "  • VPC & Networking: ~\$50-100"
    echo "  • ECS Fargate: ~\$200-400"
    echo "  • Neptune: ~\$450-600"
    echo "  • OpenSearch: ~\$400-500"
    echo "  • Load Balancer: ~\$25-50"
    echo "  • CloudWatch: ~\$50-100"
    echo "  • S3 & Other: ~\$25-50"
    echo "  • Total Estimated: ~\$1,200-1,800/month"
    print_status "WARNING" "Use AWS Cost Calculator for accurate estimates"
}

# Main execution
main() {
    echo
    check_prerequisites
    echo
    
    check_required_files
    echo
    
    validate_variables
    echo
    
    validate_modules
    echo
    
    validate_terraform
    echo
    
    check_aws_credentials
    echo
    
    security_checks
    echo
    
    validate_plan
    echo
    
    estimate_costs
    echo
    
    print_status "SUCCESS" "Validation complete!"
    echo
    echo "Next steps:"
    echo "1. Review and customize terraform.tfvars"
    echo "2. Set up remote state backend (optional)"
    echo "3. Run 'terraform plan' to review changes"
    echo "4. Run 'terraform apply' to deploy infrastructure"
}

# Run main function
main "$@"