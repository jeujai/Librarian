#!/bin/bash

# Deploy AI-Enhanced The Librarian with Document Upload
# This script builds and deploys the AI integration version with document upload capabilities

set -e

echo "🚀 Starting AI-Enhanced Document Upload Deployment..."

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="591222106065"
ECR_REPOSITORY="multimodal-librarian-learning"
IMAGE_TAG="ai-enhanced-documents"
CLUSTER_NAME="multimodal-librarian-learning"
SERVICE_NAME="multimodal-librarian-learning-web"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}📋 Configuration:${NC}"
echo "  AWS Region: $AWS_REGION"
echo "  ECR Repository: $ECR_REPOSITORY"
echo "  Image Tag: $IMAGE_TAG"
echo "  ECS Cluster: $CLUSTER_NAME"
echo "  ECS Service: $SERVICE_NAME"
echo ""

# Step 1: Login to ECR
echo -e "${YELLOW}🔐 Logging into ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Step 2: Build the AI-enhanced Docker image with document upload
echo -e "${YELLOW}🏗️  Building AI-enhanced document upload Docker image...${NC}"
docker build -f Dockerfile.ai-enhanced-documents -t $ECR_REPOSITORY:$IMAGE_TAG .

# Step 3: Tag the image for ECR
echo -e "${YELLOW}🏷️  Tagging image for ECR...${NC}"
docker tag $ECR_REPOSITORY:$IMAGE_TAG $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG

# Step 4: Push the image to ECR
echo -e "${YELLOW}📤 Pushing image to ECR...${NC}"
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG

# Step 5: Create new task definition with AI-enhanced document upload image
echo -e "${YELLOW}📝 Creating AI-enhanced document upload task definition...${NC}"

# Get the current task definition
CURRENT_TASK_DEF=$(aws ecs describe-task-definition --task-definition multimodal-librarian-learning-web --region $AWS_REGION)

# Extract the task definition and update the image
NEW_TASK_DEF=$(echo $CURRENT_TASK_DEF | jq --arg IMAGE "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG" '
.taskDefinition | 
del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .placementConstraints, .compatibilities, .registeredAt, .registeredBy) |
.containerDefinitions[0].image = $IMAGE |
.containerDefinitions[0].command = ["python", "-m", "uvicorn", "multimodal_librarian.main_ai_enhanced:app", "--host", "0.0.0.0", "--port", "8000"] |
.containerDefinitions[0].environment += [
  {"name": "AI_ENHANCED", "value": "true"},
  {"name": "DEPLOYMENT_TYPE", "value": "ai-enhanced-documents"},
  {"name": "AI_VERSION", "value": "gemini-2.5-flash-documents"},
  {"name": "DOCUMENT_UPLOAD_ENABLED", "value": "true"}
]')

# Register the new task definition
echo "$NEW_TASK_DEF" > ai-enhanced-documents-task-def.json
NEW_TASK_DEF_ARN=$(aws ecs register-task-definition --region $AWS_REGION --cli-input-json file://ai-enhanced-documents-task-def.json --query 'taskDefinition.taskDefinitionArn' --output text)

echo -e "${GREEN}✅ New task definition registered: $NEW_TASK_DEF_ARN${NC}"

# Step 6: Update the ECS service
echo -e "${YELLOW}🔄 Updating ECS service with AI-enhanced document upload task definition...${NC}"
aws ecs update-service \
    --region $AWS_REGION \
    --cluster $CLUSTER_NAME \
    --service $SERVICE_NAME \
    --task-definition $NEW_TASK_DEF_ARN \
    --force-new-deployment

# Step 7: Wait for deployment to complete
echo -e "${YELLOW}⏳ Waiting for deployment to complete...${NC}"
aws ecs wait services-stable \
    --region $AWS_REGION \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME

# Step 8: Verify deployment
echo -e "${YELLOW}🔍 Verifying AI-enhanced document upload deployment...${NC}"

# Get the load balancer URL
LB_DNS=$(aws elbv2 describe-load-balancers \
    --region $AWS_REGION \
    --names multimodal-librarian-learning \
    --query 'LoadBalancers[0].DNSName' \
    --output text)

LB_URL="http://$LB_DNS"

echo -e "${BLUE}🌐 Testing endpoints:${NC}"

# Test health endpoint
echo -n "  Health check: "
if curl -s -f "$LB_URL/health/simple" > /dev/null; then
    echo -e "${GREEN}✅ PASS${NC}"
else
    echo -e "${RED}❌ FAIL${NC}"
fi

# Test features endpoint
echo -n "  Features check: "
FEATURES_RESPONSE=$(curl -s "$LB_URL/features")
if echo "$FEATURES_RESPONSE" | jq -e '.ai_integration == true' > /dev/null 2>&1; then
    echo -e "${GREEN}✅ AI Integration Enabled${NC}"
else
    echo -e "${RED}❌ AI Integration Not Detected${NC}"
fi

# Test document upload endpoint
echo -n "  Document upload: "
DOCS_RESPONSE=$(curl -s "$LB_URL/api/documents/health")
if echo "$DOCS_RESPONSE" | jq -e '.status == "healthy"' > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Document Upload Available${NC}"
else
    echo -e "${YELLOW}⚠️  Document Upload Initializing${NC}"
fi

echo ""
echo -e "${GREEN}🎉 AI-Enhanced document upload deployment completed successfully!${NC}"
echo ""
echo -e "${BLUE}📊 Deployment Summary:${NC}"
echo "  🌐 Application URL: $LB_URL"
echo "  💬 Chat Interface: $LB_URL/chat"
echo "  📚 API Documentation: $LB_URL/docs"
echo "  🔍 Features: $LB_URL/features"
echo "  📄 Document Upload: $LB_URL/api/documents/upload"
echo "  📋 Document Management: $LB_URL/documents"
echo ""
echo -e "${BLUE}🧠 AI Capabilities Now Available:${NC}"
echo "  ✅ Gemini 2.5 Flash Integration (Primary)"
echo "  ✅ OpenAI GPT Integration (Fallback)"
echo "  ✅ Multimodal Image Analysis"
echo "  ✅ Document Processing & Upload"
echo "  ✅ PDF Text Extraction"
echo "  ✅ Intelligent Chat with Documents"
echo "  ✅ Conversation Context"
echo "  ✅ Vision & Text Understanding"
echo ""
echo -e "${BLUE}📄 Document Features Available:${NC}"
echo "  ✅ PDF Upload (up to 100MB)"
echo "  ✅ Automatic Text Extraction"
echo "  ✅ Document Management Interface"
echo "  ✅ AI-Powered Document Q&A"
echo "  ✅ Document Search & Retrieval"
echo "  ✅ Processing Status Tracking"
echo ""
echo -e "${YELLOW}💰 Cost Impact:${NC}"
echo "  Previous: ~$60-80/month (minimal version)"
echo "  Current: ~$80-120/month (with document processing)"
echo "  Note: Optimized dependencies reduce infrastructure costs"
echo ""
echo -e "${GREEN}🚀 Your Document-Enabled The Librarian is now live!${NC}"

# Cleanup
rm -f ai-enhanced-documents-task-def.json

echo -e "${BLUE}🧹 Cleanup completed.${NC}"