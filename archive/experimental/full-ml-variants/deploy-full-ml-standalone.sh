#!/bin/bash

# Deploy Full ML Configuration as Standalone Service
# This creates minimal infrastructure and deploys the Full ML container

set -e

echo "🚀 Starting Full ML Standalone deployment..."

# Configuration
AWS_REGION="us-east-1"
ECR_REPOSITORY="multimodal-librarian-full-ml"
CLUSTER_NAME="multimodal-librarian-full-ml-cluster"
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

# Step 2: Build and push the Full ML Docker image (reuse existing)
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "🏷️  Tagging existing Full ML image..."
docker tag multimodal-librarian-full-ml:full-ml ${ECR_URI}:full-ml
docker tag multimodal-librarian-full-ml:full-ml ${ECR_URI}:latest

echo "📤 Pushing Full ML image to ECR..."
docker push ${ECR_URI}:full-ml
docker push ${ECR_URI}:latest

# Step 3: Create ECS cluster
echo "🏗️  Creating ECS cluster..."
aws ecs create-cluster \
    --cluster-name ${CLUSTER_NAME} \
    --capacity-providers FARGATE \
    --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1 \
    --region ${AWS_REGION} 2>/dev/null || echo "Cluster already exists"

# Step 4: Create CloudWatch log group
echo "📊 Creating CloudWatch log group..."
aws logs create-log-group \
    --log-group-name "/aws/ecs/multimodal-librarian-full-ml" \
    --region ${AWS_REGION} 2>/dev/null || echo "Log group already exists"

# Step 5: Get default VPC and subnets
echo "🔍 Getting default VPC configuration..."
DEFAULT_VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query 'Vpcs[0].VpcId' --output text --region ${AWS_REGION})
SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${DEFAULT_VPC_ID}" --query 'Subnets[].SubnetId' --output text --region ${AWS_REGION})

# Convert subnet IDs to array format
SUBNET_ARRAY=$(echo $SUBNET_IDS | tr ' ' ',' | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$/"/')

echo "  Default VPC: ${DEFAULT_VPC_ID}"
echo "  Subnets: ${SUBNET_IDS}"

# Step 6: Create security group for the service
echo "🔒 Creating security group..."
SECURITY_GROUP_ID=$(aws ec2 create-security-group \
    --group-name multimodal-librarian-full-ml-sg \
    --description "Security group for Multimodal Librarian Full ML service" \
    --vpc-id ${DEFAULT_VPC_ID} \
    --region ${AWS_REGION} \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=multimodal-librarian-full-ml-sg" \
        --query 'SecurityGroups[0].GroupId' \
        --output text \
        --region ${AWS_REGION})

# Add inbound rule for HTTP traffic
aws ec2 authorize-security-group-ingress \
    --group-id ${SECURITY_GROUP_ID} \
    --protocol tcp \
    --port 8000 \
    --cidr 0.0.0.0/0 \
    --region ${AWS_REGION} 2>/dev/null || echo "Security group rule already exists"

echo "  Security Group: ${SECURITY_GROUP_ID}"

# Step 7: Create task definition for Full ML (standalone version)
echo "📝 Creating Full ML task definition..."
cat > full-ml-standalone-task-def.json << EOF
{
  "family": "${TASK_DEFINITION_FAMILY}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "8192",
  "memory": "16384",
  "executionRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "multimodal-librarian-full-ml",
      "image": "${ECR_URI}:full-ml",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "essential": true,
      "environment": [
        {
          "name": "DEBUG",
          "value": "false"
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
        },
        {
          "name": "API_WORKERS",
          "value": "4"
        },
        {
          "name": "CHUNK_SIZE",
          "value": "512"
        },
        {
          "name": "CHUNK_OVERLAP",
          "value": "50"
        },
        {
          "name": "EMBEDDING_MODEL",
          "value": "all-MiniLM-L6-v2"
        },
        {
          "name": "MAX_FILE_SIZE",
          "value": "104857600"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/aws/ecs/multimodal-librarian-full-ml",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "curl -f http://localhost:8000/health/simple || exit 1"
        ],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 120
      }
    }
  ]
}
EOF

# Step 8: Register the task definition
echo "📋 Registering Full ML task definition..."
aws ecs register-task-definition \
    --cli-input-json file://full-ml-standalone-task-def.json \
    --region ${AWS_REGION}

# Step 9: Create ECS service
echo "🚀 Creating Full ML ECS service..."
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

# Step 10: Wait for deployment to complete
echo "⏳ Waiting for Full ML deployment to complete (this may take 5-10 minutes)..."
aws ecs wait services-stable \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION}

# Step 11: Get service status and public IP
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

# Step 12: Get public IP of the running task
echo "🌐 Getting public IP address..."
TASK_ARN=$(aws ecs list-tasks \
    --cluster ${CLUSTER_NAME} \
    --service-name ${SERVICE_NAME} \
    --region ${AWS_REGION} \
    --query 'taskArns[0]' \
    --output text)

if [ "$TASK_ARN" != "None" ] && [ -n "$TASK_ARN" ]; then
    ENI_ID=$(aws ecs describe-tasks \
        --cluster ${CLUSTER_NAME} \
        --tasks ${TASK_ARN} \
        --region ${AWS_REGION} \
        --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
        --output text)
    
    PUBLIC_IP=$(aws ec2 describe-network-interfaces \
        --network-interface-ids ${ENI_ID} \
        --region ${AWS_REGION} \
        --query 'NetworkInterfaces[0].Association.PublicIp' \
        --output text 2>/dev/null || echo "Not available")
    
    if [ "$PUBLIC_IP" != "Not available" ] && [ -n "$PUBLIC_IP" ]; then
        echo "🎉 Full ML Deployment completed successfully!"
        echo ""
        echo "📱 Application URLs:"
        echo "  Main API: http://${PUBLIC_IP}:8000/"
        echo "  Chat Interface: http://${PUBLIC_IP}:8000/chat"
        echo "  API Documentation: http://${PUBLIC_IP}:8000/docs"
        echo "  Health Check: http://${PUBLIC_IP}:8000/health"
        echo "  Feature Status: http://${PUBLIC_IP}:8000/features"
        echo ""
        echo "🧪 Test the Full ML deployment:"
        echo "  curl http://${PUBLIC_IP}:8000/health/simple"
        echo "  curl http://${PUBLIC_IP}:8000/features"
        echo ""
        echo "🌍 Share this URL with your geographically dispersed demo audience:"
        echo "  http://${PUBLIC_IP}:8000"
    else
        echo "⚠️  Could not retrieve public IP address"
        echo "   Check ECS console for task details"
    fi
else
    echo "⚠️  No running tasks found"
    echo "   Check ECS console for service status"
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
echo "  ✅ 4 worker processes for high performance"
echo "  ✅ 16GB memory for large model processing"
echo "  ✅ 8 vCPU for parallel processing"
echo ""
echo "💰 Resource Configuration:"
echo "  🖥️  CPU: 8 vCPU (Fargate)"
echo "  🧠 Memory: 16GB RAM"
echo "  📦 Container: ~8-10GB (full ML stack)"
echo "  💵 Estimated cost: ~$200-300/month"
echo ""
echo "📊 Monitor your Full ML deployment:"
echo "  aws logs tail /aws/ecs/multimodal-librarian-full-ml --follow"
echo ""
echo "🌍 Perfect for geographically dispersed demos!"
echo "   Your audience can access the full ML capabilities from anywhere."

# Cleanup temporary files
rm -f full-ml-standalone-task-def.json

exit 0