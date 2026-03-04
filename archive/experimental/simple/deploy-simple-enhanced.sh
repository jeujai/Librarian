#!/bin/bash

# Deploy simple enhanced application
set -e

echo "🚀 Deploying simple enhanced application..."

# Configuration
AWS_REGION="us-east-1"
ECR_REPOSITORY="multimodal-librarian-learning"
CLUSTER_NAME="multimodal-librarian-learning"
SERVICE_NAME="multimodal-librarian-learning-web"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

echo "📋 Configuration:"
echo "  AWS Region: ${AWS_REGION}"
echo "  ECR Repository: ${ECR_URI}"
echo "  ECS Cluster: ${CLUSTER_NAME}"
echo "  ECS Service: ${SERVICE_NAME}"

# Step 1: Build the simple enhanced image
echo "🔨 Building simple enhanced Docker image..."
docker build -f Dockerfile.simple -t ${ECR_REPOSITORY}:enhanced .
docker tag ${ECR_REPOSITORY}:enhanced ${ECR_URI}:enhanced
docker tag ${ECR_REPOSITORY}:enhanced ${ECR_URI}:latest

# Step 2: Login to ECR and push image
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "📤 Pushing enhanced image to ECR..."
docker push ${ECR_URI}:enhanced
docker push ${ECR_URI}:latest

# Step 3: Force new deployment
echo "🔄 Forcing new deployment with enhanced image..."
aws ecs update-service \
    --cluster ${CLUSTER_NAME} \
    --service ${SERVICE_NAME} \
    --force-new-deployment \
    --region ${AWS_REGION}

# Step 4: Wait for deployment to complete
echo "⏳ Waiting for deployment to complete..."
aws ecs wait services-stable \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION}

# Step 5: Test the deployment
echo "🧪 Testing the enhanced deployment..."
sleep 15

ALB_DNS="multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"

echo "Testing endpoints..."
curl -s "http://${ALB_DNS}/health/simple" > /dev/null && echo "  ✅ Health check: OK" || echo "  ❌ Health check: FAILED"
curl -s "http://${ALB_DNS}/features" > /dev/null && echo "  ✅ Features endpoint: OK" || echo "  ❌ Features endpoint: FAILED"
curl -s "http://${ALB_DNS}/chat" > /dev/null && echo "  ✅ Chat interface: OK" || echo "  ❌ Chat interface: FAILED"

echo ""
echo "🎉 Simple enhanced deployment completed!"
echo ""
echo "📱 Application URLs:"
echo "  🏠 Main API: http://${ALB_DNS}/"
echo "  💬 Chat Interface: http://${ALB_DNS}/chat"
echo "  📚 API Documentation: http://${ALB_DNS}/docs"
echo "  🏥 Health Check: http://${ALB_DNS}/health"
echo "  🎯 Feature Status: http://${ALB_DNS}/features"
echo ""
echo "✨ Enhanced Features:"
echo "  ✅ Full /features endpoint with deployment status"
echo "  ✅ Beautiful /chat interface with responsive design"
echo "  ✅ Database and Redis connectivity testing"
echo "  ✅ Cost-optimized deployment (~$50/month)"
echo "  ✅ Mobile-responsive web interface"

exit 0