#!/bin/bash

# Deploy AI Chat Integration
# This script helps deploy the AI chat functionality to the existing infrastructure

set -e

echo "🚀 Deploying AI Chat Integration to Multimodal Librarian"
echo "========================================================="

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "❌ Error: AWS CLI not configured. Please run 'aws configure'"
    exit 1
fi

echo "✅ AWS CLI configured"

# Step 1: Setup AI API Keys
echo ""
echo "📋 Step 1: Setting up AI API Keys"
echo "=================================="

read -p "Do you want to configure AI API keys in AWS Secrets Manager? (y/N): " setup_keys
if [[ $setup_keys =~ ^[Yy]$ ]]; then
    python3 scripts/setup-ai-api-keys.py setup
    if [ $? -ne 0 ]; then
        echo "❌ Failed to setup AI API keys"
        exit 1
    fi
else
    echo "⚠️  Skipping AI API key setup. Make sure keys are configured manually."
fi

# Step 2: Apply Database Migration
echo ""
echo "📋 Step 2: Applying Database Migration"
echo "======================================"

echo "Applying chat_messages table migration..."
python3 -m src.multimodal_librarian.database.migrations.add_chat_messages
if [ $? -ne 0 ]; then
    echo "❌ Failed to apply database migration"
    exit 1
fi

echo "✅ Database migration applied successfully"

# Step 3: Build and Push Docker Image
echo ""
echo "📋 Step 3: Building and Pushing Docker Image"
echo "============================================="

# Get ECR repository URL
ECR_REPO="591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian"
IMAGE_TAG="ai-chat-$(date +%Y%m%d-%H%M%S)"

echo "Building Docker image with AI chat integration..."

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO

# Build image
docker build -t $ECR_REPO:$IMAGE_TAG .
if [ $? -ne 0 ]; then
    echo "❌ Failed to build Docker image"
    exit 1
fi

# Tag as latest
docker tag $ECR_REPO:$IMAGE_TAG $ECR_REPO:latest

# Push images
echo "Pushing Docker images..."
docker push $ECR_REPO:$IMAGE_TAG
docker push $ECR_REPO:latest

echo "✅ Docker images pushed successfully"
echo "   Image: $ECR_REPO:$IMAGE_TAG"
echo "   Latest: $ECR_REPO:latest"

# Step 4: Update ECS Task Definition
echo ""
echo "📋 Step 4: Updating ECS Task Definition"
echo "======================================="

# Create updated task definition with AI API keys
cat > task-definition-ai-chat.json << EOF
{
  "family": "multimodal-lib-prod",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "executionRoleArn": "arn:aws:iam::591222106065:role/multimodal-lib-prod-ecs-execution-role",
  "taskRoleArn": "arn:aws:iam::591222106065:role/multimodal-lib-prod-ecs-task-role",
  "containerDefinitions": [
    {
      "name": "multimodal-lib-prod",
      "image": "$ECR_REPO:$IMAGE_TAG",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "essential": true,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/multimodal-lib-prod",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "environment": [
        {
          "name": "ENVIRONMENT",
          "value": "production"
        },
        {
          "name": "LOG_LEVEL",
          "value": "INFO"
        },
        {
          "name": "API_HOST",
          "value": "0.0.0.0"
        },
        {
          "name": "API_PORT",
          "value": "8000"
        }
      ],
      "secrets": [
        {
          "name": "POSTGRES_HOST",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-lib-prod/database:host::"
        },
        {
          "name": "POSTGRES_PORT",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-lib-prod/database:port::"
        },
        {
          "name": "POSTGRES_DB",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-lib-prod/database:dbname::"
        },
        {
          "name": "POSTGRES_USER",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-lib-prod/database:username::"
        },
        {
          "name": "POSTGRES_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-lib-prod/database:password::"
        },
        {
          "name": "GEMINI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-lib-prod/ai-api-keys:GEMINI_API_KEY::"
        },
        {
          "name": "OPENAI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-lib-prod/ai-api-keys:OPENAI_API_KEY::"
        },
        {
          "name": "ANTHROPIC_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-lib-prod/ai-api-keys:ANTHROPIC_API_KEY::"
        }
      ],
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "curl -f http://localhost:8000/health/simple || exit 1"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
EOF

echo "Registering new task definition..."
aws ecs register-task-definition --cli-input-json file://task-definition-ai-chat.json > /dev/null

if [ $? -ne 0 ]; then
    echo "❌ Failed to register task definition"
    exit 1
fi

echo "✅ Task definition registered successfully"

# Step 5: Update ECS Service
echo ""
echo "📋 Step 5: Updating ECS Service"
echo "==============================="

echo "Updating ECS service with new task definition..."
aws ecs update-service \
    --cluster multimodal-lib-prod \
    --service multimodal-lib-prod \
    --task-definition multimodal-lib-prod \
    --force-new-deployment > /dev/null

if [ $? -ne 0 ]; then
    echo "❌ Failed to update ECS service"
    exit 1
fi

echo "✅ ECS service update initiated"

# Step 6: Wait for Deployment
echo ""
echo "📋 Step 6: Waiting for Deployment"
echo "================================="

echo "Waiting for service to stabilize (this may take a few minutes)..."
aws ecs wait services-stable \
    --cluster multimodal-lib-prod \
    --services multimodal-lib-prod

if [ $? -ne 0 ]; then
    echo "⚠️  Service deployment may have issues. Check ECS console for details."
else
    echo "✅ Service deployment completed successfully"
fi

# Step 7: Test Deployment
echo ""
echo "📋 Step 7: Testing Deployment"
echo "============================="

# Get load balancer URL
ALB_URL=$(aws elbv2 describe-load-balancers \
    --names multimodal-lib-prod-alb \
    --query 'LoadBalancers[0].DNSName' \
    --output text 2>/dev/null)

if [ "$ALB_URL" != "None" ] && [ -n "$ALB_URL" ]; then
    echo "Testing health endpoint..."
    if curl -f -s "http://$ALB_URL/health/simple" > /dev/null; then
        echo "✅ Health check passed"
        
        echo "Testing AI chat status..."
        if curl -f -s "http://$ALB_URL/api/chat/status" > /dev/null; then
            echo "✅ AI chat endpoint accessible"
        else
            echo "⚠️  AI chat endpoint not yet ready (may need more time)"
        fi
    else
        echo "⚠️  Health check failed (service may still be starting)"
    fi
    
    echo ""
    echo "🌐 Application URLs:"
    echo "   Main: http://$ALB_URL"
    echo "   Chat: http://$ALB_URL/chat"
    echo "   Docs: http://$ALB_URL/docs"
    echo "   AI Status: http://$ALB_URL/api/chat/status"
else
    echo "⚠️  Could not determine load balancer URL"
fi

# Cleanup
rm -f task-definition-ai-chat.json

echo ""
echo "🎉 AI Chat Integration Deployment Complete!"
echo "==========================================="
echo ""
echo "✅ What was deployed:"
echo "   • AI service with Gemini, OpenAI, and Claude support"
echo "   • WebSocket-based real-time chat"
echo "   • Conversation history and context management"
echo "   • Multi-provider fallback system"
echo "   • Enhanced chat interface"
echo ""
echo "📋 Next steps:"
echo "   1. Test the chat interface at: http://$ALB_URL/chat"
echo "   2. Check AI provider status at: http://$ALB_URL/api/chat/providers"
echo "   3. Monitor logs in CloudWatch for any issues"
echo "   4. Consider adding document upload for RAG functionality"
echo ""
echo "🔧 Troubleshooting:"
echo "   • Check ECS service logs in CloudWatch"
echo "   • Verify AI API keys are set correctly"
echo "   • Ensure database migration was applied"
echo ""

# Run integration test
echo "🧪 Running integration test..."
python3 scripts/test-ai-integration.py

echo ""
echo "🚀 Deployment complete! Your AI-powered chat is ready to use."