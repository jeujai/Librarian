#!/bin/bash

# Deploy Functional Chat Enhancement
# This script deploys the enhanced chat functionality to the existing AWS ECS service

set -e

echo "🚀 Starting Functional Chat Deployment..."

# Configuration
CLUSTER_NAME="multimodal-librarian-learning"
SERVICE_NAME="multimodal-librarian-learning-web"
TASK_DEFINITION_FAMILY="multimodal-librarian-learning-web"
ECR_REPOSITORY="multimodal-librarian-learning"
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Build and push new image
echo "📦 Building functional chat image..."
TIMESTAMP=$(date +%s)
docker build -f Dockerfile.functional-chat -t ${ECR_REPOSITORY}:functional-chat-${TIMESTAMP} .

# Tag for ECR
docker tag ${ECR_REPOSITORY}:functional-chat-${TIMESTAMP} ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:functional-chat-${TIMESTAMP}

# Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Push image
echo "⬆️ Pushing functional chat image..."
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:functional-chat-${TIMESTAMP}

# Get current task definition
echo "📋 Getting current task definition..."
CURRENT_TASK_DEF=$(aws ecs describe-task-definition --task-definition ${TASK_DEFINITION_FAMILY} --region ${AWS_REGION})

# Create new task definition with functional chat image
echo "🔄 Creating new task definition..."
NEW_TASK_DEF=$(echo $CURRENT_TASK_DEF | jq --arg IMAGE "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:functional-chat-${TIMESTAMP}" '
  .taskDefinition |
  .containerDefinitions[0].image = $IMAGE |
  del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .placementConstraints, .compatibilities, .registeredAt, .registeredBy)
')

# Register new task definition
echo "📝 Registering new task definition..."
echo "$NEW_TASK_DEF" > /tmp/new-task-def.json
NEW_TASK_DEF_ARN=$(aws ecs register-task-definition --region ${AWS_REGION} --cli-input-json file:///tmp/new-task-def.json --query 'taskDefinition.taskDefinitionArn' --output text)

echo "✅ New task definition registered: $NEW_TASK_DEF_ARN"

# Update service with new task definition
echo "🔄 Updating ECS service..."
aws ecs update-service \
  --cluster ${CLUSTER_NAME} \
  --service ${SERVICE_NAME} \
  --task-definition ${NEW_TASK_DEF_ARN} \
  --region ${AWS_REGION} \
  --query 'service.serviceName' \
  --output text

echo "⏳ Waiting for service to stabilize..."
aws ecs wait services-stable \
  --cluster ${CLUSTER_NAME} \
  --services ${SERVICE_NAME} \
  --region ${AWS_REGION}

# Get service status
echo "📊 Checking service status..."
SERVICE_STATUS=$(aws ecs describe-services \
  --cluster ${CLUSTER_NAME} \
  --services ${SERVICE_NAME} \
  --region ${AWS_REGION} \
  --query 'services[0].deployments[0].status' \
  --output text)

if [ "$SERVICE_STATUS" = "PRIMARY" ]; then
    echo "✅ Functional chat deployment successful!"
    
    # Get load balancer URL
    LB_URL=$(aws elbv2 describe-load-balancers \
      --names multimodal-librarian-learning \
      --region ${AWS_REGION} \
      --query 'LoadBalancers[0].DNSName' \
      --output text 2>/dev/null || echo "Load balancer URL not found")
    
    if [ "$LB_URL" != "Load balancer URL not found" ]; then
        echo ""
        echo "🌐 Functional Chat URLs:"
        echo "   Main Interface: http://${LB_URL}"
        echo "   Chat Interface: http://${LB_URL}/chat"
        echo "   API Docs: http://${LB_URL}/docs"
        echo "   Features: http://${LB_URL}/features"
        echo "   Health Check: http://${LB_URL}/health"
        echo ""
        echo "💬 Chat Features:"
        echo "   ✅ Intelligent responses"
        echo "   ✅ Conversation context"
        echo "   ✅ WebSocket communication"
        echo "   ✅ Rule-based processing"
        echo "   ✅ Cost-optimized (~$50/month)"
        echo ""
        echo "🎯 Try these sample messages:"
        echo "   - Hello!"
        echo "   - What can you do?"
        echo "   - Tell me about AWS costs"
        echo "   - How does this system work?"
        echo "   - What features are available?"
    fi
    
    echo ""
    echo "🎉 Functional chat is now live and ready for conversations!"
    
else
    echo "❌ Deployment may have issues. Service status: $SERVICE_STATUS"
    exit 1
fi