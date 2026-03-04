#!/bin/bash
# Restart script for enhanced deployment

echo "🔄 Restarting service with enhanced configuration..."

# Force new deployment to pick up any changes
aws ecs update-service \
    --cluster multimodal-librarian-learning \
    --service multimodal-librarian-learning-web \
    --force-new-deployment \
    --region us-east-1

echo "✅ Service restart initiated"
echo "⏳ Wait 2-3 minutes for the new task to start"
echo "🧪 Then test with: python3 scripts/test-learning-deployment.py"
