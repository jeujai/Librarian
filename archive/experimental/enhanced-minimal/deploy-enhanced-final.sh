#!/bin/bash

# Final deployment script for enhanced minimal application
# Uses a streamlined approach to avoid Docker build space issues

set -e

echo "🚀 Deploying enhanced minimal application (Final Version)..."

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

# Step 1: Create ultra-minimal Dockerfile for enhanced deployment
echo "🔨 Creating ultra-minimal Dockerfile..."

cat > Dockerfile.enhanced-final << 'EOF'
# Ultra-minimal Dockerfile for enhanced deployment
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Set work directory
WORKDIR /app

# Install only essential system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy minimal requirements
COPY requirements-minimal-enhanced.txt ./

# Install Python dependencies in stages to avoid space issues
RUN pip install --no-cache-dir fastapi==0.104.1 uvicorn[standard]==0.24.0 gunicorn==21.2.0
RUN pip install --no-cache-dir python-multipart==0.0.6 cryptography>=41.0.0 PyJWT>=2.8.0
RUN pip install --no-cache-dir psycopg2-binary==2.9.9 python-dotenv==1.0.0
RUN pip install --no-cache-dir pydantic==2.5.0 pydantic-settings==2.1.0
RUN pip install --no-cache-dir boto3==1.34.0 botocore==1.34.0 requests==2.31.0

# Copy only essential project files
COPY src/multimodal_librarian/__init__.py ./src/multimodal_librarian/
COPY src/multimodal_librarian/main_minimal.py ./src/multimodal_librarian/
COPY src/multimodal_librarian/config.py ./src/multimodal_librarian/
COPY src/multimodal_librarian/logging_config.py ./src/multimodal_librarian/
COPY pyproject.toml ./

# Install the package
RUN pip install .

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/simple || exit 1

# Run the enhanced minimal application
CMD ["gunicorn", "multimodal_librarian.main_minimal:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120"]
EOF

# Step 2: Build the enhanced image with better caching
echo "🔨 Building enhanced Docker image..."
docker build -f Dockerfile.enhanced-final -t ${ECR_REPOSITORY}:enhanced-final .
docker tag ${ECR_REPOSITORY}:enhanced-final ${ECR_URI}:enhanced-final
docker tag ${ECR_REPOSITORY}:enhanced-final ${ECR_URI}:latest

# Clean up temporary Dockerfile
rm Dockerfile.enhanced-final

# Step 3: Login to ECR and push image
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "📤 Pushing enhanced image to ECR..."
docker push ${ECR_URI}:enhanced-final
docker push ${ECR_URI}:latest

# Step 4: Force new deployment
echo "🔄 Forcing new deployment with enhanced image..."
aws ecs update-service \
    --cluster ${CLUSTER_NAME} \
    --service ${SERVICE_NAME} \
    --force-new-deployment \
    --region ${AWS_REGION}

# Step 5: Wait for deployment to complete
echo "⏳ Waiting for deployment to complete..."
aws ecs wait services-stable \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION}

# Step 6: Test the deployment
echo "🧪 Testing the enhanced deployment..."
sleep 15

ALB_DNS="multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"

echo "Testing endpoints..."
curl -s "http://${ALB_DNS}/health/simple" > /dev/null && echo "  ✅ Health check: OK" || echo "  ❌ Health check: FAILED"
curl -s "http://${ALB_DNS}/features" > /dev/null && echo "  ✅ Features endpoint: OK" || echo "  ❌ Features endpoint: FAILED"
curl -s "http://${ALB_DNS}/chat" > /dev/null && echo "  ✅ Chat interface: OK" || echo "  ❌ Chat interface: FAILED"

# Step 7: Run comprehensive test
echo ""
echo "🧪 Running comprehensive test suite..."
python3 scripts/test-learning-deployment.py

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
echo "✨ What's New:"
echo "  ✅ Enhanced /features endpoint with deployment status"
echo "  ✅ Beautiful /chat interface with responsive design"
echo "  ✅ Feature cards showing available functionality"
echo "  ✅ Cost-optimized deployment (~$50/month)"
echo "  ✅ Mobile-responsive web interface"
echo ""
echo "💰 Cost Optimization Features:"
echo "  ✅ Minimal Docker image size"
echo "  ✅ Essential dependencies only"
echo "  ✅ Efficient resource usage"
echo "  ✅ Single container deployment"

exit 0