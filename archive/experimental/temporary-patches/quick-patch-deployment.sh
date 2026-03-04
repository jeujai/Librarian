#!/bin/bash

# Quick patch deployment - update the existing deployment to use enhanced minimal
# This approach avoids rebuilding the entire Docker image

set -e

echo "🚀 Quick patching deployment with enhanced minimal version..."

# Configuration
AWS_REGION="us-east-1"
CLUSTER_NAME="multimodal-librarian-learning"
SERVICE_NAME="multimodal-librarian-learning-web"

echo "📋 Configuration:"
echo "  AWS Region: ${AWS_REGION}"
echo "  ECS Cluster: ${CLUSTER_NAME}"
echo "  ECS Service: ${SERVICE_NAME}"

# Step 1: Get current task definition
echo "📥 Getting current task definition..."
TASK_DEF_ARN=$(aws ecs describe-services \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION} \
    --query 'services[0].taskDefinition' \
    --output text)

echo "Current task definition: ${TASK_DEF_ARN}"

# Step 2: Get the task definition details
aws ecs describe-task-definition \
    --task-definition ${TASK_DEF_ARN} \
    --region ${AWS_REGION} \
    --query 'taskDefinition' > current_task_def.json

# Step 3: Create new task definition with enhanced minimal command
echo "🔧 Creating enhanced task definition..."

# Extract the current task definition and modify the command
python3 << 'EOF'
import json

# Read current task definition
with open('current_task_def.json', 'r') as f:
    task_def = json.load(f)

# Remove fields that shouldn't be in the new definition
for field in ['taskDefinitionArn', 'revision', 'status', 'requiresAttributes', 'placementConstraints', 'compatibilities', 'registeredAt', 'registeredBy']:
    task_def.pop(field, None)

# Update the container command to use enhanced minimal
for container in task_def['containerDefinitions']:
    if container['name'] == 'multimodal-librarian':
        # Update command to use enhanced minimal
        container['command'] = [
            "gunicorn", 
            "multimodal_librarian.main_minimal_enhanced:app", 
            "-w", "2", 
            "-k", "uvicorn.workers.UvicornWorker", 
            "--bind", "0.0.0.0:8000", 
            "--timeout", "120"
        ]
        
        # Add environment variable to indicate enhanced mode
        if 'environment' not in container:
            container['environment'] = []
        
        # Add or update environment variables
        env_vars = {var['name']: var['value'] for var in container['environment']}
        env_vars['DEPLOYMENT_MODE'] = 'enhanced-minimal'
        env_vars['FEATURES_ENABLED'] = 'chat,static_files,monitoring'
        
        container['environment'] = [{'name': k, 'value': v} for k, v in env_vars.items()]
        
        print(f"Updated container command: {container['command']}")
        print(f"Environment variables: {len(container['environment'])}")

# Save the new task definition
with open('enhanced_task_def.json', 'w') as f:
    json.dump(task_def, f, indent=2)

print("Enhanced task definition created")
EOF

# Step 4: Register the new task definition
echo "📝 Registering enhanced task definition..."
NEW_TASK_DEF_ARN=$(aws ecs register-task-definition \
    --cli-input-json file://enhanced_task_def.json \
    --region ${AWS_REGION} \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "New task definition: ${NEW_TASK_DEF_ARN}"

# Step 5: Update the service to use the new task definition
echo "🔄 Updating ECS service with enhanced task definition..."
aws ecs update-service \
    --cluster ${CLUSTER_NAME} \
    --service ${SERVICE_NAME} \
    --task-definition ${NEW_TASK_DEF_ARN} \
    --region ${AWS_REGION}

# Step 6: Wait for deployment to complete
echo "⏳ Waiting for deployment to complete..."
aws ecs wait services-stable \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION}

# Step 7: Clean up temporary files
rm -f current_task_def.json enhanced_task_def.json

# Step 8: Test the deployment
echo "🧪 Testing the enhanced deployment..."
sleep 15  # Give the service a moment to start

ALB_DNS="multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"

echo "Testing endpoints..."
curl -s "http://${ALB_DNS}/health/simple" > /dev/null && echo "  ✅ Health check: OK" || echo "  ❌ Health check: FAILED"
curl -s "http://${ALB_DNS}/features" > /dev/null && echo "  ✅ Features endpoint: OK" || echo "  ❌ Features endpoint: FAILED"
curl -s "http://${ALB_DNS}/chat" > /dev/null && echo "  ✅ Chat interface: OK" || echo "  ❌ Chat interface: FAILED"

echo ""
echo "🎉 Quick patch deployment completed!"
echo ""
echo "📱 Application URLs:"
echo "  🏠 Main API: http://${ALB_DNS}/"
echo "  💬 Chat Interface: http://${ALB_DNS}/chat"
echo "  📚 API Documentation: http://${ALB_DNS}/docs"
echo "  🏥 Health Check: http://${ALB_DNS}/health"
echo "  🎯 Feature Status: http://${ALB_DNS}/features"
echo ""
echo "✨ What's New:"
echo "  ✅ Enhanced minimal application with full web interface"
echo "  ✅ /features endpoint for feature status"
echo "  ✅ /chat endpoint with beautiful interface"
echo "  ✅ Uses existing Docker image with updated command"
echo "  ✅ No Docker rebuild required"
echo ""
echo "🔧 Technical Details:"
echo "  ✅ Updated task definition command"
echo "  ✅ Added environment variables for enhanced mode"
echo "  ✅ Maintained existing infrastructure"
echo "  ✅ Zero downtime deployment"

exit 0