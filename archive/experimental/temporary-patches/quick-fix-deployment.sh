#!/bin/bash

# Quick fix for current deployment - switch to learning main without full rebuild
# This updates the ECS task definition to use the learning version

set -e

echo "🔧 Quick fix: Switching to learning application..."

# Configuration
AWS_REGION="us-east-1"
CLUSTER_NAME="multimodal-librarian-learning-cluster"
SERVICE_NAME="multimodal-librarian-learning-service"

# Get current task definition
echo "📋 Getting current task definition..."
TASK_DEF_ARN=$(aws ecs describe-services \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION} \
    --query 'services[0].taskDefinition' \
    --output text)

echo "Current task definition: ${TASK_DEF_ARN}"

# Get task definition details
TASK_DEF_JSON=$(aws ecs describe-task-definition \
    --task-definition ${TASK_DEF_ARN} \
    --region ${AWS_REGION})

# Extract the task definition and modify the command
echo "🔄 Creating new task definition with learning application..."

# Create new task definition with updated command
NEW_TASK_DEF=$(echo "${TASK_DEF_JSON}" | jq '
    .taskDefinition |
    del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .placementConstraints, .compatibilities, .registeredAt, .registeredBy) |
    .containerDefinitions[0].command = ["gunicorn", "multimodal_librarian.main_learning:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120"] |
    .family = .family + "-learning"
')

# Register new task definition
echo "📝 Registering new task definition..."
NEW_TASK_DEF_ARN=$(echo "${NEW_TASK_DEF}" | aws ecs register-task-definition \
    --region ${AWS_REGION} \
    --cli-input-json file:///dev/stdin \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "New task definition: ${NEW_TASK_DEF_ARN}"

# Update service to use new task definition
echo "🚀 Updating ECS service..."
aws ecs update-service \
    --cluster ${CLUSTER_NAME} \
    --service ${SERVICE_NAME} \
    --task-definition ${NEW_TASK_DEF_ARN} \
    --region ${AWS_REGION}

# Wait for deployment to complete
echo "⏳ Waiting for deployment to complete..."
aws ecs wait services-stable \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION}

echo "✅ Quick fix deployment completed!"
echo ""
echo "🧪 Test the deployment:"
echo "  curl http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com/health/simple"
echo "  curl http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com/features"
echo ""
echo "📱 Access the application:"
echo "  http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com/chat"

exit 0