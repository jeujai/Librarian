#!/bin/bash

# Create necessary ECS IAM roles for Full ML deployment

set -e

echo "🔐 Creating ECS IAM roles..."

AWS_REGION="us-east-1"

# Create ECS Task Execution Role
echo "📝 Creating ECS Task Execution Role..."

# Trust policy for ECS Task Execution Role
cat > ecs-task-execution-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
    --role-name ecsTaskExecutionRole \
    --assume-role-policy-document file://ecs-task-execution-trust-policy.json \
    --region ${AWS_REGION} 2>/dev/null || echo "Role already exists"

# Attach the AWS managed policy for ECS task execution
aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
    --region ${AWS_REGION} 2>/dev/null || echo "Policy already attached"

echo "✅ ECS Task Execution Role created successfully"

# Create ECS Task Role (optional, for application permissions)
echo "📝 Creating ECS Task Role..."

# Trust policy for ECS Task Role
cat > ecs-task-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
    --role-name ecsTaskRole \
    --assume-role-policy-document file://ecs-task-trust-policy.json \
    --region ${AWS_REGION} 2>/dev/null || echo "Role already exists"

echo "✅ ECS Task Role created successfully"

# Clean up temporary files
rm -f ecs-task-execution-trust-policy.json ecs-task-trust-policy.json

echo "🎉 All ECS IAM roles created successfully!"
echo ""
echo "Created roles:"
echo "  - ecsTaskExecutionRole (for container management)"
echo "  - ecsTaskRole (for application permissions)"

exit 0