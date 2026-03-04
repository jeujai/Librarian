# AWS Integration Tests

This directory contains comprehensive integration tests for the AWS learning deployment of the Multimodal Librarian system.

## Test Suites

### 1. Basic AWS Integration (`test_aws_basic_integration.py`)
Tests core infrastructure connectivity and health:
- Application health endpoints
- API endpoint accessibility
- Database connectivity
- S3 bucket access
- Basic performance characteristics
- End-to-end system health checks

### 2. S3 Operations (`test_s3_basic_operations.py`)
Tests file storage operations:
- File upload and download
- Presigned URL generation
- File metadata operations
- File listing operations
- Security configurations
- Performance characteristics

### 3. Database Connectivity (`test_database_basic_connectivity.py`)
Tests database operations:
- PostgreSQL RDS connectivity
- Redis ElastiCache connectivity
- CRUD operations
- Transaction handling
- Connection pooling
- Performance monitoring
- Integration scenarios

### 4. WebSocket Functionality (`test_websocket_basic.py`)
Tests WebSocket connections through Application Load Balancer:
- Connection establishment
- Message sending and receiving
- Connection persistence
- Load balancer WebSocket support
- Performance characteristics
- Error handling

### 5. ML Training APIs (`test_ml_training_basic.py`)
Tests ML training and chunking framework:
- ML training API endpoints
- Chunking framework operations
- Performance monitoring
- Integration with other components
- Error handling and resilience

## Running Tests

### Run All Tests
```bash
# Run all integration tests
python tests/aws/run_all_integration_tests.py

# Run with options
python tests/aws/run_all_integration_tests.py --stop-on-failure --quiet
```

### Run Individual Test Suites
```bash
# Basic integration tests
python tests/aws/test_aws_basic_integration.py

# S3 operations tests
python tests/aws/test_s3_basic_operations.py

# Database connectivity tests
python tests/aws/test_database_basic_connectivity.py

# WebSocket tests
python tests/aws/test_websocket_basic.py

# ML training tests
python tests/aws/test_ml_training_basic.py
```

### Run with Pytest
```bash
# Run all AWS tests
pytest tests/aws/ -v

# Run specific test file
pytest tests/aws/test_aws_basic_integration.py -v

# Run with coverage
pytest tests/aws/ --cov=src/multimodal_librarian --cov-report=html
```

## Configuration

### Environment Variables
Set these environment variables for proper test execution:

```bash
# AWS Configuration
export AWS_REGION=us-east-1
export AWS_BASE_URL=https://your-alb-domain.com
export S3_BUCKET_NAME=your-bucket-name

# Database Configuration
export REDIS_HOST=your-redis-endpoint.cache.amazonaws.com
export REDIS_PORT=6379
export REDIS_DB=0

# Test Configuration
export TESTING=true
export LOG_LEVEL=INFO
```

### AWS Credentials
Ensure AWS credentials are configured:
```bash
# Using AWS CLI
aws configure

# Or using environment variables
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key

# Or using IAM roles (recommended for EC2/ECS)
```

## Test Categories

### Infrastructure Tests
- ✅ Application health and availability
- ✅ Load balancer functionality
- ✅ Service discovery and routing
- ✅ Basic security configurations

### Data Layer Tests
- ✅ PostgreSQL RDS connectivity and operations
- ✅ Redis ElastiCache functionality
- ✅ S3 file storage operations
- ✅ Data integrity and consistency

### Application Layer Tests
- ✅ API endpoint functionality
- ✅ WebSocket connections
- ✅ ML training workflows
- ✅ Chunking framework operations

### Integration Tests
- ✅ End-to-end system functionality
- ✅ Component interaction validation
- ✅ Performance under basic load
- ✅ Error handling and resilience

## Expected Results

### Healthy System
When the AWS deployment is healthy, you should see:
- ✅ All infrastructure connectivity tests pass
- ✅ Database operations complete successfully
- ✅ File storage operations work correctly
- ✅ WebSocket connections establish properly
- ✅ API endpoints respond appropriately

### Common Issues and Solutions

#### Connection Timeouts
- Check security group configurations
- Verify VPC networking setup
- Ensure services are running and healthy

#### Authentication Errors
- Verify AWS credentials configuration
- Check IAM permissions for test execution
- Ensure API keys are properly configured

#### Service Unavailable
- Check ECS service status
- Verify load balancer health checks
- Review CloudWatch logs for errors

#### Database Connection Issues
- Verify RDS instance is running
- Check database security groups
- Ensure connection strings are correct

## Test Output

### Success Example
```
🚀 AWS INTEGRATION TEST SUITE
================================================================================
📅 Started: 2026-01-01T12:00:00
🧪 Test Suites: 5

📋 [1/5] AWS Basic Integration
   Core infrastructure and API endpoint tests
------------------------------------------------------------
✅ PASSED (15.2s)

📋 [2/5] S3 Operations
   File storage and presigned URL tests
------------------------------------------------------------
✅ PASSED (8.7s)

📋 [3/5] Database Connectivity
   PostgreSQL and Redis connectivity tests
------------------------------------------------------------
✅ PASSED (12.3s)

📋 [4/5] WebSocket Functionality
   WebSocket connections through load balancer
------------------------------------------------------------
✅ PASSED (6.1s)

📋 [5/5] ML Training APIs
   ML training and chunking framework tests
------------------------------------------------------------
✅ PASSED (18.9s)

================================================================================
📊 FINAL TEST SUMMARY
================================================================================
⏱️  Total Duration: 61.2 seconds

📋 Test Suites:
   Total: 5
   ✅ Passed: 5
   ❌ Failed: 0
   ⚠️  Skipped: 0

🧪 Individual Tests:
   Total: 47
   ✅ Passed: 45
   ❌ Failed: 0
   ⚠️  Skipped: 2

📈 Suite Success Rate: 100.0%
📈 Test Success Rate: 95.7%

🎉 ALL TEST SUITES PASSED!
================================================================================
```

## Learning Objectives

These integration tests help you learn:

### AWS Services Integration
- How different AWS services work together
- Service discovery and networking concepts
- Load balancer configuration and behavior
- Database connectivity in cloud environments

### Testing Best Practices
- Integration testing strategies
- Test isolation and cleanup
- Error handling and resilience testing
- Performance validation approaches

### System Validation
- End-to-end functionality verification
- Component interaction validation
- Performance baseline establishment
- Security configuration validation

## Troubleshooting

### Debug Mode
Run tests with additional debugging:
```bash
export LOG_LEVEL=DEBUG
python tests/aws/test_aws_basic_integration.py
```

### Individual Test Debugging
```bash
# Run single test with verbose output
pytest tests/aws/test_aws_basic_integration.py::TestInfrastructureConnectivity::test_application_health_endpoint -v -s
```

### Check AWS Resources
```bash
# Check ECS service status
aws ecs describe-services --cluster your-cluster --services your-service

# Check RDS instance status
aws rds describe-db-instances --db-instance-identifier your-db

# Check S3 bucket access
aws s3 ls s3://your-bucket-name
```

## Contributing

When adding new integration tests:

1. Follow the existing test structure and naming conventions
2. Include proper error handling and cleanup
3. Add comprehensive docstrings
4. Update this README with new test descriptions
5. Ensure tests are idempotent and can run independently

## Cost Considerations

These tests are designed for the learning deployment with cost optimization:
- Tests use minimal resources and short timeouts
- Cleanup procedures remove test data
- Tests skip expensive operations when possible
- Focus on functionality over performance stress testing

The entire test suite should complete in under 5 minutes and cost less than $0.10 to run.