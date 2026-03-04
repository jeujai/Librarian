#!/bin/bash

# Deploy enhanced minimal using core requirements
# This uses the existing core requirements but with the enhanced minimal application

set -e

echo "🚀 Deploying enhanced minimal using core requirements..."

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

# Step 1: Create a minimal Dockerfile for enhanced deployment
echo "🔨 Creating minimal Dockerfile for enhanced deployment..."

cat > Dockerfile.enhanced-core << 'EOF'
# Enhanced minimal Dockerfile using core requirements
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy minimal enhanced requirements
COPY requirements-minimal-enhanced.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-minimal-enhanced.txt

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

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/simple || exit 1

# Run the enhanced minimal application
CMD ["gunicorn", "multimodal_librarian.main_minimal:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120"]
EOF

# Step 2: Build the enhanced image
echo "🔨 Building enhanced Docker image..."
docker build -f Dockerfile.enhanced-core -t ${ECR_REPOSITORY}:enhanced-core .
docker tag ${ECR_REPOSITORY}:enhanced-core ${ECR_URI}:enhanced-core
docker tag ${ECR_REPOSITORY}:enhanced-core ${ECR_URI}:latest

# Clean up temporary Dockerfile
rm Dockerfile.enhanced-core

# Step 3: Login to ECR and push image
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

echo "📤 Pushing enhanced image to ECR..."
docker push ${ECR_URI}:enhanced-core
docker push ${ECR_URI}:latest

# Step 4: Force new deployment
echo "🔄 Forcing new deployment..."
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

echo ""
echo "🎉 Enhanced core deployment completed!"
echo ""
echo "📱 Application URLs:"
echo "  🏠 Main API: http://${ALB_DNS}/"
echo "  💬 Chat Interface: http://${ALB_DNS}/chat"
echo "  📚 API Documentation: http://${ALB_DNS}/docs"
echo "  🏥 Health Check: http://${ALB_DNS}/health"
echo "  🎯 Feature Status: http://${ALB_DNS}/features"
echo ""
echo "✨ What's New:"
echo "  ✅ Enhanced main_minimal.py with /features and /chat endpoints"
echo "  ✅ Beautiful responsive web interface"
echo "  ✅ Feature status reporting"
echo "  ✅ Cost-optimized with core requirements only"
echo "  ✅ No ML dependencies for maximum cost efficiency"

exit 0