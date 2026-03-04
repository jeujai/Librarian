#!/bin/bash

# Fix Full ML Deployment Secrets Configuration
# This script rebuilds and redeploys the application with corrected secret references

set -e

echo "🔧 Fixing Full ML deployment secrets configuration..."

# Build and push the corrected image
echo "📦 Building corrected Docker image..."
docker build -f Dockerfile.full-ml -t multimodal-librarian-full-ml:secrets-fix .

# Tag for ECR
docker tag multimodal-librarian-full-ml:secrets-fix 591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian-full-ml:secrets-fix

# Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 591222106065.dkr.ecr.us-east-1.amazonaws.com

# Push the image
echo "⬆️ Pushing corrected image to ECR..."
docker push 591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian-full-ml:secrets-fix

# Update the ECS service to use the new image
echo "🚀 Updating ECS service with corrected image..."
aws ecs update-service \
    --cluster multimodal-librarian-full-ml \
    --service multimodal-librarian-full-ml-web \
    --force-new-deployment \
    --region us-east-1

echo "✅ Deployment update initiated. Monitoring service status..."

# Wait for deployment to complete
aws ecs wait services-stable \
    --cluster multimodal-librarian-full-ml \
    --services multimodal-librarian-full-ml-web \
    --region us-east-1

echo "🎉 Full ML deployment secrets fix completed successfully!"

# Test the corrected endpoints
echo "🧪 Testing corrected database connectivity..."
curl -s http://multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com/test/database | jq .

echo "🧪 Testing corrected Redis connectivity..."
curl -s http://multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com/test/redis | jq .

echo "✅ Full ML deployment is now using correct secret references!"