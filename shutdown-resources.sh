#!/bin/bash
# AWS Resource Shutdown Script
# Generated automatically for Multimodal Librarian cleanup

set -e  # Exit on any error

echo '🧹 Starting AWS resource shutdown...'

echo 'Executing: aws ec2 delete-nat-gateway --nat-gateway-id nat-0922d45658199821b'
aws ec2 delete-nat-gateway --nat-gateway-id nat-0922d45658199821b
echo 'Done.'

echo 'Executing: aws ec2 delete-nat-gateway --nat-gateway-id nat-08dd08fa1b4ab6083'
aws ec2 delete-nat-gateway --nat-gateway-id nat-08dd08fa1b4ab6083
echo 'Done.'

echo 'Executing: aws ec2 delete-nat-gateway --nat-gateway-id nat-0de7c20c01213cedb'
aws ec2 delete-nat-gateway --nat-gateway-id nat-0de7c20c01213cedb
echo 'Done.'

echo 'Executing: aws ec2 delete-nat-gateway --nat-gateway-id nat-0ba6c7fb864e0b7b7'
aws ec2 delete-nat-gateway --nat-gateway-id nat-0ba6c7fb864e0b7b7
echo 'Done.'

echo 'Executing: aws rds stop-db-instance --db-instance-identifier multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro'
aws rds stop-db-instance --db-instance-identifier multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro
echo 'Done.'

echo 'Executing: aws ecs update-service --cluster multimodal-lib-prod-cluster --service multimodal-lib-prod-service --desired-count 0'
aws ecs update-service --cluster multimodal-lib-prod-cluster --service multimodal-lib-prod-service --desired-count 0
echo 'Done.'

echo 'Executing: aws ecs update-service --cluster multimodal-librarian-full-ml --service multimodal-librarian-full-ml-web --desired-count 0'
aws ecs update-service --cluster multimodal-librarian-full-ml --service multimodal-librarian-full-ml-web --desired-count 0
echo 'Done.'

echo 'Executing: aws ecs update-service --cluster multimodal-librarian-full-ml --service multimodal-librarian-full-ml-service --desired-count 0'
aws ecs update-service --cluster multimodal-librarian-full-ml --service multimodal-librarian-full-ml-service --desired-count 0
echo 'Done.'

echo 'Executing: aws ec2 stop-instances --instance-ids i-0255d25fd1950ed2d'
aws ec2 stop-instances --instance-ids i-0255d25fd1950ed2d
echo 'Done.'

echo '✅ Shutdown complete!'
echo 'Monitor AWS console to verify resources are stopped/deleted.'