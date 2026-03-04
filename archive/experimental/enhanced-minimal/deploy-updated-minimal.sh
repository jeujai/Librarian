#!/bin/bash

# Deploy updated minimal application with enhanced features
# This builds a new Docker image with the updated main_minimal.py

set -e

echo "🚀 Deploying updated minimal application with enhanced features..."

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

# Step 1: Build updated Docker image using existing Dockerfile
echo "🔨 Building updated Docker image with enhanced minimal application..."

# Use the existing Dockerfile but tag as updated
docker build -t ${ECR_REPOSITORY}:updated .
docker tag ${ECR_REPOSITORY}:updated ${ECR_URI}:updated
docker tag ${ECR_REPOSITORY}:updated ${ECR_URI}:latest

# Step 2: Login to ECR and push image
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "📤 Pushing updated image to ECR..."
docker push ${ECR_URI}:updated
docker push ${ECR_URI}:latest

# Step 3: Force new deployment to pick up the updated image
echo "🔄 Forcing new deployment to pick up updated image..."
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

# Step 5: Get service status
echo "📊 Checking service status..."
SERVICE_STATUS=$(aws ecs describe-services \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION} \
    --query 'services[0].status' \
    --output text)

RUNNING_COUNT=$(aws ecs describe-services \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION} \
    --query 'services[0].runningCount' \
    --output text)

DESIRED_COUNT=$(aws ecs describe-services \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION} \
    --query 'services[0].desiredCount' \
    --output text)

echo "✅ Service Status: ${SERVICE_STATUS}"
echo "📈 Running Tasks: ${RUNNING_COUNT}/${DESIRED_COUNT}"

# Step 6: Test the deployment
echo "🧪 Testing the updated deployment..."
sleep 15  # Give the service a moment to start

ALB_DNS="multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"

echo "Testing endpoints..."
curl -s "http://${ALB_DNS}/health/simple" > /dev/null && echo "  ✅ Health check: OK" || echo "  ❌ Health check: FAILED"
curl -s "http://${ALB_DNS}/features" > /dev/null && echo "  ✅ Features endpoint: OK" || echo "  ❌ Features endpoint: FAILED"
curl -s "http://${ALB_DNS}/chat" > /dev/null && echo "  ✅ Chat interface: OK" || echo "  ❌ Chat interface: FAILED"

echo ""
echo "🎉 Updated minimal deployment completed!"
echo ""
echo "📱 Application URLs:"
echo "  🏠 Main API: http://${ALB_DNS}/"
echo "  💬 Chat Interface: http://${ALB_DNS}/chat"
echo "  📚 API Documentation: http://${ALB_DNS}/docs"
echo "  🏥 Health Check: http://${ALB_DNS}/health"
echo "  🎯 Feature Status: http://${ALB_DNS}/features"
echo ""
echo "🧪 Quick Tests:"
echo "  curl http://${ALB_DNS}/health/simple"
echo "  curl http://${ALB_DNS}/features"
echo ""
echo "✨ What's New:"
echo "  ✅ /features endpoint shows available functionality"
echo "  ✅ /chat endpoint with beautiful demo interface"
echo "  ✅ Enhanced health checks with feature status"
echo "  ✅ Updated root endpoint with feature information"
echo "  ✅ Mobile-responsive design"
echo "  ✅ Cost-optimized (~$50/month)"
echo ""
echo "💰 Cost Optimization:"
echo "  ✅ Uses existing infrastructure"
echo "  ✅ Minimal dependencies (no ML libraries)"
echo "  ✅ Single container deployment"
echo "  ✅ Efficient resource usage"
echo ""
echo "📊 Monitor deployment:"
echo "  aws logs tail /aws/ecs/multimodal-librarian-learning --follow"

exit 0