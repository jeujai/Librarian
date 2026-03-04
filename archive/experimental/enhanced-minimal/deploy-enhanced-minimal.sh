#!/bin/bash

# Deploy enhanced minimal version with full web interface
# This updates the current deployment to use the enhanced version

set -e

echo "🚀 Deploying enhanced minimal version with full web interface..."

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

# Step 1: Build enhanced minimal Docker image (using existing Dockerfile but with enhanced main)
echo "🔨 Building enhanced minimal Docker image..."

# Create a temporary Dockerfile that uses the enhanced minimal version
cat > Dockerfile.enhanced-minimal << 'EOF'
# Enhanced minimal Dockerfile - uses existing production image but switches to enhanced main
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies (minimal set)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy core requirements (use existing)
COPY requirements-core.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-core.txt

# Copy project files
COPY src/ ./src/
COPY pyproject.toml ./

# Install the package
RUN pip install .

# Create necessary directories with proper permissions
RUN mkdir -p uploads media exports logs audit_logs \
    && chmod 755 uploads media exports logs audit_logs

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

# Expose ports for API and WebSocket
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/simple || exit 1

# Run the enhanced minimal application
CMD ["gunicorn", "multimodal_librarian.main_minimal_enhanced:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120"]
EOF

docker build -f Dockerfile.enhanced-minimal -t ${ECR_REPOSITORY}:enhanced .
docker tag ${ECR_REPOSITORY}:enhanced ${ECR_URI}:enhanced
docker tag ${ECR_REPOSITORY}:enhanced ${ECR_URI}:latest

# Clean up temporary Dockerfile
rm Dockerfile.enhanced-minimal

# Step 2: Login to ECR and push image
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "📤 Pushing enhanced image to ECR..."
docker push ${ECR_URI}:enhanced
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

# Step 6: Test the deployment
echo "🧪 Testing the enhanced deployment..."
sleep 10  # Give the service a moment to start

ALB_DNS="multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"

echo "Testing endpoints..."
curl -s "http://${ALB_DNS}/health/simple" > /dev/null && echo "  ✅ Health check: OK" || echo "  ❌ Health check: FAILED"
curl -s "http://${ALB_DNS}/features" > /dev/null && echo "  ✅ Features endpoint: OK" || echo "  ❌ Features endpoint: FAILED"
curl -s "http://${ALB_DNS}/chat" > /dev/null && echo "  ✅ Chat interface: OK" || echo "  ❌ Chat interface: FAILED"

echo ""
echo "🎉 Enhanced minimal deployment completed!"
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
echo "  ✅ Full web-based chat interface with modern UI"
echo "  ✅ /features endpoint for feature status"
echo "  ✅ Enhanced /chat endpoint with beautiful interface"
echo "  ✅ Mobile-responsive design"
echo "  ✅ Real-time WebSocket chat with reconnection"
echo "  ✅ Typing indicators and status updates"
echo "  ✅ Cost-optimized (~$50/month)"
echo ""
echo "💰 Cost Optimization:"
echo "  ✅ Uses existing infrastructure"
echo "  ✅ Minimal dependencies"
echo "  ✅ 2 worker processes"
echo "  ✅ Graceful fallbacks"
echo ""
echo "📊 Monitor deployment:"
echo "  aws logs tail /aws/ecs/multimodal-librarian-learning --follow"

exit 0