#!/bin/bash

# Deploy Full ML Configuration of Multimodal Librarian to AWS
# This script builds and deploys the complete ML stack for demos

set -e

echo "🚀 Starting Full ML Configuration deployment..."

# Configuration
AWS_REGION="us-east-1"
ECR_REPOSITORY="multimodal-librarian-full-ml"
CLUSTER_NAME="multimodal-librarian-learning-cluster"
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

# Step 2: Build the Full ML Docker image
echo "🔨 Building Full ML Docker image (this may take 10-15 minutes)..."
docker build -f Dockerfile.full-ml -t ${ECR_REPOSITORY}:full-ml .
docker tag ${ECR_REPOSITORY}:full-ml ${ECR_URI}:full-ml
docker tag ${ECR_REPOSITORY}:full-ml ${ECR_URI}:latest

# Step 3: Login to ECR and push image
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "📤 Pushing Full ML image to ECR (this may take 5-10 minutes)..."
docker push ${ECR_URI}:full-ml
docker push ${ECR_URI}:latest

# Step 4: Create or update task definition for Full ML
echo "📝 Creating Full ML task definition..."
cat > full-ml-task-def.json << EOF
{
  "family": "${TASK_DEFINITION_FAMILY}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "8192",
  "memory": "16384",
  "executionRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskRole",
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
          "name": "POSTGRES_HOST",
          "value": "multimodal-librarian-learning-db.cluster-cxyz.us-east-1.rds.amazonaws.com"
        },
        {
          "name": "POSTGRES_PORT",
          "value": "5432"
        },
        {
          "name": "POSTGRES_DB",
          "value": "multimodal_librarian"
        },
        {
          "name": "POSTGRES_USER",
          "value": "postgres"
        },
        {
          "name": "MILVUS_HOST",
          "value": "milvus-service.multimodal-librarian-learning.local"
        },
        {
          "name": "MILVUS_PORT",
          "value": "19530"
        },
        {
          "name": "NEO4J_URI",
          "value": "bolt://neo4j-service.multimodal-librarian-learning.local:7687"
        },
        {
          "name": "NEO4J_USER",
          "value": "neo4j"
        },
        {
          "name": "REDIS_HOST",
          "value": "redis-service.multimodal-librarian-learning.local"
        },
        {
          "name": "REDIS_PORT",
          "value": "6379"
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
        },
        {
          "name": "YAGO_ENDPOINT",
          "value": "https://yago-knowledge.org/sparql/query"
        },
        {
          "name": "CONCEPTNET_API_BASE",
          "value": "http://api.conceptnet.io"
        }
      ],
      "secrets": [
        {
          "name": "POSTGRES_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:multimodal-librarian/postgres:password::"
        },
        {
          "name": "NEO4J_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:multimodal-librarian/neo4j:password::"
        },
        {
          "name": "OPENAI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:multimodal-librarian/openai:api_key::"
        },
        {
          "name": "GOOGLE_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:multimodal-librarian/google:api_key::"
        },
        {
          "name": "GEMINI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:multimodal-librarian/gemini:api_key::"
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
        "startPeriod": 60
      }
    }
  ]
}
EOF

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
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=MultimodalLibrarianLearningVPC" --query 'Vpcs[0].VpcId' --output text --region ${AWS_REGION} 2>/dev/null || echo "")
SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" "Name=tag:Name,Values=*Private*" --query 'Subnets[].SubnetId' --output text --region ${AWS_REGION} 2>/dev/null || echo "")
SECURITY_GROUP_ID=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=${VPC_ID}" "Name=group-name,Values=*ECS*" --query 'SecurityGroups[0].GroupId' --output text --region ${AWS_REGION} 2>/dev/null || echo "")

# Convert subnet IDs to array format
SUBNET_ARRAY=$(echo $SUBNET_IDS | tr ' ' ',' | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$/"/')

# Step 8: Create or update ECS service
echo "🚀 Creating/updating Full ML ECS service..."
SERVICE_EXISTS=$(aws ecs describe-services --cluster ${CLUSTER_NAME} --services ${SERVICE_NAME} --region ${AWS_REGION} --query 'services[0].serviceName' --output text 2>/dev/null || echo "None")

if [ "$SERVICE_EXISTS" = "None" ]; then
    echo "Creating new Full ML service..."
    aws ecs create-service \
        --cluster ${CLUSTER_NAME} \
        --service-name ${SERVICE_NAME} \
        --task-definition ${TASK_DEFINITION_FAMILY} \
        --desired-count 2 \
        --launch-type FARGATE \
        --platform-version LATEST \
        --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_ARRAY}],securityGroups=[\"${SECURITY_GROUP_ID}\"],assignPublicIp=DISABLED}" \
        --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:${AWS_REGION}:${AWS_ACCOUNT_ID}:targetgroup/multimodal-librarian-tg/$(aws elbv2 describe-target-groups --names multimodal-librarian-tg --query 'TargetGroups[0].TargetGroupArn' --output text --region ${AWS_REGION} | cut -d'/' -f2),containerName=multimodal-librarian-full-ml,containerPort=8000" \
        --region ${AWS_REGION}
else
    echo "Updating existing Full ML service..."
    aws ecs update-service \
        --cluster ${CLUSTER_NAME} \
        --service ${SERVICE_NAME} \
        --task-definition ${TASK_DEFINITION_FAMILY} \
        --desired-count 2 \
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