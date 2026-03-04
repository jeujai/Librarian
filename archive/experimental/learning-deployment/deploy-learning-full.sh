#!/bin/bash

# Deploy full-featured learning version of Multimodal Librarian
# This script builds and deploys the cost-optimized version with all features

set -e

echo "🚀 Starting full-featured learning deployment..."

# Configuration
AWS_REGION="us-east-1"
ECR_REPOSITORY="multimodal-librarian-learning"
CLUSTER_NAME="multimodal-librarian-learning-cluster"
SERVICE_NAME="multimodal-librarian-learning-service"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

echo "📋 Configuration:"
echo "  AWS Region: ${AWS_REGION}"
echo "  ECR Repository: ${ECR_URI}"
echo "  ECS Cluster: ${CLUSTER_NAME}"
echo "  ECS Service: ${SERVICE_NAME}"

# Step 1: Build the learning Docker image
echo "🔨 Building learning Docker image..."
docker build -f Dockerfile.learning -t ${ECR_REPOSITORY}:learning .
docker tag ${ECR_REPOSITORY}:learning ${ECR_URI}:learning
docker tag ${ECR_REPOSITORY}:learning ${ECR_URI}:latest

# Step 2: Login to ECR and push image
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "📤 Pushing image to ECR..."
docker push ${ECR_URI}:learning
docker push ${ECR_URI}:latest

# Step 3: Update ECS service
echo "🔄 Updating ECS service..."
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

# Step 6: Get load balancer URL
echo "🌐 Getting application URL..."
ALB_DNS=$(aws cloudformation describe-stacks \
    --stack-name MultimodalLibrarianLearningStack \
    --region ${AWS_REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDnsName`].OutputValue' \
    --output text 2>/dev/null || echo "Not found")

if [ "$ALB_DNS" != "Not found" ] && [ -n "$ALB_DNS" ]; then
    echo "🎉 Deployment completed successfully!"
    echo ""
    echo "📱 Application URLs:"
    echo "  Main API: http://${ALB_DNS}/"
    echo "  Chat Interface: http://${ALB_DNS}/chat"
    echo "  API Documentation: http://${ALB_DNS}/docs"
    echo "  Health Check: http://${ALB_DNS}/health"
    echo "  Feature Status: http://${ALB_DNS}/features"
    echo ""
    echo "🧪 Test the deployment:"
    echo "  curl http://${ALB_DNS}/health/simple"
    echo "  curl http://${ALB_DNS}/features"
else
    echo "⚠️  Could not retrieve load balancer URL"
    echo "   Check AWS CloudFormation stack outputs manually"
fi

echo ""
echo "💰 Cost Optimization Features:"
echo "  ✅ CPU-only PyTorch (smaller image)"
echo "  ✅ Minimal system dependencies"
echo "  ✅ Graceful fallbacks for missing features"
echo "  ✅ 2 worker processes (vs 4 in production)"
echo "  ✅ Optimized container size"
echo ""
echo "🎯 Available Features:"
echo "  ✅ Full web-based chat interface"
echo "  ✅ PDF document processing"
echo "  ✅ Vector search with Milvus"
echo "  ✅ Knowledge graph with Neo4j"
echo "  ✅ Database integration"
echo "  ✅ Real-time WebSocket chat"
echo "  ✅ Export functionality"
echo "  ✅ ML training endpoints"
echo "  ✅ Security and authentication"
echo ""
echo "📊 Monitor your deployment:"
echo "  aws logs tail /aws/ecs/multimodal-librarian-learning --follow"

exit 0