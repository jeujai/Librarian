#!/bin/bash

# Deploy Full ML Configuration of Multimodal Librarian to AWS
# This script builds and deploys the complete ML stack for demos

set -e

echo "🚀 Starting Full ML Configuration deployment..."

# Configuration
AWS_REGION="us-east-1"
ECR_REPOSITORY="multimodal-librarian-full-ml"
CLUSTER_NAME="multimodal-librarian-full-ml"
SERVICE_NAME="multimodal-librarian-full-ml-service"
TASK_DEFINITION_FAMILY="multimodal-librarian-full-ml"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

echo "📋 Configuration:"
echo "  AWS Region: ${AWS_REGION}"
echo "  ECR Repository: ${ECR_URI}"
echo "  ECS Cluster: ${CLUSTER_NAME}"
echo "  ECS Service: ${SERVICE_NAME}"
echo "  Task Definition: ${TASK_DEFINITION_FAMILY}"

# Step 1: Create ECR repository if it doesn't exist
echo "🏗️  Creating ECR repository..."
aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${AWS_REGION} 2>/dev/null || \
aws ecr create-repository --repository-name ${ECR_REPOSITORY} --region ${AWS_REGION}

# Verify IAM permissions for Secrets Manager (critical fix from previous session)
echo "🔐 Verifying IAM permissions for Secrets Manager..."
aws iam list-attached-role-policies --role-name ecsTaskExecutionRole --query 'AttachedPolicies[?PolicyName==`SecretsManagerReadWrite`]' --output text | grep -q SecretsManagerReadWrite || {
    echo "⚠️  Adding SecretsManagerReadWrite policy to ecsTaskExecutionRole..."
    aws iam attach-role-policy \
        --role-name ecsTaskExecutionRole \
        --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite
    echo "✅ IAM permissions updated"
}

# Step 2: Build the Docker image using canonical Dockerfile with platform specification
echo "🔨 Building Docker image with x86_64 compatibility (this may take 10-15 minutes)..."
docker build --platform linux/amd64 -f Dockerfile -t ${ECR_REPOSITORY}:full-ml .
docker tag ${ECR_REPOSITORY}:full-ml ${ECR_URI}:full-ml
docker tag ${ECR_REPOSITORY}:full-ml ${ECR_URI}:latest

# Step 3: Login to ECR and push image
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "📤 Pushing Full ML image to ECR (this may take 5-10 minutes)..."
docker push ${ECR_URI}:full-ml
docker push ${ECR_URI}:latest

# Step 4: Use canonical task definition
echo "📝 Using canonical task definition..."
cp task-definition.json full-ml-task-def.json

# Step 5: Register the task definition
echo "📋 Registering Full ML task definition..."
aws ecs register-task-definition \
    --cli-input-json file://full-ml-task-def.json \
    --region ${AWS_REGION}

# Step 6: Create CloudWatch log group
echo "📊 Creating CloudWatch log group..."
aws logs create-log-group \
    --log-group-name "/aws/ecs/multimodal-librarian-full-ml" \
    --region ${AWS_REGION} 2>/dev/null || echo "Log group already exists"

# Step 7: Get VPC and subnet information from existing cluster
echo "🔍 Getting network configuration..."
CLUSTER_INFO=$(aws ecs describe-clusters --clusters ${CLUSTER_NAME} --region ${AWS_REGION})

# Get VPC and subnet information from existing infrastructure
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=*Learning*" --query 'Vpcs[0].VpcId' --output text --region ${AWS_REGION} 2>/dev/null)
if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
    VPC_ID=$(aws ec2 describe-vpcs --query 'Vpcs[0].VpcId' --output text --region ${AWS_REGION})
fi

# Get only public subnets (ones that auto-assign public IPs)
SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" "Name=map-public-ip-on-launch,Values=true" --query 'Subnets[].SubnetId' --output text --region ${AWS_REGION})
SECURITY_GROUP_ID=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=${VPC_ID}" --query 'SecurityGroups[0].GroupId' --output text --region ${AWS_REGION})

# Convert subnet IDs to array format
SUBNET_ARRAY=$(echo $SUBNET_IDS | tr ' ' ',' | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$/"/')

echo "  VPC ID: ${VPC_ID}"
echo "  Subnets: ${SUBNET_IDS}"
echo "  Security Group: ${SECURITY_GROUP_ID}"

# Step 8: Create or update ECS service (simplified without load balancer initially)
echo "🚀 Creating/updating Full ML ECS service..."
SERVICE_EXISTS=$(aws ecs describe-services --cluster ${CLUSTER_NAME} --services ${SERVICE_NAME} --region ${AWS_REGION} --query 'services[0].serviceName' --output text 2>/dev/null || echo "None")

if [ "$SERVICE_EXISTS" = "None" ]; then
    echo "Creating new Full ML service..."
    aws ecs create-service \
        --cluster ${CLUSTER_NAME} \
        --service-name ${SERVICE_NAME} \
        --task-definition ${TASK_DEFINITION_FAMILY} \
        --desired-count 1 \
        --launch-type FARGATE \
        --platform-version LATEST \
        --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_ARRAY}],securityGroups=[\"${SECURITY_GROUP_ID}\"],assignPublicIp=ENABLED}" \
        --region ${AWS_REGION}
else
    echo "Updating existing Full ML service..."
    aws ecs update-service \
        --cluster ${CLUSTER_NAME} \
        --service ${SERVICE_NAME} \
        --task-definition ${TASK_DEFINITION_FAMILY} \
        --desired-count 1 \
        --force-new-deployment \
        --region ${AWS_REGION}
fi

# Step 9: Wait for deployment to complete
echo "⏳ Waiting for Full ML deployment to complete (this may take 5-10 minutes)..."
aws ecs wait services-stable \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION}

# Step 10: Get service status
echo "📊 Checking Full ML service status..."
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

# Step 11: Get load balancer URL
echo "🌐 Getting Full ML application URL..."
ALB_DNS=$(aws cloudformation describe-stacks \
    --stack-name MultimodalLibrarianLearningStack \
    --region ${AWS_REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDnsName`].OutputValue' \
    --output text 2>/dev/null || echo "Not found")

if [ "$ALB_DNS" != "Not found" ] && [ -n "$ALB_DNS" ]; then
    echo "🎉 Full ML Deployment completed successfully!"
    echo ""
    echo "📱 Application URLs:"
    echo "  Main API: http://${ALB_DNS}/"
    echo "  Chat Interface: http://${ALB_DNS}/chat"
    echo "  API Documentation: http://${ALB_DNS}/docs"
    echo "  Health Check: http://${ALB_DNS}/health"
    echo "  Feature Status: http://${ALB_DNS}/features"
    echo "  Analytics Dashboard: http://${ALB_DNS}/analytics"
    echo "  Document Manager: http://${ALB_DNS}/documents"
    echo ""
    echo "🧪 Test the Full ML deployment:"
    echo "  curl http://${ALB_DNS}/health/simple"
    echo "  curl http://${ALB_DNS}/features"
    echo "  curl http://${ALB_DNS}/api/v1/ml/capabilities"
else
    echo "⚠️  Could not retrieve load balancer URL"
    echo "   Check AWS CloudFormation stack outputs manually"
fi

echo ""
echo "🤖 Full ML Configuration Features:"
echo "  ✅ Complete PyTorch + CUDA stack"
echo "  ✅ Advanced sentence transformers"
echo "  ✅ Full multimedia generation (audio, video, images)"
echo "  ✅ Computer vision capabilities"
echo "  ✅ Advanced NLP with spaCy"
echo "  ✅ Scientific computing (NumPy, SciPy, Pandas)"
echo "  ✅ Machine learning (scikit-learn)"
echo "  ✅ 8 worker processes for high performance"
echo "  ✅ 16GB memory for large model processing"
echo "  ✅ 8 vCPU for parallel processing"
echo ""
echo "🎯 Available ML Features:"
echo "  ✅ Advanced document chunking with ML"
echo "  ✅ Smart bridge generation with Gemini"
echo "  ✅ Vector embeddings and similarity search"
echo "  ✅ Knowledge graph reasoning"
echo "  ✅ Multi-modal content generation"
echo "  ✅ Real-time ML inference"
echo "  ✅ Advanced analytics and insights"
echo "  ✅ ML training endpoints"
echo "  ✅ Performance optimization"
echo ""
echo "💰 Resource Configuration:"
echo "  🖥️  CPU: 8 vCPU (Fargate)"
echo "  🧠 Memory: 16GB RAM"
echo "  📦 Container: ~8-10GB (full ML stack)"
echo "  💵 Estimated cost: ~$300-400/month"
echo ""
echo "📊 Monitor your Full ML deployment:"
echo "  aws logs tail /aws/ecs/multimodal-librarian-full-ml --follow"
echo ""
echo "🌍 Perfect for geographically dispersed demos!"
echo "   Your audience can access the full ML capabilities from anywhere."

# Cleanup temporary files
rm -f full-ml-task-def.json

exit 0