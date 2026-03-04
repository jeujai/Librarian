#!/bin/bash

# Simple build and push script for learning deployment
# This script builds the Docker image and pushes it to ECR

set -e

echo "🚀 Building and pushing Docker image for learning deployment"
echo "=========================================================="

# Configuration
PROJECT_NAME="multimodal-librarian"
ENVIRONMENT="learning"
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-${ENVIRONMENT}"

# Get version from git or use timestamp
if git rev-parse --git-dir > /dev/null 2>&1; then
    VERSION=$(git rev-parse --short HEAD)
    echo "📋 Using git commit as version: $VERSION"
else
    VERSION=$(date +%Y%m%d-%H%M%S)
    echo "📋 Using timestamp as version: $VERSION"
fi

echo "📦 ECR Repository: $ECR_REPOSITORY"
echo "🏷️  Image Version: $VERSION"

# Login to ECR
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPOSITORY

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -f Dockerfile.learning -t $PROJECT_NAME:$VERSION .
docker tag $PROJECT_NAME:$VERSION $ECR_REPOSITORY:$VERSION
docker tag $PROJECT_NAME:$VERSION $ECR_REPOSITORY:latest

echo "✅ Image built successfully:"
echo "   Local: $PROJECT_NAME:$VERSION"
echo "   ECR: $ECR_REPOSITORY:$VERSION"
echo "   ECR: $ECR_REPOSITORY:latest"

# Push to ECR
echo "📤 Pushing image to ECR..."
docker push $ECR_REPOSITORY:$VERSION
docker push $ECR_REPOSITORY:latest

echo "✅ Image pushed successfully!"

# Show image details
echo "📋 Image Details:"
aws ecr describe-images \
    --repository-name $PROJECT_NAME-$ENVIRONMENT \
    --image-ids imageTag=$VERSION \
    --query 'imageDetails[0].[imageTags[0],imageSizeInBytes,imagePushedAt]' \
    --output table

echo "🎉 Build and push completed successfully!"
echo "=========================================================="
echo ""
echo "📝 Next Steps:"
echo "1. Use this image in ECS task definitions"
echo "2. Deploy to ECS cluster"
echo "3. Update load balancer target groups"
echo ""
echo "🔗 Image URIs:"
echo "   Latest: $ECR_REPOSITORY:latest"
echo "   Version: $ECR_REPOSITORY:$VERSION"